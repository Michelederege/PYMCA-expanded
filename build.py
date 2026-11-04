#!/usr/bin/env python3
"""Build a standalone xrfdesk executable for this operating system.

On Windows the result is dist/xrfdesk/xrfdesk.exe.
On Linux it is dist/xrfdesk/xrfdesk.
On macOS it is dist/xrfdesk/xrfdesk. A .app bundle is not produced; the
binary opens the Fit window directly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    bronze = ROOT / "examples" / "bronze"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "xrfdesk",
        "--paths",
        str(ROOT),
        "--add-data",
        f"{bronze}{os.pathsep}examples/bronze",
        "--collect-data",
        "PyMca5",
        "--collect-all",
        "fisx",
        "--hidden-import",
        "PyMca5.PyMcaPhysics.xrf.ClassMcaTheory",
        "--hidden-import",
        "PyMca5.PyMcaGui.physics.xrf.McaAdvancedFit",
        "--hidden-import",
        "PyMca5.PyMcaIO.ConfigDict",
        *_excludes(),
        str(ROOT / "run_xrfdesk.py"),
    ]
    env = os.environ.copy()
    env["QT_API"] = "pyside6"
    env["MALLOC_ARENA_MAX"] = "2"
    return subprocess.call(command, cwd=ROOT, env=env)


def _excludes() -> list[str]:
    names = [
        "PyQt5",
        "PyQt6",
        "PySide2",
        "tkinter",
        "pyopencl",
        "OpenGL",
        "silx",
        "h5py",
        "hdf5plugin",
        "IPython",
        "pytest",
        "sphinx",
        "numba",
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQuick3D",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtTextToSpeech",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtGraphs",
    ]
    flags: list[str] = []
    for name in names:
        flags.extend(["--exclude-module", name])
    return flags


if __name__ == "__main__":
    raise SystemExit(main())
