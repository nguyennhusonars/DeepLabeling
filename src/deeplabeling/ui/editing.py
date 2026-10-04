"""What the mouse and the editing keys do to the image on screen
(docs/design/2026-10-04-app-foundation.md#window).

Each gesture becomes an intent built by ui/actions.py and goes through Session.apply;
nothing here writes a file. This holds the one Selection and reads and sets the active
class, which is stored by name for each opening.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

from ..core.edits import Intent
from ..core.geometry import px_to_norm
from ..core.store import ImageLabels
from ..core.workspace import ACTIVE_CLASS, CLASS_COLORS, CLASS_HOTKEYS
from . import actions
from .canvas import Canvas
from .classes import ClassInfo, class_infos, class_with_hotkey
from .selection import Selection
from .session import Session


def _last(n: int) -> Callable[[ImageLabels], list[int]]:
    """The last `n` boxes of a file: where added boxes land."""
    return lambda labels: [i for i, _ in labels.boxes][-n:]


class Editing(QObject):
    activeChanged = Signal()

    def __init__(self, session: Session, canvas: Canvas, prompter, parent=None):
        super().__init__(parent)
        self.session, self.canvas, self.prompter = session, canvas, prompter
        self.selection = Selection(self)
        canvas.drawn.connect(self.draw)
        canvas.picked.connect(self.pick)
        canvas.moved.connect(self.move)
        canvas.resized.connect(self.resize)
        self.selection.changed.connect(self._selection_changed)
        session.cursorChanged.connect(self.selection.clear)
        session.opened.connect(self._active_changed)

    # -- the image being edited ----------------------------------------------------------

    def _current(self) -> tuple[Path, ImageLabels] | None:
        """The current image and its labels, while that image is on the canvas."""
        item = self.session.current()
        if item is None or self.session.workspace is None or self.canvas.image_size is None:
            return None
        return item.entry.path, self.session.labels(item.entry)

    def selected(self) -> list[int]:
        current = self._current()
        return self.selection.indices(current[1]) if current else []

    def _selection_changed(self) -> None:
        self.canvas.set_selected(self.selected())

    def _apply(self, intent: Intent | None, select=None) -> None:
        """Apply an intent; then select `select` -- indices, or a function of the new labels."""
        if intent is None or self.session.apply(intent) is None or select is None:
            return
        labels = self.session.workspace.store.get(intent.image)
        self.selection.select(labels, select(labels) if callable(select) else select)

    def _norm(self, rect):
        return px_to_norm(*rect, *self.canvas.image_size)

    # -- classes ------------------------------------------------------------------------------

    def classes(self) -> list[ClassInfo]:
        ws = self.session.workspace
        if ws is None:
            return []
        return class_infos(ws.dataset, ws.root_settings.get(CLASS_COLORS), ws.root_settings.get(CLASS_HOTKEYS))

    def active_class(self) -> ClassInfo | None:
        """The class a drawn box gets: the one chosen for this opening, else the first."""
        infos = self.classes()
        if not infos:
            return None
        name = self.session.workspace.opening_settings.get(ACTIVE_CLASS)
        return next((info for info in infos if info.name == name), infos[0])

    def set_active(self, info: ClassInfo) -> None:
        self.session.workspace.opening_settings.set(ACTIVE_CLASS, info.name)
        self.session.saver.schedule()
        self._active_changed()

    def _active_changed(self) -> None:
        active = self.active_class()
        if active is not None:
            self.canvas.set_draw_color(active.color)
        self.activeChanged.emit()

    def choose_class(self, info: ClassInfo) -> None:
        """Reclassify the selection, or make `info` the active class when nothing is selected."""
        current = self._current()
        indices = self.selected()
        if current and indices:
            image, labels = current
            self._apply(actions.reclassify(image, labels, indices, info.cls_id), select=indices)
        elif self.session.workspace is not None:
            self.set_active(info)

    def class_key(self, key: str) -> None:
        info = class_with_hotkey(self.classes(), key)
        if info is None:
            if self.session.workspace is not None:
                self.session.status.emit(f"no class has the key {key}")
            return
        self.choose_class(info)

    def pick_class(self) -> None:
        infos = self.classes()
        if infos:
            chosen = self.prompter.pick_class(infos)
            if chosen is not None:
                self.choose_class(chosen)

    # -- the canvas's gestures ------------------------------------------------------------

    def draw(self, rect) -> None:
        current, active = self._current(), self.active_class()
        if current and active is not None:
            self._apply(actions.add_box(current[0], active.cls_id, self._norm(rect)), select=_last(1))

    def pick(self, indices: list[int]) -> None:
        current = self._current()
        if current:
            self.selection.select(current[1], indices)

    def move(self, dx: float, dy: float) -> None:
        current = self._current()
        if current:
            image, labels = current
            w, h = self.canvas.image_size
            indices = self.selection.indices(labels)
            self._apply(actions.move(image, labels, indices, dx / w, dy / h), select=indices)

    def resize(self, index: int, rect) -> None:
        current = self._current()
        if current:
            image, labels = current
            self._apply(actions.resize(image, labels, index, self._norm(rect)), select=[index])

    # -- the editing keys -----------------------------------------------------------------

    def delete(self) -> None:
        current = self._current()
        if current:
            image, labels = current
            self._apply(actions.delete(image, labels, self.selection.indices(labels)), select=[])

    def select_step(self, step: int) -> None:
        """Select the next (+1) or previous (-1) box after the selection, wrapping round."""
        current = self._current()
        if not current:
            return
        labels = current[1]
        boxes = [i for i, _ in labels.boxes]
        if not boxes:
            return
        indices = self.selection.indices(labels)
        if not indices:
            target = boxes[0] if step > 0 else boxes[-1]
        else:
            at = boxes.index(indices[-1] if step > 0 else indices[0])
            target = boxes[(at + step) % len(boxes)]
        self.selection.select(labels, [target])

    def select_all(self) -> None:
        current = self._current()
        if current:
            self.selection.select(current[1], [i for i, _ in current[1].boxes])

    def escape(self) -> None:
        if not self.canvas.cancel_drag():
            self.selection.clear()

    def copy(self) -> None:
        current = self._current()
        if not current:
            return
        indices = self.selected()
        text = actions.copy_text(current[1], indices)
        if text:
            QGuiApplication.clipboard().setText(text)
            n = len(text.splitlines())
            self.session.status.emit(f"copied {n} box" if n == 1 else f"copied {n} boxes")

    def paste(self) -> None:
        current = self._current()
        if not current:
            return
        intent = actions.paste(current[0], QGuiApplication.clipboard().text(),
                               self.session.workspace.dataset.known)
        if intent is None:
            self.session.status.emit("the clipboard holds no boxes to paste")
            return
        self._apply(intent, select=_last(len(intent.ops)))
