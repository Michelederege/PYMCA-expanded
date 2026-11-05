import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from phone_salvage.gui.main_window import MainWindow
from phone_salvage.gui.theme import apply_theme


@pytest.fixture(scope="module")
def qapp():
    application = QApplication.instance() or QApplication([])
    apply_theme(application)
    yield application


def test_window_opens_the_sample_and_keeps_the_map_mode(qapp, tmp_path) -> None:
    window = MainWindow(tmp_path / "home")
    window.resize(1200, 800)
    window.show()
    qapp.processEvents()
    phones = window.store.list_phones()
    assert [phone.short_id for phone in phones] == ["PH-001", "PH-002"]
    board = window.store.list_boards(phones[0].id)[0]
    window.open_board(board.id)
    QTest.qWait(30)
    parts = window.board_page.map._parts
    assert parts
    transform = window.board_page.map.transform()
    window.set_view_mode("detailed")
    detailed = sum(item.isVisible() for item in window.board_page.map._parts)
    window.set_view_mode("simple")
    simple = sum(item.isVisible() for item in window.board_page.map._parts)
    assert simple < detailed
    assert window.board_page.map.transform().m11() == pytest.approx(transform.m11())
    window.harvest.reload()
    assert window.harvest.table.rowCount() >= 1
    window.inventory.reload()
    assert window.inventory.table.rowCount() >= 1
    image = window.grab()
    assert not image.isNull()
    assert image.width() > 100
    window.close()
