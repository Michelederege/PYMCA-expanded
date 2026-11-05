"""One side of a board: map, tools, legend, and the part panel."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from phone_salvage.catalog import DEFAULT_TOOL
from phone_salvage.geometry import norm_box
from phone_salvage.gui.dialogs import BoardDetailsDialog, CopyLayoutDialog, LabelDialog, NewPartDialog, board_type_label
from phone_salvage.gui.info_panel import InfoPanel
from phone_salvage.gui.legend import LegendBar
from phone_salvage.gui.map_view import MapView
from phone_salvage.services import label_payload


class BoardPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.board_id: int | None = None
        self.side = "front"
        self._fitted = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        back = QPushButton("Phones")
        back.clicked.connect(self.host.show_phones)
        self.title = QLabel("Board")
        self.title.setObjectName("title")
        self.front = QPushButton("Front")
        self.back = QPushButton("Back")
        self.front.setCheckable(True)
        self.back.setCheckable(True)
        self.front.setChecked(True)
        sides = QButtonGroup(self)
        sides.setExclusive(True)
        sides.addButton(self.front)
        sides.addButton(self.back)
        self.front.clicked.connect(lambda: self._switch_side("front"))
        self.back.clicked.connect(lambda: self._switch_side("back"))
        self.simple = QPushButton("Simple")
        self.detailed = QPushButton("Detailed")
        self.simple.setCheckable(True)
        self.detailed.setCheckable(True)
        modes = QButtonGroup(self)
        modes.setExclusive(True)
        modes.addButton(self.simple)
        modes.addButton(self.detailed)
        self.simple.clicked.connect(lambda: self.host.set_view_mode("simple"))
        self.detailed.clicked.connect(lambda: self.host.set_view_mode("detailed"))
        header.addWidget(back)
        header.addWidget(self.title, 1)
        header.addWidget(self.front)
        header.addWidget(self.back)
        header.addWidget(self.simple)
        header.addWidget(self.detailed)
        layout.addLayout(header)

        tools = QHBoxLayout()
        self.tools = QButtonGroup(self)
        self.tools.setExclusive(True)
        for mode, label, tip in (
            ("select", "Select", "Click a part. Drag it to adjust the copy."),
            ("box", "Draw box", "Drag a rectangle around a part."),
            ("pin", "Drop pin", "Click once to mark a tiny part."),
            ("zone", "Draw zone", "Drag a named area, such as Camera or Charging."),
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(tip)
            button.clicked.connect(lambda checked, mode=mode: self._set_mode(mode))
            self.tools.addButton(button)
            tools.addWidget(button)
            if mode == "select":
                button.setChecked(True)
        fit = QPushButton("Fit")
        fit.clicked.connect(self._fit)
        photo = QPushButton("Set photo")
        photo.clicked.connect(self._set_photo)
        copy = QPushButton("Copy layout")
        copy.clicked.connect(self._copy_layout)
        details = QPushButton("Board details")
        details.clicked.connect(self._details)
        label = QPushButton("Label")
        label.clicked.connect(self._label)
        tools.addWidget(fit)
        tools.addWidget(photo)
        tools.addWidget(copy)
        tools.addWidget(details)
        tools.addWidget(label)
        tools.addStretch(1)
        layout.addLayout(tools)

        self.map = MapView()
        self.legend = LegendBar()
        map_column = QWidget()
        map_layout = QVBoxLayout(map_column)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)
        map_layout.addWidget(self.map, 1)
        map_layout.addWidget(self.legend)
        self.info = InfoPanel(host)
        splitter = QSplitter()
        splitter.addWidget(map_column)
        splitter.addWidget(self.info)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        layout.addWidget(splitter, 1)

        self.map.partSelected.connect(self.info.show_part)
        self.map.zoneSelected.connect(self.info.show_zone)
        self.map.selectionCleared.connect(self.info.show_empty)
        self.map.boxDrawn.connect(self._box_drawn)
        self.map.pinDropped.connect(self._pin_dropped)
        self.map.geometriesChanged.connect(self._moved)
        self.info.partChanged.connect(self._part_changed)
        self.info.partDeleted.connect(lambda: self.reload(keep_view=True))
        self.info.zoneChanged.connect(self._zone_changed)
        self.info.zoneDeleted.connect(lambda: self.reload(keep_view=True))

    def open(self, board_id: int, side: str = "front", component_id: int | None = None, *, center: bool = False) -> None:
        self.board_id = board_id
        self.side = side
        self.front.setChecked(side == "front")
        self.back.setChecked(side == "back")
        self._fitted = False
        self.reload(keep_view=False)
        self.apply_view_mode()
        QTimer.singleShot(0, self.map.fit_board)
        if component_id:
            self.map.select_part(component_id, center=center)
            self.info.show_part(component_id)

    def apply_view_mode(self) -> None:
        mode = self.host.view_mode
        self.simple.setChecked(mode == "simple")
        self.detailed.setChecked(mode == "detailed")
        self.map.set_view_mode(mode)
        self.info.apply_view_mode(mode)

    def reload(self, keep_view: bool) -> None:
        if self.board_id is None:
            return
        board = self.host.store.get_board(self.board_id)
        if board is None:
            self.host.show_phones()
            return
        phone = self.host.store.get_phone(board.phone_id)
        side_row = self.host.store.get_side(board.id, self.side)
        model = f"{phone.make} {phone.model}".strip() if phone else ""
        self.title.setText(
            f"{board.short_id}  ·  {board_type_label(board.board_type)}  ·  {model or (phone.short_id if phone else '')}"
        )
        path = self.host.store.abs_path(side_row.overview_path)
        pixmap = QPixmap(str(path)) if path and path.is_file() else None
        keep = self.map.view_state() if keep_view and self._fitted else None
        selected = self.map.selected_part_id() if keep_view else None
        self.map.show_board(
            pixmap if pixmap and not pixmap.isNull() else None,
            self.host.store.list_zones(side_row.id),
            self.host.store.list_components(side_row.id),
            self.host.view_mode,
            keep=keep,
        )
        if not self._fitted:
            self.map.fit_board()
            self._fitted = True
        elif selected:
            self.map.select_part(selected, center=False)

    def _switch_side(self, side: str) -> None:
        if self.board_id is None or side == self.side:
            return
        self.side = side
        self._fitted = False
        self.info.show_empty()
        self.reload(keep_view=False)

    def _set_mode(self, mode: str) -> None:
        self.map.mode = mode

    def _fit(self) -> None:
        self.map.fit_board()

    def _side_id(self) -> int | None:
        if self.board_id is None:
            return None
        return self.host.store.get_side(self.board_id, self.side).id

    def _set_photo(self) -> None:
        side_id = self._side_id()
        if side_id is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Photo of this side",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return
        relative = self.host.store.import_file(path, "images")
        self.host.store.set_overview(side_id, relative)
        self._fitted = False
        self.reload(keep_view=False)
        self.host.set_status("Photo saved with this board.")

    def _box_drawn(self, x: float, y: float, w: float, h: float) -> None:
        if self.map.mode == "zone":
            self._create_zone(x, y, w, h)
            return
        self._create_part(x, y, w, h, "box")

    def _create_zone(self, x: float, y: float, w: float, h: float) -> None:
        side_id = self._side_id()
        if side_id is None:
            return
        name, ok = QInputDialog.getText(self, "Name this area", "For example: Camera area, Charging, Power, Audio")
        if not ok:
            return
        nx, ny, nw, nh = norm_box(x, y, w, h, self.map.board_w, self.map.board_h)
        zone = self.host.store.add_zone(side_id, name.strip() or "Area", nx, ny, nw or 0.1, nh or 0.1)
        self.reload(keep_view=True)
        self.info.show_zone(zone.id)
        self.host.set_status("Zone added.")

    def _pin_dropped(self, x: float, y: float) -> None:
        self._create_part(x, y, None, None, "pin")

    def _create_part(self, x, y, w, h, shape: str) -> None:
        side_id = self._side_id()
        if side_id is None:
            return
        if shape == "zone":
            return
        dialog = NewPartDialog(self.host, self)
        if dialog.exec() != dialog.DialogCode.Accepted or not dialog.type_id:
            return
        nx, ny, nw, nh = norm_box(x, y, w or 0, h or 0, self.map.board_w, self.map.board_h)
        type_row = self.host.store.get_type(dialog.type_id)
        removal = type_row.default_removal if type_row else "not_practical"
        shield = "unopened" if dialog.type_id == "shield" else ""
        part = self.host.store.add_component(
            side_id,
            dialog.type_id,
            shape,
            nx,
            ny,
            nw,
            nh,
            removal=removal,
            removal_tool=DEFAULT_TOOL.get(removal, ""),
            shield_state=shield,
            identification="confirmed",
        )
        self.reload(keep_view=True)
        self.map.select_part(part.id, center=False)
        self.info.show_part(part.id)
        self.host.set_status("Part added. You can correct it in the panel.")

    def _moved(self, changes) -> None:
        for kind, row_id, geom in changes:
            x, y, w, h = geom
            if kind == "component":
                self.host.store.update_component(row_id, x=x, y=y, w=w, h=h)
            else:
                self.host.store.update_zone(row_id, x=x, y=y, w=w, h=h)
        self.reload(keep_view=True)
        self.host.set_status("Moved")

    def _part_changed(self, component_id: int) -> None:
        part = self.host.store.get_component(component_id)
        if part:
            self.map.apply_part(part)

    def _zone_changed(self, zone_id: int) -> None:
        zone = self.host.store.get_zone(zone_id)
        if zone:
            self.map.apply_zone(zone)
            self.info.show_zone(zone_id)

    def _copy_layout(self) -> None:
        if self.board_id is None:
            return
        board = self.host.store.get_board(self.board_id)
        phone = self.host.store.get_phone(board.phone_id) if board else None
        side = self.host.store.get_side(self.board_id, self.side)
        if phone is None:
            return
        sources = self.host.store.layout_sources(phone.make, phone.model, side.id)
        if not sources:
            QMessageBox.information(
                self,
                "Copy a layout",
                "No other board of this make and model is in the catalogue yet. "
                "The model name has to match.",
            )
            return
        dialog = CopyLayoutDialog(sources, self)
        if dialog.exec() != dialog.DialogCode.Accepted or dialog.side_id is None:
            return
        existing = self.host.store.list_components(side.id) or self.host.store.list_zones(side.id)
        if existing:
            answer = QMessageBox.question(
                self,
                "Replace this side?",
                "This replaces the parts and zones on the side you are looking at.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.host.store.copy_layout(dialog.side_id, side.id)
        self.info.show_empty()
        self.reload(keep_view=True)
        self.host.set_status("Layout copied. Dashed boxes are not confirmed yet.")

    def _details(self) -> None:
        if self.board_id is None:
            return
        board = self.host.store.get_board(self.board_id)
        if board is None:
            return
        dialog = BoardDetailsDialog(board, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self.host.store.update_board(board.id, **dialog.values())
        self.reload(keep_view=True)
        self.host.set_status("Board details saved.")

    def _label(self) -> None:
        if self.board_id is None:
            return
        board = self.host.store.get_board(self.board_id)
        phone = self.host.store.get_phone(board.phone_id) if board else None
        if board is None or phone is None:
            return
        lines = [
            f"{phone.make} {phone.model}".strip(),
            board_type_label(board.board_type),
            f"Revision {board.revision}" if board.revision else "",
        ]
        LabelDialog(
            board.short_id,
            [line for line in lines if line],
            label_payload("board", board.short_id),
            self,
        ).exec()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._set_mode("select")
            for button in self.tools.buttons():
                if button.text() == "Select":
                    button.setChecked(True)
            return
        super().keyPressEvent(event)
