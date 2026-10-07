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

from ..core.assist import Shown, accept_image, accept_one
from ..core.edits import Intent, SetBox, SetClass
from ..core.geometry import px_to_norm
from ..core.labelio import locate_line
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
        self._predicted: tuple[Path, list[Shown] | None] | None = None    # the predictions it draws
        self._applying: tuple | None = None         # (image, what to select) while an edit applies
        self._arriving = False                      # the cursor is moving: the window redraws the new item
        self._copied: tuple[str, tuple[str, ...]] | None = None    # (text, the class names it used)
        canvas.drawn.connect(self.draw)
        canvas.picked.connect(self.pick)
        canvas.moved.connect(self.move)
        canvas.resized.connect(self.resize)
        self.selection.changed.connect(self._selection_changed)
        session.cursorChanged.connect(self._cursor_changed)
        session.opened.connect(self._active_changed)
        # Before the window and the inspector redraw for an edit, the edit's selection is
        # set, so the canvas is drawn once with it: Editing connects ahead of them.
        session.labelsChanged.connect(self._labels_changed)

    # -- the image being edited ----------------------------------------------------------

    def _cursor_changed(self) -> None:
        """A new item: a finding arrives with its label selected; anything else with none.
        The window draws the new item with its selection, so the canvas is not redrawn here."""
        self._arriving = True
        try:
            self.selection.clear()
            item = self.session.current()
            if item is None or item.focus is None or self.session.workspace is None:
                return
            labels = self.session.labels(item.entry)
            index = locate_line(labels.lines, item.focus.cls_id, item.focus.bbox, item.focus.index)
            if index is not None:
                self.selection.select(labels, [index])
        finally:
            self._arriving = False

    def _on_finding(self, labels: ImageLabels, indices) -> bool:
        """Whether these lines include the current finding's: fixing it moves on."""
        item = self.session.current()
        if item is None or item.focus is None:
            return False
        f = item.focus
        return locate_line(labels.lines, f.cls_id, f.bbox, f.index) in set(indices)

    def show(self, labels: ImageLabels) -> None:
        """The labels the canvas now draws. The file can change before the canvas is
        redrawn, so an index the canvas reports means a line of THIS snapshot: it is
        turned into a box identity here, and the core locates that box in the file."""
        self._shown = labels

    def show_predictions(self, image: Path, shown: list[Shown] | None) -> None:
        """The predictions the canvas now draws for `image`, None when the model has not
        looked at it: a double-clicked index means one of these, and `A` adds what of
        these is drawn solid."""
        self._predicted = (image, shown)

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
        if self._applying is not None or self._arriving:
            return                                  # the edit's own redraw, or the new item's, shows it
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
            on_finding = self._on_finding(labels, indices)
            if self._apply(actions.reclassify(image, labels, indices, info.cls_id), select=indices) and on_finding:
                self.session.move(1)
        elif self.session.workspace is not None:
            self.set_active(info)

    def class_key(self, key: str) -> None:
        info = class_with_hotkey(self.classes(), key)
        if info is None:
            if self.session.workspace is not None:
                self.session.status.emit(f"no class on key {key}")
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

    # -- accepting predictions --------------------------------------------------------------

    def _drawn_predictions(self) -> tuple[Path, list[Shown]] | None:
        """The predictions drawn for the image being edited, or None, said why."""
        current, model = self._current(), self.session.model
        if not current:
            return None
        if not self.canvas.show_predictions:
            self.session.status.emit("predictions hidden — P shows them")
            return None
        if model.state != "ready":
            self.session.status.emit("the model is loading" if model.state == "loading"
                                     else "no model loaded")
            return None
        if self._predicted is None or self._predicted[0] != current[0] or self._predicted[1] is None:
            self.session.status.emit("not inferred yet")
            return None
        return self._predicted

    def accept_missing(self) -> None:
        """A: every missing prediction drawn on this image, as one edit."""
        drawn = self._drawn_predictions()
        if drawn is None:
            return
        intent, unmapped = accept_image(*drawn)
        n = len(intent.ops) if intent is not None else 0
        if intent is not None and not self._apply(intent, select=_last(n)):
            return
        said = f"✚ {n} accepted" if n else "nothing missing to accept"
        if unmapped:
            said += f"; {unmapped:,} unmapped skipped"
        self.session.status.emit(said)

    def accept_prediction(self, index: int) -> None:
        """A double-clicked prediction, covered by a label or not."""
        drawn = self._drawn_predictions()
        if drawn is None or not 0 <= index < len(drawn[1]):
            return
        image, shown = drawn
        chosen = shown[index]
        intent = accept_one(image, chosen)
        if intent is None:
            names = self.session.model.names
            name = names[chosen.pred.cls] if 0 <= chosen.pred.cls < len(names) else str(chosen.pred.cls)
            self.session.status.emit(f"“{name}” is unmapped — map it in the class map")
            return
        self._apply(intent, select=_last(1))

    # -- Find Bad's keys (docs/design/2026-10-06-find-bad.md#keys) ----------------------------

    def _finding(self):
        """The finding on screen with its label shown, or None."""
        item, current = self.session.current(), self._current()
        if item is None or item.finding is None or not current:
            return None
        return item

    def take_model_class(self) -> None:
        """M: the label becomes the class the model gives it; then the next finding."""
        item = self._finding()
        if item is None:
            return
        if item.finding.model_cls is None or item.finding.kind == "not an object":
            self.session.status.emit("the model gives no class")
            return
        if item.finding.model_cls == item.focus.cls_id:         # weakly seen, as what it is
            self.session.status.emit("already the model's class — D dismisses")
            return
        intent = Intent(item.entry.path, (SetClass(item.focus, item.finding.model_cls),), "take the model's class")
        if self._apply(intent, select=[]):
            self.session.move(1)

    def take_model_box(self) -> None:
        """B: the label takes the model's box, keeping its class; then the next finding."""
        item = self._finding()
        if item is None:
            return
        box = item.finding.model_box and actions.clamp_box(item.finding.model_box)
        if box is None:
            self.session.status.emit("no model box")
            return
        labels, f = self._current()[1], item.focus
        index = locate_line(labels.lines, f.cls_id, f.bbox, f.index)
        if index is not None and all(abs(a - b) < 5e-7 for a, b in zip(box, labels.lines[index].bbox)):
            self.session.status.emit("already the model's box — D dismisses")
            return
        if self._apply(Intent(item.entry.path, (SetBox(item.focus, box),), "take the model's box"), select=[]):
            self.session.move(1)

    # -- the editing keys -----------------------------------------------------------------

    def delete(self) -> None:
        current = self._current()
        if current:
            image, labels = current
            indices = self.selection.indices(labels)
            on_finding = self._on_finding(labels, indices)
            if self._apply(actions.delete(image, labels, indices), select=[]) and on_finding:
                self.session.move(1)

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
            said.append(f"{polygons} polygon{'s' if polygons > 1 else ''} not copied (a paste makes boxes)")
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
            self.session.status.emit("no boxes on the clipboard")
            return
        n = len(intent.ops)
        if self._apply(intent, select=_last(n)):
            said = f"pasted {n} box" if n == 1 else f"pasted {n} boxes"
            skipped = lines - n
            if skipped:
                said += f"; {skipped} line{'s' if skipped > 1 else ''} skipped: not this dataset's boxes"
            self.session.status.emit(said)
