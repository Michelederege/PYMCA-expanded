"""Plain-language sentences for the part panel and the harvest list.

Kept free of the window code so the wording can be tested on its own.
"""

from __future__ import annotations

from phone_salvage.catalog import DEFAULT_TOOL, HARVEST_PRIORITY, choice_label, REMOVAL, PRACTICAL, STATUSES


def shown_in_simple(beginner_important: bool, show_in_simple: bool) -> bool:
    return bool(beginner_important) or bool(show_in_simple)


def tool_for(removal: str, removal_tool: str) -> str:
    custom = removal_tool.strip()
    if custom:
        return custom
    return DEFAULT_TOOL.get(removal, "")


def reuse_verdict(
    *,
    status: str,
    practical_reuse: str,
    removed: bool,
    bin_label: str,
) -> str:
    if removed:
        if bin_label.strip():
            return f"Removed, and stored in {bin_label.strip()}."
        return "Marked as removed. Choose a bin so you can find it later."
    if status == "junk":
        return "Treat this as junk. It is not worth putting in a project."
    if status == "not_checked":
        sentence = "Not checked yet. A tidy photo only means it looks intact."
    elif status == "usable":
        sentence = "Marked usable. That is your decision. A photo still cannot prove it works."
    elif status == "maybe":
        sentence = "Maybe worth keeping. Read the notes before you rely on it."
    else:
        sentence = "No status yet."
    extra = {
        "easy": " This kind of part is a reasonable thing for a beginner to reuse.",
        "advanced": " Reusing this well takes more experience than unplugging a module.",
        "not_practical": " This is a poor candidate for a beginner project.",
        "unknown": "",
    }.get(practical_reuse, "")
    return sentence + extra


def identification_line(identification: str, reason: str) -> str:
    if identification == "confirmed":
        return "You confirmed this."
    if identification == "suggested":
        return "Suggested, not confirmed. Confirm it if the box is right, or move it."
    cleaned = reason.strip()
    if cleaned:
        return f"Can't do better. {cleaned}"
    return "Can't do better."


def removal_summary(removal: str, removal_tool: str, tip: str) -> str:
    how = choice_label(REMOVAL, removal)
    tool = tool_for(removal, removal_tool)
    text = how
    if tool:
        text = f"{how}. Tool: {tool}."
    if tip.strip():
        text = f"{text} {tip.strip()}"
    return text


def include_in_harvest(
    *,
    removed: bool,
    status: str,
    removal: str,
    beginner_important: bool,
    show_in_simple: bool,
) -> bool:
    """Parts still on the board that are worth pulling, modules before tiny passives."""
    if removed or status == "junk" or removal == "not_practical":
        return False
    if beginner_important or show_in_simple or status in ("usable", "maybe"):
        return True
    return False


def harvest_sort_key(type_id: str, board_short_id: str, plain_name: str) -> tuple:
    return (HARVEST_PRIORITY.get(type_id, 100), board_short_id, plain_name)


def status_summary(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    if total == 0:
        return "No parts match."
    pieces = [f"{total} part" + ("" if total == 1 else "s")]
    for key, label in STATUSES:
        number = counts.get(key, 0)
        if number:
            pieces.append(f"{number} {label.lower()}")
    return " · ".join(pieces)


def practical_label(key: str) -> str:
    return choice_label(PRACTICAL, key)
