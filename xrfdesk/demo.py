"""Bronze example: a PyMca configuration and three spectra.

The configuration is produced by PyMca from the two standards. Batch can
open the example without the Fit window.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from xrfdesk.curves import Curve, Standard, attach_curves, build_curves, write_config
from xrfdesk.engine import clone_config, fit_spectrum
from xrfdesk.excel_fill import new_template
from xrfdesk.spectra import load_spectrum

CHANNELS = 2048
ZERO = 0.0
GAIN = 0.01
ELEMENTS = ("Fe", "Cu", "Zn")

# Counts in the generated line, per ppm, before PyMca fits them.
SENSITIVITY = {"Fe": 18.0, "Cu": 25.0, "Zn": 22.0}
LINES = {
    "Fe": ((6.40384, 1.0), (7.05798, 0.13)),
    "Cu": ((8.04778, 1.0), (8.90529, 0.13)),
    "Zn": ((8.63886, 1.0), (9.572, 0.14)),
}

RECIPES = (
    ("std_500", {"Fe": 500.0, "Cu": 200.0, "Zn": 100.0}, {}),
    ("std_2000", {"Fe": 2000.0, "Cu": 800.0, "Zn": 400.0}, {}),
    ("unknown", {"Fe": 1250.0, "Cu": 520.0, "Zn": 230.0}, {"Pb": ((10.5515, 7400.0), (12.6137, 4200.0))}),
)


def bronze_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "examples" / "bronze"
    return Path(__file__).resolve().parents[1] / "examples" / "bronze"


def bronze_files() -> tuple[Path, list[Path], Path]:
    folder = bronze_dir()
    scans = [folder / "std_500.csv", folder / "std_2000.csv", folder / "unknown.csv"]
    return folder / "bronze.cfg", scans, folder / "template.xlsx"


def write_bronze_example(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, recipe, extra in RECIPES:
        path = folder / f"{name}.csv"
        _write_counts(path, _spectrum(recipe, extra))
        paths.append(path)

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
    config["fit"]["xmin"] = 150
    config["fit"]["xmax"] = 1400
    config["fit"]["hypermetflag"] = 1
    config["fit"]["escapeflag"] = 0
    config["fit"]["sumflag"] = 0
    config["fit"]["strategyflag"] = 0
    config["fit"]["scatterflag"] = 0
    config["fit"]["maxiter"] = 20

    standards: list[Standard] = []
    for path, (_name, recipe, _extra) in zip(paths[:2], RECIPES[:2]):
        outcome = fit_spectrum(load_spectrum(path), config)
        standards.append(Standard(name=path.stem, areas=outcome.areas, known=dict(recipe)))
    curves: list[Curve] = build_curves(standards)
    write_config(str(folder / "bronze.cfg"), attach_curves(clone_config(config), curves))
    new_template(str(folder / "template.xlsx"), [curve.element for curve in curves])


def _spectrum(recipe: dict[str, float], extra: dict) -> np.ndarray:
    counts = np.full(CHANNELS, 12.0)
    channels = np.arange(CHANNELS, dtype=float)
    for element, ppm in recipe.items():
        for energy, fraction in LINES[element]:
            counts += _gaussian(channels, energy, SENSITIVITY[element] * ppm * fraction)
    for peaks in extra.values():
        for energy, area in peaks:
            counts += _gaussian(channels, energy, area)
    return np.rint(counts)


def _gaussian(channels: np.ndarray, energy: float, area: float) -> np.ndarray:
    sigma = (0.155 / 2.3548) / GAIN
    mu = (energy - ZERO) / GAIN
    peak = np.exp(-0.5 * ((channels - mu) / sigma) ** 2)
    total = peak.sum()
    if total <= 0:
        return peak
    return peak * (area / total)


def _write_counts(path: Path, counts: np.ndarray) -> None:
    lines = ["channel,counts"]
    lines.extend(f"{index},{int(value)}" for index, value in enumerate(counts))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
