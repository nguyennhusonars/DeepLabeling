"""Edits to label files (docs/design/2026-10-04-app-foundation.md#edits).

An Intent is what the user asked for: operations on one image's lines. An Edit is
what was done: each file's bytes before and after, which is all undo needs.
`materialize` turns operations into new bytes against the file as it is now. It
locates every line by class and box first, so an intent built from an older
snapshot either reaches the right line or is refused
(docs/knowledge/label-files.md#locate-before-writing).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from .labelio import Box, LabelLine, format_box, locate_line, parse_label_bytes, render_label_bytes


class Refused(Exception):
    """An edit or undo that would be wrong, so it was not done. The message is for the user."""


class PartlyRestored(Refused):
    """An undo or redo whose writes failed, and whose put-back failed too: `stuck` are the
    changes left restored. The history splits the edit around them (history.py::History.undo)."""

    def __init__(self, message: str, stuck: tuple, images: tuple = ()):
        super().__init__(message)
        self.stuck, self.images = stuck, images


class Conflict(Refused):
    """A file no longer holds what an edit expects: something else changed it since.

    Unlike a failed read or write, retrying cannot help, so an undo or redo refused
    this way is dropped from the history.
    """


@dataclass(frozen=True)
class LineRef:
    """Where a box was: its line index (only a hint), its class and its normalised box."""

    index: int
    cls_id: int
    bbox: Box

    @classmethod
    def of(cls, lines: Sequence[LabelLine], index: int) -> LineRef:
        line = lines[index]
        return cls(index, line.cls_id, line.bbox)


@dataclass(frozen=True)
class AddBox:
    cls_id: int
    bbox: Box


@dataclass(frozen=True)
class SetBox:
    ref: LineRef
    bbox: Box


@dataclass(frozen=True)
class SetClass:
    ref: LineRef
    cls_id: int


@dataclass(frozen=True)
class DeleteLine:
    ref: LineRef


@dataclass(frozen=True)
class CreateEmpty:
    """Create an empty label file on an image that has none: an explicit negative sample."""


Op = Union[AddBox, SetBox, SetClass, DeleteLine, CreateEmpty]


@dataclass(frozen=True)
class Intent:
    image: Path
    ops: tuple[Op, ...]
    description: str


@dataclass(frozen=True)
class FileChange:
    path: Path
    before: bytes | None    #: None: the file did not exist
    after: bytes | None

    @property
    def nbytes(self) -> int:
        return len(self.before or b"") + len(self.after or b"")


@dataclass(frozen=True)
class Edit:
    changes: tuple[FileChange, ...]
    images: tuple[Path, ...]
    description: str

    @property
    def nbytes(self) -> int:
        return sum(change.nbytes for change in self.changes)


def materialize(before: bytes | None, ops: Sequence[Op], *,
                class_ok: Callable[[int], bool]) -> bytes:
    """The file's new bytes once `ops` are applied to `before`. Refuses rather than guesses."""
    if not ops:
        raise Refused("there is nothing to change")
    if any(isinstance(op, CreateEmpty) for op in ops):
        if len(ops) > 1:
            raise Refused("marking an image negative cannot be combined with other edits")
        if before is not None:
            raise Refused("this image already has a label file")
        return b""
    lines = list(parse_label_bytes(before or b""))
    targets: dict[int, Op] = {}
    added: list[AddBox] = []
    for op in ops:
        if isinstance(op, AddBox):
            _check_class(op.cls_id, class_ok)
            _check_box(op.bbox)
            added.append(op)
            continue
        index = locate_line(lines, op.ref.cls_id, op.ref.bbox, op.ref.index)
        if index is None:
            raise Refused(f"a class-{op.ref.cls_id} box changed in the file since it was shown, "
                          "or more than one line matches it; nothing was written")
        if index in targets:
            raise Refused("two changes were aimed at the same box")
        if isinstance(op, SetBox):
            if lines[index].is_polygon:
                raise Refused("a polygon cannot be moved or resized here; reclassify or delete it")
            _check_box(op.bbox)
        elif isinstance(op, SetClass):
            _check_class(op.cls_id, class_ok)
        targets[index] = op
    out: list[LabelLine] = []
    for index, line in enumerate(lines):
        op = targets.get(index)
        if op is None:
            out.append(line)
        elif isinstance(op, SetClass):
            out.append(line if op.cls_id == line.cls_id else line.with_class(op.cls_id))
        elif isinstance(op, SetBox):
            out.append(line if _same_box(line.bbox, op.bbox) else line.with_bbox(op.bbox))
        # a DeleteLine target is simply left out
    if added:
        ending = _line_ending(out)
        if out and not out[-1].terminator:
            last = out[-1]
            out[-1] = LabelLine(last.cls_id, last.coords, last.raw + ending)
        out += [format_box(op.cls_id, op.bbox, ending) for op in added]
    return render_label_bytes(out)


def _line_ending(lines: Sequence[LabelLine]) -> str:
    """CRLF when the file's last line ending is CRLF, else LF."""
    for line in reversed(lines):
        if line.terminator:
            return "\r\n" if line.terminator == "\r\n" else "\n"
    return "\n"


def _same_box(a: Box, b: Box) -> bool:
    return all(abs(x - y) <= 1e-9 for x, y in zip(a, b))


def _check_class(cls_id, class_ok: Callable[[int], bool]) -> None:
    if (not isinstance(cls_id, int) or isinstance(cls_id, bool)
            or cls_id < 0 or not class_ok(cls_id)):
        raise Refused(f"class {cls_id} is not one of this dataset's classes")


def _check_box(bbox: Box) -> None:
    cx, cy, w, h = bbox
    tol = 1e-9
    if (not all(math.isfinite(v) for v in bbox) or w <= 0 or h <= 0
            or cx - w / 2 < -tol or cy - h / 2 < -tol
            or cx + w / 2 > 1 + tol or cy + h / 2 > 1 + tol):
        raise Refused(f"the box {bbox} is empty or outside the image")
