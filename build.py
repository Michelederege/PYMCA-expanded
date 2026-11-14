#!/usr/bin/env python3
"""Build a standalone PyMca Expanded executable for this operating system.

On Windows the result is dist/PyMca Expanded/PyMca Expanded.exe.
On Linux it is dist/PyMca Expanded/PyMca Expanded.
On macOS it is dist/PyMca Expanded/PyMca Expanded. A .app bundle is not
produced; the binary opens the Fit window directly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from xrfdesk import APP_NAME

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
        APP_NAME,
        "--paths",
        str(ROOT),
        "--add-data",
        f"{bronze}{os.pathsep}examples/bronze",
        "--add-data",
        f"{ROOT / 'xrfdesk' / 'assets' / 'xrfdesk.png'}{os.pathsep}.",
        "--collect-data",
        "PyMca5",
        "--collect-all",
        "fisx",
        "--hidden-import",
        "PyMca5.PyMcaPhysics.xrf.ClassMcaTheory",
        "--hidden-import",
        "PyMca5.PyMcaPhysics.xrf.McaAdvancedFitBatch",
        "--hidden-import",
        "PyMca5.PyMcaCore.PyMcaBatchBuildOutput",
        "--hidden-import",
        "PyMca5.PyMcaGui.physics.xrf.McaAdvancedFit",
        "--hidden-import",
        "PyMca5.PyMcaIO.ConfigDict",
        "--hidden-import",
        "h5py",
        "--collect-all",
        "h5py",
        *_excludes(),
        str(ROOT / "run_xrfdesk.py"),
    ]
    env = os.environ.copy()
    env["QT_API"] = "pyside6"
    env["MALLOC_ARENA_MAX"] = "2"
    code = subprocess.call(command, cwd=ROOT, env=env)
    if code != 0:
        return code
    folder = ROOT / "dist" / APP_NAME
    binary_name = f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME
    binary = folder / binary_name
    if not binary.is_file():
        print(f"The build did not produce {binary}.", file=sys.stderr)
        return 1
    leftover = folder / "xrfdesk.png"
    named = folder / f"{APP_NAME}.png"
    if leftover.is_file() and not named.exists():
        leftover.replace(named)
    (folder / "How to open.txt").write_text(_instructions(binary_name), encoding="utf-8")
    from xrfdesk.launch import install_launcher

    try:
        installed = install_launcher(binary)
    except OSError as exc:
        print(f"The program was built. A desktop icon was not installed: {exc}")
        return 0
    print(f"Icon launch (no terminal): {installed}")
    return 0


def _instructions(binary_name: str) -> str:
    opener = f"double-click {APP_NAME}.exe" if binary_name.endswith(".exe") else f"open the {APP_NAME} program"
    return (
        f"{APP_NAME}\n"
        "\n"
        f"To start, {opener}. The Fit window opens on its own. No Python install is required.\n"
        "\n"
        "Keep every file in this folder. Moving only the program out of the folder will not start it.\n"
        "\n"
        "Open Batch fits a list of spectra. Open map batch fits every .mca file in a sample's MCA folder.\n"
        "Choose the configuration before a map batch. The sample folder then holds 00001_to_<last>.h5,\n"
        "and IMAGES holds the .cfg, .csv, .dat, and EDF peak images.\n"
    )


def _excludes() -> list[str]:
    names = [
        "PyQt5",
        "PyQt6",
        "PySide2",
        "tkinter",
        "pyopencl",
        "OpenGL",
        "silx",
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
