"""Map batch window.

It reads each sample's MCA folder itself. It does not open PyMca's file
dialog, which stops responding when that folder holds thousands of files.
"""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
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

from xrfdesk.eta import fitting_label, format_remaining, percent_done, remaining_seconds
from xrfdesk.gui.update_bar import UpdateBar
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
from xrfdesk.schedule import machine_limit


class _RowStatus(QWidget):
    """Percent bar and remaining time for one sample folder."""

    def __init__(self) -> None:
        super().__init__()
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setMaximumHeight(14)
        self.label = QLabel()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 1, 6, 1)
        layout.setSpacing(8)
        layout.addWidget(self.bar, 1)
        layout.addWidget(self.label, 2)

    def show_fit(self, percent: int, text: str) -> None:
        self.bar.setValue(percent)
        self.label.setText(text)


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
        self._live: dict[int, MapProgress] = {}
        self._overwrite = False
        self._started = 0.0

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
            "Sample folders fit at the same time and share the process count. "
            "The count follows physical cores, so a 12-core, 24-thread processor "
            "defaults to 10 fit processes and leaves two cores free. "
            "Fit processes run at low priority and stay off those free cores, so Excel and a browser stay usable. "
            "Each row shows that folder's percent and the time left. "
            "A folder of 12,000 to 15,000 spectra matches a one-process fit. "
            "Results go in the sample folder. MCA and Older cfg used are not changed."
        )
        self.options_label.setWordWrap(True)
        self.status_label = QLabel("Select the folder that contains the sample folders.")
        self.status_label.setWordWrap(True)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Folder", "MCA files", "Output .h5", "Status"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.setColumnWidth(3, 320)
        self.table.cellDoubleClicked.connect(self.open_folder)
        self.table.itemSelectionChanged.connect(self._describe_selection)
        self.progress = QProgressBar()
        self.progress.setFormat("%p%")
        self.progress.setTextVisible(True)
        self.update_bar = UpdateBar()

        self.workers = QSpinBox()
        self.workers.setRange(1, machine_limit())
        self.workers.setValue(min(MAP_PROCESSES, machine_limit()))
        self.workers.setToolTip(
            "Fit processes shared by the sample folders in this list. "
            "The maximum is one process per physical core, not per hyper-thread. "
            "The default leaves one or two cores free, and the fit stays off those cores. "
            "Every folder that fits in this count runs at the same time. "
            "Fit processes run at low priority."
        )

        root_button = QPushButton("Sample root")
        root_button.clicked.connect(self.choose_root)
        config_button = QPushButton("Configuration")
        config_button.clicked.connect(self.choose_configuration)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        open_folder = QPushButton("Open folder")
        open_folder.setToolTip("Open the selected sample folder. The finished .h5 file is there, next to MCA. IMAGES is in that same folder.")
        open_folder.clicked.connect(self.open_selected_folder)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)

        buttons = QHBoxLayout()
        buttons.addWidget(root_button)
        buttons.addWidget(config_button)
        buttons.addWidget(refresh)
        buttons.addWidget(open_folder)
        buttons.addStretch(1)
        buttons.addWidget(QLabel("Fit processes"))
        buttons.addWidget(self.workers)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)

        layout = QVBoxLayout()
        layout.addWidget(self.update_bar)
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
        text = f"{pending} folder(s) ready. {len(self.samples) - pending} already have results."
        if pending >= 2:
            text += " Ready folders fit at the same time and share the process count."
        self.status_label.setText(text)

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
        self._prepare_run(overwrite)
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

    def _prepare_run(self, overwrite: bool) -> None:
        """Clear the shared bar and mark every folder that this run will fit."""
        import time

        self._overwrite = overwrite
        self._live = {}
        self._started = time.monotonic()
        total = 0
        folders = 0
        for index, sample in enumerate(self.samples):
            self.table.removeCellWidget(index, 3)
            if sample.has_results and not overwrite:
                continue
            total += sample.mca_count
            folders += 1
            self._set_status_text(index, "waiting")
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(0)
        self.status_label.setText(f"0 of {folders} running · 0 of {total} spectra · 0% · estimating")

    def _on_progress(self, update: object) -> None:
        if not isinstance(update, MapProgress):
            return
        self._live[update.index] = update
        if update.message == "fitting":
            text = fitting_label(update.spectra_done, update.spectra_total, update.eta_seconds)
            self._show_running(update.index, text, percent_done(update.spectra_done, update.spectra_total))
        else:
            self.table.removeCellWidget(update.index, 3)
            self._set_status_text(update.index, update.message)
        self._show_overall()

    def _show_running(self, index: int, text: str, percent: int) -> None:
        self._set_status_text(index, text)
        widget = self.table.cellWidget(index, 3)
        if not isinstance(widget, _RowStatus):
            widget = _RowStatus()
            self.table.setCellWidget(index, 3, widget)
            self.table.setRowHeight(index, 32)
        widget.show_fit(percent, text)

    def _show_overall(self) -> None:
        import time

        done = 0
        total = 0
        running = 0
        folders = 0
        for index, sample in enumerate(self.samples):
            if sample.has_results and not self._overwrite:
                continue
            folders += 1
            total += sample.mca_count
            update = self._live.get(index)
            if update is None:
                continue
            done += min(max(update.spectra_done, 0), sample.mca_count)
            if update.message == "fitting":
                running += 1
        done = min(done, total)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        eta = remaining_seconds(done, total, time.monotonic() - self._started)
        remaining = "estimating" if eta is None else f"{format_remaining(eta)} left"
        self.status_label.setText(
            f"{running} of {folders} running · {done} of {total} spectra · "
            f"{percent_done(done, total)}% · {remaining}"
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
            self.status_label.setText(
                f"{done} folder(s) fitted. Each .h5 file is in that sample folder, next to MCA. "
                "IMAGES in the same folder holds the .cfg, .csv, .dat, and EDF images. "
                "Double-click a row, or use Open folder, to show it."
            )

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
        for index in range(self.table.rowCount()):
            self.table.removeCellWidget(index, 3)
        for index, result in enumerate(self.results):
            if result.status == OK:
                status = "OK · in this folder"
            elif result.detail and result.status != OK:
                status = f"{result.status}: {result.detail}"
            else:
                status = result.status
            self._set_cells(index, result.path, result.mca_count, result.h5_name, status)

    def _set_cells(self, index: int, path: str, count: int, h5_name: str, status: str) -> None:
        name = QTableWidgetItem(Path(path).name)
        name.setToolTip(path)
        self.table.setItem(index, 0, name)
        self.table.setItem(index, 1, QTableWidgetItem(str(count)))
        h5_item = QTableWidgetItem(h5_name)
        place = _saved_in(path, h5_name) if path else ""
        if place:
            h5_item.setToolTip(place)
        self.table.setItem(index, 2, h5_item)
        if status == SKIPPED:
            status = "already has results · in this folder"
        self._set_status_text(index, status, place or None)

    def open_selected_folder(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Map batch", "Select a sample folder first.")
            return
        self.open_folder(row)

    def open_folder(self, row: int, _column: int = 0) -> None:
        """Open the sample folder that holds the finished .h5 file and IMAGES."""
        folder = self._folder_at(row)
        if not folder or not Path(folder).is_dir():
            QMessageBox.information(self, "Map batch", "That sample folder is not available.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _describe_selection(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        row = self.table.currentRow()
        folder = self._folder_at(row)
        if row < 0 or not folder:
            return
        h5_item = self.table.item(row, 2)
        h5_name = h5_item.text() if h5_item is not None else ""
        self.status_label.setText(_saved_in(folder, h5_name))

    def _folder_at(self, row: int) -> str:
        if 0 <= row < len(self.results):
            return self.results[row].path
        if 0 <= row < len(self.samples):
            return self.samples[row].path
        return ""

    def _set_status_text(self, index: int, status: str, tip: str | None = None) -> None:
        if index < 0 or index >= self.table.rowCount():
            return
        status_item = QTableWidgetItem(status)
        status_item.setToolTip(tip or status)
        self.table.setItem(index, 3, status_item)


def _saved_in(folder: str, h5_name: str) -> str:
    """Where a finished map batch is written."""
    directory = Path(folder)
    h5_path = directory / h5_name if h5_name else directory
    name = h5_name or "The .h5 file"
    return (
        f"{name} is in {directory}, next to the MCA folder. "
        f"The file is {h5_path}. "
        f"IMAGES in {directory} holds the .cfg, .csv, .dat, and EDF images."
    )
