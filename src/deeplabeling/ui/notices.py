"""The notice strip (docs/design/2026-10-04-app-foundation.md#window): every refusal and
error stays above the canvas until it is dismissed, or the next edit of its image
succeeds. Progress never comes here -- in the legacy app, a refusal shown in the status
bar was overwritten by progress within 150 ms."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

COLORS = {"error": "#5c1f1f", "warning": "#5c4a1f", "info": "#1f3a5c"}
ICONS = {"error": "✖", "warning": "⚠", "info": "ℹ"}
#: The most notices shown at once; older ones go first.
MAX_ROWS = 6
#: A notice longer than this shows shortened, the whole of it in its tooltip: a 6,000-character
#: notice once left the canvas 70 px at 1024 x 640.
MAX_CHARS = 400


class NoticeRow(QFrame):
    dismissed = Signal(object)

    def __init__(self, level: str, text: str, image: Path | None, key: str | None, parent=None):
        super().__init__(parent)
        self.level, self.text, self.image, self.key = level, text, image, key
        self.setObjectName("notice")
        self.setStyleSheet(f"#notice {{ background: {COLORS.get(level, COLORS['info'])}; }}"
                           " QLabel { color: #f0f0f0; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 4, 3)
        shown = text if len(text) <= MAX_CHARS else text[:MAX_CHARS].rstrip() + " …"
        self.label = QLabel(f"{ICONS.get(level, ICONS['info'])} {shown}")
        self.setToolTip(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        close = QToolButton()
        close.setText("×")
        close.setAutoRaise(True)
        close.setFocusPolicy(Qt.NoFocus)
        close.clicked.connect(self._dismiss)       # a method: a lambda slot would never be freed
        layout.addWidget(self.label, 1)
        layout.addWidget(close)
        self.close_button = close

    def _dismiss(self) -> None:
        self.dismissed.emit(self)


class NoticeStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(1)
        self.rows: list[NoticeRow] = []
        self.hide()

    def add(self, level: str, text: str, image: Path | None = None, key: str | None = None) -> None:
        """Show a notice, newest first. A keyed notice replaces the one with its key;
        a keyed notice with no text just removes it."""
        if key is not None:
            self.clear_key(key)
        if not text:
            return
        if key is None and any(r.text == text and r.image == image for r in self.rows if r.key is not None):
            return                                  # a standing notice says it already
        for again in [r for r in self.rows if r.text == text and r.image == image and r.key is None]:
            self._remove(again)                     # said again: one row, back at the top
        row = NoticeRow(level, text, image, key, self)
        row.dismissed.connect(self._remove)
        self.rows.insert(0, row)
        self._layout.insertWidget(0, row)
        row.show()              # a layout shows a new child of a visible parent only later
        while len(self.rows) > MAX_ROWS:
            oldest = next((r for r in reversed(self.rows) if r.key is None), None)
            if oldest is None:
                break
            self._remove(oldest)                    # a standing notice is never pushed out
        self.show()

    def texts(self) -> list[str]:
        return [row.text for row in self.rows]

    def clear_image(self, images: Iterable[Path]) -> None:
        images = set(images)
        for row in [r for r in self.rows if r.image is not None and r.image in images and r.key is None]:
            self._remove(row)

    def clear_key(self, key: str) -> None:
        for row in [r for r in self.rows if r.key == key]:
            self._remove(row)

    def clear(self) -> None:
        for row in list(self.rows):
            self._remove(row)

    def _remove(self, row: NoticeRow) -> None:
        if row in self.rows:
            self.rows.remove(row)
            self._layout.removeWidget(row)
            row.deleteLater()
        if not self.rows:
            self.hide()
