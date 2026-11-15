"""Empirical concentration curves stored inside a PyMca .cfg file.

PyMca keeps the fit configuration. A ``curves`` section records
concentration = intercept + slope × peak-group area. PyMca ignores that
section, and a configuration written here still opens in PyMca.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from PyMca5.PyMcaIO.ConfigDict import ConfigDict


@dataclass
class Curve:
    element: str
    group: str
    slope: float
    intercept: float
    r2: float | None


@dataclass
class Standard:
    name: str
    areas: dict[str, float]
    known: dict[str, float]


def build_curves(standards: list[Standard]) -> list[Curve]:
    elements: list[str] = []
    for standard in standards:
        for element in standard.known:
            if element not in elements:
                elements.append(element)
    area_names = [name for standard in standards for name in standard.areas]
    curves: list[Curve] = []
    for element in elements:
        group = group_for(element, area_names)
        if group is None:
            continue
        points: list[tuple[float, float]] = []
        for standard in standards:
            known = standard.known.get(element)
            area = standard.areas.get(group)
            if known is None or area is None or area <= 0:
                continue
            points.append((area, known))
        if not points:
            continue
        slope, intercept, r2 = _regress(points)
        curves.append(Curve(element=element, group=group, slope=slope, intercept=intercept, r2=r2))
    return curves


def predict(curve: Curve | None, area: float | None) -> float | None:
    if curve is None or area is None:
        return None
    return curve.intercept + curve.slope * area


def group_for(element: str, groups: list[str]) -> str | None:
    for series in ("K", "L", "M"):
        name = f"{element} {series}"
        if name in groups:
            return name
    for name in groups:
        if name.startswith(element + " "):
            return name
    return None


def curves_from_config(config: dict) -> list[Curve]:
    section = config.get("curves") or {}
    if not isinstance(section, dict):
        return []
    order = section.get("order") or []
    if isinstance(order, str):
        order = [order]
    elements = [element for element in order if element != "order" and element in section]
    for key in section:
        if key != "order" and key not in elements:
            elements.append(key)
    curves: list[Curve] = []
    for element in elements:
        raw = section[element]
        parts = [part.strip() for part in raw.split(",")] if isinstance(raw, str) else list(raw)
        if len(parts) < 3:
            continue
        r2_value = float(parts[3]) if len(parts) > 3 else -1.0
        curves.append(
            Curve(
                element=str(element),
                group=str(parts[2]),
                slope=float(parts[0]),
                intercept=float(parts[1]),
                r2=None if r2_value < 0 else r2_value,
            )
        )
    return curves


def pymca_config(config: dict) -> dict:
    """Configuration PyMca's fitter accepts, without our curve section."""
    cleaned = copy.deepcopy(_plain(config))
    cleaned.pop("curves", None)
    return cleaned


def attach_curves(config: dict, curves: list[Curve]) -> dict:
    merged = copy.deepcopy(_plain(config))
    merged.pop("curves", None)
    if curves:
        section: dict = {"order": [curve.element for curve in curves]}
        for curve in curves:
            r2 = -1.0 if curve.r2 is None else curve.r2
            section[curve.element] = [curve.slope, curve.intercept, curve.group, r2]
        merged["curves"] = section
    return merged


def read_config(path: str) -> dict:
    loaded = ConfigDict()
    loaded.read(path)
    return _plain(loaded)


def write_config(path: str, config: dict) -> None:
    document = ConfigDict()
    document.update(_plain(config))
    document.write(path)


def _regress(points: list[tuple[float, float]]) -> tuple[float, float, float | None]:
    if len(points) == 1:
        area, concentration = points[0]
        slope = concentration / area if area else 0.0
        return slope, 0.0, None
    n = float(len(points))
    sx = sy = sxx = sxy = syy = 0.0
    for area, concentration in points:
        sx += area
        sy += concentration
        sxx += area * area
        sxy += area * concentration
        syy += concentration * concentration
    denom = n * sxx - sx * sx
    slope = 0.0 if abs(denom) < 1e-18 else (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    ss_tot = syy - (sy * sy) / n
    ss_res = 0.0
    for area, concentration in points:
        residual = concentration - (intercept + slope * area)
        ss_res += residual * residual
    r2 = 1.0 if ss_tot <= 1e-18 else 1.0 - ss_res / ss_tot
    return slope, intercept, r2


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except ValueError:
            return value
    return value
