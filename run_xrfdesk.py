"""PyInstaller entry. Freeze support has to live in the launched script."""

from __future__ import annotations

import multiprocessing

from xrfdesk.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
