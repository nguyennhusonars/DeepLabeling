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
        self._shown: ImageLabels | None = None      # what the canvas draws; its indices mean these
        self._applying: tuple | None = None         # (image, what to select) while an edit applies
        self._copied: tuple[str, tuple[str, ...]] | None = None    # (text, the class names it used)
        canvas.drawn.connect(self.draw)
        canvas.picked.connect(self.pick)
        canvas.moved.connect(self.move)
        canvas.resized.connect(self.resize)
        self.selection.changed.connect(self._selection_changed)
        session.cursorChanged.connect(self.selection.clear)
        session.opened.connect(self._active_changed)
        # Before the window and the inspector redraw for an edit, the edit's selection is
        # set, so the canvas is drawn once with it: Editing connects ahead of them.
        session.labelsChanged.connect(self._labels_changed)

    # -- the image being edited ----------------------------------------------------------

    def show(self, labels: ImageLabels) -> None:
        """The labels the canvas now draws. The file can change before the canvas is
        redrawn, so an index the canvas reports means a line of THIS snapshot: it is
        turned into a box identity here, and the core locates that box in the file."""
        self._shown = labels

    def _current(self) -> tuple[Path, ImageLabels] | None:
        """The current image and its labels, while that image is on the canvas with its
        labels shown: hidden boxes are never acted on."""
        item = self.session.current()
        if (item is None or self.session.workspace is None or self.canvas.image_size is None
                or not self.canvas.show_labels):
            return None
        return item.entry.path, self.session.labels(item.entry)

    def selected(self) -> list[int]:
        current = self._current()
        return self.selection.indices(current[1]) if current else []

    def _selection_changed(self) -> None:
        if self._applying is not None:
            return                                  # the edit's own redraw shows it
        self.canvas.set_selected(self.selection.indices(self._shown) if self._shown is not None else [])

    def _apply(self, intent: Intent | None, select=None) -> bool:
        """Apply an intent, selecting `select` -- indices, or a function of the new labels --
        as its labels change. False when there was nothing to apply or it was refused."""
        if intent is None:
            return False
        self._applying = (intent.image, select)
        try:
            return self.session.apply(intent) is not None
        finally:
            self._applying = None

    def _labels_changed(self, images) -> None:
        if self._applying is None:
            return
        image, select = self._applying
        if select is None or image not in images:
            return
        labels = self.session.workspace.store.get(image)
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

    def pick(self, indices: list[int], labels: ImageLabels | None = None) -> None:
        """Select boxes by their indices in `labels`, the snapshot they were shown from
        (the canvas's unless given), so a file changed since selects the same boxes."""
        labels = self._shown if labels is None else labels      # before _current(): a re-read redraws
        current = self._current()
        if current and labels is not None and labels.image == current[0]:
            self.selection.select(labels, indices)

    def move(self, dx: float, dy: float) -> None:
        current = self._current()
        if current:
            image, labels = current
            w, h = self.canvas.image_size
            indices = self.selection.indices(labels)
            self._apply(actions.move(image, labels, indices, dx / w, dy / h), select=indices)

    def resize(self, index: int, rect) -> None:
        shown = self._shown                         # before _current(): a re-read redraws
        current = self._current()
        if current and shown is not None and shown.image == current[0]:
            image, labels = current
            self._apply(actions.resize(image, shown, index, self._norm(rect)),
                        select=self.selection.indices(labels))      # the one box with handles

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
        labels, indices = current[1], self.selected()
        text = actions.copy_text(labels, indices)
        polygons = sum(1 for i in indices if labels.lines[i].is_polygon)
        said = []
        if text:
            QGuiApplication.clipboard().setText(text)
            self._copied = (text, self.session.workspace.dataset.names)
            n = len(text.splitlines())
            said.append(f"copied {n} box" if n == 1 else f"copied {n} boxes")
        if polygons:
            said.append("1 polygon is not copied: a paste would make it a box" if polygons == 1 else
                        f"{polygons} polygons are not copied: a paste would make them boxes")
        if said:
            self.session.status.emit("; ".join(said))

    def paste(self) -> None:
        current = self._current()
        if not current:
            return
        text, dataset = QGuiApplication.clipboard().text(), self.session.workspace.dataset
        lines = sum(1 for line in text.splitlines() if line.strip())
        copied = self._copied
        if copied is not None and copied[0] == text and copied[1] and dataset.names and copied[1] != dataset.names:
            # Copied under another class list of this root: the ids follow their names.
            text, _ = actions.remap_classes(text, copied[1], dataset.names)
        intent = actions.paste(current[0], text, dataset.known)
        if intent is None:
            self.session.status.emit("the clipboard holds no boxes to paste")
            return
        n = len(intent.ops)
        if self._apply(intent, select=_last(n)):
            said = f"pasted {n} box" if n == 1 else f"pasted {n} boxes"
            skipped = lines - n
            if skipped:
                said += (f"; 1 line was not a box of this dataset's classes" if skipped == 1 else
                         f"; {skipped} lines were not boxes of this dataset's classes")
            self.session.status.emit(said)
