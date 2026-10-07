"""Queues: the list being worked through (docs/design/2026-10-04-app-foundation.md#queue).

A source builds its items on a worker from immutable inputs -- the dataset, the
thread-safe store and a snapshot of the review marks -- and streams them in
batches. A Queue holds them on the GUI thread with one cursor, an identity key.
"""

from __future__ import annotations

import bisect
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from .classmap import ClassMap
from .dataset import Dataset, ImageEntry
from .disagree import unlabelled_predictions, unseen_labels
from .edits import LineRef
from .imagesize import ImageSizes, image_size
from .inference import FLOOR, Prediction
from .overlap import SCOPES, stack_counts
from .predstore import PredictionStore, image_stamp
from .ranges import range_error
from .store import ImageLabels, LabelState, LabelStore

LABEL_STATES = ("missing", "negative", "boxes")
UNITS = ("px", "%")
#: Label files hold six decimals: a box drawn exactly at a range's end reads back within
#: half a step of it (10 px of a 48 px side is 0.208333, so 9.999984 px).
HALF_STEP = 5e-7


@dataclass(frozen=True)
class Scanned:
    """A build's progress, sent among its batches: images looked at, of how many."""

    done: int
    total: int


@dataclass(frozen=True)
class QueueItem:
    key: str
    entry: ImageEntry
    rank: tuple = ()                #: where it sorts in its queue; () is dataset order
    focus: LineRef | None = None    #: the label line it is about: a finding's
    finding: Any = None             #: the findings.Finding it stands for, in a findings queue

    @property
    def sort_key(self) -> tuple:
        return self.rank or (self.entry.order,)


@dataclass(frozen=True)
class ModelSnapshot:
    """The loaded model, as a build reads it: its rows in the store and its class map."""

    key: str
    store: PredictionStore
    class_map: ClassMap


@dataclass(frozen=True)
class BuildContext:
    dataset: Dataset
    store: LabelStore
    reviewed: frozenset[str]        #: review-mark keys, snapshotted before the build
    sizes: ImageSizes | None = None     #: the open dataset's size cache, when there is one
    model: ModelSnapshot | None = None  #: the loaded model, when a condition asks for it
    #: Dismissed findings, (image, label line, kind), snapshotted before the build.
    dismissed: frozenset[tuple[str, str, str]] = frozenset()
    #: Images a condition could not settle ("could not be sized", "not inferred"), counted
    #: for the queue chip. One build or recheck owns it; it is never shared across threads.
    unsettled: Counter = field(default_factory=Counter)
    #: The same, by image: which ones, so an image left out as not inferred can join the
    #: queue when its predictions arrive.
    left_out: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def labels(self, entry: ImageEntry) -> ImageLabels:
        return self.store.get(entry.path)

    def size(self, entry: ImageEntry) -> tuple[int, int] | None:
        """The image's size as shown, from its header; None when it cannot be read."""
        return self.sizes.get(entry.path) if self.sizes is not None else image_size(entry.path)

    def predictions(self, entry: ImageEntry) -> list[Prediction] | None:
        """The model's predictions for the image at the floor; None when it never looked,
        or the image has changed since (the store's stamp)."""
        try:
            stamp = image_stamp(entry.path)
        except OSError:
            return None
        return self.model.store.get(self.model.key, entry.rel, stamp)

    def count(self, what: str, entry: ImageEntry) -> None:
        self.unsettled[what] += 1
        self.left_out[what].add(entry.rel)


@dataclass(frozen=True)
class Seen:
    """What a view knows of an image besides its labels, for a condition's highlight."""

    size: tuple[int, int] | None = None     #: as shown: what a size in px is scaled by
    predictions: list[Prediction] | None = None     #: the model's, at the floor, untranslated
    class_map: ClassMap | None = None


NOTHING_SEEN = Seen()


class Condition:
    """One test an image must pass. Subclasses are frozen dataclasses."""

    kind: ClassVar[str]
    needs_labels: ClassVar[bool] = True
    needs_model: ClassVar[bool] = False

    @property
    def cost(self) -> int:
        """Conditions run cheapest first: 0 asks nothing of the disk, 1 reads the label
        file, 2 an image header, 3 the prediction store."""
        return 1 if self.needs_labels else 0

    def test(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        raise NotImplementedError

    def describe(self, dataset: Dataset) -> str:
        raise NotImplementedError

    def highlight(self, labels: ImageLabels, dataset: Dataset, seen: Seen = NOTHING_SEEN) -> frozenset[int]:
        """Line indices of the boxes that made the condition hold."""
        return frozenset()

    def highlight_predictions(self, labels: ImageLabels, dataset: Dataset,
                              seen: Seen = NOTHING_SEEN) -> frozenset[int]:
        """Indices into `seen.predictions` of the predictions that made it hold."""
        return frozenset()

    def to_json(self) -> dict:
        raise NotImplementedError


@dataclass(frozen=True)
class HasClass(Condition):
    """The image has (or lacks) a box of any of the named classes."""

    names: tuple[str, ...]
    present: bool = True
    kind: ClassVar[str] = "class"

    def _ids(self, dataset: Dataset) -> set[int]:
        return {i for i in map(dataset.id_of, self.names) if i is not None}

    def test(self, entry, ctx):
        ids = self._ids(ctx.dataset)
        found = any(line.cls_id in ids for _, line in ctx.labels(entry).boxes)
        return found == self.present

    def describe(self, dataset):
        return ("has " if self.present else "lacks ") + " or ".join(self.names)

    def highlight(self, labels, dataset, seen=NOTHING_SEEN):
        if not self.present:
            return frozenset()
        ids = self._ids(dataset)
        return frozenset(i for i, line in labels.boxes if line.cls_id in ids)

    def to_json(self):
        return {"kind": self.kind, "names": list(self.names), "present": self.present}


@dataclass(frozen=True)
class LabelStateIs(Condition):
    """No label file, an empty one (a negative sample), or one with boxes."""

    state: str
    kind: ClassVar[str] = "label"

    def __post_init__(self):
        if self.state not in LABEL_STATES:
            raise ValueError(f"unknown label state {self.state!r}")

    def test(self, entry, ctx):
        labels = ctx.labels(entry)
        if self.state == "missing":
            return labels.raw is None and labels.state is not LabelState.ERROR
        if self.state == "negative":
            return labels.negative
        return bool(labels.boxes)

    def describe(self, dataset):
        return {"missing": "no label file", "negative": "negative",
                "boxes": "has boxes"}[self.state]

    def to_json(self):
        return {"kind": self.kind, "state": self.state}


@dataclass(frozen=True)
class Reviewed(Condition):
    value: bool = True
    kind: ClassVar[str] = "reviewed"
    needs_labels: ClassVar[bool] = False

    def test(self, entry, ctx):
        return (entry.rel in ctx.reviewed) == self.value

    def describe(self, dataset):
        return "reviewed" if self.value else "not reviewed"

    def to_json(self):
        return {"kind": self.kind, "value": self.value}


@dataclass(frozen=True)
class NameContains(Condition):
    """The dataset-relative path contains the text, ignoring case."""

    text: str
    kind: ClassVar[str] = "name"
    needs_labels: ClassVar[bool] = False

    def test(self, entry, ctx):
        return self.text.lower() in entry.rel.lower()

    def describe(self, dataset):
        return f'name contains "{self.text}"'

    def to_json(self):
        return {"kind": self.kind, "text": self.text}


def _in(value: float, bounds: tuple[float | None, float | None], tol: float) -> bool:
    lo, hi = bounds
    return (lo is None or value >= lo - tol) and (hi is None or value <= hi + tol)


def _bounds(bounds: tuple[float | None, float | None], unit: str) -> str:
    lo, hi = bounds
    sep = "" if unit == "%" else " "
    if lo is not None and hi is not None:
        return f"{lo:g}–{hi:g}{sep}{unit}"
    return f"≥ {lo:g}{sep}{unit}" if lo is not None else f"≤ {hi:g}{sep}{unit}"


@dataclass(frozen=True)
class Boxes(Condition):
    """A box of the chosen classes (any class, when none is chosen) whose width and
    height are in range: both on the same box
    (docs/design/2026-10-06-filters.md#boxes-size-on-the-same-box-as-the-class). In % the
    label's own coordinates answer; in px the frame's size, read from its header."""

    names: tuple[str, ...] = ()
    w: tuple[float | None, float | None] = (None, None)
    h: tuple[float | None, float | None] = (None, None)
    unit: str = "px"
    kind: ClassVar[str] = "boxes"

    def __post_init__(self):
        if self.unit not in UNITS:
            raise ValueError(f"unknown size unit {self.unit!r}")
        for name, (lo, hi) in (("width", self.w), ("height", self.h)):
            why = range_error(lo, hi, name, hi_max=100.0 if self.unit == "%" else None, open_ends=True)
            if why:
                raise ValueError(why)

    @property
    def cost(self) -> int:
        return 2 if self.unit == "px" else 1

    def _matching(self, labels: ImageLabels, dataset: Dataset, size) -> frozenset[int]:
        ids = {i for i in map(dataset.id_of, self.names) if i is not None}
        sx, sy = size if self.unit == "px" else (100.0, 100.0)
        return frozenset(i for i, line in labels.boxes
                         if (not self.names or line.cls_id in ids)
                         and _in(line.bbox[2] * sx, self.w, HALF_STEP * sx)
                         and _in(line.bbox[3] * sy, self.h, HALF_STEP * sy))

    def test(self, entry, ctx):
        size = None
        if self.unit == "px":
            size = ctx.size(entry)
            if size is None:
                ctx.count("could not be sized", entry)
                return False
        return bool(self._matching(ctx.labels(entry), ctx.dataset, size))

    def highlight(self, labels, dataset, seen=NOTHING_SEEN):
        if self.unit == "px" and seen.size is None:
            return frozenset()
        return self._matching(labels, dataset, seen.size)

    def describe(self, dataset):
        what = "a " + " or ".join(self.names) if self.names else "a box"
        sizes = [f"{_bounds(b, self.unit)} {word}" for b, word in ((self.w, "wide"), (self.h, "high"))
                 if b != (None, None)]
        return f"has {what}" + (" " + ", ".join(sizes) if sizes else "")

    def to_json(self):
        return {"kind": self.kind, "names": list(self.names), "w": list(self.w), "h": list(self.h),
                "unit": self.unit}


SCOPE_WORDS = {"different": "different classes", "same": "same class", "any": "any class"}


@dataclass(frozen=True)
class Overlap(Condition):
    """Some pair of labels in scope overlaps at an IoU in the range, both ends inclusive
    (docs/design/2026-10-06-filters.md#overlap-between-labels). The test and the highlight
    are one predicate, core/overlap.py's, which the canvas's stack counts use too."""

    scope: str = "different"
    lo: float = 0.5
    hi: float = 1.0
    kind: ClassVar[str] = "overlap"

    def __post_init__(self):
        if self.scope not in SCOPES:
            raise ValueError(f"unknown overlap scope {self.scope!r}")
        why = range_error(self.lo, self.hi, "IoU")
        if why:
            raise ValueError(why)

    def _overlapping(self, labels: ImageLabels) -> frozenset[int]:
        boxes = labels.boxes
        stacked = stack_counts([(line.cls_id, line.bbox) for _, line in boxes], self.scope, self.lo, self.hi)
        return frozenset(boxes[k][0] for k in stacked)

    def test(self, entry, ctx):
        return bool(self._overlapping(ctx.labels(entry)))

    def highlight(self, labels, dataset, seen=NOTHING_SEEN):
        return self._overlapping(labels)

    def describe(self, dataset):
        return f"labels overlapping, {SCOPE_WORDS[self.scope]}, IoU {self.lo:.2f}–{self.hi:.2f}"

    def to_json(self):
        return {"kind": self.kind, "scope": self.scope, "lo": self.lo, "hi": self.hi}


DIRECTIONS = ("unseen", "unlabelled", "either")
DIRECTION_WORDS = {"unseen": "labels the model does not see", "unlabelled": "predictions nobody labelled",
                   "either": "labels and predictions that disagree"}


@dataclass(frozen=True)
class ModelDisagrees(Condition):
    """The loaded model and the labels disagree: a label it does not see, a prediction
    nobody labelled, or either (docs/design/2026-10-06-filters.md#labelprediction-iou).
    An image the model never looked at is left out and counted, never passed as clean."""

    direction: str = "unseen"
    match_iou: float = 0.5
    conf: tuple[float, float] = (0.25, 1.0)
    kind: ClassVar[str] = "model"
    needs_model: ClassVar[bool] = True

    def __post_init__(self):
        if self.direction not in DIRECTIONS:
            raise ValueError(f"unknown direction {self.direction!r}")
        if not 0 < self.match_iou <= 1:
            raise ValueError("matching IoU: must be above 0 and at most 1")
        why = range_error(*self.conf, "confidence", lo_min=FLOOR)
        if why:
            raise ValueError(why)

    @property
    def cost(self) -> int:
        return 3

    def _unseen(self, labels, preds, cmap, dataset) -> frozenset[int]:
        if self.direction == "unlabelled":
            return frozenset()
        return unseen_labels(labels, preds, cmap, dataset, self.match_iou, self.conf[0])

    def _unlabelled(self, labels, preds, cmap, dataset) -> frozenset[int]:
        if self.direction == "unseen":
            return frozenset()
        return unlabelled_predictions(labels, preds, cmap, dataset, self.match_iou, *self.conf)

    def test(self, entry, ctx):
        if ctx.model is None:
            ctx.count("no model", entry)
            return False
        preds = ctx.predictions(entry)
        if preds is None:
            ctx.count("not inferred", entry)
            return False
        labels, cmap = ctx.labels(entry), ctx.model.class_map
        if labels.state is LabelState.ERROR:
            ctx.count("labels unreadable", entry)    # what it holds is unknown, not "nobody labelled"
            return False
        return bool(self._unseen(labels, preds, cmap, ctx.dataset)
                    or self._unlabelled(labels, preds, cmap, ctx.dataset))

    def highlight(self, labels, dataset, seen=NOTHING_SEEN):
        if seen.predictions is None or seen.class_map is None:
            return frozenset()
        return self._unseen(labels, seen.predictions, seen.class_map, dataset)

    def highlight_predictions(self, labels, dataset, seen=NOTHING_SEEN):
        if seen.predictions is None or seen.class_map is None:
            return frozenset()
        return self._unlabelled(labels, seen.predictions, seen.class_map, dataset)

    def describe(self, dataset):
        lo, hi = self.conf
        conf = f"conf ≥ {lo:.2f}" if self.direction == "unseen" else f"conf {lo:.2f}–{hi:.2f}"
        return f"{DIRECTION_WORDS[self.direction]} (IoU {self.match_iou:.2f}, {conf})"

    def to_json(self):
        return {"kind": self.kind, "direction": self.direction, "match_iou": self.match_iou,
                "conf": list(self.conf)}


def condition_from_json(data) -> Condition:
    try:
        kind = data["kind"]
        if kind == "class":
            return HasClass(tuple(str(n) for n in data["names"]), bool(data.get("present", True)))
        if kind == "label":
            return LabelStateIs(str(data["state"]))
        if kind == "reviewed":
            return Reviewed(bool(data.get("value", True)))
        if kind == "name":
            return NameContains(str(data["text"]))
        if kind == "model":
            return ModelDisagrees(str(data["direction"]), float(data["match_iou"]),
                                  tuple(float(c) for c in data["conf"]))
        if kind == "overlap":
            return Overlap(str(data["scope"]), float(data["lo"]), float(data["hi"]))
        if kind == "boxes":
            return Boxes(tuple(str(n) for n in data["names"]), tuple(data["w"]), tuple(data["h"]),
                         str(data["unit"]))
    except (KeyError, TypeError) as e:
        raise ValueError(f"not a queue condition: {data!r}") from e
    raise ValueError(f"unknown queue condition {kind!r}")


@dataclass(frozen=True)
class ImageFilter:
    """Every image of the chosen splits that passes every condition, in dataset order.

    Slice 3 adds conditions; it does not add a second filter system.
    """

    splits: tuple[str, ...] = ()
    conditions: tuple[Condition, ...] = ()

    def describe(self, dataset: Dataset) -> str:
        text = " and ".join(c.describe(dataset) for c in self.conditions) or "all images"
        return f"{text} in {' + '.join(self.splits)}" if self.splits else text

    def holds(self, item: QueueItem, ctx: BuildContext) -> bool:
        """Whether an item still belongs: its image still matches."""
        return self.matches(item.entry, ctx)

    def still(self, entry: ImageEntry, items: list[QueueItem], ctx: BuildContext) -> set[str]:
        """The keys of one image's items that still belong."""
        return {item.key for item in items if self.holds(item, ctx)}

    def items_for(self, entry: ImageEntry, ctx: BuildContext) -> list[QueueItem]:
        """The items one image stands behind: itself when it matches."""
        return [QueueItem(entry.rel, entry)] if self.matches(entry, ctx) else []

    def matches(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        if self.splits and entry.split not in self.splits:
            return False
        cheap_first = sorted(self.conditions, key=lambda c: c.cost)
        return all(c.test(entry, ctx) for c in cheap_first)

    def highlight(self, labels: ImageLabels, dataset: Dataset, seen: Seen = NOTHING_SEEN) -> frozenset[int]:
        found: frozenset[int] = frozenset()
        for condition in self.conditions:
            found |= condition.highlight(labels, dataset, seen)
        return found

    def highlight_predictions(self, labels: ImageLabels, dataset: Dataset,
                              seen: Seen = NOTHING_SEEN) -> frozenset[int]:
        found: frozenset[int] = frozenset()
        for condition in self.conditions:
            found |= condition.highlight_predictions(labels, dataset, seen)
        return found

    @property
    def needs_model(self) -> bool:
        """Whether a condition reads the loaded model's predictions."""
        return any(c.needs_model for c in self.conditions)

    def build(self, ctx: BuildContext, emit: Callable[[list[QueueItem]], None],
              cancelled: Callable[[], bool] = lambda: False, *,
              batch: int = 500, interval: float = 0.2, progress=None) -> bool:
        """Stream the matching items to `emit`. False when cancelled part-way."""
        pending: list[QueueItem] = []
        last = time.monotonic()
        for entry in ctx.dataset.images:
            if cancelled():
                return False
            if self.matches(entry, ctx):
                pending.append(QueueItem(entry.rel, entry))
            now = time.monotonic()
            if pending and (len(pending) >= batch or now - last >= interval):
                emit(pending)
                pending, last = [], now
        if pending:
            emit(pending)
        return True

    def to_json(self) -> dict:
        return {"splits": list(self.splits), "conditions": [c.to_json() for c in self.conditions]}

    @classmethod
    def from_json(cls, data) -> ImageFilter:
        if not isinstance(data, dict):
            raise ValueError(f"not a queue: {data!r}")
        splits, conditions = data.get("splits", []), data.get("conditions", [])
        if (not isinstance(splits, list) or not all(isinstance(s, str) for s in splits)
                or not isinstance(conditions, list)):
            raise ValueError(f"not a queue: {data!r}")
        return cls(tuple(splits), tuple(condition_from_json(c) for c in conditions))


class Queue:
    """A queue's items in their order -- dataset order for an image queue, kind and score
    for findings -- with one cursor (an identity key), and which items no longer hold since
    the queue was built. Used on the GUI thread.

    Rows are found by bisecting the items' sort keys, never stored: an item joining a
    45k-item queue after its build costs two list insertions, not a re-numbering of every
    row after it. An image may stand behind several items (its findings)."""

    def __init__(self, source, *, follow: ImageEntry | None = None):
        self.source = source
        self.items: list[QueueItem] = []
        self.cursor: str | None = None
        self.stale: set[str] = set()
        self.complete = False
        self.failed: str | None = None      #: why the build stopped early, if it failed
        #: What the build could not settle, by image ("not inferred", "could not be sized").
        self.left_out: dict[str, set[str]] = {}
        self.waiting = False        #: a model condition waits for a model: nothing is built yet
        self.scanned: Scanned | None = None     #: how far a scanning build has got
        self.built_with = None      #: the model (key, class map) its build read, if any
        self._rank: dict[str, tuple] = {}           #: each item's sort key, by key
        self._ranks: list[tuple] = []               #: the items' sort keys, row by row: ascending
        self._by_image: dict[str, list[str]] = {}   #: the keys of each image's items
        #: Where the cursor was before a rebuild: an image (its first item takes the cursor)
        #: or an item (that item, else the next after it in its order).
        self._follow = follow
        self._moved = False

    def __len__(self) -> int:
        return len(self.items)

    def __contains__(self, key: str) -> bool:
        return key in self._rank

    def has_image(self, rel: str) -> bool:
        return rel in self._by_image

    def keys_of(self, rel: str) -> list[str]:
        """The keys of the items an image stands behind, in queue order."""
        return sorted(self._by_image.get(rel, ()), key=self._rank.__getitem__)

    def _row(self, key: str) -> int:
        return bisect.bisect_left(self._ranks, self._rank[key])

    def _add(self, row: int, item: QueueItem) -> None:
        self.items.insert(row, item)
        self._ranks.insert(row, item.sort_key)
        self._rank[item.key] = item.sort_key
        self._by_image.setdefault(item.entry.rel, []).append(item.key)

    def extend(self, batch: Iterable[QueueItem]) -> None:
        for item in batch:
            if item.key in self._rank:
                continue
            if self._ranks and item.sort_key < self._ranks[-1]:
                raise ValueError(f"{item.key} arrives out of order")
            self._add(len(self.items), item)
            if self._follow is not None and not self._moved and self._is_followed(item):
                self.cursor = item.key
                self._follow = None
        if self.cursor is None and self.items:
            self.cursor = self.items[0].key

    @property
    def following(self) -> bool:
        """Whether the cursor still waits for its place from before the rebuild."""
        return self._follow is not None and not self._moved

    def _is_followed(self, item: QueueItem) -> bool:
        f = self._follow
        if not isinstance(f, QueueItem):
            return item.entry.rel == f.rel
        if item.key == f.key:
            return True
        # An image's item for a finding's, or a finding's for an image's: its image. Between
        # findings only the same finding will do -- another of its image may arrive first.
        return (item.key == item.entry.rel) != (f.key == f.entry.rel) and item.entry.rel == f.entry.rel

    def _comes_after(self, item: QueueItem) -> bool:
        f = self._follow
        if isinstance(f, QueueItem):
            if len(item.sort_key) == len(f.sort_key):       # the same kind of queue: its order
                return item.sort_key > f.sort_key
            f = f.entry
        return item.entry.order > f.order

    def insert(self, item: QueueItem) -> int | None:
        """Add an item after the build, in its place: an image whose predictions have
        arrived. Its row, or None when it is already there."""
        if item.key in self._rank:
            return None
        row = bisect.bisect_right(self._ranks, item.sort_key)
        self._add(row, item)
        if self.cursor is None:
            self.cursor = item.key
        return row

    def finish(self) -> None:
        """The build is done. A cursor still waiting for its old item takes the first
        item after it in dataset order, or the last item."""
        self.complete = True
        if self._follow is not None and not self._moved and self.items:
            after = next((it for it in self.items if self._comes_after(it)), None)
            self.cursor = (after or self.items[-1]).key
        self._follow = None

    def fail(self, why: str) -> None:
        """The build stopped with an error. The items that came stay, and the queue is
        settled as if complete: nothing waits for items that will not come."""
        self.failed = why
        self.finish()

    def current(self) -> QueueItem | None:
        return self.items[self._row(self.cursor)] if self.cursor is not None else None

    def position(self) -> int | None:
        return self._row(self.cursor) if self.cursor is not None else None

    def index_of(self, key: str) -> int | None:
        """The row of the item with this key, or None when it is not in the queue."""
        return self._row(key) if key in self._rank else None

    def move(self, delta: int) -> bool:
        """Step through the queue; False, and no move, at either end."""
        if self.cursor is None:
            return False
        index = self._row(self.cursor) + delta
        if not 0 <= index < len(self.items):
            return False
        return self._set(self.items[index].key)

    def go_to(self, key: str) -> bool:
        return key in self._rank and self._set(key)

    def _set(self, key: str) -> bool:
        self.cursor = key
        self._moved = True
        self._follow = None
        return True

    def left(self, is_reviewed: Callable[[str], bool]) -> int:
        """Items whose image is not reviewed: review marks are an image's."""
        return sum(1 for item in self.items if not is_reviewed(item.entry.rel))

    def recheck(self, entry: ImageEntry, ctx: BuildContext) -> None:
        """After `entry` changed: mark each of its items stale while it no longer holds."""
        keys = self.keys_of(entry.rel)
        if not keys:
            return
        held = self.source.still(entry, [self.items[self._row(key)] for key in keys], ctx)
        for key in keys:
            if key in held:
                self.stale.discard(key)
            else:
                self.stale.add(key)


def source_from_json(data):
    """A saved queue's source: an image filter, or Find Bad's findings."""
    if isinstance(data, dict) and data.get("source") == "findings":
        from .findings import Findings              # findings.py builds on this module
        return Findings.from_json(data)
    return ImageFilter.from_json(data)
