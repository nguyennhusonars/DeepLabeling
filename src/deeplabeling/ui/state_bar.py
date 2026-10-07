"""The state bar (docs/design/2026-10-04-app-foundation.md#window): a row of chips, always
visible, each showing a setting in force; clicking a chip changes it."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QMenu, QSizePolicy, QToolButton, QWidget

from .session import Session

#: The fewest milliseconds between refreshes while a queue builds.
REFRESH_MS = 250


class Chip(QToolButton):
    """Its short text when it fits, elided when not, and the setting in full words as its
    tooltip: a chip squeezed by a narrow window still shows that its setting exists."""

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

    def set_full_text(self, text: str, tip: str | None = None) -> None:
        self._full = text
        self.setToolTip(tip or text)
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


def model_text(model) -> str:
    """The model chip: 🧠, the weights, the threshold and how much of the queue is inferred."""
    if model.state == "none":
        return "🧠 load a model"
    name = model.path.name
    if model.state == "loading":
        return f"🧠 {name} · loading…"
    if model.state == "failed":
        return f"🧠 {name} · failed"
    text = f"🧠 {name} · ≥{model.conf:.2f}"
    if model.passing:
        return text + f" · inferring {model.pass_walked:,}/{model.pass_total:,}"
    counted = model.inferred_count()
    return text if counted is None else text + f" · {counted[0]:,}/{counted[1]:,} inferred"


def model_tip(model) -> str:
    """The model chip in full words."""
    if model.state == "none":
        return "No model loaded. Click to load one."
    if model.state != "ready":
        return f"Model {model.path} — {model.state}" + (f": {model.error}" if model.error else "")
    return (f"Model {model.path}\n{len(model.names)} classes · predictions shown at confidence ≥ {model.conf:.2f}"
            "\nClick for the threshold, the class map, inferring and accepting.")


class StateBar(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self.dataset, self.queue, self.layers, self.reviewed = Chip(), Chip(), Chip(), Chip()
        self.model = Chip()
        for chip in (self.dataset, self.model, self.layers):
            chip.setPopupMode(QToolButton.InstantPopup)
            chip.setMenu(QMenu(chip))
        # A click on the queue chip edits the queue; its arrow offers what acts on the queue
        # (docs/design/2026-10-07-bulk-and-stats.md#the-queue-chip).
        self.queue.setPopupMode(QToolButton.MenuButtonPopup)
        self.queue.setMenu(QMenu(self.queue))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        for chip, stretch in ((self.dataset, 3), (self.queue, 4), (self.model, 3), (self.layers, 1),
                              (self.reviewed, 1)):
            layout.addWidget(chip, stretch)
        for signal in (session.opened, session.closed, session.queueReset,
                       session.queueDone, session.reviewChanged):
            signal.connect(self.refresh)
        session.model.changed.connect(self.refresh)
        session.model.progress.connect(self._refresh_model)
        session.model.ready.connect(self._refresh_model)
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

    def _refresh_model(self, _=None) -> None:
        self.model.set_full_text(model_text(self._session.model), model_tip(self._session.model))

    def refresh(self) -> None:
        session, ws = self._session, self._session.workspace
        if ws is None:
            self.dataset.set_full_text("📁 open a dataset", "No dataset open. Click to open a yaml or an image folder.")
            self.queue.set_full_text("☰ —", "The queue: open a dataset first.")
            self.reviewed.set_full_text("✓ —", "Images reviewed: open a dataset first.")
        else:
            d = ws.dataset
            self.dataset.set_full_text(f"📁 {d.root.name} · {'+'.join(d.splits)} · {len(d.images):,}",
                                       f"{d.root}\n{d.source.name}: {' + '.join(d.splits)}, {len(d.images):,} images"
                                       "\nClick to open another.")
            q = session.queue
            if q is None:
                self.queue.set_full_text("☰ —", "The queue: none yet.")
            else:
                left, progress = session.left(), session.progress_text()
                self.queue.set_full_text(f"☰ {q.source.describe(d)} · {left:,} left of {len(q):,}{progress}",
                                         f"Queue: {q.source.describe(d)}\n{len(q):,} items, {left:,} not reviewed"
                                         f"{progress}\nClick to edit it; ▾ to reassign a class or see statistics.")
            marked, total = session.reviewed_counts()
            self.reviewed.set_full_text(f"✓ {marked:,}/{total:,}", f"{marked:,} of {total:,} images reviewed")
        self.model.set_full_text(model_text(session.model), model_tip(session.model))
        shown = [a.text().lower() for a in self.layers.menu().actions() if a.isChecked()]
        self.layers.set_full_text("👁 " + (" · ".join(shown) if shown else "none"),
                                  "Layers shown on the canvas: " + (", ".join(shown) if shown else "none"))
