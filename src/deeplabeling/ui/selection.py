"""The boxes selected on the image on screen.

Held by identity (LineRef: index hint, class and box), not by index: a stored index
moves when a line is added or removed, and acting on a stale one edits the wrong box
(docs/knowledge/label-files.md#locate-before-writing). The canvas and the inspector's
box list both show this one selection; neither keeps its own.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..core.edits import LineRef
from ..core.labelio import locate_line
from ..core.store import ImageLabels


class Selection(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image: Path | None = None
        self.refs: tuple[LineRef, ...] = ()

    def __len__(self) -> int:
        return len(self.refs)

    def set(self, image, refs: Iterable[LineRef]) -> None:
        image, refs = (Path(image) if image is not None else None), tuple(refs)
        if (image, refs) != (self.image, self.refs):
            self.image, self.refs = image, refs
            self.changed.emit()

    def select(self, labels: ImageLabels, indices: Iterable[int]) -> None:
        """Select these lines of `labels`; anything that is not a box is ignored."""
        parsed = {i for i, _ in labels.boxes}
        self.set(labels.image, (labels.ref(i) for i in sorted(set(indices)) if i in parsed))

    def clear(self) -> None:
        self.set(self.image, ())

    def indices(self, labels: ImageLabels) -> list[int]:
        """Where the selected boxes are now in `labels`; a box that is gone drops out."""
        if labels.image != self.image:
            return []
        found = []
        for ref in self.refs:
            i = locate_line(labels.lines, ref.cls_id, ref.bbox, ref.index)
            if i is not None and i not in found:
                found.append(i)
        return sorted(found)
