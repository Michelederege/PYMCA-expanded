"""Part and zone details, in the order a beginner needs them."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from phone_salvage.catalog import (
    CANT_REASONS,
    IDENTIFICATION,
    PRACTICAL,
    REMOVAL,
    SHIELD_STATES,
    STATUSES,
)
from phone_salvage.present import identification_line, removal_summary, reuse_verdict, tool_for


class NotesEdit(QPlainTextEdit):
    editingFinished = Signal()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.editingFinished.emit()


class InfoPanel(QScrollArea):
    partChanged = Signal(int)
    partDeleted = Signal()
    zoneChanged = Signal(int)
    zoneDeleted = Signal()

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.part_id: int | None = None
        self.zone_id: int | None = None
        self._loading = False
        self.setWidgetResizable(True)
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)

        root = QWidget()
        self.setWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 16)
        layout.setSpacing(10)

        self.empty = QLabel("Click a part, or draw a box around one.")
        self.empty.setObjectName("quiet")
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)

        self.part_body = QWidget()
        part_layout = QVBoxLayout(self.part_body)
        part_layout.setContentsMargins(0, 0, 0, 0)
        part_layout.setSpacing(10)

        self.heading = QLabel("Part")
        self.heading.setObjectName("title")
        self.heading.setWordWrap(True)
        part_layout.addWidget(self.heading)

        what = QGroupBox("What it is")
        what_form = QFormLayout(what)
        self.type_combo = QComboBox()
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)
        self.what_link = QPushButton("What is this?")
        self.what_link.setFlat(True)
        what_form.addRow("Name", self.type_combo)
        what_form.addRow(self.explanation)
        what_form.addRow(self.what_link)
        part_layout.addWidget(what)

        does = QGroupBox("What it does in this phone")
        does_layout = QVBoxLayout(does)
        self.does_default = QLabel()
        self.does_default.setWordWrap(True)
        self.does_default.setObjectName("quiet")
        self.function_notes = NotesEdit()
        self.function_notes.setPlaceholderText("Add a note about this one, if you know more.")
        self.function_notes.setFixedHeight(72)
        does_layout.addWidget(self.does_default)
        does_layout.addWidget(self.function_notes)
        part_layout.addWidget(does)

        reuse = QGroupBox("Can I reuse it?")
        reuse_form = QFormLayout(reuse)
        self.status_combo = QComboBox()
        self.practical_combo = QComboBox()
        self.condition = NotesEdit()
        self.condition.setPlaceholderText("Damage or wear you can see.")
        self.condition.setFixedHeight(64)
        self.verdict = QLabel()
        self.verdict.setObjectName("verdict")
        self.verdict.setWordWrap(True)
        reuse_form.addRow("Status", self.status_combo)
        reuse_form.addRow("Reuse", self.practical_combo)
        reuse_form.addRow("Condition", self.condition)
        reuse_form.addRow(self.verdict)
        part_layout.addWidget(reuse)

        removal = QGroupBox("How hard is it to remove?")
        removal_form = QFormLayout(removal)
        self.removal_combo = QComboBox()
        self.tool = QLineEdit()
        self.removed = QCheckBox("Removed from the board")
        self.bin_combo = QComboBox()
        self.removal_tip = QLabel()
        self.removal_tip.setWordWrap(True)
        self.removal_tip.setObjectName("quiet")
        removal_form.addRow("Removal", self.removal_combo)
        removal_form.addRow("Tool", self.tool)
        removal_form.addRow(self.removed)
        removal_form.addRow("Bin", self.bin_combo)
        removal_form.addRow(self.removal_tip)
        part_layout.addWidget(removal)

        test = QGroupBox("How to test it")
        test_layout = QVBoxLayout(test)
        self.test_hint = QLabel()
        self.test_hint.setWordWrap(True)
        self.test_later = QLabel("Saving a meter reading comes in a later version. The decision above is still yours.")
        self.test_later.setObjectName("quiet")
        self.test_later.setWordWrap(True)
        test_layout.addWidget(self.test_hint)
        test_layout.addWidget(self.test_later)
        part_layout.addWidget(test)

        self.tech_button = QPushButton("Technical details")
        self.tech_button.setCheckable(True)
        part_layout.addWidget(self.tech_button)
        self.technical = QGroupBox("Technical details")
        tech_form = QFormLayout(self.technical)
        self.designator = QLineEdit()
        self.marking = QLineEdit()
        self.part_number = QLineEdit()
        self.manufacturer = QLineEdit()
        self.value_text = QLineEdit()
        self.identification = QComboBox()
        self.reason = QComboBox()
        self.reason.setEditable(True)
        self.shield = QComboBox()
        self.show_simple = QCheckBox("Show this part in Simple view")
        self.library_hint = QLabel()
        self.library_hint.setWordWrap(True)
        self.use_library = QPushButton("Use the library details")
        self.designator_link = QPushButton("What is a designator?")
        self.designator_link.setFlat(True)
        self.marking_link = QPushButton("What is a marking code?")
        self.marking_link.setFlat(True)
        tech_form.addRow(self.designator_link)
        tech_form.addRow("Designator", self.designator)
        tech_form.addRow(self.marking_link)
        tech_form.addRow("Marking", self.marking)
        tech_form.addRow("Part number", self.part_number)
        tech_form.addRow("Maker", self.manufacturer)
        tech_form.addRow("Value", self.value_text)
        tech_form.addRow("Identified", self.identification)
        tech_form.addRow("Reason", self.reason)
        tech_form.addRow("Shield", self.shield)
        tech_form.addRow(self.show_simple)
        tech_form.addRow(self.library_hint)
        tech_form.addRow(self.use_library)
        part_layout.addWidget(self.technical)

        self.confirm = QPushButton("Confirm this part")
        self.confirm.setObjectName("primary")
        self.delete_part = QPushButton("Delete this part")
        self.delete_part.setObjectName("danger")
        part_layout.addWidget(self.confirm)
        part_layout.addWidget(self.delete_part)
        part_layout.addStretch(1)
        layout.addWidget(self.part_body)

        self.zone_body = QWidget()
        zone_layout = QVBoxLayout(self.zone_body)
        zone_layout.setContentsMargins(0, 0, 0, 0)
        self.zone_title = QLabel("Zone")
        self.zone_title.setObjectName("title")
        self.zone_help = QLabel("A zone is a named area, such as Camera or Charging. It keeps the map readable when you zoom out.")
        self.zone_help.setWordWrap(True)
        self.zone_help.setObjectName("quiet")
        self.zone_name = QLineEdit()
        self.zone_state = QLabel()
        self.zone_state.setWordWrap(True)
        self.zone_confirm = QPushButton("Confirm this zone")
        self.delete_zone = QPushButton("Delete this zone")
        self.delete_zone.setObjectName("danger")
        zone_layout.addWidget(self.zone_title)
        zone_layout.addWidget(self.zone_help)
        zone_layout.addWidget(QLabel("Name"))
        zone_layout.addWidget(self.zone_name)
        zone_layout.addWidget(self.zone_state)
        zone_layout.addWidget(self.zone_confirm)
        zone_layout.addWidget(self.delete_zone)
        zone_layout.addStretch(1)
        layout.addWidget(self.zone_body)

        self._fill_fixed_choices()
        self._wire()
        self.technical.setVisible(False)
        self.show_empty()

    def _fill_fixed_choices(self) -> None:
        self._load_types()
        for combo, options in (
            (self.status_combo, STATUSES),
            (self.practical_combo, PRACTICAL),
            (self.removal_combo, REMOVAL),
            (self.identification, IDENTIFICATION),
            (self.shield, SHIELD_STATES),
        ):
            combo.clear()
            for key, label in options:
                combo.addItem(label, key)
        self.reason.clear()
        self.reason.addItem("")
        for reason in CANT_REASONS:
            self.reason.addItem(reason)

    def _load_types(self) -> None:
        current = self.type_combo.currentData()
        self.type_combo.clear()
        for row in self.host.store.list_types():
            self.type_combo.addItem(row.plain_name, row.id)
        if current:
            index = self.type_combo.findData(current)
            if index >= 0:
                self.type_combo.setCurrentIndex(index)

    def _wire(self) -> None:
        self.type_combo.currentIndexChanged.connect(lambda: self._save(type_id=self.type_combo.currentData()))
        self.status_combo.currentIndexChanged.connect(lambda: self._save(status=self.status_combo.currentData()))
        self.practical_combo.currentIndexChanged.connect(
            lambda: self._save(practical_reuse=self.practical_combo.currentData())
        )
        self.removal_combo.currentIndexChanged.connect(lambda: self._save(removal=self.removal_combo.currentData()))
        self.identification.currentIndexChanged.connect(
            lambda: self._save(identification=self.identification.currentData())
        )
        self.shield.currentIndexChanged.connect(lambda: self._save(shield_state=self.shield.currentData() or ""))
        self.reason.currentTextChanged.connect(lambda text: self._save(identification_reason=text))
        self.function_notes.editingFinished.connect(
            lambda: self._save(function_notes=self.function_notes.toPlainText())
        )
        self.condition.editingFinished.connect(lambda: self._save(condition_notes=self.condition.toPlainText()))
        self.tool.editingFinished.connect(lambda: self._save(removal_tool=self.tool.text()))
        self.designator.editingFinished.connect(lambda: self._save(designator=self.designator.text()))
        self.marking.editingFinished.connect(lambda: self._save(marking_code=self.marking.text()))
        self.part_number.editingFinished.connect(lambda: self._save(part_number=self.part_number.text()))
        self.manufacturer.editingFinished.connect(lambda: self._save(manufacturer=self.manufacturer.text()))
        self.value_text.editingFinished.connect(lambda: self._save(value_text=self.value_text.text()))
        self.removed.toggled.connect(lambda checked: self._save(removed=checked))
        self.show_simple.toggled.connect(lambda checked: self._save(show_in_simple=checked))
        self.bin_combo.currentIndexChanged.connect(self._save_bin)
        self.tech_button.toggled.connect(self.technical.setVisible)
        self.confirm.clicked.connect(self._confirm)
        self.delete_part.clicked.connect(self._delete_part)
        self.what_link.clicked.connect(lambda: self.host.show_glossary(self.type_combo.currentData() or "simple view"))
        self.designator_link.clicked.connect(lambda: self.host.show_glossary("designator"))
        self.marking_link.clicked.connect(lambda: self.host.show_glossary("marking code"))
        self.use_library.clicked.connect(self._use_library)
        self.zone_name.editingFinished.connect(self._save_zone_name)
        self.zone_confirm.clicked.connect(lambda: self._set_zone_confirmed(True))
        self.delete_zone.clicked.connect(self._delete_zone)

    def apply_view_mode(self, mode: str) -> None:
        self.tech_button.setChecked(mode == "detailed")

    def show_empty(self) -> None:
        self.part_id = None
        self.zone_id = None
        self.empty.setVisible(True)
        self.part_body.setVisible(False)
        self.zone_body.setVisible(False)

    def show_part(self, component_id: int) -> None:
        part = self.host.store.get_component(component_id)
        if part is None:
            self.show_empty()
            return
        self.zone_id = None
        self.part_id = part.id
        self._loading = True
        self._load_types()
        self._load_bins(part.bin_id)
        self._set_combo(self.type_combo, part.type_id)
        self._set_combo(self.status_combo, part.status)
        self._set_combo(self.practical_combo, part.practical_reuse)
        self._set_combo(self.removal_combo, part.removal)
        self._set_combo(self.identification, part.identification)
        self._set_combo(self.shield, part.shield_state)
        self.reason.setCurrentText(part.identification_reason)
        self.function_notes.setPlainText(part.function_notes)
        self.condition.setPlainText(part.condition_notes)
        self.tool.setText(part.removal_tool)
        self.designator.setText(part.designator)
        self.marking.setText(part.marking_code)
        self.part_number.setText(part.part_number)
        self.manufacturer.setText(part.manufacturer)
        self.value_text.setText(part.value_text)
        self.removed.setChecked(part.removed)
        self.show_simple.setChecked(part.show_in_simple)
        self._loading = False
        self._refresh_labels(part)
        self.empty.setVisible(False)
        self.zone_body.setVisible(False)
        self.part_body.setVisible(True)

    def show_zone(self, zone_id: int) -> None:
        zone = self.host.store.get_zone(zone_id)
        if zone is None:
            self.show_empty()
            return
        self.part_id = None
        self.zone_id = zone.id
        self._loading = True
        self.zone_name.setText(zone.name)
        self._loading = False
        self.zone_title.setText(zone.name)
        if zone.confirmed:
            self.zone_state.setText("You named this area.")
            self.zone_confirm.setVisible(False)
        else:
            self.zone_state.setText("Suggested from a copied map. Confirm the name if it is right.")
            self.zone_confirm.setVisible(True)
        self.empty.setVisible(False)
        self.part_body.setVisible(False)
        self.zone_body.setVisible(True)

    def _refresh_labels(self, part) -> None:
        self.heading.setText(part.type_plain or "Part")
        self.explanation.setText(part.type_explanation)
        self.does_default.setText(part.type_what)
        self.removal_tip.setText(removal_summary(part.removal, part.removal_tool, part.type_removal_tip))
        self.test_hint.setText(part.type_test_hint)
        self.verdict.setText(
            reuse_verdict(
                status=part.status,
                practical_reuse=part.practical_reuse,
                removed=part.removed,
                bin_label=part.bin_label,
            )
        )
        self.tool.setPlaceholderText(tool_for(part.removal, ""))
        self.confirm.setVisible(part.identification == "suggested")
        self.shield.setVisible(part.type_id == "shield")
        matches = self.host.store.find_parts_by_marking(part.marking_code) if part.marking_code else []
        if matches:
            match = matches[0]
            self.library_hint.setText(
                f"Library: {match.part_number or match.marking_code}"
                + (f", {match.manufacturer}" if match.manufacturer else "")
                + (f". {match.expected_notes}" if match.expected_notes else "")
            )
            self.use_library.setVisible(True)
        else:
            self.library_hint.setText(identification_line(part.identification, part.identification_reason))
            self.use_library.setVisible(False)

    def _save(self, **fields) -> None:
        if self._loading or self.part_id is None:
            return
        if any(value is None for value in fields.values()):
            return
        self.host.store.update_component(self.part_id, **fields)
        part = self.host.store.get_component(self.part_id)
        if part is None:
            return
        self._refresh_labels(part)
        self.partChanged.emit(part.id)
        self.host.set_status("Saved")

    def _save_bin(self) -> None:
        if self._loading or self.part_id is None:
            return
        bin_id = self.bin_combo.currentData()
        self.host.store.update_component(self.part_id, bin_id=bin_id)
        part = self.host.store.get_component(self.part_id)
        if part:
            self._refresh_labels(part)
            self.partChanged.emit(part.id)

    def _load_bins(self, current: int | None) -> None:
        self.bin_combo.clear()
        self.bin_combo.addItem("No bin yet", None)
        for bin_row in self.host.store.list_bins():
            self.bin_combo.addItem(bin_row.label, bin_row.id)
        index = self.bin_combo.findData(current)
        self.bin_combo.setCurrentIndex(max(0, index))

    def _confirm(self) -> None:
        self._save(identification="confirmed")
        self._loading = True
        self._set_combo(self.identification, "confirmed")
        self._loading = False

    def _use_library(self) -> None:
        if self.part_id is None:
            return
        part = self.host.store.get_component(self.part_id)
        if part is None:
            return
        matches = self.host.store.find_parts_by_marking(part.marking_code)
        if not matches:
            return
        match = matches[0]
        self.host.store.update_component(
            part.id,
            part_number=match.part_number,
            manufacturer=match.manufacturer,
            type_id=match.type_id or part.type_id,
        )
        self.show_part(part.id)
        self.partChanged.emit(part.id)

    def _delete_part(self) -> None:
        if self.part_id is None:
            return
        answer = QMessageBox.question(self, "Delete this part", "Remove this part from the map?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.host.store.delete_component(self.part_id)
        self.partDeleted.emit()

    def _save_zone_name(self) -> None:
        if self._loading or self.zone_id is None:
            return
        self.host.store.update_zone(self.zone_id, name=self.zone_name.text().strip() or "Area")
        self.zoneChanged.emit(self.zone_id)
        self.host.set_status("Saved")

    def _set_zone_confirmed(self, confirmed: bool) -> None:
        if self.zone_id is None:
            return
        self.host.store.update_zone(self.zone_id, confirmed=confirmed)
        self.zoneChanged.emit(self.zone_id)
        self.show_zone(self.zone_id)

    def _delete_zone(self) -> None:
        if self.zone_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete this zone",
            "Remove this named area? Parts inside it stay on the map.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.host.store.delete_zone(self.zone_id)
        self.zoneDeleted.emit()

    def _set_combo(self, combo: QComboBox, value) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)
