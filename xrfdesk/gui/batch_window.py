"""Batch window. Its file list is not the Fit window's spectrum."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
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

from xrfdesk.batch import (
    CANCELLED,
    DONE,
    FAILED,
    RUNNING,
    WAITING,
    ScanResult,
    default_workers,
    run_batch,
    write_csv,
)
from xrfdesk.curves import curves_from_config, read_config
from xrfdesk.schedule import machine_limit
from xrfdesk.demo import bronze_files
from xrfdesk.excel_fill import fill_workbook
from xrfdesk.spectra import list_labels


class _BatchThread(QThread):
    update = Signal(int, str, object)
    completed = Signal(object)

    def __init__(self, paths: list[str], config: dict, workers: int) -> None:
        super().__init__()
        self.paths = paths
        self.config = config
        self.workers = workers
        self.cancel_event = Event()

    def run(self) -> None:
        results = run_batch(
            self.paths,
            self.config,
            workers=self.workers,
            progress=lambda index, status, payload: self.update.emit(index, status, payload),
            cancel=self.cancel_event,
        )
        self.completed.emit(results)

    def request_cancel(self) -> None:
        self.cancel_event.set()


class BatchWindow(QMainWindow):
    def __init__(self, config: dict | None = None, config_name: str = "") -> None:
        super().__init__()
        self.setWindowTitle("Batch")
        self.resize(980, 720)
        self.paths: list[str] = []
        self.config: dict | None = None
        self.config_name = ""
        self.results: list[ScanResult] = []
        self._labels: list[str] = []
        self._thread: _BatchThread | None = None

        self.config_label = QLabel("No configuration loaded.")
        self.config_label.setWordWrap(True)
        self.file_table = QTableWidget(0, 3)
        self.file_table.setHorizontalHeaderLabels(["File", "Status", "Detail"])
        self.file_table.horizontalHeader().setStretchLastSection(False)
        self.file_table.horizontalHeader().setSectionResizeMode(0, self.file_table.horizontalHeader().ResizeMode.Stretch)
        self.progress = QProgressBar()
        self.workers = QSpinBox()
        self.workers.setRange(1, machine_limit())
        self.workers.setValue(min(default_workers(), machine_limit()))
        self.workers.setToolTip(
            "Fit processes for this list. The maximum is one process per physical core. "
            "The default leaves one or two cores free, and the fit stays off those cores. "
            "A batch waits if other fits are already using those processes. "
            "Fit processes run at low priority."
        )

        add = QPushButton("Add files")
        add.clicked.connect(self.add_files_dialog)
        remove = QPushButton("Remove")
        remove.clicked.connect(self.remove_selected)
        up = QPushButton("Up")
        up.clicked.connect(lambda: self.move_selected(-1))
        down = QPushButton("Down")
        down.clicked.connect(lambda: self.move_selected(1))
        load = QPushButton("Load configuration")
        load.clicked.connect(self.choose_configuration)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        bronze = QPushButton("Bronze example")
        bronze.clicked.connect(self.load_bronze)
        csv_button = QPushButton("Export CSV")
        csv_button.clicked.connect(self.export_csv)
        excel_button = QPushButton("Fill Excel template")
        excel_button.clicked.connect(self.export_excel)

        file_buttons = QHBoxLayout()
        for button in (add, remove, up, down):
            file_buttons.addWidget(button)
        file_buttons.addStretch(1)

        run_row = QHBoxLayout()
        run_row.addWidget(QLabel("Fit processes"))
        run_row.addWidget(self.workers)
        run_row.addWidget(self.start_button)
        run_row.addWidget(self.cancel_button)
        run_row.addStretch(1)
        run_row.addWidget(load)
        run_row.addWidget(bronze)

        export_row = QHBoxLayout()
        export_row.addWidget(csv_button)
        export_row.addWidget(excel_button)
        export_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addWidget(self.config_label)
        layout.addLayout(file_buttons)
        layout.addWidget(self.file_table, 1)
        layout.addWidget(self.progress)
        layout.addLayout(run_row)
        layout.addLayout(export_row)
        holder = QWidget()
        holder.setLayout(layout)
        self.setCentralWidget(holder)

        if config is not None:
            self.set_config(config, config_name)

    def set_config(self, config: dict, name: str = "") -> None:
        self.config = config
        self.config_name = name or "configuration"
        curves = curves_from_config(config)
        if curves:
            summary = ", ".join(curve.element for curve in curves)
            extra = f" Curves: {summary}."
        else:
            extra = " No concentration curves; the table will show areas only."
        self.config_label.setText(f"Configuration: {self.config_name}.{extra}")
        self._apply_headers()
        self._fill_rows()

    def load_configuration(self, path: str) -> None:
        self.set_config(read_config(path), path)

    def choose_configuration(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(self, "Load configuration", "", "PyMca configuration (*.cfg)")
        if path:
            self.load_configuration(path)

    def add_files(self, paths: list[str]) -> None:
        for path in paths:
            self.paths.append(path)
        self._fill_rows()

    def add_files_dialog(self) -> None:
        paths, _selected = QFileDialog.getOpenFileNames(
            self,
            "Add scans",
            "",
            "Spectra (*.mca *.spe *.csv *.txt);;All files (*)",
        )
        if paths:
            self.add_files(paths)

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.file_table.selectedIndexes()}, reverse=True)
        if not rows and self.file_table.currentRow() >= 0:
            rows = [self.file_table.currentRow()]
        for row in rows:
            if 0 <= row < len(self.paths):
                del self.paths[row]
        self._fill_rows()

    def move_selected(self, direction: int) -> None:
        row = self.file_table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= len(self.paths):
            return
        self.paths[row], self.paths[target] = self.paths[target], self.paths[row]
        self._fill_rows()
        self.file_table.setCurrentCell(target, 0)

    def load_bronze(self) -> None:
        config_path, scans, _template = bronze_files()
        self.load_configuration(str(config_path))
        self.paths = [str(path) for path in scans]
        self.results = []
        self._fill_rows()
        self.progress.setValue(0)

    def start(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if self.config is None:
            QMessageBox.warning(self, "Batch", "Load a configuration first.")
            return
        if not self.paths:
            QMessageBox.warning(self, "Batch", "Add at least one scan.")
            return
        self.results = []
        self.progress.setRange(0, len(self.paths))
        self.progress.setValue(0)
        self._fill_rows()
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._thread = _BatchThread(list(self.paths), self.config, self.workers.value())
        self._thread.update.connect(self._on_update)
        self._thread.completed.connect(self._on_completed)
        self._thread.start()

    def cancel(self) -> None:
        if self._thread is not None:
            self._thread.request_cancel()

    def export_csv(self) -> None:
        if not self.results:
            QMessageBox.warning(self, "Batch", "Run the batch before exporting.")
            return
        path, _selected = QFileDialog.getSaveFileName(self, "Export CSV", "results.csv", "CSV (*.csv)")
        if path:
            self.write_results_csv(path)

    def write_results_csv(self, path: str) -> None:
        elements, groups = self._columns()
        write_csv(path, self.results, elements, groups)

    def export_excel(self) -> None:
        if not self.results:
            QMessageBox.warning(self, "Batch", "Run the batch before filling a workbook.")
            return
        _config, _scans, template = bronze_files()
        template_path, _selected = QFileDialog.getOpenFileName(
            self,
            "Excel template",
            str(template) if template.exists() else "",
            "Excel (*.xlsx *.xlsm)",
        )
        if not template_path:
            return
        destination, _selected = QFileDialog.getSaveFileName(
            self,
            "Filled workbook",
            "filled.xlsx",
            "Excel (*.xlsx)",
        )
        if not destination:
            return
        elements, _groups = self._columns()
        fill_workbook(template_path, destination, self.results, elements)

    def _on_update(self, index: int, status: str, payload: object) -> None:
        detail = ""
        if isinstance(payload, ScanResult):
            if payload.status == DONE and payload.chisq is not None:
                detail = f"chi-square {payload.chisq:.3f}"
            elif payload.error:
                detail = payload.error
        self._set_row(index, status, detail)
        done = sum(
            self.file_table.item(row, 1).text() in {DONE, FAILED, CANCELLED}
            for row in range(self.file_table.rowCount())
            if self.file_table.item(row, 1) is not None
        )
        self.progress.setValue(done)

    def _on_completed(self, results: object) -> None:
        self.results = list(results)
        for index, result in enumerate(self.results):
            detail = ""
            if result.status == DONE and result.chisq is not None:
                bits = [f"χ² {result.chisq:.3f}"]
                bits.extend(f"{element} {value:.2f}" for element, value in result.concentrations.items())
                detail = ", ".join(bits)
            elif result.error:
                detail = result.error
            self._set_row(index, result.status, detail)
            self._set_concentrations(index, result)
        self.progress.setValue(len(self.results))
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        failed = sum(1 for result in self.results if result.status == FAILED)
        if failed:
            QMessageBox.warning(self, "Batch", f"{failed} file(s) failed. The others were still fitted.")

    def _columns(self) -> tuple[list[str], list[str]]:
        curves = curves_from_config(self.config or {})
        return [curve.element for curve in curves], [curve.group for curve in curves]

    def _apply_headers(self) -> None:
        elements, _groups = self._columns()
        self.file_table.setColumnCount(3 + len(elements))
        self.file_table.setHorizontalHeaderLabels(["File", "Status", "Detail", *elements])
        self.file_table.setColumnWidth(0, 180)
        self.file_table.setColumnWidth(1, 80)
        self.file_table.setColumnWidth(2, 240)

    def _fill_rows(self) -> None:
        self._labels = list_labels(self.paths)
        self._apply_headers()
        self.file_table.setRowCount(len(self.paths))
        for index in range(len(self.paths)):
            self._set_row(index, WAITING, "")
            self._clear_concentrations(index)

    def _set_concentrations(self, index: int, result: ScanResult) -> None:
        elements, _groups = self._columns()
        for offset, element in enumerate(elements):
            value = result.concentrations.get(element) if result.status == DONE else None
            text = "" if value is None else f"{value:.4f}"
            self.file_table.setItem(index, 3 + offset, QTableWidgetItem(text))

    def _clear_concentrations(self, index: int) -> None:
        elements, _groups = self._columns()
        for offset in range(len(elements)):
            self.file_table.setItem(index, 3 + offset, QTableWidgetItem(""))

    def _set_row(self, index: int, status: str, detail: str) -> None:
        if index >= self.file_table.rowCount():
            return
        name = self._labels[index] if index < len(self._labels) else ""
        name_item = QTableWidgetItem(name)
        if index < len(self.paths):
            name_item.setToolTip(self.paths[index])
        self.file_table.setItem(index, 0, name_item)
        self.file_table.setItem(index, 1, QTableWidgetItem(status))
        if status in {WAITING, RUNNING}:
            detail_item = QTableWidgetItem("")
        else:
            detail_item = QTableWidgetItem(detail)
            detail_item.setToolTip(detail)
        self.file_table.setItem(index, 2, detail_item)
