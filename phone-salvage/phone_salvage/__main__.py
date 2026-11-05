import sys

from PySide6.QtWidgets import QApplication

from phone_salvage.gui.main_window import MainWindow
from phone_salvage.gui.theme import apply_theme


def main(argv: list[str] | None = None) -> int:
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("Phone Salvage")
    apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
