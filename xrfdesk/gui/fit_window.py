"""Fit one spectrum at a time, using PyMca's own advanced-fit widget."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from xrfdesk.curves import (
    Curve,
    Standard,
    attach_curves,
    build_curves,
    curves_from_config,
    pymca_config,
    read_config,
    write_config,
)
from xrfdesk.engine import FitOutcome, fit_spectrum
from xrfdesk.spectra import Spectrum, load_spectrum


class FitWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Fit")
        self.resize(1280, 800)
        self.spectrum: Spectrum | None = None
        self.curves: list[Curve] = []
        self.standards: list[Standard] = []
        self._config_name = "Untitled"
        self._batch_window = None
        self._map_window = None
        self._known: dict[str, QLineEdit] = {}

        from PyMca5.PyMcaGui.physics.xrf.McaAdvancedFit import McaAdvancedFit

        self.widget = McaAdvancedFit()
        self.widget.dismissButton.hide()

        self.file_label = QLabel("No spectrum loaded.")
        self.file_label.setWordWrap(True)
        self.curve_label = QLabel("No concentration curves yet.")
        self.curve_label.setWordWrap(True)
        self.result_label = QLabel("Use Configure and Fit Again on the PyMca panel, then record this spectrum.")
        self.result_label.setWordWrap(True)
        self.standard_list = QListWidget()

        self.known_box = QGroupBox("Known concentrations")
        self.known_form = QFormLayout(self.known_box)

        record = QPushButton("Record as standard")
        record.clicked.connect(self.record_standard)
        remove = QPushButton("Remove standard")
        remove.clicked.connect(self.remove_standard)
        fit_button = QPushButton("Fit this spectrum")
        fit_button.clicked.connect(self.fit_current)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(self.file_label)
        side_layout.addWidget(fit_button)
        side_layout.addWidget(self.result_label)
        side_layout.addWidget(self.known_box)
        side_layout.addWidget(record)
        side_layout.addWidget(self.standard_list)
        side_layout.addWidget(remove)
        side_layout.addWidget(self.curve_label)
        side_layout.addStretch(1)

        splitter = QSplitter()
        splitter.addWidget(self.widget)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        toolbar = self.addToolBar("Fit")
        toolbar.addAction("Open spectrum", self.choose_spectrum)
        toolbar.addAction("Load configuration", self.choose_configuration)
        toolbar.addAction("Save configuration", self.choose_save)
        toolbar.addAction("Open Batch", self.open_batch)
        toolbar.addAction("Open map batch", self.open_map)

        self._refresh_known_fields()

    def choose_spectrum(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Open spectrum",
            "",
            "Spectra (*.mca *.spe *.csv *.txt);;All files (*)",
        )
        if path:
            self.open_spectrum(path)

    def open_spectrum(self, path: str) -> Spectrum:
        spectrum = load_spectrum(path)
        self.spectrum = spectrum
        calibration = None
        if spectrum.zero is not None and spectrum.gain is not None:
            calibration = [spectrum.zero, spectrum.gain, 0.0]
        self.widget.setData(
            x=spectrum.channels,
            y=spectrum.counts,
            legend=spectrum.name,
            calibration=calibration,
            xlabel="Channel",
        )
        self.file_label.setText(f"{spectrum.name}  ·  {spectrum.counts.size} channels")
        return spectrum

    def choose_configuration(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(self, "Load configuration", "", "PyMca configuration (*.cfg)")
        if path:
            self.load_configuration(path)

    def load_configuration(self, path: str) -> None:
        config = read_config(path)
        self.curves = curves_from_config(config)
        self.widget.configure(pymca_config(config))
        self._config_name = path
        self._refresh_known_fields()
        self._show_curves()

    def choose_save(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(self, "Save configuration", "fit.cfg", "PyMca configuration (*.cfg)")
        if path:
            self.save_configuration(path)

    def save_configuration(self, path: str) -> None:
        write_config(path, self.current_config())
        self._config_name = path

    def current_config(self) -> dict:
        return attach_curves(self.widget.configure(), self.curves)

    def fit_current(self) -> FitOutcome:
        if self.spectrum is None:
            raise RuntimeError("Open a spectrum first.")
        outcome = fit_spectrum(self.spectrum, self.widget.configure(), self.curves)
        lines = [f"chi-square {outcome.chisq:.4f}"]
        for group, area in outcome.areas.items():
            lines.append(f"{group}  area {area:.2f}")
        for element, value in outcome.concentrations.items():
            lines.append(f"{element}  {value:.2f}")
        self.result_label.setText("\n".join(lines))
        return outcome

    def record_standard(self) -> None:
        try:
            outcome = self.fit_current()
        except RuntimeError as exc:
            QMessageBox.warning(self, "Fit", str(exc))
            return
        known = {}
        for element, field in self._known.items():
            text = field.text().strip()
            if not text:
                continue
            try:
                known[element] = float(text)
            except ValueError:
                QMessageBox.warning(self, "Fit", f"{element} is not a number.")
                return
        if not known:
            QMessageBox.warning(self, "Fit", "Enter a known concentration for at least one element.")
            return
        name = self.spectrum.name if self.spectrum else "standard"
        self.standards = [item for item in self.standards if item.name != name]
        self.standards.append(Standard(name=name, areas=dict(outcome.areas), known=known))
        self.curves = build_curves(self.standards)
        self._show_standards()
        self._show_curves()

    def remove_standard(self) -> None:
        row = self.standard_list.currentRow()
        if row < 0:
            return
        del self.standards[row]
        self.curves = build_curves(self.standards)
        self._show_standards()
        self._show_curves()

    def open_batch(self) -> None:
        from xrfdesk.gui.batch_window import BatchWindow

        if self._batch_window is None:
            self._batch_window = BatchWindow()
        self._batch_window.set_config(self.current_config(), self._config_name)
        self._batch_window.show()
        self._batch_window.raise_()
        self._batch_window.activateWindow()

    def open_map(self) -> None:
        from pathlib import Path

        from xrfdesk.gui.map_window import MapWindow

        if self._map_window is None:
            self._map_window = MapWindow()
        if Path(self._config_name).is_file():
            self._map_window.set_configuration(self._config_name)
        self._map_window.show()
        self._map_window.raise_()
        self._map_window.activateWindow()

    def _refresh_known_fields(self) -> None:
        while self.known_form.rowCount():
            self.known_form.removeRow(0)
        self._known = {}
        peaks = self.widget.configure().get("peaks") or {}
        elements = list(peaks.keys())
        for curve in self.curves:
            if curve.element not in elements:
                elements.append(curve.element)
        for element in elements:
            field = QLineEdit()
            self._known[element] = field
            self.known_form.addRow(element, field)
        if not elements:
            self.known_form.addRow(QLabel("Configure peaks in the PyMca dialog, then record a standard."))

    def _show_standards(self) -> None:
        self.standard_list.clear()
        for standard in self.standards:
            known = ", ".join(f"{element} {value:g}" for element, value in standard.known.items())
            self.standard_list.addItem(f"{standard.name}: {known}")

    def _show_curves(self) -> None:
        if not self.curves:
            self.curve_label.setText("No concentration curves yet. Record at least one standard.")
            return
        lines = []
        for curve in self.curves:
            r2 = "one point, intercept 0" if curve.r2 is None else f"R² {curve.r2:.4f}"
            lines.append(f"{curve.element} = {curve.intercept:.4g} + {curve.slope:.4g} × {curve.group} area ({r2})")
        self.curve_label.setText("\n".join(lines))
