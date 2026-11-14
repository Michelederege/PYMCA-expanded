"""Launch the Fit window from an icon, with no terminal window."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def detach_from_controlling_terminal() -> None:
    """Leave a terminal that was only opened to start the window.

    Icon launches are not attached to a terminal, so this does nothing for them.
    A command with ``--cfg`` keeps the terminal, because that is the batch log.
    Set ``XRFDESK_FOREGROUND=1`` to stay attached while debugging.
    """
    if sys.platform == "win32" or len(sys.argv) > 1:
        return
    if os.environ.get("XRFDESK_FOREGROUND") == "1":
        return
    try:
        attached = sys.stdin.isatty()
    except Exception:
        return
    if not attached:
        return
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    if devnull > 2:
        os.close(devnull)


def prepare_windowed_launch() -> None:
    """Detach a console that a double-clicked program would otherwise keep.

    Command-line batch mode keeps the terminal, because that is where the
    CSV path and per-file errors are printed. An icon launch has no arguments.
    """
    if len(sys.argv) > 1:
        return
    _hide_windows_console()
    _capture_missing_stdio()


def desktop_entry(executable: Path, icon: Path) -> str:
    program = str(executable)
    picture = str(icon)
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=xrfdesk\n"
        "GenericName=XRF fitting\n"
        "Comment=Fit X-ray fluorescence spectra\n"
        f"Exec={_desktop_quote(program)}\n"
        f"Path={executable.parent}\n"
        f"Icon={picture}\n"
        "Terminal=false\n"
        "Categories=Science;\n"
        "StartupNotify=true\n"
        "StartupWMClass=xrfdesk\n"
    )


def install_launcher(executable: Path) -> Path:
    """Write a desktop icon that opens the program and does not open a terminal."""
    executable = executable.resolve()
    icon = _publish_icon(executable.parent)
    entry = desktop_entry(executable, icon)
    locations = [
        executable.parent / "xrfdesk.desktop",
        Path.home() / ".local" / "share" / "applications" / "xrfdesk.desktop",
    ]
    desktop = Path.home() / "Desktop"
    desktop.mkdir(exist_ok=True)
    locations.append(desktop / "xrfdesk.desktop")
    written = locations[0]
    for path in locations:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry, encoding="utf-8")
        path.chmod(0o755)
        written = path
    return written


def apply_window_icon(app) -> None:
    picture = icon_file()
    if picture is None:
        return
    from PySide6.QtGui import QIcon

    app.setWindowIcon(QIcon(str(picture)))
    setter = getattr(app, "setDesktopFileName", None)
    if setter is not None:
        setter("xrfdesk")


def install_exception_dialog() -> None:
    """Show a crash in a dialog. An icon launch has nowhere else to print it."""

    def _report(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log = _log_file()
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError:
            pass
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(None, "xrfdesk", f"{exc}\n\nDetails were saved to:\n{log}")
                return
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _report


def icon_file() -> Path | None:
    frozen = Path(getattr(sys, "_MEIPASS", "")) / "xrfdesk.png"
    if frozen.is_file():
        return frozen
    packaged = Path(__file__).resolve().parent / "assets" / "xrfdesk.png"
    if packaged.is_file():
        return packaged
    beside = Path(sys.executable).resolve().parent / "xrfdesk.png"
    if beside.is_file():
        return beside
    return None


def _publish_icon(folder: Path) -> Path:
    source = icon_file()
    destination = Path.home() / ".local" / "share" / "icons" / "hicolor" / "128x128" / "apps" / "xrfdesk.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source is None:
        return destination
    payload = source.read_bytes()
    destination.write_bytes(payload)
    beside = folder / "xrfdesk.png"
    if beside.resolve() != source.resolve():
        beside.write_bytes(payload)
    return destination


def _desktop_quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def _hide_windows_console() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    kernel = ctypes.windll.kernel32
    hwnd = kernel.GetConsoleWindow()
    if not hwnd:
        return
    ctypes.windll.user32.ShowWindow(hwnd, 0)
    kernel.FreeConsole()


def _capture_missing_stdio() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    log = _log_file()
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log, "a", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle


def _log_file() -> Path:
    return Path.home() / ".local" / "share" / "xrfdesk" / "xrfdesk.log"
