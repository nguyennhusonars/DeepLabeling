"""Queues: the list being worked through (docs/design/2026-10-04-app-foundation.md#queue).

A source builds its items on a worker from immutable inputs -- the dataset, the
thread-safe store and a snapshot of the review marks -- and streams them in
batches. A Queue holds them on the GUI thread with one cursor, an identity key.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import ClassVar

from .dataset import Dataset, ImageEntry
from .store import ImageLabels, LabelState, LabelStore

LABEL_STATES = ("missing", "negative", "boxes")


@dataclass(frozen=True)
class QueueItem:
    key: str
    entry: ImageEntry


@dataclass(frozen=True)
class BuildContext:
    dataset: Dataset
    store: LabelStore
    reviewed: frozenset[str]        #: review-mark keys, snapshotted before the build

    def labels(self, entry: ImageEntry) -> ImageLabels:
        return self.store.get(entry.path)


class Condition:
    """One test an image must pass. Subclasses are frozen dataclasses."""

    kind: ClassVar[str]
    needs_labels: ClassVar[bool] = True

    def test(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        raise NotImplementedError

    def describe(self, dataset: Dataset) -> str:
        raise NotImplementedError

    def highlight(self, labels: ImageLabels, dataset: Dataset) -> frozenset[int]:
        """Line indices of the boxes that made the condition hold."""
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

    def highlight(self, labels, dataset):
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

    def matches(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        if self.splits and entry.split not in self.splits:
            return False
        cheap_first = sorted(self.conditions, key=lambda c: c.needs_labels)
        return all(c.test(entry, ctx) for c in cheap_first)

    def highlight(self, labels: ImageLabels, dataset: Dataset) -> frozenset[int]:
        found: frozenset[int] = frozenset()
        for condition in self.conditions:
            found |= condition.highlight(labels, dataset)
        return found

    def build(self, ctx: BuildContext, emit: Callable[[list[QueueItem]], None],
              cancelled: Callable[[], bool] = lambda: False, *,
              batch: int = 500, interval: float = 0.2) -> bool:
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
    """A queue's items in order, one cursor (an identity key), and which items no
    longer match since the queue was built. Used on the GUI thread."""

    def __init__(self, source: ImageFilter, *, follow: ImageEntry | None = None):
        self.source = source
        self.items: list[QueueItem] = []
        self.cursor: str | None = None
        self.stale: set[str] = set()
        self.complete = False
        self._pos: dict[str, int] = {}
        self._follow = follow       #: the item the cursor was on before a rebuild
        self._moved = False

    def __len__(self) -> int:
        return len(self.items)

    def __contains__(self, key: str) -> bool:
        return key in self._pos

    def extend(self, batch: Iterable[QueueItem]) -> None:
        for item in batch:
            if item.key in self._pos:
                continue
            self._pos[item.key] = len(self.items)
            self.items.append(item)
            if self._follow is not None and not self._moved and item.key == self._follow.rel:
                self.cursor = item.key
                self._follow = None
        if self.cursor is None and self.items:
            self.cursor = self.items[0].key

    def finish(self) -> None:
        """The build is done. A cursor still waiting for its old item takes the first
        item after it in dataset order, or the last item."""
        self.complete = True
        if self._follow is not None and not self._moved and self.items:
            after = next((it for it in self.items if it.entry.order > self._follow.order), None)
            self.cursor = (after or self.items[-1]).key
        self._follow = None

    def current(self) -> QueueItem | None:
        return self.items[self._pos[self.cursor]] if self.cursor is not None else None

    def position(self) -> int | None:
        return self._pos[self.cursor] if self.cursor is not None else None

    def index_of(self, key: str) -> int | None:
        """The row of the item with this key, or None when it is not in the queue."""
        return self._pos.get(key)

    def move(self, delta: int) -> bool:
        """Step through the queue; False, and no move, at either end."""
        if self.cursor is None:
            return False
        index = self._pos[self.cursor] + delta
        if not 0 <= index < len(self.items):
            return False
        return self._set(self.items[index].key)

    def go_to(self, key: str) -> bool:
        return key in self._pos and self._set(key)

    def _set(self, key: str) -> bool:
        self.cursor = key
        self._moved = True
        self._follow = None
        return True

    def left(self, is_reviewed: Callable[[str], bool]) -> int:
        return sum(1 for item in self.items if not is_reviewed(item.key))

    def recheck(self, entry: ImageEntry, ctx: BuildContext) -> None:
        """After `entry` changed: mark its item stale while it no longer matches."""
        if entry.rel not in self._pos:
            return
        if self.source.matches(entry, ctx):
            self.stale.discard(entry.rel)
        else:
            self.stale.add(entry.rel)
