"""Application window. The catalogue itself does not depend on this module."""

from __future__ import annotations

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from phone_salvage.gui.board_page import BoardPage
from phone_salvage.gui.dialogs import GlossaryDialog, LimitsDialog, PartNamesDialog
from phone_salvage.gui.lists_page import BinsPage, HarvestPage, InventoryPage, PartsPage
from phone_salvage.gui.phones_page import PhonesPage
from phone_salvage.services import backup_store, export_csvs, restore_store
from phone_salvage.session import open_session


class MainWindow(QMainWindow):
    def __init__(self, root=None):
        super().__init__()
        self.setWindowTitle("Phone Salvage")
        self.resize(1280, 820)
        self._store = open_session(root)
        stored_mode = self._store.get_setting("start_view") or "simple"
        self.view_mode = stored_mode if stored_mode in ("simple", "detailed") else "simple"

        self.phones = PhonesPage(self)
        self.harvest = HarvestPage(self)
        self.inventory = InventoryPage(self)
        self.parts = PartsPage(self)
        self.bins = BinsPage(self)
        self.board_page = BoardPage(self)
        self._pages = [self.phones, self.harvest, self.inventory, self.parts, self.bins]

        self.stack = QStackedWidget()
        for page in self._pages:
            self.stack.addWidget(page)
        self.stack.addWidget(self.board_page)

        self.nav = QListWidget()
        self.nav.addItems(["Phones", "Harvest", "Inventory", "Parts library", "Bins"])
        self.nav.setFixedWidth(168)
        self.nav.currentRowChanged.connect(self._nav)

        shell = QWidget()
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.nav)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self.statusBar().showMessage("Ready")
        self._build_menus()
        self.glossary = GlossaryDialog(self)
        self.nav.setCurrentRow(0)

    @property
    def store(self):
        return self._store

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        export = QAction("Export CSV…", self)
        export.triggered.connect(self._export)
        backup = QAction("Back up…", self)
        backup.triggered.connect(self._backup)
        restore = QAction("Restore…", self)
        restore.triggered.connect(self._restore)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(export)
        file_menu.addAction(backup)
        file_menu.addAction(restore)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("View")
        group = QActionGroup(self)
        group.setExclusive(True)
        self.simple_action = QAction("Simple view", self)
        self.detailed_action = QAction("Detailed view", self)
        for action, mode in ((self.simple_action, "simple"), (self.detailed_action, "detailed")):
            action.setCheckable(True)
            action.setChecked(self.view_mode == mode)
            group.addAction(action)
            view_menu.addAction(action)
        self.simple_action.triggered.connect(lambda: self.set_view_mode("simple"))
        self.detailed_action.triggered.connect(lambda: self.set_view_mode("detailed"))

        settings = self.menuBar().addMenu("Settings")
        names = QAction("Part names…", self)
        names.triggered.connect(lambda: PartNamesDialog(self, self).exec())
        settings.addAction(names)

        help_menu = self.menuBar().addMenu("Help")
        glossary = QAction("Glossary", self)
        glossary.triggered.connect(lambda: self.show_glossary(None))
        limits = QAction("What this app cannot do", self)
        limits.triggered.connect(lambda: LimitsDialog(self).exec())
        help_menu.addAction(glossary)
        help_menu.addAction(limits)

    def _nav(self, row: int) -> None:
        if row < 0 or row >= len(self._pages):
            return
        self.stack.setCurrentIndex(row)
        self._pages[row].reload()

    def show_phones(self) -> None:
        self.nav.setCurrentRow(0)

    def open_board(self, board_id: int, side: str = "front", component_id: int | None = None, *, center: bool = False) -> None:
        self.stack.setCurrentWidget(self.board_page)
        self.nav.blockSignals(True)
        self.nav.clearSelection()
        self.nav.blockSignals(False)
        self.board_page.open(board_id, side, component_id, center=center)

    def open_component(self, component_id: int) -> None:
        part = self.store.get_component(component_id)
        if part is None:
            return
        self.open_board(part.board_id, part.side, part.id, center=True)

    def set_view_mode(self, mode: str) -> None:
        if mode not in ("simple", "detailed"):
            return
        self.view_mode = mode
        self.store.set_setting("start_view", mode)
        self.simple_action.setChecked(mode == "simple")
        self.detailed_action.setChecked(mode == "detailed")
        self.board_page.apply_view_mode()

    def set_status(self, text: str) -> None:
        self.statusBar().showMessage(text, 4000)

    def show_glossary(self, term: str | None) -> None:
        self.glossary.open_term(term)

    def _export(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Export CSV files")
        if not directory:
            return
        paths = export_csvs(self.store, directory)
        self.set_status("Exported " + ", ".join(path.name for path in paths))

    def _backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Back up", "phone-salvage-backup.zip", "Zip (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        backup_store(self.store, path)
        self.set_status("Backup saved.")

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore a backup", "", "Zip (*.zip)")
        if not path:
            return
        answer = QMessageBox.question(
            self,
            "Restore",
            "Replace the catalogue on this computer with that backup?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        root = self._store.root
        self._store.close()
        try:
            restore_store(root, path)
        except Exception as exc:
            QMessageBox.critical(self, "Restore", str(exc))
        self._store = open_session(root, seed=False)
        self.show_phones()
        self.set_status("Catalogue reopened.")

    def closeEvent(self, event) -> None:
        self._store.close()
        super().closeEvent(event)


def run(root=None) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(root)
    window.show()
    return app.exec()
