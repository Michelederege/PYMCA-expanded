"""SQLite catalogue. Images live in a folder next to the database file."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from phone_salvage.catalog import (
    BOARD_TYPES,
    BUILTIN_TYPES,
    GLOSSARY_EXTRAS,
    IDENTIFICATION,
    LIQUID,
    POWERED,
    PRACTICAL,
    REMOVAL,
    SHIELD_STATES,
    SIDES,
    STATUSES,
    keys,
)
from phone_salvage.geometry import ZoneBox, assign_zone, clamp_box

_SCHEMA = """
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE phones (
    id INTEGER PRIMARY KEY,
    short_id TEXT NOT NULL UNIQUE,
    make TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    model_number TEXT NOT NULL DEFAULT '',
    colour TEXT NOT NULL DEFAULT '',
    imei_or_serial TEXT NOT NULL DEFAULT '',
    purchase_date TEXT NOT NULL DEFAULT '',
    purchase_price TEXT NOT NULL DEFAULT '',
    condition_notes TEXT NOT NULL DEFAULT '',
    photo_path TEXT,
    powered_on TEXT NOT NULL DEFAULT 'not_tried'
        CHECK (powered_on IN ('yes', 'no', 'not_tried')),
    known_faults TEXT NOT NULL DEFAULT '',
    liquid_contact TEXT NOT NULL DEFAULT 'unknown'
        CHECK (liquid_contact IN ('yes', 'no', 'unknown')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE bins (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL UNIQUE,
    notes TEXT NOT NULL DEFAULT '',
    photo_path TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE component_types (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    plain_name TEXT NOT NULL,
    explanation TEXT NOT NULL,
    what_it_does TEXT NOT NULL DEFAULT '',
    removal_tip TEXT NOT NULL DEFAULT '',
    test_hint TEXT NOT NULL DEFAULT '',
    beginner_important INTEGER NOT NULL DEFAULT 0,
    default_removal TEXT NOT NULL DEFAULT 'not_practical',
    sort_order INTEGER NOT NULL DEFAULT 0,
    builtin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE glossary (
    term TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    builtin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE parts (
    id INTEGER PRIMARY KEY,
    marking_code TEXT NOT NULL DEFAULT '',
    part_number TEXT NOT NULL DEFAULT '',
    type_id TEXT REFERENCES component_types(id),
    manufacturer TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    datasheet_path TEXT,
    expected_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE boards (
    id INTEGER PRIMARY KEY,
    phone_id INTEGER NOT NULL REFERENCES phones(id) ON DELETE CASCADE,
    short_id TEXT NOT NULL UNIQUE,
    board_type TEXT NOT NULL CHECK (board_type IN ('main', 'sub', 'charging', 'flex', 'other')),
    part_number TEXT NOT NULL DEFAULT '',
    revision TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE board_sides (
    id INTEGER PRIMARY KEY,
    board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    side TEXT NOT NULL CHECK (side IN ('front', 'back')),
    overview_path TEXT,
    width_mm REAL,
    height_mm REAL,
    UNIQUE (board_id, side)
);

CREATE TABLE zones (
    id INTEGER PRIMARY KEY,
    side_id INTEGER NOT NULL REFERENCES board_sides(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    w REAL NOT NULL,
    h REAL NOT NULL,
    confirmed INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE components (
    id INTEGER PRIMARY KEY,
    side_id INTEGER NOT NULL REFERENCES board_sides(id) ON DELETE CASCADE,
    zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
    type_id TEXT NOT NULL REFERENCES component_types(id),
    shape TEXT NOT NULL CHECK (shape IN ('box', 'pin')),
    x REAL NOT NULL,
    y REAL NOT NULL,
    w REAL,
    h REAL,
    designator TEXT NOT NULL DEFAULT '',
    marking_code TEXT NOT NULL DEFAULT '',
    part_number TEXT NOT NULL DEFAULT '',
    manufacturer TEXT NOT NULL DEFAULT '',
    function_notes TEXT NOT NULL DEFAULT '',
    value_text TEXT NOT NULL DEFAULT '',
    image_path TEXT,
    quality_score REAL,
    status TEXT NOT NULL DEFAULT 'not_checked'
        CHECK (status IN ('usable', 'maybe', 'junk', 'not_checked')),
    condition_notes TEXT NOT NULL DEFAULT '',
    removal TEXT NOT NULL DEFAULT 'not_practical'
        CHECK (removal IN ('easy_unplug', 'hot_air', 'not_practical')),
    removal_tool TEXT NOT NULL DEFAULT '',
    removed INTEGER NOT NULL DEFAULT 0,
    bin_id INTEGER REFERENCES bins(id) ON DELETE SET NULL,
    identification TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (identification IN ('suggested', 'confirmed', 'cant_do_better')),
    identification_reason TEXT NOT NULL DEFAULT '',
    practical_reuse TEXT NOT NULL DEFAULT 'unknown'
        CHECK (practical_reuse IN ('easy', 'advanced', 'not_practical', 'unknown')),
    shield_state TEXT NOT NULL DEFAULT ''
        CHECK (shield_state IN ('', 'unopened', 'opened', 'not_visible')),
    pin_count INTEGER,
    show_in_simple INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_components_side ON components(side_id);
CREATE INDEX idx_components_marking ON components(marking_code);
CREATE INDEX idx_boards_phone ON boards(phone_id);
"""

_COMPONENT_FROM = """
FROM components c
JOIN component_types t ON t.id = c.type_id
JOIN board_sides s ON s.id = c.side_id
JOIN boards b ON b.id = s.board_id
JOIN phones p ON p.id = b.phone_id
LEFT JOIN bins bn ON bn.id = c.bin_id
LEFT JOIN zones z ON z.id = c.zone_id
"""

_COMPONENT_SELECT = f"""
SELECT
    c.*,
    t.label AS type_label,
    t.plain_name AS type_plain,
    t.explanation AS type_explanation,
    t.what_it_does AS type_what,
    t.removal_tip AS type_removal_tip,
    t.test_hint AS type_test_hint,
    t.beginner_important AS beginner_important,
    t.default_removal AS type_default_removal,
    b.id AS board_id,
    b.short_id AS board_short_id,
    b.board_type AS board_type,
    s.side AS side,
    p.id AS phone_id,
    p.short_id AS phone_short_id,
    p.make AS phone_make,
    p.model AS phone_model,
    COALESCE(bn.label, '') AS bin_label,
    COALESCE(z.name, '') AS zone_name
{_COMPONENT_FROM}
"""

_COMPONENT_FIELDS = {
    "zone_id",
    "type_id",
    "shape",
    "x",
    "y",
    "w",
    "h",
    "designator",
    "marking_code",
    "part_number",
    "manufacturer",
    "function_notes",
    "value_text",
    "image_path",
    "quality_score",
    "status",
    "condition_notes",
    "removal",
    "removal_tool",
    "removed",
    "bin_id",
    "identification",
    "identification_reason",
    "practical_reuse",
    "shield_state",
    "pin_count",
    "show_in_simple",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check(value: str, allowed: set[str], name: str) -> str:
    if value not in allowed:
        raise ValueError(f"Unknown {name}: {value}")
    return value


def _slug(text: str) -> str:
    cleaned = []
    for char in text.strip().lower():
        cleaned.append(char if char.isalnum() else "-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "part"


@dataclass
class Phone:
    id: int
    short_id: str
    make: str
    model: str
    model_number: str
    colour: str
    imei_or_serial: str
    purchase_date: str
    purchase_price: str
    condition_notes: str
    photo_path: str | None
    powered_on: str
    known_faults: str
    liquid_contact: str
    created_at: str
    updated_at: str


@dataclass
class Board:
    id: int
    phone_id: int
    short_id: str
    board_type: str
    part_number: str
    revision: str
    notes: str
    created_at: str
    updated_at: str


@dataclass
class Side:
    id: int
    board_id: int
    side: str
    overview_path: str | None
    width_mm: float | None
    height_mm: float | None


@dataclass
class Zone:
    id: int
    side_id: int
    name: str
    x: float
    y: float
    w: float
    h: float
    confirmed: bool
    sort_order: int


@dataclass
class ComponentTypeRow:
    id: str
    label: str
    plain_name: str
    explanation: str
    what_it_does: str
    removal_tip: str
    test_hint: str
    beginner_important: bool
    default_removal: str
    sort_order: int
    builtin: bool


@dataclass
class Component:
    id: int
    side_id: int
    zone_id: int | None
    type_id: str
    shape: str
    x: float
    y: float
    w: float | None
    h: float | None
    designator: str
    marking_code: str
    part_number: str
    manufacturer: str
    function_notes: str
    value_text: str
    image_path: str | None
    quality_score: float | None
    status: str
    condition_notes: str
    removal: str
    removal_tool: str
    removed: bool
    bin_id: int | None
    identification: str
    identification_reason: str
    practical_reuse: str
    shield_state: str
    pin_count: int | None
    show_in_simple: bool
    created_at: str
    updated_at: str
    type_label: str = ""
    type_plain: str = ""
    type_explanation: str = ""
    type_what: str = ""
    type_removal_tip: str = ""
    type_test_hint: str = ""
    beginner_important: bool = False
    type_default_removal: str = ""
    board_id: int = 0
    board_short_id: str = ""
    board_type: str = ""
    side: str = ""
    phone_id: int = 0
    phone_short_id: str = ""
    phone_make: str = ""
    phone_model: str = ""
    bin_label: str = ""
    zone_name: str = ""


@dataclass
class PartRecord:
    id: int
    marking_code: str
    part_number: str
    type_id: str | None
    manufacturer: str
    notes: str
    datasheet_path: str | None
    expected_notes: str
    created_at: str
    updated_at: str
    type_plain: str = ""


@dataclass
class Bin:
    id: int
    label: str
    notes: str
    photo_path: str | None
    created_at: str


@dataclass
class GlossaryEntry:
    term: str
    title: str
    body: str
    builtin: bool


@dataclass
class LayoutSource:
    side_id: int
    side: str
    board_short_id: str
    revision: str
    phone_short_id: str
    make: str
    model: str


def _phone(row: sqlite3.Row) -> Phone:
    return Phone(**{field: row[field] for field in Phone.__dataclass_fields__})


def _board(row: sqlite3.Row) -> Board:
    return Board(**{field: row[field] for field in Board.__dataclass_fields__})


def _side(row: sqlite3.Row) -> Side:
    return Side(
        id=row["id"],
        board_id=row["board_id"],
        side=row["side"],
        overview_path=row["overview_path"],
        width_mm=row["width_mm"],
        height_mm=row["height_mm"],
    )


def _zone(row: sqlite3.Row) -> Zone:
    return Zone(
        id=row["id"],
        side_id=row["side_id"],
        name=row["name"],
        x=row["x"],
        y=row["y"],
        w=row["w"],
        h=row["h"],
        confirmed=bool(row["confirmed"]),
        sort_order=row["sort_order"],
    )


def _type_row(row: sqlite3.Row) -> ComponentTypeRow:
    return ComponentTypeRow(
        id=row["id"],
        label=row["label"],
        plain_name=row["plain_name"],
        explanation=row["explanation"],
        what_it_does=row["what_it_does"],
        removal_tip=row["removal_tip"],
        test_hint=row["test_hint"],
        beginner_important=bool(row["beginner_important"]),
        default_removal=row["default_removal"],
        sort_order=row["sort_order"],
        builtin=bool(row["builtin"]),
    )


def _component(row: sqlite3.Row) -> Component:
    return Component(
        id=row["id"],
        side_id=row["side_id"],
        zone_id=row["zone_id"],
        type_id=row["type_id"],
        shape=row["shape"],
        x=row["x"],
        y=row["y"],
        w=row["w"],
        h=row["h"],
        designator=row["designator"],
        marking_code=row["marking_code"],
        part_number=row["part_number"],
        manufacturer=row["manufacturer"],
        function_notes=row["function_notes"],
        value_text=row["value_text"],
        image_path=row["image_path"],
        quality_score=row["quality_score"],
        status=row["status"],
        condition_notes=row["condition_notes"],
        removal=row["removal"],
        removal_tool=row["removal_tool"],
        removed=bool(row["removed"]),
        bin_id=row["bin_id"],
        identification=row["identification"],
        identification_reason=row["identification_reason"],
        practical_reuse=row["practical_reuse"],
        shield_state=row["shield_state"],
        pin_count=row["pin_count"],
        show_in_simple=bool(row["show_in_simple"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        type_label=row["type_label"],
        type_plain=row["type_plain"],
        type_explanation=row["type_explanation"],
        type_what=row["type_what"],
        type_removal_tip=row["type_removal_tip"],
        type_test_hint=row["type_test_hint"],
        beginner_important=bool(row["beginner_important"]),
        type_default_removal=row["type_default_removal"],
        board_id=row["board_id"],
        board_short_id=row["board_short_id"],
        board_type=row["board_type"],
        side=row["side"],
        phone_id=row["phone_id"],
        phone_short_id=row["phone_short_id"],
        phone_make=row["phone_make"],
        phone_model=row["phone_model"],
        bin_label=row["bin_label"] or "",
        zone_name=row["zone_name"] or "",
    )


def _part(row: sqlite3.Row) -> PartRecord:
    return PartRecord(
        id=row["id"],
        marking_code=row["marking_code"],
        part_number=row["part_number"],
        type_id=row["type_id"],
        manufacturer=row["manufacturer"],
        notes=row["notes"],
        datasheet_path=row["datasheet_path"],
        expected_notes=row["expected_notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        type_plain=row["type_plain"] if "type_plain" in row.keys() else "",
    )


def _bin(row: sqlite3.Row) -> Bin:
    return Bin(
        id=row["id"],
        label=row["label"],
        notes=row["notes"],
        photo_path=row["photo_path"],
        created_at=row["created_at"],
    )


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.images.mkdir(exist_ok=True)
        self.datasheets.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(self.root / "salvage.db")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def datasheets(self) -> Path:
        return self.root / "datasheets"

    def close(self) -> None:
        self.conn.close()

    def abs_path(self, relative: str | None) -> Path | None:
        if not relative:
            return None
        path = (self.root / relative).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError("Path escapes the catalogue folder")
        return path

    def import_file(self, source: Path, kind: str) -> str:
        source = Path(source)
        if kind not in ("images", "datasheets"):
            raise ValueError(kind)
        if not source.is_file():
            raise ValueError(f"File not found: {source}")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        suffix = source.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".pdf"}:
            suffix = ".png"
        folder = self.images if kind == "images" else self.datasheets
        dest = folder / f"{digest}{suffix}"
        if not dest.exists():
            shutil.copy2(source, dest)
        return dest.relative_to(self.root).as_posix()

    def _migrate(self) -> None:
        current = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        version = 0
        if current:
            row = self.conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
            version = row["version"] or 0
        if version < 1:
            self.conn.executescript(_SCHEMA)
            self.conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
                (_now(),),
            )
            self.conn.commit()

    def ensure_catalog(self) -> None:
        for item in BUILTIN_TYPES:
            self.conn.execute(
                """
                INSERT INTO component_types (
                    id, label, plain_name, explanation, what_it_does, removal_tip,
                    test_hint, beginner_important, default_removal, sort_order, builtin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    item.id,
                    item.label,
                    item.plain_name,
                    item.explanation,
                    item.what_it_does,
                    item.removal_tip,
                    item.test_hint,
                    int(item.beginner_important),
                    item.default_removal,
                    item.sort_order,
                ),
            )
            self.conn.execute(
                """
                INSERT INTO glossary(term, title, body, builtin) VALUES (?, ?, ?, 1)
                ON CONFLICT(term) DO NOTHING
                """,
                (
                    item.id,
                    item.plain_name,
                    item.explanation + "\n\n" + item.what_it_does,
                ),
            )
        for term, title, body in GLOSSARY_EXTRAS:
            self.conn.execute(
                """
                INSERT INTO glossary(term, title, body, builtin) VALUES (?, ?, ?, 1)
                ON CONFLICT(term) DO NOTHING
                """,
                (term, title, body),
            )
        self.conn.commit()

    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["value"]

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO app_settings(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def phone_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM phones").fetchone()["n"])

    def _next_phone_short(self) -> str:
        rows = self.conn.execute("SELECT short_id FROM phones").fetchall()
        highest = 0
        for row in rows:
            text = row["short_id"]
            if text.startswith("PH-") and text[3:].isdigit():
                highest = max(highest, int(text[3:]))
        return f"PH-{highest + 1:03d}"

    def _next_board_short(self, phone_short: str) -> str:
        prefix = phone_short + "-B"
        rows = self.conn.execute(
            "SELECT short_id FROM boards WHERE short_id LIKE ?",
            (prefix + "%",),
        ).fetchall()
        highest = 0
        for row in rows:
            tail = row["short_id"][len(prefix) :]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return f"{prefix}{highest + 1}"

    def list_phones(self) -> list[Phone]:
        rows = self.conn.execute("SELECT * FROM phones ORDER BY short_id").fetchall()
        return [_phone(row) for row in rows]

    def get_phone(self, phone_id: int) -> Phone | None:
        row = self.conn.execute("SELECT * FROM phones WHERE id = ?", (phone_id,)).fetchone()
        return None if row is None else _phone(row)

    def add_phone(self, **fields) -> Phone:
        short_id = self._next_phone_short()
        stamp = _now()
        powered = _check(fields.get("powered_on", "not_tried"), keys(POWERED), "powered on")
        liquid = _check(fields.get("liquid_contact", "unknown"), keys(LIQUID), "liquid contact")
        cur = self.conn.execute(
            """
            INSERT INTO phones (
                short_id, make, model, model_number, colour, imei_or_serial,
                purchase_date, purchase_price, condition_notes, photo_path,
                powered_on, known_faults, liquid_contact, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                short_id,
                fields.get("make", ""),
                fields.get("model", ""),
                fields.get("model_number", ""),
                fields.get("colour", ""),
                fields.get("imei_or_serial", ""),
                fields.get("purchase_date", ""),
                fields.get("purchase_price", ""),
                fields.get("condition_notes", ""),
                fields.get("photo_path"),
                powered,
                fields.get("known_faults", ""),
                liquid,
                stamp,
                stamp,
            ),
        )
        self.conn.commit()
        phone = self.get_phone(int(cur.lastrowid))
        assert phone is not None
        return phone

    def update_phone(self, phone_id: int, **fields) -> None:
        allowed = {
            "make",
            "model",
            "model_number",
            "colour",
            "imei_or_serial",
            "purchase_date",
            "purchase_price",
            "condition_notes",
            "photo_path",
            "powered_on",
            "known_faults",
            "liquid_contact",
        }
        if "powered_on" in fields:
            _check(fields["powered_on"], keys(POWERED), "powered on")
        if "liquid_contact" in fields:
            _check(fields["liquid_contact"], keys(LIQUID), "liquid contact")
        self._update("phones", phone_id, fields, allowed, touch_updated=True)

    def delete_phone(self, phone_id: int) -> None:
        self.conn.execute("DELETE FROM phones WHERE id = ?", (phone_id,))
        self.conn.commit()

    def list_boards(self, phone_id: int) -> list[Board]:
        rows = self.conn.execute(
            "SELECT * FROM boards WHERE phone_id = ? ORDER BY short_id",
            (phone_id,),
        ).fetchall()
        return [_board(row) for row in rows]

    def get_board(self, board_id: int) -> Board | None:
        row = self.conn.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
        return None if row is None else _board(row)

    def add_board(self, phone_id: int, board_type: str, **fields) -> Board:
        phone = self.get_phone(phone_id)
        if phone is None:
            raise ValueError("Phone not found")
        _check(board_type, keys(BOARD_TYPES), "board type")
        stamp = _now()
        cur = self.conn.execute(
            """
            INSERT INTO boards (
                phone_id, short_id, board_type, part_number, revision, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                phone_id,
                self._next_board_short(phone.short_id),
                board_type,
                fields.get("part_number", ""),
                fields.get("revision", ""),
                fields.get("notes", ""),
                stamp,
                stamp,
            ),
        )
        board_id = int(cur.lastrowid)
        for side, _label in SIDES:
            self.conn.execute(
                "INSERT INTO board_sides(board_id, side) VALUES (?, ?)",
                (board_id, side),
            )
        self.conn.commit()
        board = self.get_board(board_id)
        assert board is not None
        return board

    def update_board(self, board_id: int, **fields) -> None:
        if "board_type" in fields:
            _check(fields["board_type"], keys(BOARD_TYPES), "board type")
        self._update(
            "boards",
            board_id,
            fields,
            {"board_type", "part_number", "revision", "notes"},
            touch_updated=True,
        )

    def delete_board(self, board_id: int) -> None:
        self.conn.execute("DELETE FROM boards WHERE id = ?", (board_id,))
        self.conn.commit()

    def get_side(self, board_id: int, side: str) -> Side:
        _check(side, keys(SIDES), "side")
        row = self.conn.execute(
            "SELECT * FROM board_sides WHERE board_id = ? AND side = ?",
            (board_id, side),
        ).fetchone()
        if row is None:
            raise ValueError("Board side not found")
        return _side(row)

    def get_side_by_id(self, side_id: int) -> Side | None:
        row = self.conn.execute("SELECT * FROM board_sides WHERE id = ?", (side_id,)).fetchone()
        return None if row is None else _side(row)

    def set_overview(self, side_id: int, relative: str | None) -> None:
        self.conn.execute(
            "UPDATE board_sides SET overview_path = ? WHERE id = ?",
            (relative, side_id),
        )
        self.conn.commit()

    def layout_sources(self, make: str, model: str, exclude_side_id: int) -> list[LayoutSource]:
        if not model.strip():
            return []
        rows = self.conn.execute(
            """
            SELECT s.id AS side_id, s.side, b.short_id AS board_short_id, b.revision,
                   p.short_id AS phone_short_id, p.make, p.model
            FROM board_sides s
            JOIN boards b ON b.id = s.board_id
            JOIN phones p ON p.id = b.phone_id
            WHERE lower(trim(p.make)) = lower(trim(?))
              AND lower(trim(p.model)) = lower(trim(?))
              AND s.id != ?
            ORDER BY p.short_id, b.short_id, s.side
            """,
            (make, model, exclude_side_id),
        ).fetchall()
        return [
            LayoutSource(
                side_id=row["side_id"],
                side=row["side"],
                board_short_id=row["board_short_id"],
                revision=row["revision"],
                phone_short_id=row["phone_short_id"],
                make=row["make"],
                model=row["model"],
            )
            for row in rows
        ]

    def list_zones(self, side_id: int) -> list[Zone]:
        rows = self.conn.execute(
            "SELECT * FROM zones WHERE side_id = ? ORDER BY sort_order, id",
            (side_id,),
        ).fetchall()
        return [_zone(row) for row in rows]

    def get_zone(self, zone_id: int) -> Zone | None:
        row = self.conn.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
        return None if row is None else _zone(row)

    def add_zone(self, side_id: int, name: str, x: float, y: float, w: float, h: float, *, confirmed: bool = True) -> Zone:
        x, y, w, h = clamp_box(x, y, w, h)
        assert w is not None and h is not None
        cur = self.conn.execute(
            """
            INSERT INTO zones(side_id, name, x, y, w, h, confirmed, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (side_id, name.strip() or "Area", x, y, w, h, int(confirmed), 0),
        )
        self.conn.commit()
        zone = self.get_zone(int(cur.lastrowid))
        assert zone is not None
        return zone

    def update_zone(self, zone_id: int, **fields) -> None:
        if {"x", "y", "w", "h"} & set(fields):
            current = self.get_zone(zone_id)
            if current is None:
                raise ValueError("Zone not found")
            x, y, w, h = clamp_box(
                fields.get("x", current.x),
                fields.get("y", current.y),
                fields.get("w", current.w),
                fields.get("h", current.h),
            )
            fields.update(x=x, y=y, w=w, h=h)
        if "confirmed" in fields:
            fields["confirmed"] = int(bool(fields["confirmed"]))
        self._update("zones", zone_id, fields, {"name", "x", "y", "w", "h", "confirmed"}, touch_updated=False)

    def delete_zone(self, zone_id: int) -> None:
        self.conn.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
        self.conn.commit()

    def list_types(self) -> list[ComponentTypeRow]:
        rows = self.conn.execute(
            "SELECT * FROM component_types ORDER BY sort_order, plain_name"
        ).fetchall()
        return [_type_row(row) for row in rows]

    def get_type(self, type_id: str) -> ComponentTypeRow | None:
        row = self.conn.execute("SELECT * FROM component_types WHERE id = ?", (type_id,)).fetchone()
        return None if row is None else _type_row(row)

    def add_type(self, plain_name: str, explanation: str, *, beginner_important: bool = False) -> ComponentTypeRow:
        base = _slug(plain_name)
        type_id = base
        number = 2
        while self.get_type(type_id) is not None:
            type_id = f"{base}-{number}"
            number += 1
        order = 200 + number
        self.conn.execute(
            """
            INSERT INTO component_types (
                id, label, plain_name, explanation, what_it_does, removal_tip, test_hint,
                beginner_important, default_removal, sort_order, builtin
            ) VALUES (?, ?, ?, ?, '', '', '', ?, 'not_practical', ?, 0)
            """,
            (type_id, plain_name.strip(), plain_name.strip(), explanation.strip(), int(beginner_important), order),
        )
        self.conn.execute(
            "INSERT INTO glossary(term, title, body, builtin) VALUES (?, ?, ?, 0)",
            (type_id, plain_name.strip(), explanation.strip() or plain_name.strip()),
        )
        self.conn.commit()
        created = self.get_type(type_id)
        assert created is not None
        return created

    def update_type(self, type_id: str, **fields) -> None:
        if "beginner_important" in fields:
            fields["beginner_important"] = int(bool(fields["beginner_important"]))
        self._update(
            "component_types",
            type_id,
            fields,
            {
                "label",
                "plain_name",
                "explanation",
                "what_it_does",
                "removal_tip",
                "test_hint",
                "beginner_important",
                "default_removal",
            },
            touch_updated=False,
            id_column="id",
        )

    def list_glossary(self) -> list[GlossaryEntry]:
        rows = self.conn.execute("SELECT * FROM glossary ORDER BY title").fetchall()
        return [
            GlossaryEntry(term=row["term"], title=row["title"], body=row["body"], builtin=bool(row["builtin"]))
            for row in rows
        ]

    def get_glossary(self, term: str) -> GlossaryEntry | None:
        row = self.conn.execute("SELECT * FROM glossary WHERE term = ?", (term,)).fetchone()
        if row is None:
            return None
        return GlossaryEntry(term=row["term"], title=row["title"], body=row["body"], builtin=bool(row["builtin"]))

    def update_glossary(self, term: str, title: str, body: str) -> None:
        self.conn.execute(
            "UPDATE glossary SET title = ?, body = ? WHERE term = ?",
            (title.strip(), body.strip(), term),
        )
        self.conn.commit()

    def _zone_boxes(self, side_id: int) -> list[ZoneBox]:
        return [ZoneBox(zone.id, zone.x, zone.y, zone.w, zone.h) for zone in self.list_zones(side_id)]

    def list_components(self, side_id: int) -> list[Component]:
        rows = self.conn.execute(
            _COMPONENT_SELECT + " WHERE c.side_id = ? ORDER BY c.id",
            (side_id,),
        ).fetchall()
        return [_component(row) for row in rows]

    def get_component(self, component_id: int) -> Component | None:
        row = self.conn.execute(
            _COMPONENT_SELECT + " WHERE c.id = ?",
            (component_id,),
        ).fetchone()
        return None if row is None else _component(row)

    def components_for_phone(self, phone_id: int) -> list[Component]:
        rows = self.conn.execute(
            _COMPONENT_SELECT + " WHERE p.id = ? ORDER BY b.short_id, c.id",
            (phone_id,),
        ).fetchall()
        return [_component(row) for row in rows]

    def search_components(
        self,
        *,
        text: str = "",
        type_id: str | None = None,
        status: str | None = None,
        identification: str | None = None,
        model: str | None = None,
        bin_id: int | None = None,
        location: str | None = None,
        practical_reuse: str | None = None,
    ) -> list[Component]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if text.strip():
            like = _like(text.strip())
            clauses.append(
                """(
                    c.marking_code LIKE ? ESCAPE '\\'
                    OR c.part_number LIKE ? ESCAPE '\\'
                    OR c.designator LIKE ? ESCAPE '\\'
                    OR c.function_notes LIKE ? ESCAPE '\\'
                    OR c.condition_notes LIKE ? ESCAPE '\\'
                    OR t.plain_name LIKE ? ESCAPE '\\'
                    OR p.short_id LIKE ? ESCAPE '\\'
                    OR p.model LIKE ? ESCAPE '\\'
                    OR b.short_id LIKE ? ESCAPE '\\'
                    OR bn.label LIKE ? ESCAPE '\\'
                )"""
            )
            params.extend([like] * 10)
        if type_id:
            clauses.append("c.type_id = ?")
            params.append(type_id)
        if status:
            clauses.append("c.status = ?")
            params.append(status)
        if identification:
            clauses.append("c.identification = ?")
            params.append(identification)
        if model:
            clauses.append("p.model = ?")
            params.append(model)
        if bin_id is not None:
            clauses.append("c.bin_id = ?")
            params.append(bin_id)
        if location == "board":
            clauses.append("c.removed = 0")
        elif location == "stored":
            clauses.append("c.removed = 1")
        if practical_reuse:
            clauses.append("c.practical_reuse = ?")
            params.append(practical_reuse)
        sql = _COMPONENT_SELECT + " WHERE " + " AND ".join(clauses) + " ORDER BY p.short_id, b.short_id, t.sort_order, c.id"
        return [_component(row) for row in self.conn.execute(sql, params).fetchall()]

    def add_component(self, side_id: int, type_id: str, shape: str, x: float, y: float, w: float | None = None, h: float | None = None, **fields) -> Component:
        if self.get_type(type_id) is None:
            raise ValueError("Unknown part type")
        _check(shape, {"box", "pin"}, "shape")
        if shape == "pin":
            x, y, w, h = clamp_box(x, y, None, None)
        else:
            if w is None or h is None:
                raise ValueError("A box needs a width and a height")
            x, y, w, h = clamp_box(x, y, w, h)
        zone_id = fields.get("zone_id")
        if zone_id is None and "zone_id" not in fields:
            zone_id = assign_zone(x, y, w, h, self._zone_boxes(side_id))
        status = _check(fields.get("status", "not_checked"), keys(STATUSES), "status")
        removal = _check(fields.get("removal", "not_practical"), keys(REMOVAL), "removal")
        identification = _check(fields.get("identification", "confirmed"), keys(IDENTIFICATION), "identification")
        practical = _check(fields.get("practical_reuse", "unknown"), keys(PRACTICAL), "practical reuse")
        shield = _check(fields.get("shield_state", ""), keys(SHIELD_STATES), "shield")
        stamp = _now()
        cur = self.conn.execute(
            """
            INSERT INTO components (
                side_id, zone_id, type_id, shape, x, y, w, h,
                designator, marking_code, part_number, manufacturer, function_notes, value_text,
                image_path, quality_score, status, condition_notes, removal, removal_tool,
                removed, bin_id, identification, identification_reason, practical_reuse,
                shield_state, pin_count, show_in_simple, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            (
                side_id,
                zone_id,
                type_id,
                shape,
                x,
                y,
                w,
                h,
                fields.get("designator", ""),
                fields.get("marking_code", ""),
                fields.get("part_number", ""),
                fields.get("manufacturer", ""),
                fields.get("function_notes", ""),
                fields.get("value_text", ""),
                fields.get("image_path"),
                fields.get("quality_score"),
                status,
                fields.get("condition_notes", ""),
                removal,
                fields.get("removal_tool", ""),
                int(bool(fields.get("removed", False))),
                fields.get("bin_id"),
                identification,
                fields.get("identification_reason", ""),
                practical,
                shield,
                fields.get("pin_count"),
                int(bool(fields.get("show_in_simple", False))),
                stamp,
                stamp,
            ),
        )
        self.conn.commit()
        created = self.get_component(int(cur.lastrowid))
        assert created is not None
        return created

    def update_component(self, component_id: int, **fields) -> None:
        current = self.get_component(component_id)
        if current is None:
            raise ValueError("Part not found")
        unknown = set(fields) - _COMPONENT_FIELDS
        if unknown:
            raise ValueError(f"Unknown fields: {', '.join(sorted(unknown))}")
        if "status" in fields:
            _check(fields["status"], keys(STATUSES), "status")
        if "removal" in fields:
            _check(fields["removal"], keys(REMOVAL), "removal")
        if "identification" in fields:
            _check(fields["identification"], keys(IDENTIFICATION), "identification")
        if "practical_reuse" in fields:
            _check(fields["practical_reuse"], keys(PRACTICAL), "practical reuse")
        if "shield_state" in fields:
            _check(fields["shield_state"], keys(SHIELD_STATES), "shield")
        if "shape" in fields:
            _check(fields["shape"], {"box", "pin"}, "shape")
        if "type_id" in fields and self.get_type(fields["type_id"]) is None:
            raise ValueError("Unknown part type")
        if {"x", "y", "w", "h", "shape"} & set(fields):
            shape = fields.get("shape", current.shape)
            x = fields.get("x", current.x)
            y = fields.get("y", current.y)
            w = fields.get("w", current.w)
            h = fields.get("h", current.h)
            if shape == "pin":
                x, y, w, h = clamp_box(x, y, None, None)
            else:
                x, y, w, h = clamp_box(x, y, w if w is not None else 0.02, h if h is not None else 0.02)
            fields.update(x=x, y=y, w=w, h=h)
            if "zone_id" not in fields:
                fields["zone_id"] = assign_zone(x, y, w, h, self._zone_boxes(current.side_id))
        if "removed" in fields:
            fields["removed"] = int(bool(fields["removed"]))
        if "show_in_simple" in fields:
            fields["show_in_simple"] = int(bool(fields["show_in_simple"]))
        self._update("components", component_id, fields, _COMPONENT_FIELDS, touch_updated=True)

    def delete_component(self, component_id: int) -> None:
        self.conn.execute("DELETE FROM components WHERE id = ?", (component_id,))
        self.conn.commit()

    def copy_layout(self, source_side_id: int, dest_side_id: int) -> None:
        if source_side_id == dest_side_id:
            raise ValueError("Choose a different board side to copy from")
        if self.get_side_by_id(source_side_id) is None or self.get_side_by_id(dest_side_id) is None:
            raise ValueError("Board side not found")
        zones = self.list_zones(source_side_id)
        components = self.list_components(source_side_id)
        try:
            self.conn.execute("BEGIN")
            self.conn.execute("DELETE FROM components WHERE side_id = ?", (dest_side_id,))
            self.conn.execute("DELETE FROM zones WHERE side_id = ?", (dest_side_id,))
            zone_map: dict[int, int] = {}
            for zone in zones:
                cur = self.conn.execute(
                    """
                    INSERT INTO zones(side_id, name, x, y, w, h, confirmed, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (dest_side_id, zone.name, zone.x, zone.y, zone.w, zone.h, zone.sort_order),
                )
                zone_map[zone.id] = int(cur.lastrowid)
            stamp = _now()
            for part in components:
                self.conn.execute(
                    """
                    INSERT INTO components (
                        side_id, zone_id, type_id, shape, x, y, w, h,
                        designator, marking_code, part_number, manufacturer, function_notes, value_text,
                        image_path, quality_score, status, condition_notes, removal, removal_tool,
                        removed, bin_id, identification, identification_reason, practical_reuse,
                        shield_state, pin_count, show_in_simple, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        NULL, NULL, 'not_checked', '', ?, ?,
                        0, NULL, 'suggested', '', ?,
                        ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        dest_side_id,
                        zone_map.get(part.zone_id) if part.zone_id else None,
                        part.type_id,
                        part.shape,
                        part.x,
                        part.y,
                        part.w,
                        part.h,
                        part.designator,
                        part.marking_code,
                        part.part_number,
                        part.manufacturer,
                        part.function_notes,
                        part.value_text,
                        part.removal,
                        part.removal_tool,
                        part.practical_reuse,
                        part.shield_state,
                        part.pin_count,
                        int(part.show_in_simple),
                        stamp,
                        stamp,
                    ),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def list_parts(self) -> list[PartRecord]:
        rows = self.conn.execute(
            """
            SELECT parts.*, COALESCE(component_types.plain_name, '') AS type_plain
            FROM parts
            LEFT JOIN component_types ON component_types.id = parts.type_id
            ORDER BY parts.marking_code, parts.part_number, parts.id
            """
        ).fetchall()
        return [_part(row) for row in rows]

    def add_part(self, **fields) -> PartRecord:
        type_id = fields.get("type_id")
        if type_id and self.get_type(type_id) is None:
            raise ValueError("Unknown part type")
        stamp = _now()
        cur = self.conn.execute(
            """
            INSERT INTO parts (
                marking_code, part_number, type_id, manufacturer, notes,
                datasheet_path, expected_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields.get("marking_code", ""),
                fields.get("part_number", ""),
                type_id,
                fields.get("manufacturer", ""),
                fields.get("notes", ""),
                fields.get("datasheet_path"),
                fields.get("expected_notes", ""),
                stamp,
                stamp,
            ),
        )
        self.conn.commit()
        return self._get_part(int(cur.lastrowid))

    def update_part(self, part_id: int, **fields) -> None:
        if fields.get("type_id") and self.get_type(fields["type_id"]) is None:
            raise ValueError("Unknown part type")
        self._update(
            "parts",
            part_id,
            fields,
            {
                "marking_code",
                "part_number",
                "type_id",
                "manufacturer",
                "notes",
                "datasheet_path",
                "expected_notes",
            },
            touch_updated=True,
        )

    def delete_part(self, part_id: int) -> None:
        self.conn.execute("DELETE FROM parts WHERE id = ?", (part_id,))
        self.conn.commit()

    def find_parts_by_marking(self, marking: str) -> list[PartRecord]:
        cleaned = marking.strip()
        if not cleaned:
            return []
        rows = self.conn.execute(
            """
            SELECT parts.*, COALESCE(component_types.plain_name, '') AS type_plain
            FROM parts
            LEFT JOIN component_types ON component_types.id = parts.type_id
            WHERE lower(trim(parts.marking_code)) = lower(trim(?))
            ORDER BY parts.id
            """,
            (cleaned,),
        ).fetchall()
        return [_part(row) for row in rows]

    def _get_part(self, part_id: int) -> PartRecord:
        row = self.conn.execute(
            """
            SELECT parts.*, COALESCE(component_types.plain_name, '') AS type_plain
            FROM parts
            LEFT JOIN component_types ON component_types.id = parts.type_id
            WHERE parts.id = ?
            """,
            (part_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Library entry not found")
        return _part(row)

    def list_bins(self) -> list[Bin]:
        rows = self.conn.execute("SELECT * FROM bins ORDER BY label").fetchall()
        return [_bin(row) for row in rows]

    def get_bin(self, bin_id: int) -> Bin | None:
        row = self.conn.execute("SELECT * FROM bins WHERE id = ?", (bin_id,)).fetchone()
        return None if row is None else _bin(row)

    def add_bin(self, label: str, notes: str = "") -> Bin:
        cleaned = label.strip()
        if not cleaned:
            raise ValueError("A bin needs a label")
        cur = self.conn.execute(
            "INSERT INTO bins(label, notes, created_at) VALUES (?, ?, ?)",
            (cleaned, notes, _now()),
        )
        self.conn.commit()
        created = self.get_bin(int(cur.lastrowid))
        assert created is not None
        return created

    def update_bin(self, bin_id: int, **fields) -> None:
        if "label" in fields:
            fields["label"] = fields["label"].strip()
            if not fields["label"]:
                raise ValueError("A bin needs a label")
        self._update("bins", bin_id, fields, {"label", "notes", "photo_path"}, touch_updated=False)

    def delete_bin(self, bin_id: int) -> None:
        self.conn.execute("DELETE FROM bins WHERE id = ?", (bin_id,))
        self.conn.commit()

    def phone_models(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT model FROM phones WHERE trim(model) != '' ORDER BY model"
        ).fetchall()
        return [row["model"] for row in rows]

    def _update(
        self,
        table: str,
        row_id: int | str,
        fields: dict,
        allowed: set[str],
        *,
        touch_updated: bool,
        id_column: str = "id",
    ) -> None:
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown fields: {', '.join(sorted(unknown))}")
        if not fields and not touch_updated:
            return
        assignments = dict(fields)
        if touch_updated:
            assignments["updated_at"] = _now()
        if not assignments:
            return
        columns = ", ".join(f"{name} = ?" for name in assignments)
        self.conn.execute(
            f"UPDATE {table} SET {columns} WHERE {id_column} = ?",
            (*assignments.values(), row_id),
        )
        self.conn.commit()


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
