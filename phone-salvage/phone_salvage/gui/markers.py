"""Status shapes shared by the map and the legend."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen

from phone_salvage.gui.theme import INK, STATUS_COLOR


def paint_marker(
    painter: QPainter,
    status: str,
    *,
    suggested: bool = False,
    selected: bool = False,
    removed: bool = False,
) -> None:
    color = QColor(STATUS_COLOR.get(status, STATUS_COLOR["not_checked"]))
    fill = QColor(color)
    fill.setAlpha(70 if suggested else 220)
    if suggested:
        color.setAlpha(160)
    pen = QPen(color, 2.6 if selected else 1.8)
    if suggested:
        pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(QBrush(fill))
    if status == "usable":
        painter.drawEllipse(QRectF(-8, -8, 16, 16))
    elif status == "maybe":
        painter.drawPolygon(
            [QPointF(0, -9), QPointF(9, 0), QPointF(0, 9), QPointF(-9, 0)]
        )
    elif status == "junk":
        painter.drawRoundedRect(QRectF(-7, -7, 14, 14), 2, 2)
    else:
        painter.drawPolygon([QPointF(0, -9), QPointF(8, 7), QPointF(-8, 7)])
    if removed:
        painter.setPen(QPen(QColor(INK), 1.6))
        painter.drawLine(QPointF(-8, -8), QPointF(8, 8))
