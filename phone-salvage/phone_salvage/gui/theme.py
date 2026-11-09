"""Calm, readable colours for a bench tool. Status is never colour alone."""

from __future__ import annotations

PAPER = "#f3f0e8"
PANEL = "#fffcf8"
INK = "#1c1915"
MUTED = "#5e584e"
LINE = "#e3ddd2"
ACCENT = "#1f4e5f"
ACCENT_SOFT = "#e4eef1"

STATUS_COLOR = {
    "usable": "#1d6a4f",
    "maybe": "#a15c07",
    "junk": "#9b2c2c",
    "not_checked": "#4f636c",
}

ZONE_COLORS = ("#1f4e5f", "#8a5a12", "#2f6b4f", "#5c4d7a")

STYLESHEET = f"""
QMainWindow, QWidget {{
    background: {PAPER};
    color: {INK};
    font-size: 14px;
}}
QLabel#title {{
    font-size: 22px;
    font-weight: 600;
}}
QLabel#sectionTitle {{
    font-size: 12px;
    font-weight: 600;
    color: {MUTED};
}}
QLabel#quiet {{
    color: {MUTED};
}}
QLabel#verdict {{
    background: {ACCENT_SOFT};
    border-radius: 6px;
    padding: 8px;
}}
QListWidget, QTableWidget, QTreeWidget {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 6px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {INK};
}}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 4px;
    padding: 4px 6px;
    min-height: 22px;
}}
QPushButton {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 6px;
    padding: 6px 12px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:checked {{
    background: {ACCENT};
    color: white;
    border-color: {ACCENT};
}}
QPushButton#primary {{
    background: {ACCENT};
    color: white;
    border: none;
}}
QPushButton#danger {{
    color: #9b2c2c;
}}
QGroupBox {{
    font-weight: 600;
    border: 1px solid {LINE};
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    background: {PANEL};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {MUTED};
}}
QStatusBar {{
    color: {MUTED};
}}
QSplitter::handle {{
    background: {LINE};
}}
QScrollArea {{
    border: none;
}}
"""


def apply_theme(app) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
