"""Always-visible key for colours, shapes, and line styles."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from phone_salvage.gui.markers import paint_marker
from phone_salvage.gui.theme import INK, LINE, MUTED, PANEL


class LegendBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(72)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(PANEL))
        painter.setPen(QColor(LINE))
        painter.drawLine(0, 0, self.width(), 0)
        entries = (
            ("usable", False, False, "Usable"),
            ("maybe", False, False, "Maybe"),
            ("junk", False, False, "Junk"),
            ("not_checked", False, False, "Not yet checked"),
        )
        x = 16
        for status, suggested, removed, label in entries:
            painter.save()
            painter.translate(x + 10, 26)
            paint_marker(painter, status, suggested=suggested, removed=removed)
            painter.restore()
            painter.setPen(QColor(INK))
            painter.drawText(QRectF(x + 24, 14, 130, 24), Qt.AlignmentFlag.AlignVCenter, label)
            x += 150
        painter.setPen(QColor(MUTED))
        painter.drawText(
            QRectF(16, 44, self.width() - 32, 22),
            "Dashed or faded: not confirmed.  Shaded area: a zone.  Slash: removed, still on the map.",
        )
