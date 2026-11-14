"""Map batch window.

It reads each sample's MCA folder itself. It does not open PyMca's file
dialog, which stops responding when that folder holds thousands of files.
"""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xrfdesk.mapbatch import (
    MAP_PROCESSES,
    OK,
    SKIPPED,
    MapProgress,
    MapResult,
    Sample,
    discover_configs,
    discover_samples,
    run_maps,
)


class _MapThread(QThread):
    progress = Signal(object)
    completed = Signal(object)

    def __init__(self, cfg: str, folders: list[str], workers: int, overwrite: bool) -> None:
        super().__init__()
        self.cfg = cfg
        self.folders = folders
        self.workers = workers
        self.overwrite = overwrite
        self.cancel_event = Event()

    def run(self) -> None:
        results = run_maps(
            self.cfg,
            folders=self.folders,
            workers=self.workers,
            overwrite=self.overwrite,
            progress=self.progress.emit,
            cancel=self.cancel_event,
        )
        self.completed.emit(results)

    def request_cancel(self) -> None:
        self.cancel_event.set()


class MapWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Map batch")
        self.resize(980, 640)
        self.root = ""
        self.cfg = ""
        self.samples: list[Sample] = []
        self.results: list[MapResult] = []
        self._thread: _MapThread | None = None

        self.root_label = QLabel("No sample root selected.")
        self.root_label.setWordWrap(True)
        self.config_label = QLabel(self._config_prompt())
        self.config_label.setWordWrap(True)
        self.config_list = QListWidget()
        self.config_list.setSelectionMode(QListWidget.SingleSelection)
        self.config_list.setMaximumHeight(120)
        self.config_list.itemClicked.connect(self._use_listed_configuration)
        self.options_label = QLabel(
            "Fit files off. HDF5, CSV, DAT, and EDF on. TIFF, multipage, the report, "
            "concentrations, diagnostics, and ROI fitting off. ROI width 100 eV. "
            "The process count starts at 10. Results go in the sample folder. MCA and Older cfg used are not changed."
        )
        self.options_label.setWordWrap(True)
        self.status_label = QLabel("Select the folder that contains the sample folders.")
        self.status_label.setWordWrap(True)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Folder", "MCA files", "Output .h5", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeMode.Stretch)
        self.progress = QProgressBar()

        self.workers = QSpinBox()
        self.workers.setRange(1, 64)
        self.workers.setValue(MAP_PROCESSES)

        root_button = QPushButton("Sample root")
        root_button.clicked.connect(self.choose_root)
        config_button = QPushButton("Configuration")
        config_button.clicked.connect(self.choose_configuration)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)

        buttons = QHBoxLayout()
        buttons.addWidget(root_button)
        buttons.addWidget(config_button)
        buttons.addWidget(refresh)
        buttons.addStretch(1)
        buttons.addWidget(QLabel("Processes"))
        buttons.addWidget(self.workers)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)

        layout = QVBoxLayout()
        layout.addWidget(self.root_label)
        layout.addWidget(self.config_label)
        layout.addWidget(self.config_list)
        layout.addWidget(self.options_label)
        layout.addLayout(buttons)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        holder = QWidget()
        holder.setLayout(layout)
        self.setCentralWidget(holder)

    def set_root(self, path: str) -> None:
        self.root = path
        self.cfg = ""
        self.root_label.setText(f"Sample root: {path}")
        self.config_label.setText(self._config_prompt())
        self.refresh()

    def set_configuration(self, path: str) -> None:
        self.cfg = path
        self.config_label.setText(f"Configuration: {path}")
        self._show_configuration(path)

    def choose_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Sample root", self.root)
        if path:
            self.set_root(path)

    def choose_configuration(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Fit configuration",
            self.cfg or self.root,
            "PyMca configuration (*.cfg)",
        )
        if path:
            self.set_configuration(path)

    def refresh(self) -> None:
        if not self.root:
            return
        try:
            self.samples = discover_samples(self.root)
        except OSError as exc:
            QMessageBox.warning(self, "Map batch", str(exc))
            return
        self._fill_configs(keep=self.cfg)
        self._fill()
        pending = sum(not sample.has_results for sample in self.samples)
        self.status_label.setText(f"{pending} folder(s) ready. {len(self.samples) - pending} already have results.")

    def start(self, overwrite: bool | None = None) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if not self.cfg or not Path(self.cfg).is_file():
            QMessageBox.warning(
                self,
                "Map batch",
                "Select a configuration file. More than one may be available, and this run uses only the file you select.",
            )
            return
        if not self.samples:
            QMessageBox.warning(self, "Map batch", "Choose a sample root that contains MCA folders.")
            return
        if overwrite is None:
            overwrite = self._ask_overwrite()
            if overwrite is None:
                return
        self.results = []
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._thread = _MapThread(self.cfg, [sample.path for sample in self.samples], self.workers.value(), overwrite)
        self._thread.progress.connect(self._on_progress)
        self._thread.completed.connect(self._on_completed)
        self._thread.start()

    def cancel(self) -> None:
        if self._thread is not None:
            self._thread.request_cancel()

    def _ask_overwrite(self) -> bool | None:
        finished = [sample for sample in self.samples if sample.has_results]
        if not finished:
            return False
        answer = QMessageBox.question(
            self,
            "Map batch",
            f"{len(finished)} folder(s) already have an .h5 file or an IMAGES folder.\n\n"
            "Overwrite them? No leaves those folders as they are and fits only the folders that have no results.",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Cancel:
            return None
        return answer == QMessageBox.Yes

    def _on_progress(self, update: object) -> None:
        if not isinstance(update, MapProgress):
            return
        if 0 <= update.index < self.table.rowCount():
            self.table.setItem(update.index, 3, QTableWidgetItem(update.message))
        total = max(update.spectra_total, 1)
        self.progress.setRange(0, total)
        self.progress.setValue(min(update.spectra_done, total))
        self.status_label.setText(
            f"{update.index + 1} of {update.total}: {update.folder}  ·  {update.spectra_done} spectra"
        )

    def _on_completed(self, results: object) -> None:
        self.results = list(results)
        self._show_results()
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        problems = [result for result in self.results if result.status not in {OK, SKIPPED}]
        if problems:
            self.status_label.setText(problems[0].detail or problems[0].status)
        else:
            done = sum(result.status == OK for result in self.results)
            self.status_label.setText(f"{done} folder(s) fitted.")

    def _use_listed_configuration(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.cfg = str(path)
            self.config_label.setText(f"Configuration: {self.cfg}")

    def _fill_configs(self, keep: str) -> None:
        self.config_list.clear()
        paths = [str(path) for path in discover_configs(self.root)]
        if keep and keep not in paths and Path(keep).is_file():
            paths.append(keep)
        for path in paths:
            item = QListWidgetItem(Path(path).name)
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.config_list.addItem(item)
        self._show_configuration(keep)

    def _show_configuration(self, path: str) -> None:
        if not path:
            self.config_list.clearSelection()
            return
        if self.config_list.count() == 0 or not any(
            self.config_list.item(row).data(Qt.ItemDataRole.UserRole) == path for row in range(self.config_list.count())
        ):
            if Path(path).is_file():
                item = QListWidgetItem(Path(path).name)
                item.setToolTip(path)
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.config_list.addItem(item)
        for row in range(self.config_list.count()):
            item = self.config_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                self.config_list.setCurrentItem(item)
                return

    def _config_prompt(self) -> str:
        return (
            "No configuration selected. Choose one of the configuration files. "
            "The fit uses only the file you select."
        )

    def _fill(self) -> None:
        self.table.setRowCount(len(self.samples))
        for index, sample in enumerate(self.samples):
            self._set_cells(
                index,
                sample.path,
                sample.mca_count,
                sample.existing_h5 or sample.expected_h5,
                SKIPPED if sample.has_results else "ready",
            )

    def _show_results(self) -> None:
        self.table.setRowCount(len(self.results))
        for index, result in enumerate(self.results):
            status = result.status if not result.detail or result.status == OK else f"{result.status}: {result.detail}"
            self._set_cells(index, result.path, result.mca_count, result.h5_name, status)

    def _set_cells(self, index: int, path: str, count: int, h5_name: str, status: str) -> None:
        name = QTableWidgetItem(Path(path).name)
        name.setToolTip(path)
        self.table.setItem(index, 0, name)
        self.table.setItem(index, 1, QTableWidgetItem(str(count)))
        self.table.setItem(index, 2, QTableWidgetItem(h5_name))
        status_item = QTableWidgetItem(status)
        status_item.setToolTip(status)
        self.table.setItem(index, 3, status_item)
