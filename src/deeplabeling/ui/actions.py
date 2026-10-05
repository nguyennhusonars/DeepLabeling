"""The editing actions as intents, built from what is on screen. No Qt: tested headless.

Each function takes the image's labels as shown and the line indices it acts on, and
returns an Intent for Session.apply -- or None when there is nothing to do. The core
locates every line again before writing, so an intent built from a stale view is
refused, never misapplied (docs/knowledge/label-files.md#locate-before-writing).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from ..core.edits import AddBox, DeleteLine, Intent, SetBox, SetClass
from ..core.geometry import Box, corners, px_to_norm
from ..core.labelio import parse_label_text
from ..core.store import ImageLabels


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}es"


def _rows(labels: ImageLabels, indices: Iterable[int]) -> list[int]:
    """The given indices that are boxes (parsed lines), in file order."""
    parsed = {i for i, _ in labels.boxes}
    return sorted(i for i in set(indices) if i in parsed)


def add_box(image, cls_id: int, bbox: Box) -> Intent:
    return Intent(Path(image), (AddBox(cls_id, bbox),), "draw a box")


def reclassify(image, labels: ImageLabels, indices: Iterable[int], cls_id: int) -> Intent | None:
    rows = [i for i in _rows(labels, indices) if labels.lines[i].cls_id != cls_id]
    if not rows:
        return None
    return Intent(Path(image), tuple(SetClass(labels.ref(i), cls_id) for i in rows),
                  f"reclassify {_plural(len(rows), 'box')}")


def delete(image, labels: ImageLabels, indices: Iterable[int]) -> Intent | None:
    rows = _rows(labels, indices)
    if not rows:
        return None
    return Intent(Path(image), tuple(DeleteLine(labels.ref(i)) for i in rows),
                  f"delete {_plural(len(rows), 'box')}")


def move(image, labels: ImageLabels, indices: Iterable[int], dx: float, dy: float) -> Intent | None:
    """Shift boxes by (dx, dy), normalised. They keep their sizes and move together: the
    shift is cut where the first of them would leave the image."""
    rows = _rows(labels, indices)
    if not rows or (dx == 0 and dy == 0):
        return None
    boxes = [labels.lines[i].bbox for i in rows]
    dx = min(max(dx, max(w / 2 - cx for cx, _, w, _ in boxes)), min(1 - w / 2 - cx for cx, _, w, _ in boxes))
    dy = min(max(dy, max(h / 2 - cy for _, cy, _, h in boxes)), min(1 - h / 2 - cy for _, cy, _, h in boxes))
    ops = [SetBox(labels.ref(i), (cx + dx, cy + dy, w, h)) for i, (cx, cy, w, h) in zip(rows, boxes)]
    return Intent(Path(image), tuple(ops), f"move {_plural(len(rows), 'box')}")


def resize(image, labels: ImageLabels, index: int, bbox: Box) -> Intent | None:
    if not _rows(labels, [index]):
        return None
    return Intent(Path(image), (SetBox(labels.ref(index), bbox),), "resize a box")


def _line(cls_id: int, bbox: Box) -> str:
    cx, cy, w, h = bbox
    return f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n"


def copy_text(labels: ImageLabels, indices: Iterable[int]) -> str:
    """The boxes as label-file lines. Polygons are left out: pasted, one would become a box."""
    return "".join(_line(labels.lines[i].cls_id, labels.lines[i].bbox)
                   for i in _rows(labels, indices) if not labels.lines[i].is_polygon)


def remap_classes(text: str, old_names, new_names) -> tuple[str, int]:
    """Boxes copied under the class list `old_names`, re-numbered by name for `new_names`.
    A line that is no box is dropped; a box whose class the new list lacks is dropped and
    counted: (the text, how many were lost)."""
    index = {name: i for i, name in enumerate(new_names)}
    out, lost = [], 0
    for line in parse_label_text(text):
        if not line.parsed or line.is_polygon or not 0 <= line.cls_id < len(old_names):
            continue
        name = old_names[line.cls_id]
        if name in index:
            out.append(_line(index[name], line.bbox))
        else:
            lost += 1
    return "".join(out), lost


def clamp_box(bbox: Box) -> Box | None:
    """The part of a normalised box inside the image, or None when nothing is left."""
    cx, cy, w, h = px_to_norm(*corners(bbox), 1, 1)
    return (cx, cy, w, h) if w > 0 and h > 0 else None


def paste(image, text: str, class_ok: Callable[[int], bool]) -> Intent | None:
    """Boxes from text in label-file form -- what copy_text writes, or lines of any label
    file -- clamped into the image. A line that is no box of a known class is skipped."""
    ops = []
    for line in parse_label_text(text):
        if not line.parsed or line.is_polygon or line.cls_id < 0 or not class_ok(line.cls_id):
            continue
        box = clamp_box(line.bbox)
        if box is not None:
            ops.append(AddBox(line.cls_id, box))
    if not ops:
        return None
    return Intent(Path(image), tuple(ops), f"paste {_plural(len(ops), 'box')}")
