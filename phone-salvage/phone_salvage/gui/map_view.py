"""Zoomable board map. Coordinates on the items are fractions of the overview."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsObject, QGraphicsPixmapItem, QGraphicsView, QGraphicsScene

from phone_salvage.geometry import norm_box
from phone_salvage.gui.markers import paint_marker
from phone_salvage.gui.theme import ACCENT, INK, MUTED, PANEL, ZONE_COLORS
from phone_salvage.present import shown_in_simple
from phone_salvage.store import Component, Zone

ROLE_KIND = 0
ROLE_ID = 1
BLANK_W = 900
BLANK_H = 1500


class PartItem(QGraphicsObject):
    def __init__(self, part: Component, board_w: float, board_h: float):
        super().__init__()
        self.part = part
        self.board_w = board_w
        self.board_h = board_h
        self.view_mode = "simple"
        self.lod = 1.0
        self.setData(ROLE_KIND, "component")
        self.setData(ROLE_ID, part.id)
        self.setFlags(
            QGraphicsObject.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsObject.GraphicsItemFlag.ItemIsMovable
            | QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        if part.shape == "pin" or not part.w or not part.h:
            self._box = False
            self._w = 0.0
            self._h = 0.0
            self.setPos(part.x * board_w, part.y * board_h)
            self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIgnoresTransformations, True)
        else:
            self._box = True
            self._w = part.w * board_w
            self._h = part.h * board_h
            self.setPos(part.x * board_w, part.y * board_h)
        self.setZValue(2)

    def set_view(self, mode: str, lod: float) -> None:
        self.prepareGeometryChange()
        self.view_mode = mode
        self.lod = max(lod, 0.05)
        hide = (
            mode == "simple"
            and not shown_in_simple(self.part.beginner_important, self.part.show_in_simple)
            and not self.isSelected()
        )
        self.setVisible(not hide)
        self.update()

    def norm_geom(self) -> tuple[float, float, float | None, float | None]:
        pos = self.scenePos() if not self._box else self.pos()
        if not self._box:
            return norm_box(pos.x(), pos.y(), 0, 0, self.board_w, self.board_h)
        return norm_box(self.pos().x(), self.pos().y(), self._w, self._h, self.board_w, self.board_h)

    def boundingRect(self) -> QRectF:
        if not self._box:
            return QRectF(-70, -28, 140, 56)
        pad = 20 / self.lod
        rect = QRectF(0, 0, self._w, self._h)
        return rect.adjusted(-pad, -pad - (16 / self.lod), pad, pad)

    def paint(self, painter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        suggested = self.part.identification != "confirmed"
        if self._box:
            color = QColor(self._status_color())
            pen = QPen(color, 2)
            if suggested:
                pen.setStyle(Qt.PenStyle.DashLine)
                color.setAlpha(150)
                pen.setColor(color)
            if self.isSelected():
                pen.setWidth(3)
            painter.setPen(pen)
            fill = QColor(color)
            fill.setAlpha(36)
            painter.setBrush(QBrush(fill))
            painter.drawRect(QRectF(0, 0, self._w, self._h))
            painter.save()
            center = QPointF(self._w / 2, self._h / 2)
            painter.translate(center)
            painter.scale(1 / self.lod, 1 / self.lod)
            self._paint_marker_and_label(painter, suggested)
            painter.restore()
        else:
            self._paint_marker_and_label(painter, suggested)

    def _paint_marker_and_label(self, painter, suggested: bool) -> None:
        paint_marker(
            painter,
            self.part.status,
            suggested=suggested,
            selected=self.isSelected(),
            removed=self.part.removed,
        )
        if not self._label_on():
            return
        painter.setPen(QColor(INK))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(QRectF(-80, 10, 160, 18), Qt.AlignmentFlag.AlignHCenter, self._label())

    def _label_on(self) -> bool:
        important = shown_in_simple(self.part.beginner_important, self.part.show_in_simple)
        if self.view_mode == "simple":
            return important and self.lod >= 0.25
        if important:
            return self.lod >= 0.35
        return self.lod >= 0.9

    def _label(self) -> str:
        name = self.part.type_plain or "Part"
        if self.view_mode == "detailed" and self.lod >= 1.5 and self.part.designator:
            return f"{name}  {self.part.designator}"
        if self.view_mode == "detailed" and self.lod >= 2.2 and self.part.marking_code:
            return f"{name}  {self.part.marking_code}"
        return name

    def _status_color(self) -> str:
        from phone_salvage.gui.theme import STATUS_COLOR

        return STATUS_COLOR.get(self.part.status, STATUS_COLOR["not_checked"])


class ZoneItem(QGraphicsObject):
    def __init__(self, zone: Zone, board_w: float, board_h: float, color: str):
        super().__init__()
        self.zone = zone
        self.board_w = board_w
        self.board_h = board_h
        self.color = color
        self.lod = 1.0
        self._w = zone.w * board_w
        self._h = zone.h * board_h
        self.setPos(zone.x * board_w, zone.y * board_h)
        self.setData(ROLE_KIND, "zone")
        self.setData(ROLE_ID, zone.id)
        self.setFlags(
            QGraphicsObject.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsObject.GraphicsItemFlag.ItemIsMovable
            | QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(1)

    def set_lod(self, lod: float) -> None:
        self.prepareGeometryChange()
        self.lod = max(lod, 0.05)
        self.update()

    def norm_geom(self) -> tuple[float, float, float, float]:
        x, y, w, h = norm_box(self.pos().x(), self.pos().y(), self._w, self._h, self.board_w, self.board_h)
        return x, y, w or 0.01, h or 0.01

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h).adjusted(0, -18 / self.lod, 0, 0)

    def paint(self, painter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(self.color)
        fill = QColor(color)
        fill.setAlpha(42)
        pen = QPen(color, 1.5)
        if not self.zone.confirmed:
            pen.setStyle(Qt.PenStyle.DashLine)
        if self.isSelected():
            pen.setWidth(2.5)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(QRectF(0, 0, self._w, self._h), 8, 8)
        if self.lod > 2.4:
            return
        painter.save()
        painter.translate(8, 4)
        painter.scale(1 / self.lod, 1 / self.lod)
        painter.setPen(QColor(INK))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, 220, 18), self.zone.name)
        painter.restore()


class MapView(QGraphicsView):
    partSelected = Signal(int)
    zoneSelected = Signal(int)
    selectionCleared = Signal()
    boxDrawn = Signal(float, float, float, float)
    pinDropped = Signal(float, float)
    geometriesChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor(PANEL))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.mode = "select"
        self.board_w = float(BLANK_W)
        self.board_h = float(BLANK_H)
        self._parts: list[PartItem] = []
        self._zones: list[ZoneItem] = []
        self._part_by_id: dict[int, PartItem] = {}
        self._rebuilding = False
        self._panning = False
        self._pan_pos = None
        self._origin: QPointF | None = None
        self._band = None
        self._view_mode = "simple"
        self.scene().selectionChanged.connect(self._on_selection)

    def show_board(
        self,
        pixmap: QPixmap | None,
        zones: list[Zone],
        parts: list[Component],
        view_mode: str,
        *,
        keep: tuple | None = None,
    ) -> None:
        self._rebuilding = True
        self._view_mode = view_mode
        scene = self.scene()
        scene.clear()
        self._parts = []
        self._zones = []
        self._part_by_id = {}
        self._band = None
        if pixmap is not None and not pixmap.isNull():
            self.board_w = float(pixmap.width())
            self.board_h = float(pixmap.height())
            item = QGraphicsPixmapItem(pixmap)
            item.setZValue(0)
            scene.addItem(item)
        else:
            self.board_w = float(BLANK_W)
            self.board_h = float(BLANK_H)
            from PySide6.QtWidgets import QGraphicsTextItem

            note = QGraphicsTextItem("No photo yet. Set a photo, or mark parts on this blank board.")
            note.setDefaultTextColor(QColor(MUTED))
            note.setPos(24, 16)
            note.setZValue(3)
            note.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            scene.addItem(note)
        scene.setSceneRect(0, 0, self.board_w, self.board_h)
        for index, zone in enumerate(zones):
            item = ZoneItem(zone, self.board_w, self.board_h, ZONE_COLORS[index % len(ZONE_COLORS)])
            scene.addItem(item)
            self._zones.append(item)
        for part in parts:
            item = PartItem(part, self.board_w, self.board_h)
            scene.addItem(item)
            self._parts.append(item)
            self._part_by_id[part.id] = item
        self._rebuilding = False
        if keep is not None:
            transform, center = keep
            self.setTransform(transform)
            self.centerOn(center)
        self.push_lod()

    def view_state(self) -> tuple:
        center = self.mapToScene(self.viewport().rect().center())
        return self.transform(), center

    def push_lod(self) -> None:
        lod = self.transform().m11() or 1.0
        for part in self._parts:
            part.set_view(self._view_mode, lod)
        for zone in self._zones:
            zone.set_lod(lod)

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        self.push_lod()

    def fit_board(self) -> None:
        self.fitInView(QRectF(0, 0, self.board_w, self.board_h), Qt.AspectRatioMode.KeepAspectRatio)
        self.push_lod()

    def select_part(self, component_id: int, *, center: bool) -> None:
        item = self._part_by_id.get(component_id)
        if item is None:
            return
        self.scene().clearSelection()
        item.setSelected(True)
        if center:
            self.centerOn(item.sceneBoundingRect().center())

    def selected_part_id(self) -> int | None:
        for item in self.scene().selectedItems():
            if item.data(ROLE_KIND) == "component":
                return int(item.data(ROLE_ID))
        return None

    def apply_part(self, part: Component) -> None:
        item = self._part_by_id.get(part.id)
        if item is None:
            return
        item.part = part
        item.set_view(self._view_mode, self.transform().m11() or 1.0)

    def apply_zone(self, zone: Zone) -> None:
        for item in self._zones:
            if item.zone.id == zone.id:
                item.zone = zone
                item.update()
                return

    def _on_selection(self) -> None:
        if self._rebuilding:
            return
        parts = []
        zones = []
        for item in self.scene().selectedItems():
            kind = item.data(ROLE_KIND)
            if kind == "component":
                parts.append(int(item.data(ROLE_ID)))
            elif kind == "zone":
                zones.append(int(item.data(ROLE_ID)))
        if parts:
            self.partSelected.emit(parts[-1])
        elif zones:
            self.zoneSelected.emit(zones[-1])
        else:
            self.selectionCleared.emit()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_scale = (self.transform().m11() or 1) * factor
        if new_scale < 0.12 or new_scale > 24:
            return
        self.scale(factor, factor)
        self.push_lod()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
            self.mode == "select"
            and event.button() == Qt.MouseButton.LeftButton
            and self._top_marked(event.position().toPoint()) is None
        ):
            self._panning = True
            self._pan_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self.mode in ("box", "zone") and event.button() == Qt.MouseButton.LeftButton:
            self._origin = self.mapToScene(event.position().toPoint())
            self._band = self.scene().addRect(QRectF(self._origin, self._origin), self._band_pen(), self._band_brush())
            self._band.setZValue(4)
            event.accept()
            return
        if self.mode == "pin" and event.button() == Qt.MouseButton.LeftButton:
            point = self.mapToScene(event.position().toPoint())
            self.pinDropped.emit(point.x(), point.y())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._pan_pos is not None:
            current = event.position().toPoint()
            delta = current - self._pan_pos
            self._pan_pos = current
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        if self._origin is not None and self._band is not None:
            point = self.mapToScene(event.position().toPoint())
            self._band.setRect(QRectF(self._origin, point).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._panning:
            self._panning = False
            self._pan_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if self._origin is not None and self._band is not None:
            rect = self._band.rect()
            self.scene().removeItem(self._band)
            self._band = None
            self._origin = None
            if rect.width() > 8 and rect.height() > 8:
                self.boxDrawn.emit(rect.x(), rect.y(), rect.width(), rect.height())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._emit_moves()

    def _emit_moves(self) -> None:
        changes = []
        for item in self._parts:
            geom = item.norm_geom()
            original = (
                item.part.x,
                item.part.y,
                item.part.w,
                item.part.h,
            )
            if _moved(original, geom):
                changes.append(("component", item.part.id, geom))
        for item in self._zones:
            geom = item.norm_geom()
            original = (item.zone.x, item.zone.y, item.zone.w, item.zone.h)
            if _moved(original, geom):
                changes.append(("zone", item.zone.id, geom))
        if changes:
            self.geometriesChanged.emit(changes)

    def _top_marked(self, pos):
        for item in self.items(pos):
            if item.data(ROLE_KIND) in ("component", "zone"):
                return item
        return None

    def _band_pen(self) -> QPen:
        pen = QPen(QColor(ACCENT))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        return pen

    def _band_brush(self) -> QBrush:
        return QBrush(QColor(31, 78, 95, 36))


def _moved(original, geom) -> bool:
    for left, right in zip(original, geom):
        if left is None and right is None:
            continue
        if left is None or right is None:
            return True
        if abs(float(left) - float(right)) > 0.002:
            return True
    return False
