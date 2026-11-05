"""Sample phones so every screen has something to click on the first launch."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from phone_salvage.catalog import DEFAULT_TOOL
from phone_salvage.store import Store


def seed_demo(store: Store) -> None:
    main_rel = _save(store, "demo-main-board.png", _draw_main_board())
    charge_rel = _save(store, "demo-charge-board.png", _draw_charge_board())
    photo_rel = _save(store, "demo-phone.png", _draw_phone("Sample S1", "Black"))
    photo_two = _save(store, "demo-phone-blue.png", _draw_phone("Sample S1", "Blue"))

    first = store.add_phone(
        make="Sample",
        model="S1",
        model_number="S1-DEMO",
        colour="Black",
        purchase_date="2026-01-15",
        purchase_price="12",
        condition_notes="Bought in a lot of two. The case is worn.",
        photo_path=photo_rel,
        powered_on="no",
        known_faults="Does not turn on.",
        liquid_contact="unknown",
    )
    main = store.add_board(
        first.id,
        "main",
        revision="A",
        part_number="S1-MB-A",
        notes="Sample layout for learning the screens.",
    )
    front = store.get_side(main.id, "front")
    store.set_overview(front.id, main_rel)
    zones = {
        "Camera area": store.add_zone(front.id, "Camera area", 0.14, 0.04, 0.72, 0.16),
        "Power": store.add_zone(front.id, "Power", 0.16, 0.34, 0.68, 0.22),
        "Audio": store.add_zone(front.id, "Audio", 0.06, 0.60, 0.38, 0.14),
        "Charging": store.add_zone(front.id, "Charging", 0.12, 0.78, 0.76, 0.14),
    }
    _add_main_parts(store, front.id, zones)

    charging = store.add_board(first.id, "charging", revision="A", notes="Small board at the bottom edge.")
    charge_front = store.get_side(charging.id, "front")
    store.set_overview(charge_front.id, charge_rel)
    store.add_component(
        charge_front.id,
        "connector",
        "box",
        0.28,
        0.32,
        0.44,
        0.36,
        status="usable",
        removal="easy_unplug",
        removal_tool=DEFAULT_TOOL["easy_unplug"],
        practical_reuse="easy",
        function_notes="Charging port on its own small board. Unplug the flex before you lift the board.",
        identification="confirmed",
    )

    store.add_part(
        marking_code="DEMO-PMIC",
        part_number="DEMO-PMIC-1",
        type_id="ic",
        manufacturer="Demo Silicon",
        notes="Sample power chip for the Sample S1. Beginners usually leave this on the board.",
        expected_notes="No meter test proves this chip. Record what you can see, and stop there.",
    )

    second = store.add_phone(
        make="Sample",
        model="S1",
        model_number="S1-DEMO",
        colour="Blue",
        purchase_date="2026-01-15",
        purchase_price="12",
        condition_notes="Second phone from the same lot.",
        photo_path=photo_two,
        powered_on="no",
        known_faults="No sound from the loudspeaker.",
        liquid_contact="no",
    )
    other = store.add_board(second.id, "main", revision="A", part_number="S1-MB-A")
    other_front = store.get_side(other.id, "front")
    store.set_overview(other_front.id, main_rel)
    store.copy_layout(front.id, other_front.id)
    copied = store.list_components(other_front.id)
    camera = next(part for part in copied if part.type_id == "camera")
    store.update_component(camera.id, y=min(0.92, camera.y + 0.03))
    motor = next(part for part in copied if part.type_id == "vibration_motor")
    motors = store.add_bin("Vibration motors", notes="Small motors pulled from phone lots.")
    store.update_component(motor.id, removed=True, bin_id=motors.id, status="usable", identification="confirmed")


def _add_main_parts(store: Store, side_id: int, zones: dict) -> None:
    easy = DEFAULT_TOOL["easy_unplug"]
    store.add_component(
        side_id,
        "camera",
        "box",
        0.36,
        0.06,
        0.28,
        0.10,
        zone_id=zones["Camera area"].id,
        status="usable",
        removal="easy_unplug",
        removal_tool=easy,
        practical_reuse="easy",
        function_notes="Rear camera. Unplug the flex beside it. Same model only.",
        identification="confirmed",
    )
    store.add_component(
        side_id,
        "shield",
        "box",
        0.22,
        0.38,
        0.56,
        0.14,
        zone_id=zones["Power"].id,
        status="not_checked",
        removal="not_practical",
        removal_tool=DEFAULT_TOOL["not_practical"],
        practical_reuse="not_practical",
        shield_state="unopened",
        function_notes="Metal can over the power area. The parts under it are unknown.",
        identification="confirmed",
    )
    store.add_component(
        side_id,
        "ic",
        "box",
        0.30,
        0.26,
        0.22,
        0.06,
        status="maybe",
        removal="hot_air",
        removal_tool=DEFAULT_TOOL["hot_air"],
        practical_reuse="advanced",
        marking_code="DEMO-PMIC",
        part_number="DEMO-PMIC-1",
        manufacturer="Demo Silicon",
        function_notes="Power chip. The marking is in the parts library.",
        identification="confirmed",
    )
    store.add_component(
        side_id,
        "speaker",
        "box",
        0.10,
        0.63,
        0.16,
        0.08,
        zone_id=zones["Audio"].id,
        status="junk",
        removal="easy_unplug",
        removal_tool=easy,
        practical_reuse="easy",
        condition_notes="Membrane is torn.",
        function_notes="Loudspeaker.",
        identification="confirmed",
    )
    store.add_component(
        side_id,
        "vibration_motor",
        "box",
        0.62,
        0.62,
        0.18,
        0.08,
        status="usable",
        removal="easy_unplug",
        removal_tool=easy,
        practical_reuse="easy",
        function_notes="Vibration motor, stuck down with a little adhesive.",
        identification="confirmed",
    )
    store.add_component(
        side_id,
        "button",
        "box",
        0.08,
        0.22,
        0.10,
        0.06,
        status="usable",
        removal="easy_unplug",
        removal_tool=easy,
        practical_reuse="easy",
        function_notes="Power button on a small flex.",
        identification="confirmed",
    )
    store.add_component(
        side_id,
        "battery_connector",
        "box",
        0.40,
        0.50,
        0.20,
        0.05,
        status="usable",
        removal="easy_unplug",
        removal_tool=easy,
        practical_reuse="easy",
        function_notes="Battery plugs in here. Unplug the battery before any other work.",
        identification="confirmed",
    )
    store.add_component(
        side_id,
        "connector",
        "box",
        0.34,
        0.81,
        0.32,
        0.08,
        zone_id=zones["Charging"].id,
        status="maybe",
        removal="easy_unplug",
        removal_tool=easy,
        practical_reuse="easy",
        function_notes="Charging flex socket on the main board.",
        identification="confirmed",
    )
    store.add_component(
        side_id,
        "capacitor",
        "box",
        0.18,
        0.46,
        0.04,
        0.03,
        zone_id=zones["Power"].id,
        status="not_checked",
        removal="hot_air",
        removal_tool=DEFAULT_TOOL["hot_air"],
        practical_reuse="not_practical",
        identification="confirmed",
    )
    store.add_component(
        side_id,
        "resistor",
        "pin",
        0.78,
        0.48,
        status="not_checked",
        removal="hot_air",
        removal_tool=DEFAULT_TOOL["hot_air"],
        practical_reuse="not_practical",
        identification="confirmed",
    )


def _save(store: Store, name: str, image: Image.Image) -> str:
    path = store.images / name
    image.save(path, "PNG")
    return path.relative_to(store.root).as_posix()


def _rect(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], size: tuple[int, int], **kwargs) -> None:
    width, height = size
    x, y, w, h = box
    draw.rounded_rectangle((x * width, y * height, (x + w) * width, (y + h) * height), **kwargs)


def _draw_main_board() -> Image.Image:
    size = (900, 1600)
    image = Image.new("RGB", size, "#d9d3c7")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((36, 28, 864, 1572), radius=56, fill="#1f6b4a", outline="#143d2c", width=6)
    _rect(draw, (0.14, 0.04, 0.72, 0.16), size, radius=18, fill="#1a5c3e")
    _rect(draw, (0.36, 0.06, 0.28, 0.10), size, radius=16, fill="#1c1c1c")
    draw.ellipse((430, 130, 500, 200), fill="#2a2a2a", outline="#c6b48a", width=4)
    _rect(draw, (0.16, 0.34, 0.68, 0.22), size, radius=18, fill="#1a5c3e")
    _rect(draw, (0.22, 0.38, 0.56, 0.14), size, radius=8, fill="#c5ccd1", outline="#8e979c", width=3)
    _rect(draw, (0.30, 0.26, 0.22, 0.06), size, radius=4, fill="#111111")
    label = ImageFont.load_default(size=28)
    draw.text((286, 444), "DEMO-PMIC", fill="#d7d7d7", font=label)
    _rect(draw, (0.40, 0.50, 0.20, 0.05), size, radius=4, fill="#d4b46a")
    _rect(draw, (0.10, 0.63, 0.16, 0.08), size, radius=20, fill="#2b2b2b")
    _rect(draw, (0.62, 0.62, 0.18, 0.08), size, radius=24, fill="#9aa3a8", outline="#5c656a", width=3)
    _rect(draw, (0.08, 0.22, 0.10, 0.06), size, radius=6, fill="#3a3a3a")
    _rect(draw, (0.12, 0.78, 0.76, 0.14), size, radius=16, fill="#1a5c3e")
    _rect(draw, (0.34, 0.81, 0.32, 0.08), size, radius=6, fill="#d4b46a", outline="#8a6a2f", width=3)
    caption = ImageFont.load_default(size=32)
    draw.text((48, 1488), "Sample drawing, not a microscope photo.", fill="#efe8dc", font=caption)
    return image


def _draw_charge_board() -> Image.Image:
    size = (900, 420)
    image = Image.new("RGB", size, "#d9d3c7")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 70, 860, 350), radius=28, fill="#1f6b4a", outline="#143d2c", width=5)
    _rect(draw, (0.28, 0.32, 0.44, 0.36), size, radius=10, fill="#d4b46a", outline="#8a6a2f", width=3)
    draw.text(
        (48, 24),
        "Illustrated charging board. Not a microscope photo.",
        fill="#3d3830",
        font=ImageFont.load_default(size=20),
    )
    return image


def _draw_phone(title: str, colour: str) -> Image.Image:
    fill = "#1c1c1c" if colour == "Black" else "#2f4f73"
    image = Image.new("RGB", (600, 900), "#efeae2")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((120, 40, 480, 860), radius=48, fill=fill, outline="#111111", width=4)
    draw.rounded_rectangle((150, 90, 450, 760), radius=8, fill="#101418")
    draw.ellipse((270, 780, 330, 840), outline="#c8c8c8", width=3)
    font = ImageFont.load_default(size=28)
    draw.text((180, 390), title, fill="#efe8dc", font=font)
    draw.text((180, 430), colour, fill="#c8c0b4", font=font)
    return image
