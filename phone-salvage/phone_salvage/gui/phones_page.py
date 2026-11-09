"""Phone list, the record for one phone, and the boards inside it."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from phone_salvage.catalog import BOARD_TYPES, LIQUID, POWERED
from phone_salvage.gui.dialogs import LabelDialog, board_type_label
from phone_salvage.services import label_payload


class PhonesPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.phone_id: int | None = None
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.banner = QLabel(
            "Two sample phones are loaded so you can try every screen. "
            "PH-002's main board was copied from PH-001, so those boxes stay dashed until you confirm them. "
            "Add your own phone beside the samples."
        )
        self.banner.setWordWrap(True)
        self.banner.setObjectName("verdict")
        dismiss = QPushButton("Hide this note")
        dismiss.clicked.connect(self._hide_banner)
        banner_row = QHBoxLayout()
        banner_row.addWidget(self.banner, 1)
        banner_row.addWidget(dismiss, 0, Qt.AlignmentFlag.AlignTop)
        self.banner_wrap = QWidget()
        self.banner_wrap.setLayout(banner_row)
        layout.addWidget(self.banner_wrap)

        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search phones")
        self.search.textChanged.connect(self._filter_list)
        self.phone_list = QListWidget()
        self.phone_list.currentRowChanged.connect(self._phone_chosen)
        add = QPushButton("Add a phone")
        add.setObjectName("primary")
        add.clicked.connect(self._add_phone)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.phone_list, 1)
        left_layout.addWidget(add)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        self.heading = QLabel("No phone yet")
        self.heading.setObjectName("title")
        self.photo = QLabel()
        self.photo.setFixedSize(120, 160)
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head = QHBoxLayout()
        head.addWidget(self.heading, 1)
        head.addWidget(self.photo)
        right_layout.addLayout(head)

        form = QFormLayout()
        self.make = QLineEdit()
        self.model = QLineEdit()
        self.model_number = QLineEdit()
        self.colour = QLineEdit()
        self.imei = QLineEdit()
        self.imei.setPlaceholderText("Optional")
        self.purchased = QLineEdit()
        self.purchased.setPlaceholderText("YYYY-MM-DD")
        self.price = QLineEdit()
        self.powered = QComboBox()
        self.liquid = QComboBox()
        self.faults = QLineEdit()
        self.condition = QLineEdit()
        for combo, options in ((self.powered, POWERED), (self.liquid, LIQUID)):
            for key, label in options:
                combo.addItem(label, key)
        form.addRow("Make", self.make)
        form.addRow("Model", self.model)
        form.addRow("Model number", self.model_number)
        form.addRow("Colour", self.colour)
        form.addRow("IMEI or serial", self.imei)
        form.addRow("Purchase date", self.purchased)
        form.addRow("Purchase price", self.price)
        form.addRow("Powered on when bought", self.powered)
        form.addRow("Liquid contact", self.liquid)
        form.addRow("Known faults", self.faults)
        form.addRow("Condition notes", self.condition)
        right_layout.addLayout(form)

        photo_row = QHBoxLayout()
        choose_photo = QPushButton("Set phone photo")
        choose_photo.clicked.connect(self._photo)
        phone_label = QPushButton("Phone label")
        phone_label.clicked.connect(self._phone_label)
        delete = QPushButton("Delete phone")
        delete.setObjectName("danger")
        delete.clicked.connect(self._delete_phone)
        photo_row.addWidget(choose_photo)
        photo_row.addWidget(phone_label)
        photo_row.addStretch(1)
        photo_row.addWidget(delete)
        right_layout.addLayout(photo_row)

        right_layout.addWidget(QLabel("Boards"))
        self.board_list = QListWidget()
        self.board_list.itemDoubleClicked.connect(lambda _item: self._open_board())
        right_layout.addWidget(self.board_list, 1)
        board_row = QHBoxLayout()
        self.new_board_type = QComboBox()
        for key, label in BOARD_TYPES:
            self.new_board_type.addItem(label, key)
        add_board = QPushButton("Add board")
        add_board.setObjectName("primary")
        add_board.clicked.connect(self._add_board)
        open_board = QPushButton("Open map")
        open_board.clicked.connect(self._open_board)
        delete_board = QPushButton("Delete board")
        delete_board.clicked.connect(self._delete_board)
        board_row.addWidget(self.new_board_type)
        board_row.addWidget(add_board)
        board_row.addWidget(open_board)
        board_row.addWidget(delete_board)
        right_layout.addLayout(board_row)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        for widget in (
            self.make,
            self.model,
            self.model_number,
            self.colour,
            self.imei,
            self.purchased,
            self.price,
            self.faults,
            self.condition,
        ):
            widget.editingFinished.connect(self._save)
        self.powered.currentIndexChanged.connect(self._save)
        self.liquid.currentIndexChanged.connect(self._save)
        self.reload()

    def reload(self) -> None:
        show_note = self.host.store.get_setting("sample_note") != "hide" and any(
            phone.model_number == "S1-DEMO" for phone in self.host.store.list_phones()
        )
        self.banner_wrap.setVisible(show_note)
        selected = self.phone_id
        self._fill_list()
        if selected is not None:
            self._select_phone(selected)
        elif self.phone_list.count():
            self.phone_list.setCurrentRow(0)
        else:
            self._show_phone(None)

    def _fill_list(self) -> None:
        self._loading = True
        self.phone_list.clear()
        query = self.search.text().strip().casefold()
        self._ids = []
        for phone in self.host.store.list_phones():
            blob = " ".join((phone.short_id, phone.make, phone.model, phone.colour, phone.known_faults)).casefold()
            if query and query not in blob:
                continue
            colour = f" · {phone.colour}" if phone.colour else ""
            model = f"{phone.make} {phone.model}".strip() or "No model yet"
            self.phone_list.addItem(f"{phone.short_id}   {model}{colour}")
            self._ids.append(phone.id)
        self._loading = False

    def _filter_list(self) -> None:
        current = self.phone_id
        self._fill_list()
        if current in getattr(self, "_ids", []):
            self._select_phone(current)

    def _select_phone(self, phone_id: int) -> None:
        if phone_id in self._ids:
            self.phone_list.setCurrentRow(self._ids.index(phone_id))

    def _phone_chosen(self, row: int) -> None:
        if self._loading:
            return
        if row < 0 or row >= len(self._ids):
            self._show_phone(None)
            return
        self._show_phone(self._ids[row])

    def _show_phone(self, phone_id: int | None) -> None:
        self.phone_id = phone_id
        phone = self.host.store.get_phone(phone_id) if phone_id else None
        self._loading = True
        if phone is None:
            self.heading.setText("Add a phone")
            self.photo.clear()
            for widget in (
                self.make,
                self.model,
                self.model_number,
                self.colour,
                self.imei,
                self.purchased,
                self.price,
                self.faults,
                self.condition,
            ):
                widget.clear()
            self.board_list.clear()
            self._loading = False
            return
        self.heading.setText(phone.short_id)
        self.make.setText(phone.make)
        self.model.setText(phone.model)
        self.model_number.setText(phone.model_number)
        self.colour.setText(phone.colour)
        self.imei.setText(phone.imei_or_serial)
        self.purchased.setText(phone.purchase_date)
        self.price.setText(phone.purchase_price)
        self.faults.setText(phone.known_faults)
        self.condition.setText(phone.condition_notes)
        self._set_combo(self.powered, phone.powered_on)
        self._set_combo(self.liquid, phone.liquid_contact)
        path = self.host.store.abs_path(phone.photo_path)
        pixmap = QPixmap(str(path)) if path and path.is_file() else QPixmap()
        if pixmap.isNull():
            self.photo.setText("No photo")
        else:
            self.photo.setPixmap(
                pixmap.scaled(self.photo.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        self.board_list.clear()
        self._board_ids = []
        for board in self.host.store.list_boards(phone.id):
            revision = f"  rev {board.revision}" if board.revision else ""
            self.board_list.addItem(f"{board.short_id}   {board_type_label(board.board_type)}{revision}")
            self._board_ids.append(board.id)
        if self._board_ids:
            self.board_list.setCurrentRow(0)
        self._loading = False

    def _save(self) -> None:
        if self._loading or self.phone_id is None:
            return
        self.host.store.update_phone(
            self.phone_id,
            make=self.make.text().strip(),
            model=self.model.text().strip(),
            model_number=self.model_number.text().strip(),
            colour=self.colour.text().strip(),
            imei_or_serial=self.imei.text().strip(),
            purchase_date=self.purchased.text().strip(),
            purchase_price=self.price.text().strip(),
            powered_on=self.powered.currentData(),
            liquid_contact=self.liquid.currentData(),
            known_faults=self.faults.text().strip(),
            condition_notes=self.condition.text().strip(),
        )
        self._fill_list()
        self._select_phone(self.phone_id)
        self.host.set_status("Saved")

    def _add_phone(self) -> None:
        phone = self.host.store.add_phone()
        self.reload()
        self._select_phone(phone.id)
        self.make.setFocus()
        self.host.set_status(f"{phone.short_id} added. Write that ID on the bag.")

    def _delete_phone(self) -> None:
        if self.phone_id is None:
            return
        phone = self.host.store.get_phone(self.phone_id)
        if phone is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete phone",
            f"Delete {phone.short_id} and every board on it?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.host.store.delete_phone(phone.id)
        self.phone_id = None
        self.reload()

    def _photo(self) -> None:
        if self.phone_id is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Phone photo", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        relative = self.host.store.import_file(path, "images")
        self.host.store.update_phone(self.phone_id, photo_path=relative)
        self._show_phone(self.phone_id)

    def _add_board(self) -> None:
        if self.phone_id is None:
            return
        board = self.host.store.add_board(self.phone_id, self.new_board_type.currentData())
        self._show_phone(self.phone_id)
        self.host.open_board(board.id)

    def _open_board(self) -> None:
        row = self.board_list.currentRow()
        if row < 0 or row >= len(getattr(self, "_board_ids", [])):
            return
        self.host.open_board(self._board_ids[row])

    def _delete_board(self) -> None:
        row = self.board_list.currentRow()
        if row < 0 or row >= len(getattr(self, "_board_ids", [])):
            return
        answer = QMessageBox.question(self, "Delete board", "Delete this board and its map?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.host.store.delete_board(self._board_ids[row])
        self._show_phone(self.phone_id)

    def _phone_label(self) -> None:
        phone = self.host.store.get_phone(self.phone_id) if self.phone_id else None
        if phone is None:
            return
        lines = [f"{phone.make} {phone.model}".strip(), phone.colour, phone.known_faults]
        LabelDialog(phone.short_id, [line for line in lines if line], label_payload("phone", phone.short_id), self).exec()

    def _hide_banner(self) -> None:
        self.host.store.set_setting("sample_note", "hide")
        self.banner_wrap.setVisible(False)

    def _set_combo(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)
