"""One-spectrum fitting through PyMca's ClassMcaTheory.

Nothing in this module reimplements the peak model. Batch and the Fit
window both call ``fit_spectrum``.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field

import numpy as np
from PyMca5.PyMcaPhysics.xrf.ClassMcaTheory import ClassMcaTheory

from xrfdesk.curves import Curve, predict, pymca_config
from xrfdesk.spectra import Spectrum


@dataclass
class FitOutcome:
    areas: dict[str, float]
    chisq: float
    concentrations: dict[str, float] = field(default_factory=dict)


def fit_spectrum(spectrum: Spectrum, config: dict, curves: list[Curve] | None = None) -> FitOutcome:
    """Fit one spectrum. ``config`` is a PyMca configuration dictionary."""
    _quiet_numeric_libraries()
    theory = ClassMcaTheory()
    prepared = pymca_config(config)
    if spectrum.zero is not None and spectrum.gain is not None:
        detector = prepared.setdefault("detector", {})
        detector["zero"] = float(spectrum.zero)
        detector["gain"] = float(spectrum.gain)
    theory.configure(prepared)
    theory.setData(
        np.asarray(spectrum.channels, dtype=float),
        np.asarray(spectrum.counts, dtype=float),
    )
    theory.estimate()
    _fitresult, result = theory.startfit(digest=1)
    areas = {group: float(result[group]["fitarea"]) for group in result["groups"]}
    concentrations = {}
    for curve in curves or []:
        value = predict(curve, areas.get(curve.group))
        if value is not None:
            concentrations[curve.element] = float(value)
    return FitOutcome(areas=areas, chisq=float(result["chisq"]), concentrations=concentrations)


def clone_config(config: dict) -> dict:
    return copy.deepcopy(config)


def _quiet_numeric_libraries() -> None:
    # One thread in each process keeps serial and parallel fits on the same numbers.
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
