from pathlib import Path

import pytest

from phone_salvage.geometry import ZoneBox, assign_zone, clamp_box, norm_box
from phone_salvage.present import include_in_harvest, reuse_verdict, shown_in_simple
from phone_salvage.services import backup_store, export_csvs, harvest_for, label_payload, label_png, restore_store
from phone_salvage.session import open_session
from phone_salvage.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    opened = Store(tmp_path / "cat")
    opened.ensure_catalog()
    yield opened
    opened.close()


def test_phone_and_board_ids(store: Store) -> None:
    first = store.add_phone(make="Sample", model="S1")
    second = store.add_phone(make="Other", model="T2")
    assert first.short_id == "PH-001"
    assert second.short_id == "PH-002"
    board = store.add_board(first.id, "main", revision="A")
    assert board.short_id == "PH-001-B1"
    assert store.get_side(board.id, "front").side == "front"
    assert store.get_side(board.id, "back").overview_path is None


def test_manual_part_zone_and_delete_cascades(store: Store, tmp_path: Path) -> None:
    phone = store.add_phone(model="S1")
    board = store.add_board(phone.id, "main")
    side = store.get_side(board.id, "front")
    zone = store.add_zone(side.id, "Camera area", 0.1, 0.1, 0.4, 0.2)
    part = store.add_component(
        side.id,
        "camera",
        "box",
        0.15,
        0.12,
        0.2,
        0.1,
        status="usable",
        removal="easy_unplug",
        practical_reuse="easy",
    )
    assert part.zone_id == zone.id
    assert part.identification == "confirmed"
    photo = tmp_path / "shot.png"
    photo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"not really")
    relative = store.import_file(photo, "images")
    store.set_overview(side.id, relative)
    assert store.abs_path(relative).is_file()

    store.delete_phone(phone.id)
    assert store.get_phone(phone.id) is None
    assert store.get_component(part.id) is None
    assert store.get_side_by_id(side.id) is None


def test_copy_layout_is_a_suggestion_and_not_the_removed_part(store: Store) -> None:
    phone = store.add_phone(make="Sample", model="S1")
    other = store.add_phone(make="Sample", model="S1")
    source_board = store.add_board(phone.id, "main")
    dest_board = store.add_board(other.id, "main")
    source = store.get_side(source_board.id, "front")
    dest = store.get_side(dest_board.id, "front")
    store.add_zone(source.id, "Charging", 0.1, 0.7, 0.8, 0.2)
    bin_row = store.add_bin("Speakers")
    store.add_component(
        source.id,
        "speaker",
        "box",
        0.2,
        0.72,
        0.2,
        0.1,
        status="usable",
        removal="easy_unplug",
        practical_reuse="easy",
        removed=True,
        bin_id=bin_row.id,
        condition_notes="Torn",
        function_notes="Loudspeaker.",
    )
    store.copy_layout(source.id, dest.id)
    copied = store.list_components(dest.id)
    assert len(copied) == 1
    assert copied[0].identification == "suggested"
    assert copied[0].status == "not_checked"
    assert copied[0].removed is False
    assert copied[0].bin_id is None
    assert copied[0].condition_notes == ""
    assert copied[0].function_notes == "Loudspeaker."
    assert store.list_zones(dest.id)[0].confirmed is False
    assert store.list_components(source.id)[0].removed is True


def test_search_and_library_marking(store: Store) -> None:
    phone = store.add_phone(make="Sample", model="S1")
    board = store.add_board(phone.id, "main")
    side = store.get_side(board.id, "front")
    store.add_component(
        side.id,
        "ic",
        "pin",
        0.4,
        0.4,
        marking_code="DEMO-PMIC",
        status="maybe",
    )
    store.add_part(marking_code="DEMO-PMIC", part_number="DEMO-PMIC-1", type_id="ic", manufacturer="Demo Silicon")
    found = store.search_components(text="DEMO-PMIC", model="S1", status="maybe")
    assert len(found) == 1
    assert found[0].phone_short_id == phone.short_id
    assert store.search_components(text="100%_not", location="stored") == []
    assert store.find_parts_by_marking(" demo-pmic ")[0].part_number == "DEMO-PMIC-1"


def test_harvest_skips_junk_passives_and_removed_parts(store: Store) -> None:
    phone = store.add_phone(model="S1")
    board = store.add_board(phone.id, "main")
    side = store.get_side(board.id, "front")
    store.add_component(side.id, "camera", "pin", 0.2, 0.2, status="not_checked", removal="easy_unplug")
    store.add_component(side.id, "resistor", "pin", 0.3, 0.3, status="not_checked", removal="hot_air")
    store.add_component(
        side.id, "speaker", "pin", 0.4, 0.4, status="junk", removal="easy_unplug", practical_reuse="easy"
    )
    store.add_component(
        side.id,
        "vibration_motor",
        "pin",
        0.5,
        0.5,
        status="usable",
        removal="easy_unplug",
        removed=True,
    )
    store.add_component(side.id, "capacitor", "pin", 0.6, 0.6, status="usable", removal="hot_air")
    rows = harvest_for(store.components_for_phone(phone.id))
    assert [row.type_id for row in rows] == ["camera", "capacitor"]


def test_wording_keeps_photo_and_test_apart() -> None:
    text = reuse_verdict(status="usable", practical_reuse="easy", removed=False, bin_label="")
    assert "cannot prove" in text
    assert "beginner" in text
    stored = reuse_verdict(status="usable", practical_reuse="easy", removed=True, bin_label="Motors")
    assert stored == "Removed, and stored in Motors."
    assert shown_in_simple(False, False) is False
    assert shown_in_simple(True, False) is True
    assert include_in_harvest(
        removed=False,
        status="not_checked",
        removal="not_practical",
        beginner_important=True,
        show_in_simple=False,
    ) is False


def test_geometry_clamps_and_picks_the_smallest_zone() -> None:
    x, y, w, h = clamp_box(-0.2, 0.2, 2, 0.1)
    assert (x, y) == (0.0, 0.2)
    assert w == 1.0
    big = ZoneBox(1, 0.0, 0.0, 1.0, 1.0)
    small = ZoneBox(2, 0.2, 0.2, 0.2, 0.2)
    assert assign_zone(0.25, 0.25, 0.1, 0.1, [big, small]) == 2
    assert norm_box(100, 50, 0, 0, 200, 100)[2] is None


def test_export_backup_and_label(store: Store, tmp_path: Path) -> None:
    session = open_session(tmp_path / "home", seed=True)
    try:
        assert session.phone_count() == 2
        folder = tmp_path / "csv"
        paths = export_csvs(session, folder)
        text = paths[0].read_text(encoding="utf-8-sig")
        assert "PH-001" in text
        assert "Phone ID" in text
        components = paths[2].read_text(encoding="utf-8-sig")
        assert "Vibration motor" in components
        archive = tmp_path / "backup.zip"
        backup_store(session, archive)
        image = next((session.root / "images").glob("*.png"))
        assert image.is_file()
    finally:
        session.close()

    restored = tmp_path / "restored"
    restore_store(restored, archive)
    again = Store(restored)
    try:
        assert again.phone_count() == 2
        assert list((again.root / "images").glob("*.png"))
        motor = again.search_components(text="Vibration", location="stored")
        assert len(motor) == 1
        assert motor[0].bin_label == "Vibration motors"
        copied = again.search_components(text="Camera", identification="suggested")
        assert len(copied) == 1
    finally:
        again.close()

    png = label_png("PH-001", ["Sample S1"], label_payload("phone", "PH-001"))
    assert png.startswith(b"\x89PNG")


def test_custom_part_name_is_kept(store: Store) -> None:
    created = store.add_type("Hall sensor", "Senses a magnet.", beginner_important=True)
    assert created.id == "hall-sensor"
    assert store.get_glossary("hall-sensor").title == "Hall sensor"
    store.ensure_catalog()
    assert store.get_type("camera").plain_name == "Camera"
