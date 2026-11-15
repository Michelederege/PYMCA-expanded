"""Fifteen simulated spectra, each between 10,000 and 15,000 channels.

The shapes differ (plain CSV, text, Amptek, SPE, energy axes). The fit
window in the generated configuration covers the peaks, so the extra
channels are present in the file and are handed to PyMca.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from PyMcaExpanded.curves import Standard, attach_curves, build_curves, write_config
from PyMcaExpanded.demo import GAIN, LINES, SENSITIVITY, ZERO, _gaussian
from PyMcaExpanded.engine import clone_config, fit_spectrum
from PyMcaExpanded.spectra import load_spectrum

LENGTHS = [10000 + round(i * 5000 / 14) for i in range(15)]

# Fifteen different compositions. The first two are the standards.
RECIPES: tuple[tuple[str, dict[str, float]], ...] = (
    ("std_low", {"Fe": 400.0, "Cu": 150.0, "Zn": 80.0}),
    ("std_high", {"Fe": 1800.0, "Cu": 700.0, "Zn": 360.0}),
    ("mix_a", {"Fe": 900.0, "Cu": 220.0, "Zn": 140.0}),
    ("mix_b", {"Fe": 1100.0, "Cu": 480.0, "Zn": 90.0}),
    ("mix_c", {"Fe": 650.0, "Cu": 310.0, "Zn": 260.0}),
    ("mix_d", {"Fe": 1500.0, "Cu": 120.0, "Zn": 180.0}),
    ("mix_e", {"Fe": 720.0, "Cu": 640.0, "Zn": 210.0}),
    ("mix_f", {"Fe": 980.0, "Cu": 260.0, "Zn": 330.0}),
    ("mix_g", {"Fe": 430.0, "Cu": 510.0, "Zn": 70.0}),
    ("mix_h", {"Fe": 1320.0, "Cu": 340.0, "Zn": 155.0}),
    ("mix_i", {"Fe": 860.0, "Cu": 90.0, "Zn": 240.0}),
    ("mix_j", {"Fe": 1040.0, "Cu": 410.0, "Zn": 125.0}),
    ("mix_k", {"Fe": 560.0, "Cu": 275.0, "Zn": 190.0}),
    ("mix_l", {"Fe": 1210.0, "Cu": 180.0, "Zn": 300.0}),
    ("mix_m", {"Fe": 770.0, "Cu": 590.0, "Zn": 110.0}),
)


def write_wide_set(folder: Path) -> tuple[list[Path], Path]:
    folder.mkdir(parents=True, exist_ok=True)
    if len(LENGTHS) != 15 or any(not 10000 <= size <= 15000 for size in LENGTHS):
        raise RuntimeError("The wide set must be 15 files of 10,000 to 15,000 channels.")
    spectra = [_counts(index, recipe, LENGTHS[index]) for index, (_name, recipe) in enumerate(RECIPES)]
    paths = [_write(folder, index, name, spectra[index]) for index, (name, _recipe) in enumerate(RECIPES)]

    from PyMca5.PyMcaPhysics.xrf.ClassMcaTheory import ClassMcaTheory

    theory = ClassMcaTheory()
    config = theory.configure()
    config["peaks"] = {"Fe": "K", "Cu": "K", "Zn": "K"}
    config["detector"]["zero"] = ZERO
    config["detector"]["gain"] = GAIN
    config["detector"]["fixedzero"] = 1
    config["detector"]["fixedgain"] = 1
    config["fit"]["stripflag"] = 1
    config["fit"]["use_limit"] = 1
    config["fit"]["xmin"] = 80
    config["fit"]["xmax"] = 2200
    config["fit"]["hypermetflag"] = 1
    config["fit"]["escapeflag"] = 0
    config["fit"]["sumflag"] = 0
    config["fit"]["strategyflag"] = 0
    config["fit"]["scatterflag"] = 0
    config["fit"]["maxiter"] = 20

    standards: list[Standard] = []
    for index in (0, 1):
        outcome = fit_spectrum(load_spectrum(paths[index]), config)
        standards.append(Standard(name=RECIPES[index][0], areas=outcome.areas, known=dict(RECIPES[index][1])))
    config_path = folder / "wide.cfg"
    write_config(str(config_path), attach_curves(clone_config(config), build_curves(standards)))
    return paths, config_path


def _counts(index: int, recipe: dict[str, float], length: int) -> np.ndarray:
    counts = np.full(length, 8.0 + (index % 5))
    channels = np.arange(length, dtype=float)
    for element, ppm in recipe.items():
        for energy, fraction in LINES[element]:
            counts += _gaussian(channels, energy, SENSITIVITY[element] * ppm * fraction)
    if index % 4 == 3:
        counts += _gaussian(channels, 10.5515, 3000.0 + index * 10)
    rng = np.random.default_rng(2000 + index)
    counts += rng.normal(0.0, 0.4, size=length)
    return np.rint(np.clip(counts, 0, None))


def _write(folder: Path, index: int, name: str, counts: np.ndarray) -> Path:
    kind = index % 7
    if index == 8:
        path = folder / "scan folder" / f"{name}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_pairs(path, np.arange(counts.size), counts, ",")
        return path
    if kind == 0:
        path = folder / f"{name}.csv"
        _write_pairs(path, np.arange(counts.size), counts, ",")
    elif kind == 1:
        path = folder / f"{name}.txt"
        path.write_text("\n".join(str(int(value)) for value in counts) + "\n", encoding="utf-8")
    elif kind == 2:
        path = folder / f"{name}.mca"
        body = ["<<CALIBRATION>>", "0", "0.01", "<<DATA>>"]
        body.extend(str(int(value)) for value in counts)
        body.append("<<END>>")
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
    elif kind == 3:
        path = folder / f"{name}.spe"
        header = ["$SPEC_ID:", name, "$DATA:", f"0 {counts.size - 1}"]
        header.extend(str(int(value)) for value in counts)
        header.extend(["$ENER_FIT:", "0.0 0.01"])
        path.write_text("\n".join(header) + "\n", encoding="utf-8")
    elif kind == 4:
        path = folder / f"{name}.csv"
        _write_pairs(path, np.arange(counts.size), counts, ";")
    elif kind == 5:
        path = folder / f"{name}.txt"
        _write_pairs(path, np.arange(counts.size) * GAIN, counts, "\t", header="energy_keV\tcounts")
    else:
        path = folder / f"{name}.csv"
        ev = np.arange(counts.size) * (GAIN * 1000.0)
        text = "\ufeff# simulated\nenergy_eV,counts\n"
        text += "\n".join(f"{energy:.4f},{int(value)}" for energy, value in zip(ev, counts))
        path.write_text(text + "\n", encoding="utf-8")
    return path


def _write_pairs(path: Path, xs: np.ndarray, counts: np.ndarray, separator: str, header: str | None = None) -> None:
    lines = [] if header is None else [header]
    if header is None and separator == ",":
        lines = ["channel,counts"]
    for x_value, counts_value in zip(xs, counts):
        left = str(int(x_value)) if float(x_value).is_integer() else f"{x_value:.8f}"
        lines.append(f"{left}{separator}{int(counts_value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
