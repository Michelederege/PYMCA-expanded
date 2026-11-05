"""Board coordinates are fractions of the overview, from 0 to 1.

The origin is the top-left of the overview photo. A box is
(x, y, w, h). A pin is a point, with w and h left empty.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZoneBox:
    id: int
    x: float
    y: float
    w: float
    h: float


def clamp_box(x: float, y: float, w: float | None, h: float | None) -> tuple[float, float, float | None, float | None]:
    x = min(max(float(x), 0.0), 1.0)
    y = min(max(float(y), 0.0), 1.0)
    if w is None or h is None:
        return x, y, None, None
    w = min(max(float(w), 0.004), 1.0)
    h = min(max(float(h), 0.004), 1.0)
    if x + w > 1.0:
        w = max(0.004, 1.0 - x)
    if y + h > 1.0:
        h = max(0.004, 1.0 - y)
    return x, y, w, h


def center(x: float, y: float, w: float | None, h: float | None) -> tuple[float, float]:
    if w is None or h is None:
        return x, y
    return x + w / 2.0, y + h / 2.0


def assign_zone(x: float, y: float, w: float | None, h: float | None, zones: list[ZoneBox]) -> int | None:
    """Smallest zone that contains the part's center."""
    cx, cy = center(x, y, w, h)
    hits = [
        zone
        for zone in zones
        if zone.x <= cx <= zone.x + zone.w and zone.y <= cy <= zone.y + zone.h
    ]
    if not hits:
        return None
    return min(hits, key=lambda zone: zone.w * zone.h).id


def scene_box(
    x: float,
    y: float,
    w: float | None,
    h: float | None,
    board_w: float,
    board_h: float,
) -> tuple[float, float, float, float]:
    if w is None or h is None:
        return x * board_w, y * board_h, 0.0, 0.0
    return x * board_w, y * board_h, w * board_w, h * board_h


def norm_box(
    sx: float,
    sy: float,
    sw: float,
    sh: float,
    board_w: float,
    board_h: float,
) -> tuple[float, float, float | None, float | None]:
    if board_w <= 0 or board_h <= 0:
        raise ValueError("Board size must be positive")
    if sw <= 0 or sh <= 0:
        return clamp_box(sx / board_w, sy / board_h, None, None)
    return clamp_box(sx / board_w, sy / board_h, sw / board_w, sh / board_h)
