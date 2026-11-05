"""Harvest list, inventory, parts library, and bins."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from phone_salvage.catalog import IDENTIFICATION, PRACTICAL, STATUSES, choice_label
from phone_salvage.gui.dialogs import LabelDialog
from phone_salvage.present import status_summary, tool_for
from phone_salvage.services import harvest_for, label_payload


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _item(text: str, row_id: int | None = None) -> QTableWidgetItem:
    cell = QTableWidgetItem(text)
    if row_id is not None:
        cell.setData(Qt.ItemDataRole.UserRole, row_id)
    return cell


class HarvestPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        intro = QLabel(
            "Parts still on the board that are worth pulling. Modules and plugs come first. "
            "Tiny parts stay off this list until you mark them usable or maybe. Junk and anything you already removed stay off it."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        row = QHBoxLayout()
        row.addWidget(QLabel("Phone"))
        self.phone = QComboBox()
        self.phone.currentIndexChanged.connect(self.reload)
        row.addWidget(self.phone, 1)
        layout.addLayout(row)
        self.summary = QLabel()
        self.summary.setObjectName("quiet")
        layout.addWidget(self.summary)
        self.table = _table(["Part", "Board", "Removal", "Tool", "Status"])
        self.table.itemDoubleClicked.connect(self._open)
        layout.addWidget(self.table, 1)
        open_button = QPushButton("Show on map")
        open_button.setObjectName("primary")
        open_button.clicked.connect(self._open)
        layout.addWidget(open_button, 0, Qt.AlignmentFlag.AlignLeft)

    def reload(self) -> None:
        current = self.phone.currentData()
        self.phone.blockSignals(True)
        self.phone.clear()
        for phone in self.host.store.list_phones():
            label = f"{phone.short_id}  {phone.make} {phone.model}".strip()
            self.phone.addItem(label, phone.id)
        index = self.phone.findData(current)
        self.phone.setCurrentIndex(index if index >= 0 else 0)
        self.phone.blockSignals(False)
        phone_id = self.phone.currentData()
        parts = harvest_for(self.host.store.components_for_phone(phone_id)) if phone_id else []
        self.summary.setText(f"{len(parts)} to remove" if parts else "Nothing to pull on this phone.")
        self.table.setRowCount(len(parts))
        for row, part in enumerate(parts):
            removal = choice_label(
                (("easy_unplug", "Easy unplug"), ("hot_air", "Needs hot air"), ("not_practical", "Not practical")),
                part.removal,
            )
            self.table.setItem(row, 0, _item(part.type_plain, part.id))
            self.table.setItem(row, 1, _item(part.board_short_id))
            self.table.setItem(row, 2, _item(removal))
            self.table.setItem(row, 3, _item(tool_for(part.removal, part.removal_tool)))
            self.table.setItem(row, 4, _item(choice_label(STATUSES, part.status)))
        self.table.resizeColumnsToContents()

    def _open(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        cell = self.table.item(row, 0)
        if cell is None:
            return
        self.host.open_component(int(cell.data(Qt.ItemDataRole.UserRole)))


class InventoryPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(QLabel("Every part, across all phones. A row opens that spot on the map."))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search markings, notes, phones, bins")
        self.search.textChanged.connect(self.reload)
        layout.addWidget(self.search)
        filters = QHBoxLayout()
        self.type_filter = QComboBox()
        self.status_filter = QComboBox()
        self.ident_filter = QComboBox()
        self.reuse_filter = QComboBox()
        self.model_filter = QComboBox()
        self.where_filter = QComboBox()
        self.bin_filter = QComboBox()
        for combo in (
            self.type_filter,
            self.status_filter,
            self.ident_filter,
            self.reuse_filter,
            self.model_filter,
            self.where_filter,
            self.bin_filter,
        ):
            combo.currentIndexChanged.connect(self.reload)
            filters.addWidget(combo)
        layout.addLayout(filters)
        self.summary = QLabel()
        self.summary.setObjectName("quiet")
        layout.addWidget(self.summary)
        self.table = _table(["Part", "Status", "Phone", "Board", "Where", "Marking"])
        self.table.itemDoubleClicked.connect(self._open)
        layout.addWidget(self.table, 1)

    def reload(self) -> None:
        self._refill_filters()
        parts = self.host.store.search_components(
            text=self.search.text(),
            type_id=self.type_filter.currentData(),
            status=self.status_filter.currentData(),
            identification=self.ident_filter.currentData(),
            practical_reuse=self.reuse_filter.currentData(),
            model=self.model_filter.currentData(),
            location=self.where_filter.currentData(),
            bin_id=self.bin_filter.currentData(),
        )
        counts: dict[str, int] = {}
        for part in parts:
            counts[part.status] = counts.get(part.status, 0) + 1
        self.summary.setText(status_summary(counts))
        self.table.setRowCount(len(parts))
        for row, part in enumerate(parts):
            where = part.bin_label if part.removed and part.bin_label else ("Removed" if part.removed else "On the board")
            self.table.setItem(row, 0, _item(part.type_plain, part.id))
            self.table.setItem(row, 1, _item(choice_label(STATUSES, part.status)))
            self.table.setItem(row, 2, _item(part.phone_short_id))
            self.table.setItem(row, 3, _item(f"{part.board_short_id} {part.side}"))
            self.table.setItem(row, 4, _item(where))
            self.table.setItem(row, 5, _item(part.marking_code))
        self.table.resizeColumnsToContents()

    def _refill_filters(self) -> None:
        combos = (
            (self.type_filter, "Any part", [(row.id, row.plain_name) for row in self.host.store.list_types()]),
            (self.status_filter, "Any status", list(STATUSES)),
            (self.ident_filter, "Any identification", list(IDENTIFICATION)),
            (self.reuse_filter, "Any reuse", list(PRACTICAL)),
            (self.model_filter, "Any model", [(model, model) for model in self.host.store.phone_models()]),
            (self.where_filter, "On the board or removed", [("board", "On the board"), ("stored", "Removed")]),
            (self.bin_filter, "Any bin", [(row.id, row.label) for row in self.host.store.list_bins()]),
        )
        for combo, any_label, options in combos:
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(any_label, None)
            for key, label in options:
                combo.addItem(label, key)
            index = combo.findData(current)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    def _open(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        cell = self.table.item(row, 0)
        if cell is None:
            return
        self.host.open_component(int(cell.data(Qt.ItemDataRole.UserRole)))


class PartsPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.part_id: int | None = None
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(
            QLabel("When you identify a marking once, save it here. The next part with that marking can use these details.")
        )
        splitter = QSplitter()
        self.table = _table(["Marking", "Part number", "Type", "Maker"])
        self.table.itemSelectionChanged.connect(self._chosen)
        form = QWidget()
        form_layout = QFormLayout(form)
        self.marking = QLineEdit()
        self.number = QLineEdit()
        self.type_combo = QComboBox()
        self.maker = QLineEdit()
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(80)
        self.expected = QPlainTextEdit()
        self.expected.setFixedHeight(64)
        self.expected.setPlaceholderText("What a meter should roughly show, if you know.")
        form_layout.addRow("Marking code", self.marking)
        form_layout.addRow("Part number", self.number)
        form_layout.addRow("Type", self.type_combo)
        form_layout.addRow("Maker", self.maker)
        form_layout.addRow("Notes", self.notes)
        form_layout.addRow("Expected test", self.expected)
        buttons = QHBoxLayout()
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        new = QPushButton("New entry")
        new.clicked.connect(self._new)
        delete = QPushButton("Delete")
        delete.setObjectName("danger")
        delete.clicked.connect(self._delete)
        buttons.addWidget(save)
        buttons.addWidget(new)
        buttons.addWidget(delete)
        form_layout.addRow(buttons)
        splitter.addWidget(self.table)
        splitter.addWidget(form)
        layout.addWidget(splitter, 1)
        self.reload()

    def reload(self) -> None:
        self.type_combo.blockSignals(True)
        current_type = self.type_combo.currentData()
        self.type_combo.clear()
        self.type_combo.addItem("Not set", None)
        for row in self.host.store.list_types():
            self.type_combo.addItem(row.plain_name, row.id)
        index = self.type_combo.findData(current_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        self.type_combo.blockSignals(False)
        selected = self.part_id
        parts = self.host.store.list_parts()
        self.table.setRowCount(len(parts))
        ids = []
        for row, part in enumerate(parts):
            ids.append(part.id)
            self.table.setItem(row, 0, _item(part.marking_code, part.id))
            self.table.setItem(row, 1, _item(part.part_number))
            self.table.setItem(row, 2, _item(part.type_plain))
            self.table.setItem(row, 3, _item(part.manufacturer))
        self._ids = ids
        self.table.resizeColumnsToContents()
        if selected in ids:
            self.table.selectRow(ids.index(selected))

    def _chosen(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(getattr(self, "_ids", [])):
            return
        part = next((item for item in self.host.store.list_parts() if item.id == self._ids[row]), None)
        if part is None:
            return
        self.part_id = part.id
        self._loading = True
        self.marking.setText(part.marking_code)
        self.number.setText(part.part_number)
        self.maker.setText(part.manufacturer)
        self.notes.setPlainText(part.notes)
        self.expected.setPlainText(part.expected_notes)
        index = self.type_combo.findData(part.type_id)
        self.type_combo.setCurrentIndex(index if index >= 0 else 0)
        self._loading = False

    def _save(self) -> None:
        fields = dict(
            marking_code=self.marking.text().strip(),
            part_number=self.number.text().strip(),
            type_id=self.type_combo.currentData(),
            manufacturer=self.maker.text().strip(),
            notes=self.notes.toPlainText().strip(),
            expected_notes=self.expected.toPlainText().strip(),
        )
        if self.part_id is None:
            created = self.host.store.add_part(**fields)
            self.part_id = created.id
        else:
            self.host.store.update_part(self.part_id, **fields)
        self.reload()
        self.host.set_status("Library saved")

    def _new(self) -> None:
        self.part_id = None
        self.marking.clear()
        self.number.clear()
        self.maker.clear()
        self.notes.clear()
        self.expected.clear()
        self.type_combo.setCurrentIndex(0)
        self.table.clearSelection()

    def _delete(self) -> None:
        if self.part_id is None:
            return
        answer = QMessageBox.question(self, "Delete library entry", "Delete this marking from the library?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.host.store.delete_part(self.part_id)
        self.part_id = None
        self.reload()


class BinsPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.bin_id: int | None = None
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(QLabel("A bin is a drawer or a bag. Print its label and write the same words on the container."))
        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.bin_list = QTableWidget(0, 1)
        self.bin_list.setHorizontalHeaderLabels(["Bin"])
        self.bin_list.verticalHeader().setVisible(False)
        self.bin_list.setShowGrid(False)
        self.bin_list.horizontalHeader().setStretchLastSection(True)
        self.bin_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.bin_list.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.bin_list.itemSelectionChanged.connect(self._chosen)
        add = QPushButton("Add a bin")
        add.setObjectName("primary")
        add.clicked.connect(self._add)
        left_layout.addWidget(self.bin_list, 1)
        left_layout.addWidget(add)
        right = QWidget()
        form = QFormLayout(right)
        self.label = QLineEdit()
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(80)
        self.contents = _table(["Part", "From", "Status"])
        self.contents.itemDoubleClicked.connect(self._open_part)
        save = QPushButton("Save bin")
        save.clicked.connect(self._save)
        label_button = QPushButton("Bin label")
        label_button.clicked.connect(self._label)
        delete = QPushButton("Delete bin")
        delete.setObjectName("danger")
        delete.clicked.connect(self._delete)
        buttons = QHBoxLayout()
        buttons.addWidget(save)
        buttons.addWidget(label_button)
        buttons.addWidget(delete)
        form.addRow("Label", self.label)
        form.addRow("Notes", self.notes)
        form.addRow(buttons)
        form.addRow(QLabel("Parts in this bin"))
        form.addRow(self.contents)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        self.reload()

    def reload(self) -> None:
        selected = self.bin_id
        bins = self.host.store.list_bins()
        self.bin_list.setRowCount(len(bins))
        self._ids = []
        for row, bin_row in enumerate(bins):
            self._ids.append(bin_row.id)
            self.bin_list.setItem(row, 0, _item(bin_row.label, bin_row.id))
        if selected in self._ids:
            self.bin_list.selectRow(self._ids.index(selected))
        elif self._ids:
            self.bin_list.selectRow(0)
        else:
            self._clear()

    def _chosen(self) -> None:
        row = self.bin_list.currentRow()
        if row < 0 or row >= len(getattr(self, "_ids", [])):
            return
        bin_row = self.host.store.get_bin(self._ids[row])
        if bin_row is None:
            return
        self.bin_id = bin_row.id
        self._loading = True
        self.label.setText(bin_row.label)
        self.notes.setPlainText(bin_row.notes)
        self._loading = False
        parts = self.host.store.search_components(bin_id=bin_row.id, location="stored")
        self.contents.setRowCount(len(parts))
        for index, part in enumerate(parts):
            self.contents.setItem(index, 0, _item(part.type_plain, part.id))
            self.contents.setItem(index, 1, _item(part.phone_short_id))
            self.contents.setItem(index, 2, _item(choice_label(STATUSES, part.status)))

    def _clear(self) -> None:
        self.bin_id = None
        self.label.clear()
        self.notes.clear()
        self.contents.setRowCount(0)

    def _add(self) -> None:
        created = self.host.store.add_bin("New bin")
        self.bin_id = created.id
        self.reload()
        self.label.setFocus()
        self.label.selectAll()

    def _save(self) -> None:
        if self._loading or self.bin_id is None:
            return
        try:
            self.host.store.update_bin(self.bin_id, label=self.label.text(), notes=self.notes.toPlainText().strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Bin", str(exc))
            return
        self.reload()
        self.host.set_status("Bin saved")

    def _delete(self) -> None:
        if self.bin_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete bin",
            "Delete this bin? Parts that pointed at it stay in the catalogue, with no bin.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.host.store.delete_bin(self.bin_id)
        self.bin_id = None
        self.reload()

    def _label(self) -> None:
        if self.bin_id is None:
            return
        bin_row = self.host.store.get_bin(self.bin_id)
        if bin_row is None:
            return
        LabelDialog(bin_row.label, [bin_row.notes] if bin_row.notes else [], label_payload("bin", bin_row.label), self).exec()

    def _open_part(self) -> None:
        row = self.contents.currentRow()
        if row < 0:
            return
        cell = self.contents.item(row, 0)
        if cell is None:
            return
        self.host.open_component(int(cell.data(Qt.ItemDataRole.UserRole)))
