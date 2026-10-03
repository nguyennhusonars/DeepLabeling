"""Entry point: `python -m deeplabeling` opens the main window."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMainWindow


def build_window() -> QMainWindow:
    """The main window. Empty until the app design says what goes in it."""
    window = QMainWindow()
    window.setWindowTitle("DeepLabeling")
    window.resize(1280, 800)
    return window


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    window = build_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
