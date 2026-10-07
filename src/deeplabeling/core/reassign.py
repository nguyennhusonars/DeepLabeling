"""Bulk reassign, planned (docs/design/2026-10-07-bulk-and-stats.md#bulk-reassign): every box
of one class in some images becomes another class. It reads only, so it is looked at a chunk
at a time; its intents are written as one edit (`src/deeplabeling/core/editor.py::Editor.batch`).
A class id the yaml does not name can be reassigned too."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .dataset import ImageEntry
from .edits import Intent, LineRef, SetClass
from .store import ImageLabels, LabelState


@dataclass(frozen=True)
class Reassign:
    intents: tuple[Intent, ...]     #: one per image, setting the class of each of its boxes of it
    boxes: int
    read_only: int                  #: images skipped: their label file cannot be edited, and holds the class or cannot be read

    def __add__(self, other: Reassign) -> Reassign:
        return Reassign(self.intents + other.intents, self.boxes + other.boxes, self.read_only + other.read_only)


def plan_reassign(entries: Iterable[ImageEntry], labels_of: Callable[[Path], ImageLabels],
                  source: int, target: int, description: str) -> Reassign:
    """What turning every class-`source` box of these images into `target` would write."""
    if source == target:
        raise ValueError("From and To are the same class")
    intents, boxes, read_only = [], 0, 0
    for entry in entries:
        labels = labels_of(entry.path)
        lines = [(i, line) for i, line in labels.boxes if line.cls_id == source]
        if not labels.editable:
            read_only += bool(lines) or labels.state is LabelState.ERROR
            continue
        if lines:
            ops = tuple(SetClass(LineRef(i, line.cls_id, line.bbox), target) for i, line in lines)
            intents.append(Intent(entry.path, ops, description))
            boxes += len(lines)
    return Reassign(tuple(intents), boxes, read_only)
