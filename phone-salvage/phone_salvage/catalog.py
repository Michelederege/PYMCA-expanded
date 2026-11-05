"""Names, plain-language explanations, and the fixed choices used in the catalogue."""

from __future__ import annotations

from dataclasses import dataclass


STATUSES: tuple[tuple[str, str], ...] = (
    ("usable", "Usable"),
    ("maybe", "Maybe"),
    ("junk", "Junk"),
    ("not_checked", "Not yet checked"),
)

IDENTIFICATION: tuple[tuple[str, str], ...] = (
    ("suggested", "Suggested"),
    ("confirmed", "Confirmed"),
    ("cant_do_better", "Can't do better"),
)

REMOVAL: tuple[tuple[str, str], ...] = (
    ("easy_unplug", "Easy unplug"),
    ("hot_air", "Needs hot air"),
    ("not_practical", "Not practical"),
)

PRACTICAL: tuple[tuple[str, str], ...] = (
    ("easy", "Easy to reuse"),
    ("advanced", "Advanced"),
    ("not_practical", "Not practical to reuse"),
    ("unknown", "Not sure yet"),
)

BOARD_TYPES: tuple[tuple[str, str], ...] = (
    ("main", "Main board"),
    ("sub", "Sub board"),
    ("charging", "Charging port board"),
    ("flex", "Flex cable"),
    ("other", "Other"),
)

SIDES: tuple[tuple[str, str], ...] = (
    ("front", "Front"),
    ("back", "Back"),
)

POWERED: tuple[tuple[str, str], ...] = (
    ("yes", "Yes"),
    ("no", "No"),
    ("not_tried", "Not tried"),
)

LIQUID: tuple[tuple[str, str], ...] = (
    ("yes", "Yes"),
    ("no", "No"),
    ("unknown", "Not sure"),
)

SHIELD_STATES: tuple[tuple[str, str], ...] = (
    ("", "Not a shield"),
    ("unopened", "Unopened"),
    ("opened", "Opened"),
    ("not_visible", "Contents not visible"),
)

CANT_REASONS: tuple[str, ...] = (
    "Under a shield",
    "Markings worn off",
    "No marking on the part",
    "Too small to see",
    "Glare will not go away",
)

DEFAULT_TOOL = {
    "easy_unplug": "Plastic spudger",
    "hot_air": "Hot air station",
    "not_practical": "Leave it on the board",
}

# Lower numbers are pulled first: modules and plugs before tiny parts.
HARVEST_PRIORITY = {
    "camera": 10,
    "display": 11,
    "battery_connector": 20,
    "vibration_motor": 30,
    "speaker": 31,
    "earpiece": 32,
    "microphone": 33,
    "button": 40,
    "connector": 50,
    "flex_connector": 51,
    "sim_tray": 52,
    "sd_slot": 53,
    "antenna": 54,
    "ic": 70,
    "shield": 80,
    "other": 85,
    "crystal": 90,
    "transistor": 91,
    "diode": 92,
    "inductor": 93,
    "capacitor": 94,
    "resistor": 95,
    "test_point": 99,
}

LIMITS_TEXT = (
    "A photo can show damage you can see. It cannot prove a part works.\n\n"
    "Metal shields hide the parts underneath. If a can is unopened, what is under it is unknown.\n\n"
    "Tiny parts often look the same. This version does not name them for you. You mark each part yourself.\n\n"
    "You can map a board from a photo, with no camera connected and no detection."
)


@dataclass(frozen=True)
class ComponentType:
    id: str
    plain_name: str
    label: str
    explanation: str
    what_it_does: str
    removal_tip: str
    test_hint: str
    beginner_important: bool
    default_removal: str
    sort_order: int


def _type(
    id: str,
    plain_name: str,
    explanation: str,
    what_it_does: str,
    removal_tip: str,
    test_hint: str,
    *,
    important: bool,
    removal: str,
    order: int,
    label: str | None = None,
) -> ComponentType:
    return ComponentType(
        id=id,
        plain_name=plain_name,
        label=label or plain_name,
        explanation=explanation,
        what_it_does=what_it_does,
        removal_tip=removal_tip,
        test_hint=test_hint,
        beginner_important=important,
        default_removal=removal,
        sort_order=order,
    )


BUILTIN_TYPES: tuple[ComponentType, ...] = (
    _type(
        "camera",
        "Camera",
        "The phone's camera module.",
        "Takes the photos and video. It usually plugs in with a short flex cable.",
        "Lift the connector latch with a plastic tool, then unplug the flex. Do not pull on the cable itself.",
        "A meter cannot prove a camera works. Try it in a working phone of the same model, or leave it as not tested.",
        important=True,
        removal="easy_unplug",
        order=10,
    ),
    _type(
        "display",
        "Display",
        "The screen.",
        "Shows the picture. On many phones it is a separate assembly, not a tiny part on the main board.",
        "Screens crack easily. If it is glued on, heat and a plastic tool are safer than prying with metal.",
        "A meter cannot prove a display works. Look for cracks, then try it in a working phone of the same model if you have one.",
        important=True,
        removal="easy_unplug",
        order=11,
    ),
    _type(
        "vibration_motor",
        "Vibration motor",
        "The small motor that makes the phone buzz.",
        "Spins an off-center weight so the phone vibrates.",
        "Often held by adhesive or a small plug. A plastic spudger is enough.",
        "Measure resistance across the two contacts. A reading, rather than a dead short or an open line, is a hint. It does not prove the motor spins.",
        important=True,
        removal="easy_unplug",
        order=12,
    ),
    _type(
        "speaker",
        "Speaker",
        "The loudspeaker.",
        "Plays sound from calls and alerts.",
        "Usually held by screws or adhesive, then a plug. Do not poke the membrane.",
        "Measure resistance across the two contacts. A few ohms to a few tens of ohms is a hint that the coil is present. It does not prove the sound is good.",
        important=True,
        removal="easy_unplug",
        order=13,
    ),
    _type(
        "earpiece",
        "Earpiece",
        "The small speaker you hold to your ear.",
        "Plays the caller's voice.",
        "Usually a small plug or a lightly glued module. Lift it with plastic, not metal.",
        "Measure resistance across the two contacts. A modest reading is a hint. It does not prove the sound is good.",
        important=True,
        removal="easy_unplug",
        order=14,
    ),
    _type(
        "microphone",
        "Microphone",
        "The part that hears sound.",
        "Turns your voice into an electrical signal.",
        "Often a tiny plug on a flex. Unplug it. Do not scrape the hole.",
        "A meter cannot fully test a microphone. Try it in a working phone of the same model, or leave it as not tested.",
        important=True,
        removal="easy_unplug",
        order=15,
    ),
    _type(
        "button",
        "Button",
        "A switch you press.",
        "Power, volume, or another key. Some are on their own small board.",
        "The button board often unplugs. The switch itself is rarely worth desoldering.",
        "Continuity should change when the button is pressed and when it is released.",
        important=True,
        removal="easy_unplug",
        order=16,
    ),
    _type(
        "connector",
        "Connector",
        "A plug or socket.",
        "Joins a cable, a board, or the charging lead.",
        "Unplug any cable first. Replacing the socket on the board is a harder job than unplugging the cable.",
        "Check for bent pins. For a cable, continuity runs pin to pin, and neighbouring pins should not be shorted.",
        important=True,
        removal="easy_unplug",
        order=17,
    ),
    _type(
        "flex_connector",
        "Flex connector",
        "The socket a ribbon cable plugs into.",
        "Holds a flex cable. The cable is often the part worth keeping. The socket usually stays.",
        "Flip the latch, if there is one, and slide the cable out straight. Do not peel the socket off.",
        "Look along the cable for tears. Continuity is pin to pin, and neighbouring pins should not be shorted.",
        important=True,
        removal="easy_unplug",
        order=18,
    ),
    _type(
        "battery_connector",
        "Battery connector",
        "Where the battery plugs into the board.",
        "Brings power from the battery. Unplug the battery before other work on the board.",
        "Unplug the battery with plastic. Leave the socket on the board unless you have a reason to replace it.",
        "With the battery removed, look for bent pins and for a short between the power contacts. Do not probe this connector while a battery is plugged in.",
        important=True,
        removal="easy_unplug",
        order=19,
    ),
    _type(
        "sim_tray",
        "SIM tray",
        "The tray that holds the SIM card.",
        "Slides the SIM into the phone.",
        "Eject it with the pin hole. It is a mechanical part, not a soldered one.",
        "Check that it slides and that the contacts are not bent.",
        important=True,
        removal="easy_unplug",
        order=20,
    ),
    _type(
        "sd_slot",
        "Memory card slot",
        "Where a memory card sits.",
        "Holds an SD card, on phones that have one.",
        "The slot is usually soldered. The card itself just slides out.",
        "Check that a card seats, and look for bent contacts.",
        important=True,
        removal="not_practical",
        order=21,
    ),
    _type(
        "antenna",
        "Antenna",
        "The radio antenna.",
        "Sends and receives the phone's radio signal. Many are a flex or a coax lead that unplugs.",
        "Unplug coax by lifting it straight off the round socket. Do not yank the cable.",
        "Look for a snapped lead or a ripped pad. A meter will not tell you if the radio still works.",
        important=True,
        removal="easy_unplug",
        order=22,
    ),
    _type(
        "shield",
        "Metal shield",
        "A metal can covering parts underneath.",
        "Protects the circuits under it. The camera only sees the can, not the parts inside.",
        "Leave the can on unless you have a reason to open it. Opening it bends the can.",
        "There is nothing to meter on a closed can. If it is unopened, the parts under it are unknown.",
        important=True,
        removal="not_practical",
        order=30,
    ),
    _type(
        "ic",
        "Chip",
        "An integrated circuit, many circuits in one package.",
        "Does a specific job such as power, radio, or storage. The marking, if you can read it, is the clue.",
        "Needs hot air, and it is easy to lift the pads. Leave it if you are unsure.",
        "Most chips cannot be proved with a meter. Record what you can see. A working phone of the same model is the practical test, when you have one.",
        important=True,
        removal="hot_air",
        order=31,
    ),
    _type(
        "crystal",
        "Crystal",
        "A timing part.",
        "Keeps a clock steady for the chips around it.",
        "Needs hot air. It is easy to mix up with nearby parts.",
        "A meter cannot prove a crystal. Look for cracks, and keep it with the board it came from.",
        important=False,
        removal="hot_air",
        order=40,
    ),
    _type(
        "transistor",
        "Transistor",
        "A small switch or amplifier.",
        "Lets a small signal control a larger current.",
        "Needs hot air. On a phone board these are tiny.",
        "A meter check on the board is only a hint. Treat it as not final unless the part is off the board.",
        important=False,
        removal="hot_air",
        order=41,
    ),
    _type(
        "diode",
        "Diode",
        "Lets current through in one direction.",
        "Steers current, or clamps a spike.",
        "Needs hot air. Confirm you have the direction written down before it comes off.",
        "Use diode mode, both directions. A good diode conducts one way and blocks the other. On the board, other parts can affect the reading.",
        important=False,
        removal="hot_air",
        order=42,
    ),
    _type(
        "inductor",
        "Inductor",
        "A coil.",
        "Resists changes in current. Used in power circuits and filters.",
        "Needs hot air. Many look like capacitors.",
        "Use continuity. A coil should beep or show a low resistance. That does not prove its value.",
        important=False,
        removal="hot_air",
        order=43,
    ),
    _type(
        "capacitor",
        "Capacitor",
        "A small part that stores a little charge.",
        "Smooths and filters power. On a phone board most of them are tiny and unmarked.",
        "Usually not worth removing one by one. They need hot air, and the value is rarely printed.",
        "On the board, check that it is not a short. A capacitance reading on the board is usually misleading. Capacitance mode is useful after the part is off the board, if your meter has it.",
        important=False,
        removal="hot_air",
        order=44,
    ),
    _type(
        "resistor",
        "Resistor",
        "A small part that limits current.",
        "Sets currents and divides voltages. Phone resistors are tiny, and many have no readable value.",
        "Usually not worth removing one by one. They need hot air.",
        "Set the meter to resistance and compare with the value, if you know it. On the board, other parts affect the reading. A sure result means measuring it after it is removed.",
        important=False,
        removal="hot_air",
        order=45,
    ),
    _type(
        "test_point",
        "Test point",
        "A metal pad meant for meter probes.",
        "Gives a place to measure a signal. It is not a part you harvest.",
        "Leave it. There is nothing to remove.",
        "These pads are places a probe can touch. They are not parts you reuse.",
        important=False,
        removal="not_practical",
        order=46,
    ),
    _type(
        "other",
        "Other part",
        "A part that does not fit the other names.",
        "Use the notes to say what it is in this phone.",
        "Decide from the notes whether it unplugs, needs hot air, or should stay.",
        "Decide the check from what the part is. A photo still cannot prove it works.",
        important=False,
        removal="not_practical",
        order=90,
    ),
)

BUILTIN_TYPE_BY_ID = {item.id: item for item in BUILTIN_TYPES}

GLOSSARY_EXTRAS: tuple[tuple[str, str, str], ...] = (
    (
        "designator",
        "Designator",
        "A printed code such as R15 or C23 that names one part on a board. "
        "Most phone boards do not print these, because the parts are too close together. "
        "Use one when you can see it. Do not expect one.",
    ),
    (
        "marking code",
        "Marking code",
        "The short code printed on a part, often a chip. "
        "It is not always the full part number. When you identify a code once, "
        "save it in the parts library and it can be offered next time.",
    ),
    (
        "zone",
        "Zone",
        "A named area of the board, such as Camera or Charging. "
        "Zones make the map readable when you are zoomed out.",
    ),
    (
        "shield can",
        "Shield can",
        "A metal cover over part of the board. "
        "The photo shows the cover only. Parts under an unopened can are unknown, not missing.",
    ),
    (
        "simple view",
        "Simple view",
        "Shows the parts that matter for salvage: cameras, speakers, connectors, shields, and other large parts. "
        "Tiny resistors and capacitors stay hidden until you switch to Detailed view.",
    ),
    (
        "detailed view",
        "Detailed view",
        "Shows every part you have marked, including tiny ones, plus designators, markings, and part numbers.",
    ),
    (
        "hot air",
        "Hot air",
        "A tool that melts solder with a stream of hot air so a part can be lifted. "
        "It is easy to tear pads off a phone board. If a part says it needs hot air, "
        "leave it until you have practiced on a scrap board.",
    ),
    (
        "continuity",
        "Continuity",
        "A meter mode that beeps when two points are connected. "
        "Useful for fuses, switches, speakers, and cables. "
        "A beep is not a full test of every part.",
    ),
    (
        "diode mode",
        "Diode mode",
        "A meter mode for checking diodes. "
        "A good diode conducts in one direction and blocks in the other. "
        "On a board, other parts can create a path and confuse the reading.",
    ),
    (
        "looks ok",
        "Looks OK",
        "The part has no damage you can see, or you marked it usable from a photo and your notes. "
        "That is separate from Tested OK, which this version does not record yet.",
    ),
)


def choice_label(options: tuple[tuple[str, str], ...], key: str) -> str:
    for option_id, label in options:
        if option_id == key:
            return label
    return key


def keys(options: tuple[tuple[str, str], ...]) -> set[str]:
    return {option_id for option_id, _label in options}
