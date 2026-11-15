"""PyInstaller entry. Freeze support has to live in the launched script."""

from __future__ import annotations

import os
import sys

# Before NumPy, and before a worker process imports the fitting code.
for _thread_var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_thread_var, "1")

if __name__ == "__main__" and len(sys.argv) == 1:
    from PyMcaExpanded.launch import detach_from_controlling_terminal

    detach_from_controlling_terminal()

import multiprocessing

from PyMcaExpanded.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
