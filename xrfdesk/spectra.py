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


_SUFFIXES = (".csv", ".txt", ".mca", ".spe")


def spectrum_stem(path: str | Path) -> str:
    name = Path(path).name
    lowered = name.lower()
    for suffix in _SUFFIXES:
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return name


def list_labels(paths: list[str]) -> list[str]:
    """Names for a batch list. A repeated file name keeps its folder."""
    stems = [spectrum_stem(path) for path in paths]
    counts: dict[str, int] = {}
    for stem in stems:
        counts[stem] = counts.get(stem, 0) + 1
    draft: list[str] = []
    for path, stem in zip(paths, stems):
        if counts[stem] == 1:
            draft.append(stem)
            continue
        parent = Path(path).parent.name
        draft.append(f"{parent}/{stem}" if parent else stem)
    total: dict[str, int] = {}
    for label in draft:
        total[label] = total.get(label, 0) + 1
    running: dict[str, int] = {}
    labels: list[str] = []
    for label in draft:
        running[label] = running.get(label, 0) + 1
        if total[label] == 1:
            labels.append(label)
        else:
            labels.append(f"{label} ({running[label]})")
    return labels


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
    if xs is not None and len(xs) == len(counts):
        axis = np.asarray(xs, dtype=float)
        if _looks_like_channel(axis):
            channels = axis
        else:
            energy = _energy_axis(axis)
            if energy is not None:
                slope, intercept = _linear(np.arange(energy.size, dtype=float), energy)
                if slope > 0:
                    zero, gain = intercept, slope
    return Spectrum(
        name=spectrum_stem(path),
        path=str(path),
        channels=channels,
        counts=values,
        zero=zero,
        gain=gain,
    )


def _split_row(line: str) -> list[str]:
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    if ";" in line:
        return [part.strip() for part in line.split(";")]
    if "," in line:
        return [part.strip() for part in line.split(",")]
    return line.split()


def _looks_like_channel(values: np.ndarray) -> bool:
    index = np.arange(values.size, dtype=float)
    matches = np.count_nonzero((values == index) | (values == index + 1))
    return matches / values.size > 0.95


def _energy_axis(values: np.ndarray) -> np.ndarray | None:
    """Return a keV axis, or None when the column is not an energy axis.

    Channel indexes are handled before this is called. A column whose steps
    are a few eV is converted to keV. A column already in keV is returned
    unchanged, including spectra whose last channel is above 200 keV.
    """
    if values.size < 2 or not np.isfinite(values).all():
        return None
    diffs = np.diff(values)
    if np.count_nonzero(diffs >= 0) / diffs.size <= 0.9:
        return None
    step = float(np.median(diffs))
    if step >= 2.0 and values[-1] > 1000:
        return values / 1000.0
    if 0 < step < 2.0:
        return values
    return None


def _linear(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    n = float(x.size)
    denom = n * np.sum(x * x) - np.sum(x) ** 2
    if abs(denom) < 1e-12:
        return 0.0, float(y[0])
    slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / denom
    intercept = (np.sum(y) - slope * np.sum(x)) / n
    return float(slope), float(intercept)
