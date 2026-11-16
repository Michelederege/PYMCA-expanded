"""Check for a GitHub build and replace this program's folder with it."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QWidget,
)

from xrfdesk import __version__
from xrfdesk.update import (
    Release,
    UpdateError,
    clear_token,
    download_release,
    fetch_latest,
    install_folder,
    installed_stamp,
    launch_updater,
    load_token,
    same_build,
    save_token,
)


class _CheckThread(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.finished_ok.emit(fetch_latest())
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc).strip() or exc.__class__.__name__)


class _DownloadThread(QThread):
    advanced = Signal(int, int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, release: Release, destination: Path) -> None:
        super().__init__()
        self.release = release
        self.destination = destination

    def run(self) -> None:
        try:
            download_release(self.release, self.destination, progress=lambda got, total: self.advanced.emit(got, total))
        except UpdateError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(str(exc).strip() or exc.__class__.__name__)
            return
        self.finished_ok.emit(str(self.destination))


class UpdateBar(QWidget):
    """One row: the version, a check button, and the result of the last check."""

    def __init__(self) -> None:
        super().__init__()
        self.release: Release | None = None
        self._check_thread: _CheckThread | None = None
        self._download_thread: _DownloadThread | None = None
        self._dialog: QProgressDialog | None = None
        self._cancel_download = False

        self.version = QLabel(f"xrfdesk {__version__}")
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.check_button = QPushButton("Check for updates")
        self.check_button.clicked.connect(self.check)
        self.update_button = QPushButton("Update")
        self.update_button.setEnabled(False)
        self.update_button.clicked.connect(self.apply_update)
        self.token_button = QPushButton("GitHub token")
        self.token_button.clicked.connect(self.edit_token)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.version)
        row.addWidget(self.check_button)
        row.addWidget(self.update_button)
        row.addWidget(self.token_button)
        row.addWidget(self.message, 1)

    def check(self) -> None:
        if self._check_thread is not None and self._check_thread.isRunning():
            return
        self.update_button.setEnabled(False)
        self.release = None
        self.message.setText("Checking GitHub…")
        self._check_thread = _CheckThread()
        self._check_thread.finished_ok.connect(self._show_release)
        self._check_thread.failed.connect(self._show_error)
        self._check_thread.start()

    def edit_token(self) -> None:
        current = load_token()
        text, ok = QInputDialog.getText(
            self,
            "GitHub token",
            "A public repository needs no token.\n"
            "If the repository is private, paste a token that can read releases.\n"
            "Leave this empty to forget a saved token.",
            QLineEdit.EchoMode.Password,
            current,
        )
        if not ok:
            return
        if text.strip():
            save_token(text)
            self.message.setText("Token saved on this computer. Check for updates again.")
        else:
            clear_token()
            self.message.setText("Saved token removed.")

    def apply_update(self) -> None:
        release = self.release
        folder = install_folder()
        if release is None or folder is None:
            QMessageBox.information(
                self,
                "Update",
                "This copy was started from source. Pull the repository to update it. "
                "The packaged program replaces its own folder.",
            )
            return
        if self._download_thread is not None and self._download_thread.isRunning():
            return
        destination = Path(tempfile.gettempdir()) / release.asset_name
        self._cancel_download = False
        self._dialog = QProgressDialog("Downloading the update…", "Cancel", 0, 0, self)
        self._dialog.setWindowTitle("Update")
        self._dialog.setAutoClose(False)
        self._dialog.show()
        self._download_thread = _DownloadThread(release, destination)
        self._download_thread.advanced.connect(self._on_download)
        self._download_thread.finished_ok.connect(self._swap)
        self._download_thread.failed.connect(self._download_failed)
        self._dialog.canceled.connect(self._mark_cancelled)
        self._download_thread.start()

    def _mark_cancelled(self) -> None:
        self._cancel_download = True

    def _show_release(self, release: object) -> None:
        if not isinstance(release, Release):
            return
        self.release = release
        label = release.version or "the latest build"
        if same_build(release):
            self.update_button.setEnabled(False)
            self.message.setText(f"This is the current GitHub build ({label}).")
            return
        if install_folder() is None:
            self.update_button.setEnabled(False)
            self.message.setText(
                f"GitHub has {label}. This copy was started from source, so use git pull to update it."
            )
            return
        self.update_button.setEnabled(True)
        self.message.setText(f"GitHub has {label}. Update replaces this program and opens it again.")

    def _show_error(self, text: str) -> None:
        self.update_button.setEnabled(False)
        self.message.setText(text)

    def _on_download(self, got: int, total: int) -> None:
        dialog = self._dialog
        if dialog is None:
            return
        if total > 0:
            dialog.setMaximum(total)
            dialog.setValue(min(got, total))
        else:
            dialog.setMaximum(0)

    def _download_failed(self, text: str) -> None:
        if self._dialog is not None:
            self._dialog.close()
        QMessageBox.warning(self, "Update", text)

    def _swap(self, path: str) -> None:
        if self._dialog is not None:
            self._dialog.close()
        if self._cancel_download:
            return
        folder = install_folder()
        if folder is None:
            return
        try:
            launch_updater(os.getpid(), Path(path), folder)
        except OSError as exc:
            QMessageBox.warning(self, "Update", f"Could not start the updater ({exc}).")
            return
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()


def stamp_for_title() -> str:
    stamp = installed_stamp()
    if not stamp:
        return __version__
    return f"{__version__} · {stamp[:7]}"
