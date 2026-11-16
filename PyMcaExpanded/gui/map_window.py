"""Map batch window.

Each row is a sample folder from anywhere on the computer. The folder can
be pasted as a path or chosen in a file dialog. Each row keeps its own
configuration, and the same configuration can be applied to every selected
row. The window reads each sample's MCA folder itself. It does not open
PyMca's file dialog on that MCA folder, which stops responding when the
folder holds thousands of files.
"""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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

from PyMcaExpanded import APP_NAME
from PyMcaExpanded.eta import fitting_label, format_remaining, percent_done, remaining_seconds
from PyMcaExpanded.gui.update_bar import UpdateBar
from PyMcaExpanded.mapbatch import (
    MAP_PROCESSES,
    NO_CONFIG,
    OK,
    SKIPPED,
    MapProgress,
    MapResult,
    Sample,
    discover_configs,
    inspect_sample,
    run_maps,
    samples_from_location,
)
from PyMcaExpanded.schedule import machine_limit

COL_FOLDER = 0
COL_CONFIG = 1
COL_COUNT = 2
COL_H5 = 3
COL_STATUS = 4
_HEADERS = ["Folder", "Configuration", "MCA files", "Output .h5", "Status"]
_UNSET = "—"


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
    failed = Signal(str)

    def __init__(self, folders: list[str], configs: list[str], workers: int, overwrite: bool) -> None:
        super().__init__()
        self.folders = folders
        self.configs = configs
        self.workers = workers
        self.overwrite = overwrite
        self.cancel_event = Event()

    def run(self) -> None:
        try:
            results = run_maps(
                folders=self.folders,
                configs=self.configs,
                workers=self.workers,
                overwrite=self.overwrite,
                progress=self.progress.emit,
                cancel=self.cancel_event,
            )
        except Exception as exc:
            self.failed.emit(str(exc).strip() or exc.__class__.__name__)
            return
        self.completed.emit(results)

    def request_cancel(self) -> None:
        self.cancel_event.set()


class MapWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — Map batch")
        self.resize(1120, 700)
        self.root = ""
        self.cfg = ""
        self.samples: list[Sample] = []
        self.assigned: dict[str, str] = {}
        self._extra_configs: list[str] = []
        self.results: list[MapResult] = []
        self._thread: _MapThread | None = None
        self._live: dict[int, MapProgress] = {}
        self._overwrite = False
        self._started = 0.0

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Paste a folder path, or browse to it")
        self.path_edit.setClearButtonEnabled(True)
        self.path_edit.setToolTip(
            "A sample folder contains an MCA folder. "
            "A folder of sample folders adds each of them. "
            "The MCA files stay where they are."
        )
        self.path_edit.returnPressed.connect(self.add_from_path)
        self.config_combo = QComboBox()
        self.config_combo.setMinimumWidth(280)
        self.config_combo.setToolTip("Configuration to apply to the selected folders. Each row keeps the file you apply.")
        self.options_label = QLabel(
            "Select one or more folders, then apply a configuration. "
            "The same file can go on every selected row, and each row can keep a different file. "
            "Folders can stay anywhere on this computer. "
            "Fit processes follow physical cores and leave cores free, so the machine stays usable. "
            "A finished .h5 file is in that sample folder, next to MCA."
        )
        self.options_label.setWordWrap(True)
        self.status_label = QLabel("Add a sample folder. Paste its path, or use Browse.")
        self.status_label.setWordWrap(True)
        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_FOLDER, header.ResizeMode.Stretch)
        self.table.setColumnWidth(COL_CONFIG, 240)
        self.table.setColumnWidth(COL_COUNT, 90)
        self.table.setColumnWidth(COL_H5, 180)
        self.table.setColumnWidth(COL_STATUS, 320)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._on_double_click)
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

        self.browse_button = QPushButton("Browse…")
        self.browse_button.setToolTip("Open a folder browser and add the folder you choose.")
        self.browse_button.clicked.connect(self.browse_location)
        self.add_button = QPushButton("Add")
        self.add_button.setToolTip("Add the folder in the path box.")
        self.add_button.clicked.connect(self.add_from_path)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip("Take the selected rows off this list. The files stay where they are.")
        self.remove_button.clicked.connect(self.remove_selected)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.open_button = QPushButton("Open folder")
        self.open_button.setToolTip("Open the selected sample folder. The finished .h5 file is there, next to MCA.")
        self.open_button.clicked.connect(self.open_selected_folder)
        self.choose_button = QPushButton("Choose file…")
        self.choose_button.setToolTip("Choose a .cfg file from anywhere. It is applied to the selected folders.")
        self.choose_button.clicked.connect(self.choose_configuration)
        self.apply_button = QPushButton("Apply to selected")
        self.apply_button.setToolTip("Write the configuration shown above onto every selected folder.")
        self.apply_button.clicked.connect(self.apply_selected)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        self._lock_while_running = [
            self.path_edit,
            self.config_combo,
            self.workers,
            self.browse_button,
            self.add_button,
            self.remove_button,
            self.refresh_button,
            self.choose_button,
            self.apply_button,
        ]

        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("Folder"))
        add_row.addWidget(self.path_edit, 1)
        add_row.addWidget(self.browse_button)
        add_row.addWidget(self.add_button)
        add_row.addWidget(self.remove_button)
        add_row.addWidget(self.refresh_button)
        add_row.addWidget(self.open_button)

        config_row = QHBoxLayout()
        config_row.addWidget(QLabel("Configuration"))
        config_row.addWidget(self.config_combo, 1)
        config_row.addWidget(self.choose_button)
        config_row.addWidget(self.apply_button)
        config_row.addStretch(1)
        config_row.addWidget(QLabel("Fit processes"))
        config_row.addWidget(self.workers)
        config_row.addWidget(self.start_button)
        config_row.addWidget(self.cancel_button)

        layout = QVBoxLayout()
        layout.addWidget(self.update_bar)
        layout.addWidget(self.options_label)
        layout.addLayout(add_row)
        layout.addLayout(config_row)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        holder = QWidget()
        holder.setLayout(layout)
        self.setCentralWidget(holder)

    def set_root(self, path: str) -> None:
        """Replace the list with the samples found at ``path``."""
        self.root = path
        self.path_edit.setText(path)
        self.samples = []
        self.assigned.clear()
        self.results = []
        self.add_location(path)

    def set_configuration(self, path: str, rows: list[int] | None = None, *, empty_means_all: bool = True) -> None:
        """Assign ``path`` to ``rows``.

        With no rows given, the current selection is used. With no selection
        either, every row is used when ``empty_means_all`` is set.
        """
        file_path = str(Path(path).expanduser())
        if not Path(file_path).is_file():
            QMessageBox.warning(self, "Map batch", f"Configuration not found: {file_path}")
            return
        self._remember_config(file_path)
        if rows is None:
            rows = self._selected_rows()
            if not rows and empty_means_all:
                rows = list(range(len(self.samples)))
        rows = [row for row in rows if 0 <= row < len(self.samples)]
        if not rows:
            self.status_label.setText(
                f"{Path(file_path).name} is ready. Select one or more folders and press Apply to selected."
            )
            return
        for row in rows:
            self.assigned[self.samples[row].path] = file_path
            self._set_config_cell(row)
        self.status_label.setText(_applied_text(file_path, [self.samples[row].path for row in rows]))

    def add_from_path(self) -> None:
        self.add_location(self.path_edit.text())

    def browse_location(self) -> None:
        start = self.path_edit.text().strip() or self.root or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Add a sample folder", start)
        if not path:
            return
        self.path_edit.setText(path)
        self.add_location(path)

    def add_location(self, path: str) -> None:
        """Add the sample folders at ``path`` without moving their files."""
        if self._running():
            return
        text = _clean_path(path)
        if not text:
            QMessageBox.information(self, "Map batch", "Paste a folder path, or use Browse.")
            return
        try:
            found = samples_from_location(text)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Map batch", str(exc))
            return
        if not found:
            QMessageBox.warning(
                self,
                "Map batch",
                f"No sample folder with an MCA directory in {text}.",
            )
            return
        known = {sample.path for sample in self.samples}
        added = 0
        already = 0
        for sample in found:
            if sample.path in known:
                already += 1
                continue
            self.samples.append(sample)
            known.add(sample.path)
            added += 1
        self.root = str(Path(text).expanduser())
        self.path_edit.setText(self.root)
        self._fill_configs()
        self._fill()
        if added == 0:
            self.status_label.setText(f"Already in the list: {Path(found[0].path).name}.")
            return
        message = f"Added {added} folder(s)."
        if already:
            message += f" {already} already in the list."
        message += " Select the folders and apply a configuration. The same file can cover every selected row."
        self.status_label.setText(message)

    def remove_selected(self) -> None:
        if self._running():
            return
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "Map batch", "Select the folders to take off this list.")
            return
        for row in reversed(rows):
            if 0 <= row < len(self.samples):
                sample = self.samples.pop(row)
                self.assigned.pop(sample.path, None)
        self.results = []
        self._fill()
        self.status_label.setText(f"{len(self.samples)} folder(s) in the list.")

    def choose_configuration(self) -> None:
        start = str(self.config_combo.currentData() or self.cfg or self.root or Path.home())
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Fit configuration",
            start,
            "PyMca configuration (*.cfg)",
        )
        if not path:
            return
        if self._selected_rows():
            self.set_configuration(path)
            return
        file_path = str(Path(path).expanduser())
        if not Path(file_path).is_file():
            QMessageBox.warning(self, "Map batch", f"Configuration not found: {file_path}")
            return
        self._remember_config(file_path)
        self.status_label.setText(
            f"{Path(file_path).name} is ready. Select one or more folders and press Apply to selected."
        )

    def apply_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(
                self,
                "Map batch",
                "Select one or more folders, then apply the configuration.",
            )
            return
        path = self.config_combo.currentData()
        if not path:
            QMessageBox.information(self, "Map batch", "Choose a configuration file first.")
            return
        self.set_configuration(str(path), rows)

    def refresh(self) -> None:
        if self._running():
            return
        if not self.samples:
            self.status_label.setText("Add a sample folder. Paste its path, or use Browse.")
            return
        refreshed: list[Sample] = []
        assigned: dict[str, str] = {}
        for sample in self.samples:
            try:
                current = _canonical_sample(inspect_sample(sample.path))
            except OSError as exc:
                QMessageBox.warning(self, "Map batch", str(exc))
                return
            refreshed.append(current)
            chosen = self.assigned.get(sample.path) or self.assigned.get(current.path, "")
            if chosen:
                assigned[current.path] = chosen
        self.samples = refreshed
        self.assigned = assigned
        self._fill_configs()
        self._fill()
        pending = sum(not sample.has_results for sample in self.samples)
        configured = sum(bool(self.assigned.get(sample.path)) for sample in self.samples)
        self.status_label.setText(
            f"{len(self.samples)} folder(s). {configured} have a configuration. "
            f"{pending} still need a fit."
        )

    def start(self, overwrite: bool | None = None) -> None:
        if self._running():
            return
        if not self.samples:
            QMessageBox.warning(self, "Map batch", "Add a sample folder. Paste a path or use Browse.")
            return
        configured = [sample for sample in self.samples if self._config_for(sample)]
        if not configured:
            QMessageBox.warning(
                self,
                "Map batch",
                "Select a configuration file. Select one or more folders and apply it. "
                "The same file can cover every selected folder, and each folder can keep its own file.",
            )
            return
        if overwrite is None:
            overwrite = self._ask_overwrite()
            if overwrite is None:
                return
        pending = [sample for sample in self.samples if self._will_run(sample, overwrite)]
        bare = [sample for sample in self.samples if self._needs_config(sample, overwrite)]
        if not pending:
            QMessageBox.warning(
                self,
                "Map batch",
                "Every folder that has a configuration already has results. "
                "Apply a configuration to a folder that still needs a fit, or overwrite the finished ones.",
            )
            return
        if bare:
            answer = QMessageBox.question(
                self,
                "Map batch",
                f"{len(bare)} folder(s) have no configuration and will be left as they are.\n\n"
                f"Start the {len(pending)} folder(s) that have one?",
                QMessageBox.Yes | QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
        self.results = []
        self._prepare_run(overwrite)
        self._set_busy(True)
        configs = [self._config_for(sample) for sample in self.samples]
        self._thread = _MapThread([sample.path for sample in self.samples], configs, self.workers.value(), overwrite)
        self._thread.progress.connect(self._on_progress)
        self._thread.completed.connect(self._on_completed)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def cancel(self) -> None:
        if self._thread is not None:
            self._thread.request_cancel()

    def _ask_overwrite(self) -> bool | None:
        finished = [sample for sample in self.samples if sample.has_results and self._config_for(sample)]
        if not finished:
            return False
        answer = QMessageBox.question(
            self,
            "Map batch",
            f"{len(finished)} folder(s) already have an .h5 file or an IMAGES folder and have a configuration.\n\n"
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
            self.table.removeCellWidget(index, COL_STATUS)
            if not self._config_for(sample):
                if self._needs_config(sample, overwrite):
                    self._set_status_text(index, NO_CONFIG)
                continue
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
            self.table.removeCellWidget(update.index, COL_STATUS)
            self._set_status_text(update.index, update.message)
        self._show_overall()

    def _show_running(self, index: int, text: str, percent: int) -> None:
        self._set_status_text(index, text)
        widget = self.table.cellWidget(index, COL_STATUS)
        if not isinstance(widget, _RowStatus):
            widget = _RowStatus()
            self.table.setCellWidget(index, COL_STATUS, widget)
            self.table.setRowHeight(index, 32)
        widget.show_fit(percent, text)

    def _show_overall(self) -> None:
        import time

        done = 0
        total = 0
        running = 0
        folders = 0
        for index, sample in enumerate(self.samples):
            if not self._will_run(sample, self._overwrite):
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
        self._set_busy(False)
        problems = [result for result in self.results if result.status not in {OK, SKIPPED, NO_CONFIG}]
        if problems:
            self.status_label.setText(problems[0].detail or problems[0].status)
            return
        done = sum(result.status == OK for result in self.results)
        bare = sum(result.status == NO_CONFIG for result in self.results)
        text = (
            f"{done} folder(s) fitted. Each .h5 file is in that sample folder, next to MCA. "
            "IMAGES in the same folder holds the .cfg, .csv, .dat, and EDF images. "
            "Double-click a row, or use Open folder, to show it."
        )
        if bare:
            text += f" {bare} folder(s) had no configuration and were left as they are."
        self.status_label.setText(text)

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.status_label.setText(message)
        QMessageBox.warning(self, "Map batch", message)

    def _fill_configs(self) -> None:
        current = self.config_combo.currentData() or self.cfg
        paths = self._known_config_paths()
        self.config_combo.blockSignals(True)
        self.config_combo.clear()
        for path in paths:
            label = _config_caption(path, paths)
            self.config_combo.addItem(label, path)
            self.config_combo.setItemData(self.config_combo.count() - 1, path, Qt.ItemDataRole.ToolTipRole)
        if current:
            index = self.config_combo.findData(current)
            if index >= 0:
                self.config_combo.setCurrentIndex(index)
        self.config_combo.blockSignals(False)

    def _known_config_paths(self) -> list[str]:
        seen: set[str] = set()
        paths: list[str] = []

        def add(path: str) -> None:
            if path and path not in seen and Path(path).is_file():
                seen.add(path)
                paths.append(path)

        bases: list[Path] = []
        if self.root:
            bases.append(Path(self.root))
        for sample in self.samples:
            folder = Path(sample.path)
            bases.append(folder)
            bases.append(folder.parent)
        for base in bases:
            for cfg in discover_configs(base):
                add(str(cfg))
        for extra in self._extra_configs:
            add(extra)
        return paths

    def _remember_config(self, path: str) -> None:
        if path not in self._extra_configs:
            self._extra_configs.append(path)
        self.cfg = path
        self._fill_configs()
        index = self.config_combo.findData(path)
        if index >= 0:
            self.config_combo.setCurrentIndex(index)

    def _fill(self) -> None:
        for index in range(self.table.rowCount()):
            self.table.removeCellWidget(index, COL_STATUS)
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
            self.table.removeCellWidget(index, COL_STATUS)
        for index, result in enumerate(self.results):
            if result.status == OK:
                status = "OK · in this folder"
            elif result.detail and result.status != OK:
                status = f"{result.status}: {result.detail}"
            else:
                status = result.status
            self._set_cells(index, result.path, result.mca_count, result.h5_name, status)

    def _set_cells(self, index: int, path: str, count: int, h5_name: str, status: str) -> None:
        name = self._cell(Path(path).name, path)
        self.table.setItem(index, COL_FOLDER, name)
        self.table.setItem(index, COL_COUNT, self._cell(str(count)))
        h5_item = self._cell(h5_name)
        place = _saved_in(path, h5_name) if path else ""
        if place:
            h5_item.setToolTip(place)
        self.table.setItem(index, COL_H5, h5_item)
        self._set_config_cell(index)
        if status == SKIPPED:
            status = "already has results · in this folder"
        self._set_status_text(index, status, place or None)

    def _set_config_cell(self, index: int) -> None:
        if index < 0 or index >= len(self.samples) or index >= self.table.rowCount():
            return
        chosen = self.assigned.get(self.samples[index].path, "")
        if chosen:
            item = self._cell(Path(chosen).name, chosen)
        else:
            item = self._cell(_UNSET, "No configuration yet. Select this row and apply one.")
            item.setForeground(self.palette().placeholderText())
        self.table.setItem(index, COL_CONFIG, item)

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

    def _on_double_click(self, row: int, column: int) -> None:
        if column == COL_CONFIG:
            rows = self._selected_rows()
            if row not in rows:
                rows = [row]
            path = self.config_combo.currentData()
            if path:
                self.set_configuration(str(path), rows)
                return
            self.choose_configuration()
            return
        self.open_folder(row, column)

    def _describe_selection(self) -> None:
        if self._running():
            return
        row = self.table.currentRow()
        folder = self._folder_at(row)
        if row < 0 or not folder:
            return
        h5_item = self.table.item(row, COL_H5)
        h5_name = h5_item.text() if h5_item is not None else ""
        chosen = self.assigned.get(folder, "")
        config_name = Path(chosen).name if chosen else "No configuration assigned."
        count = len(self._selected_rows())
        selected = f"{count} selected. " if count > 1 else ""
        self.status_label.setText(f"{selected}{config_name}. {_saved_in(folder, h5_name)}")

    def _folder_at(self, row: int) -> str:
        if 0 <= row < len(self.results):
            return self.results[row].path
        if 0 <= row < len(self.samples):
            return self.samples[row].path
        return ""

    def _selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectionModel().selectedRows()})

    def _config_for(self, sample: Sample) -> str:
        return self.assigned.get(sample.path, "")

    def _will_run(self, sample: Sample, overwrite: bool) -> bool:
        return bool(self._config_for(sample)) and (overwrite or not sample.has_results)

    def _needs_config(self, sample: Sample, overwrite: bool) -> bool:
        return not self._config_for(sample) and (overwrite or not sample.has_results)

    def _set_status_text(self, index: int, status: str, tip: str | None = None) -> None:
        if index < 0 or index >= self.table.rowCount():
            return
        status_item = self._cell(status, tip or status)
        self.table.setItem(index, COL_STATUS, status_item)

    def _cell(self, text: str, tip: str = "") -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        if tip:
            item.setToolTip(tip)
        return item

    def _running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def _set_busy(self, busy: bool) -> None:
        for widget in self._lock_while_running:
            widget.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)


def _canonical_sample(sample: Sample) -> Sample:
    try:
        canonical = str(Path(sample.path).resolve())
    except OSError:
        return sample
    if canonical == sample.path:
        return sample
    return Sample(
        path=canonical,
        has_results=sample.has_results,
        mca_count=sample.mca_count,
        existing_h5=sample.existing_h5,
        expected_h5=sample.expected_h5,
    )


def _clean_path(text: str) -> str:
    return text.strip().strip('"').strip("'")


def _config_caption(path: str, paths: list[str]) -> str:
    name = Path(path).name
    if sum(Path(other).name == name for other in paths) > 1:
        return f"{name} — {Path(path).parent.name}"
    return name


def _applied_text(path: str, folders: list[str]) -> str:
    names = [Path(folder).name for folder in folders[:3]]
    shown = ", ".join(names)
    if len(folders) > 3:
        shown += f", and {len(folders) - 3} more"
    return f"Applied {Path(path).name} to {len(folders)} folder(s): {shown}."


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
