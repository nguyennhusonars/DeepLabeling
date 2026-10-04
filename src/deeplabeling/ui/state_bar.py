"""The state bar (docs/design/2026-10-04-app-foundation.md#window): a row of chips, always
visible, each showing a setting in force; clicking a chip changes it."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QMenu, QSizePolicy, QToolButton, QWidget

from .session import Session

#: The fewest milliseconds between refreshes while a queue builds.
REFRESH_MS = 250


class Chip(QToolButton):
    """Its whole text when it fits, elided when not, and the whole text as its tooltip:
    a chip squeezed by a narrow window still shows that its setting exists."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAutoRaise(False)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._full = ""

    @property
    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 28, hint.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(48, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        room = max(self.width() - 20, 16)
        self.setText(self.fontMetrics().elidedText(self._full, Qt.ElideRight, room))


class StateBar(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self.dataset, self.queue, self.layers, self.reviewed = Chip(), Chip(), Chip(), Chip()
        self.dataset.setPopupMode(QToolButton.InstantPopup)
        self.dataset.setMenu(QMenu(self.dataset))
        self.layers.setPopupMode(QToolButton.InstantPopup)
        self.layers.setMenu(QMenu(self.layers))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        for chip, stretch in ((self.dataset, 3), (self.queue, 4), (self.layers, 1), (self.reviewed, 1)):
            layout.addWidget(chip, stretch)
        for signal in (session.opened, session.closed, session.queueReset,
                       session.queueDone, session.reviewChanged):
            signal.connect(self.refresh)
        # A building queue grows every 0.2 s, and each refresh counts what is left across
        # the whole queue; while it builds, refresh at most every REFRESH_MS.
        self._soon = QTimer(self)
        self._soon.setSingleShot(True)
        self._soon.setInterval(REFRESH_MS)
        self._soon.timeout.connect(self.refresh)
        session.queueGrew.connect(self._soon_once)
        self.refresh()

    def _soon_once(self) -> None:
        # Start the timer only when it is idle: restarting it on every batch would hold
        # the refresh off until the queue stopped growing.
        if not self._soon.isActive():
            self._soon.start()

    def refresh(self) -> None:
        session, ws = self._session, self._session.workspace
        if ws is None:
            self.dataset.set_full_text("No dataset · open one")
            self.queue.set_full_text("Queue: —")
            self.reviewed.set_full_text("Reviewed —")
        else:
            d = ws.dataset
            self.dataset.set_full_text(f"{d.root.name} · {d.source.name} · {' + '.join(d.splits)}"
                                       f" · {len(d.images):,} images")
            q = session.queue
            if q is None:
                self.queue.set_full_text("Queue: —")
            else:
                building = "" if q.complete else " · building…"
                self.queue.set_full_text(f"Queue: {q.source.describe(d)} · {len(q):,} · "
                                         f"{session.left():,} left{building}")
            marked, total = session.reviewed_counts()
            self.reviewed.set_full_text(f"Reviewed {marked:,} / {total:,}")
        shown = [a.text().lower() for a in self.layers.menu().actions() if a.isChecked()]
        self.layers.set_full_text("Layers: " + (", ".join(shown) if shown else "none"))
