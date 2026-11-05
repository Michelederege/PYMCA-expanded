"""Small dialogs: labels, copy, glossary, and the limits of this version."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from phone_salvage.catalog import BOARD_TYPES, LIMITS_TEXT, choice_label
from phone_salvage.services import label_png


class GlossaryDialog(QDialog):
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.setWindowTitle("Glossary")
        self.resize(640, 420)
        layout = QHBoxLayout(self)
        self.list = QListWidget()
        self.title = QLabel()
        self.title.setObjectName("title")
        self.title.setWordWrap(True)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        text = QWidget()
        text_layout = QVBoxLayout(text)
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.body, 1)
        layout.addWidget(self.list, 1)
        layout.addWidget(text, 2)
        self.list.currentRowChanged.connect(self._show_current)
        self._entries = []

    def open_term(self, term: str | None = None) -> None:
        self._entries = self.host.store.list_glossary()
        self.list.clear()
        for entry in self._entries:
            self.list.addItem(entry.title)
        index = 0
        if term:
            for i, entry in enumerate(self._entries):
                if entry.term == term:
                    index = i
                    break
        if self._entries:
            self.list.setCurrentRow(index)
        self.show()
        self.raise_()
        self.activateWindow()

    def _show_current(self, row: int) -> None:
        if row < 0 or row >= len(self._entries):
            return
        entry = self._entries[row]
        self.title.setText(entry.title)
        self.body.setText(entry.body)


class LimitsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("What this app cannot do")
        self.resize(460, 320)
        layout = QVBoxLayout(self)
        label = QLabel(LIMITS_TEXT)
        label.setWordWrap(True)
        layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class LabelDialog(QDialog):
    def __init__(self, title: str, lines: list[str], payload: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Label")
        self._png = label_png(title, lines, payload)
        layout = QVBoxLayout(self)
        image = QImage.fromData(self._png)
        preview = QLabel()
        preview.setPixmap(QPixmap.fromImage(image))
        layout.addWidget(preview)
        row = QHBoxLayout()
        save = QPushButton("Save image")
        print_button = QPushButton("Print")
        print_button.setObjectName("primary")
        close = QPushButton("Close")
        save.clicked.connect(self._save)
        print_button.clicked.connect(self._print)
        close.clicked.connect(self.accept)
        row.addWidget(save)
        row.addWidget(print_button)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save label", "label.png", "PNG (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            with open(path, "wb") as handle:
                handle.write(self._png)

    def _print(self) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        from PySide6.QtGui import QPainter

        painter = QPainter(printer)
        pixmap = QPixmap.fromImage(QImage.fromData(self._png))
        page = printer.pageRect(QPrinter.Unit.DevicePixel)
        scaled = pixmap.scaled(
            int(page.width() * 0.8),
            int(page.height() * 0.4),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(40, 40, scaled)
        painter.end()


class NewPartDialog(QDialog):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New part")
        self.type_id = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("What is this part?"))
        self.combo = QComboBox()
        for row in host.store.list_types():
            self.combo.addItem(row.plain_name, row.id)
        layout.addWidget(self.combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self.type_id = self.combo.currentData()
        super().accept()


class CopyLayoutDialog(QDialog):
    def __init__(self, sources, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Copy a layout")
        self.resize(460, 320)
        self.side_id = None
        layout = QVBoxLayout(self)
        note = QLabel(
            "Copy zones and parts from another board of the same model. "
            "The copies stay dashed until you confirm them. Removal difficulty is copied. "
            "Status goes back to not yet checked, because this is a different board."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list = QListWidget()
        self._ids = []
        for source in sources:
            revision = f", rev {source.revision}" if source.revision else ""
            self.list.addItem(
                f"{source.phone_short_id}  {source.board_short_id}  {source.side}{revision}"
            )
            self._ids.append(source.side_id)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self._ids:
            self.list.setCurrentRow(0)

    def accept(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.side_id = self._ids[row]
        super().accept()


class BoardDetailsDialog(QDialog):
    def __init__(self, board, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Board details")
        layout = QFormLayout(self)
        self.board_type = QComboBox()
        for key, label in BOARD_TYPES:
            self.board_type.addItem(label, key)
        index = self.board_type.findData(board.board_type)
        self.board_type.setCurrentIndex(max(0, index))
        self.revision = QLineEdit(board.revision)
        self.part_number = QLineEdit(board.part_number)
        self.notes = QPlainTextEdit(board.notes)
        self.notes.setFixedHeight(80)
        layout.addRow("Type", self.board_type)
        layout.addRow("Revision", self.revision)
        layout.addRow("Part number", self.part_number)
        layout.addRow("Notes", self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict:
        return {
            "board_type": self.board_type.currentData(),
            "revision": self.revision.text().strip(),
            "part_number": self.part_number.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class PartNamesDialog(QDialog):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.setWindowTitle("Part names")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Plain names are what Simple view shows. You can add a name of your own."))
        splitter = QSplitter()
        self.list = QListWidget()
        form = QWidget()
        form_layout = QFormLayout(form)
        self.plain = QLineEdit()
        self.explanation = QPlainTextEdit()
        self.explanation.setFixedHeight(100)
        self.important = QCheckBox("Show this kind of part in Simple view")
        form_layout.addRow("Plain name", self.plain)
        form_layout.addRow("Explanation", self.explanation)
        form_layout.addRow(self.important)
        save = QPushButton("Save name")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        add = QPushButton("Add a new name")
        add.clicked.connect(self._add)
        form_layout.addRow(save)
        form_layout.addRow(add)
        splitter.addWidget(self.list)
        splitter.addWidget(form)
        layout.addWidget(splitter)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self._ids: list[str] = []
        self._loading = False
        self.list.currentRowChanged.connect(self._fill)
        self.reload()

    def reload(self) -> None:
        self._loading = True
        self.list.clear()
        self._ids = []
        for row in self.host.store.list_types():
            self.list.addItem(row.plain_name)
            self._ids.append(row.id)
        self._loading = False
        if self._ids:
            self.list.setCurrentRow(0)

    def _fill(self, row: int) -> None:
        if self._loading or row < 0:
            return
        item = self.host.store.get_type(self._ids[row])
        if item is None:
            return
        self._loading = True
        self.plain.setText(item.plain_name)
        self.explanation.setPlainText(item.explanation)
        self.important.setChecked(item.beginner_important)
        self._loading = False

    def _save(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        type_id = self._ids[row]
        plain = self.plain.text().strip() or "Part"
        explanation = self.explanation.toPlainText().strip()
        self.host.store.update_type(
            type_id,
            plain_name=plain,
            label=plain,
            explanation=explanation,
            beginner_important=self.important.isChecked(),
        )
        entry = self.host.store.get_glossary(type_id)
        if entry:
            self.host.store.update_glossary(type_id, plain, explanation)
        self.reload()
        QMessageBox.information(self, "Part names", "Saved.")

    def _add(self) -> None:
        created = self.host.store.add_type("New part", "Describe this part in plain words.")
        self.reload()
        if created.id in self._ids:
            self.list.setCurrentRow(self._ids.index(created.id))


def board_type_label(key: str) -> str:
    return choice_label(BOARD_TYPES, key)
