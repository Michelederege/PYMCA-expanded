"""Desktop XRF fitting. PyMca5 performs the fit; this package runs it."""

from __future__ import annotations

import os

# Set before NumPy is imported. Later changes do not affect a library that
# has already started its threads, and serial and parallel fits would drift.
for _thread_var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_thread_var, "1")

try:
    from xrfdesk._build_stamp import STAMP as _STAMP
except ImportError:
    _STAMP = ""

__version__ = "1.2.0"
__stamp__ = _STAMP
