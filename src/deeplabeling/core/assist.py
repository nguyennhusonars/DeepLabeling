"""What accepting predictions adds (docs/design/2026-10-05-model-assist.md#accepting).

A prediction is shown with its dataset class (or None, unmapped) and whether it is
missing: above the threshold, overlapped by no label of any class, and the most confident
prediction at its place. Of overlapping predictions the most confident speaks for the
place (docs/knowledge/matching.md#candidates-and-the-deciding-prediction): ultralytics
keeps one box per class, so one car often comes with a weaker truck. An unmapped one
speaking for a place keeps every weaker one out (matching.md#unmapped-classes-are-inconclusive).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .classmap import ClassMap
from .dataset import Dataset, ImageEntry
from .edits import AddBox, Intent
from .geometry import iou
from .inference import Prediction
from .store import ImageLabels

MATCH_IOU = 0.5     #: a label or a stronger prediction this close covers a prediction


@dataclass(frozen=True)
class Shown:
    pred: Prediction
    cls: int | None     #: the dataset class id, or None when the class map leaves it out
    missing: bool       #: what an accept of the whole image would add (or skip, if unmapped)


def shown_predictions(preds: Iterable[Prediction], labels: ImageLabels, cmap: ClassMap,
                      dataset: Dataset, conf: float) -> list[Shown]:
    """The predictions at or above `conf`, strongest first, each translated and marked."""
    boxes = [line.bbox for _, line in labels.boxes]
    places: list[Prediction] = []           # the strongest prediction at each place
    out = []
    for pred in sorted((p for p in preds if p.conf >= conf), key=lambda p: -p.conf):
        covered = any(iou(pred.box, box) >= MATCH_IOU for box in boxes)
        shadowed = any(iou(pred.box, q.box) >= MATCH_IOU for q in places)
        if not shadowed:
            places.append(pred)                 # covered or not, it speaks for its place
        out.append(Shown(pred, cmap.translate(pred.cls, dataset), not covered and not shadowed))
    return out


def _plural(n: int) -> str:
    return "1 prediction" if n == 1 else f"{n} predictions"


def accept_image(image, shown: Iterable[Shown]) -> tuple[Intent | None, int]:
    """The image's missing predictions as one intent, and how many of them it skipped for
    being unmapped."""
    missing = [s for s in shown if s.missing]
    ops = tuple(AddBox(s.cls, s.pred.box) for s in missing if s.cls is not None)
    unmapped = len(missing) - len(ops)
    return (Intent(Path(image), ops, f"accept {_plural(len(ops))}") if ops else None), unmapped


def accept_one(image, shown: Shown) -> Intent | None:
    """One prediction the user chose, covered or not; never an unmapped one."""
    if shown.cls is None:
        return None
    return Intent(Path(image), (AddBox(shown.cls, shown.pred.box),), "accept a prediction")


@dataclass(frozen=True)
class QueueAccept:
    intents: tuple[Intent, ...]
    boxes: int          #: predictions the intents add
    uninferred: int     #: images with no row: skipped
    unmapped: int       #: missing predictions skipped for an unmapped class
    read_only: int      #: images whose label file cannot be edited: skipped
    negative: int       #: negative samples (an empty label file, a decision): skipped


def plan_queue_accept(entries: Iterable[ImageEntry], labels_of: Callable[[Path], ImageLabels],
                      preds_of: Callable[[ImageEntry], list[Prediction] | None], cmap: ClassMap,
                      dataset: Dataset, conf: float,
                      cancelled: Callable[[], bool] = lambda: False) -> QueueAccept | None:
    """What accepting the missing predictions across these images would do. Reads only, so
    it runs on a worker; None when cancelled part-way."""
    intents, boxes, uninferred, unmapped, read_only, negative = [], 0, 0, 0, 0, 0
    for entry in entries:
        if cancelled():
            return None
        preds = preds_of(entry)
        if preds is None:
            uninferred += 1
            continue
        labels = labels_of(entry.path)
        if not labels.editable:
            read_only += 1
            continue
        if labels.negative:
            negative += 1                       # someone decided it has no objects
            continue
        intent, skipped = accept_image(entry.path, shown_predictions(preds, labels, cmap, dataset, conf))
        unmapped += skipped
        if intent is not None:
            intents.append(intent)
            boxes += len(intent.ops)
    return QueueAccept(tuple(intents), boxes, uninferred, unmapped, read_only, negative)
