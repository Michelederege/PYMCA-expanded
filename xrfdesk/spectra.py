"""Read spectrum files. The fit itself is left to PyMca."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Spectrum:
    name: str
    path: str
    channels: np.ndarray
    counts: np.ndarray
    zero: float | None = None
    gain: float | None = None


def load_spectrum(path: str | Path) -> Spectrum:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    suffix = file_path.suffix.lower()
    if suffix == ".mca" or "<<DATA>>" in text.upper():
        return _load_amptek(file_path, text)
    if suffix == ".spe" or text.lstrip().startswith("$"):
        return _load_spe(file_path, text)
    return _load_table(file_path, text)


def _load_table(path: Path, text: str) -> Spectrum:
    counts: list[float] = []
    xs: list[float] = []
    saw_pair = False
    for line in text.replace("\ufeff", "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        parts = [part for part in _split_row(stripped) if part]
        numbers = []
        numeric = True
        for part in parts:
            try:
                numbers.append(float(part.replace(",", ".")))
            except ValueError:
                numeric = False
                break
        if not numeric or not numbers:
            continue
        if len(numbers) == 1:
            counts.append(numbers[0])
        else:
            xs.append(numbers[0])
            counts.append(numbers[1])
            saw_pair = True
    return _finish(path, counts, xs if saw_pair else None)


def _load_amptek(path: Path, text: str) -> Spectrum:
    zero = None
    gain = None
    counts: list[float] = []
    in_data = False
    in_cal = False
    cal_numbers: list[float] = []
    for line in text.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("<<") and upper.endswith(">>"):
            in_data = upper == "<<DATA>>"
            in_cal = upper == "<<CALIBRATION>>"
            continue
        if in_cal:
            try:
                cal_numbers.append(float(stripped.split()[0]))
            except (ValueError, IndexError):
                if cal_numbers:
                    in_cal = False
            continue
        if in_data:
            if not stripped:
                continue
            try:
                counts.append(float(stripped.split()[0]))
            except ValueError:
                continue
    if len(cal_numbers) >= 2:
        # Amptek writes the quadratic terms as channel = a + b E + c E^2, or the
        # two-point offset and gain in keV. Two leading values are offset then gain.
        zero, gain = cal_numbers[0], cal_numbers[1]
    return _finish(path, counts, None, zero, gain)


def _load_spe(path: Path, text: str) -> Spectrum:
    lines = text.splitlines()
    counts: list[float] = []
    zero = None
    gain = None
    index = 0
    while index < len(lines):
        tag = lines[index].strip().upper()
        if tag.startswith("$DATA"):
            index += 1
            if index >= len(lines):
                break
            header = lines[index].split()
            index += 1
            expected = None
            if len(header) >= 2:
                try:
                    expected = int(float(header[1])) - int(float(header[0])) + 1
                except ValueError:
                    expected = None
            while index < len(lines) and not lines[index].strip().startswith("$"):
                for part in lines[index].split():
                    try:
                        counts.append(float(part))
                    except ValueError:
                        pass
                index += 1
                if expected is not None and len(counts) >= expected:
                    break
            continue
        if tag.startswith("$ENER_FIT") or tag.startswith("$MCA_CAL"):
            index += 1
            if index < len(lines):
                numbers = []
                for part in lines[index].replace(",", " ").split():
                    try:
                        numbers.append(float(part))
                    except ValueError:
                        break
                if len(numbers) >= 2:
                    zero, gain = numbers[0], numbers[1]
            index += 1
            continue
        index += 1
    return _finish(path, counts, None, zero, gain)


def _finish(
    path: Path,
    counts: list[float],
    xs: list[float] | None,
    zero: float | None = None,
    gain: float | None = None,
) -> Spectrum:
    if len(counts) < 8:
        raise ValueError(f"{path.name} does not contain a spectrum of at least 8 channels.")
    values = np.asarray(counts, dtype=float)
    channels = np.arange(values.size, dtype=float)
    if xs is not None and len(xs) == len(counts) and _looks_like_energy(xs):
        slope, intercept = _linear(np.arange(len(xs), dtype=float), np.asarray(xs, dtype=float))
        if slope > 0:
            zero, gain = intercept, slope
    elif xs is not None and len(xs) == len(counts) and _looks_like_channel(xs):
        channels = np.asarray(xs, dtype=float)
    name = path.name
    for suffix in (".csv", ".txt", ".mca", ".spe"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return Spectrum(name=name, path=str(path), channels=channels, counts=values, zero=zero, gain=gain)


def _split_row(line: str) -> list[str]:
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    if ";" in line:
        return [part.strip() for part in line.split(";")]
    if "," in line:
        return [part.strip() for part in line.split(",")]
    return line.split()


def _looks_like_energy(values: list[float]) -> bool:
    if values[-1] > 200 or values[-1] <= values[0]:
        return False
    increasing = sum(1 for i in range(1, len(values)) if values[i] >= values[i - 1])
    return increasing / (len(values) - 1) > 0.9


def _looks_like_channel(values: list[float]) -> bool:
    matches = sum(1 for i, value in enumerate(values) if value == i or value == i + 1)
    return matches / len(values) > 0.95


def _linear(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    n = float(x.size)
    denom = n * np.sum(x * x) - np.sum(x) ** 2
    if abs(denom) < 1e-12:
        return 0.0, float(y[0])
    slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / denom
    intercept = (np.sum(y) - slope * np.sum(x)) / n
    return float(slope), float(intercept)
