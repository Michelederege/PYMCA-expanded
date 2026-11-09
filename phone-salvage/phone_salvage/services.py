"""Export, backup, labels, and harvest. No window code."""

from __future__ import annotations

import csv
import sqlite3
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import qrcode

from phone_salvage.catalog import BOARD_TYPES, PRACTICAL, REMOVAL, STATUSES, choice_label
from phone_salvage.present import harvest_sort_key, include_in_harvest, tool_for
from phone_salvage.store import Component, Store


def harvest_for(parts: list[Component]) -> list[Component]:
    chosen = [
        part
        for part in parts
        if include_in_harvest(
            removed=part.removed,
            status=part.status,
            removal=part.removal,
            beginner_important=part.beginner_important,
            show_in_simple=part.show_in_simple,
        )
    ]
    chosen.sort(key=lambda part: harvest_sort_key(part.type_id, part.board_short_id, part.type_plain))
    return chosen


def export_csvs(store: Store, directory: Path) -> list[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    phones_path = directory / "phones.csv"
    boards_path = directory / "boards.csv"
    parts_path = directory / "components.csv"
    _write_csv(
        phones_path,
        [
            "Phone ID",
            "Make",
            "Model",
            "Model number",
            "Colour",
            "IMEI or serial",
            "Purchase date",
            "Purchase price",
            "Powered on when bought",
            "Liquid contact",
            "Known faults",
            "Condition notes",
        ],
        [
            [
                phone.short_id,
                phone.make,
                phone.model,
                phone.model_number,
                phone.colour,
                phone.imei_or_serial,
                phone.purchase_date,
                phone.purchase_price,
                phone.powered_on,
                phone.liquid_contact,
                phone.known_faults,
                phone.condition_notes,
            ]
            for phone in store.list_phones()
        ],
    )
    board_rows = []
    for phone in store.list_phones():
        for board in store.list_boards(phone.id):
            board_rows.append(
                [
                    board.short_id,
                    phone.short_id,
                    choice_label(BOARD_TYPES, board.board_type),
                    board.part_number,
                    board.revision,
                    board.notes,
                ]
            )
    _write_csv(
        boards_path,
        ["Board ID", "Phone ID", "Type", "Part number", "Revision", "Notes"],
        board_rows,
    )
    component_rows = []
    for phone in store.list_phones():
        for part in store.components_for_phone(phone.id):
            component_rows.append(
                [
                    phone.short_id,
                    part.board_short_id,
                    part.side,
                    part.zone_name,
                    part.type_plain,
                    choice_label(STATUSES, part.status),
                    choice_label(PRACTICAL, part.practical_reuse),
                    part.identification,
                    part.designator,
                    part.marking_code,
                    part.part_number,
                    part.manufacturer,
                    part.value_text,
                    choice_label(REMOVAL, part.removal),
                    tool_for(part.removal, part.removal_tool),
                    "yes" if part.removed else "no",
                    part.bin_label,
                    part.condition_notes,
                    part.function_notes,
                    part.shield_state,
                ]
            )
    _write_csv(
        parts_path,
        [
            "Phone ID",
            "Board ID",
            "Side",
            "Zone",
            "Part",
            "Status",
            "Practical reuse",
            "Identification",
            "Designator",
            "Marking",
            "Part number",
            "Manufacturer",
            "Value",
            "Removal",
            "Tool",
            "Removed",
            "Bin",
            "Condition",
            "Notes",
            "Shield",
        ],
        component_rows,
    )
    return [phones_path, boards_path, parts_path]


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def backup_store(store: Store, zip_path: Path) -> None:
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = zip_path.with_suffix(zip_path.suffix + ".tmpdb")
    if tmp_db.exists():
        tmp_db.unlink()
    out = sqlite3.connect(tmp_db)
    try:
        store.conn.execute("PRAGMA wal_checkpoint(FULL)")
        store.conn.backup(out)
    finally:
        out.close()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(tmp_db, "salvage.db")
        for folder in ("images", "datasheets"):
            base = store.root / folder
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file():
                    archive.write(path, Path(folder) / path.relative_to(base))
    tmp_db.unlink(missing_ok=True)


def restore_store(root: Path, zip_path: Path) -> None:
    """Replace the catalogue folder with a backup. Close the store before calling this."""
    root = Path(root)
    zip_path = Path(zip_path)
    staging = root.with_name(root.name + "-incoming")
    if staging.exists():
        _remove_tree(staging)
    with zipfile.ZipFile(zip_path) as archive:
        _safe_extract(archive, staging)
    if not (staging / "salvage.db").is_file():
        _remove_tree(staging)
        raise ValueError("This file is not a Phone Salvage backup. It has no database.")
    previous = root.with_name(root.name + "-previous")
    if root.exists():
        if previous.exists():
            _remove_tree(previous)
        root.rename(previous)
    staging.rename(root)


def _remove_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path)


def _safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    for info in archive.infolist():
        name = info.filename
        if not name or name.startswith("/") or ".." in Path(name).parts:
            raise ValueError("Unsafe path in backup")
        target = (dest / name).resolve()
        if target != root and root not in target.parents:
            raise ValueError("Unsafe path in backup")
        archive.extract(info, dest)


def label_payload(kind: str, short_id: str) -> str:
    if kind not in {"phone", "board", "bin"}:
        raise ValueError(kind)
    return f"phonesalvage:{kind}:{short_id}"


def render_label(title: str, lines: list[str], payload: str) -> Image.Image:
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(payload)
    qr.make(fit=True)
    code = qr.make_image(fill_color="#1c1915", back_color="white").convert("RGB")
    code = code.resize((220, 220), Image.Resampling.NEAREST)
    image = Image.new("RGB", (640, 280), "#fffcf8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 639, 279), outline="#1f4e5f", width=4)
    image.paste(code, (24, 30))
    font = ImageFont.load_default()
    draw.text((270, 48), title, fill="#1c1915", font=font)
    y = 84
    for line in lines[:4]:
        draw.text((270, y), line, fill="#5e584e", font=font)
        y += 28
    draw.text((270, 220), "Phone Salvage", fill="#1f4e5f", font=font)
    return image


def label_png(title: str, lines: list[str], payload: str) -> bytes:
    buffer = BytesIO()
    render_label(title, lines, payload).save(buffer, format="PNG")
    return buffer.getvalue()
