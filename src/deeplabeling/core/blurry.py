"""Blurry boxes (docs/design/2026-10-27-blurry.md): every label box scored for sharpness,
ranked against boxes of its own class and size, the blurriest share of each group listed."""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from .dataset import Dataset
from .edits import LineRef
from .findings import BlurFinding
from .predstore import image_stamp
from .queue import BuildContext, ImageFilter, QueueItem, Scored
from .sharpness import MIN_SCORED, box_rect, read_grey, score_image
from .store import LabelState

#: Short sides in px: a box is compared only with boxes of its class in its octave.
OCTAVES = ((8, 15), (16, 31), (32, 63), (64, 127), (128, None))
MIN_PEERS = 20          #: a smaller group is not ranked
MAD_SCALE = 1.4826      #: MAD to a standard deviation, for normal data


def octave(side: int) -> int:
    return next(i for i, (lo, hi) in enumerate(OCTAVES) if hi is None or side <= hi)


def octave_name(i: int) -> str:
    lo, hi = OCTAVES[i]
    return f"{lo}+ px" if hi is None else f"{lo}–{hi} px"


@dataclass(frozen=True)
class BlurSettings:
    share: float = 0.05     #: of each group, listed
    min_side: int = 16      #: px: smaller boxes are too small to judge

    def __post_init__(self):
        if not 0 < self.share <= 1:
            raise ValueError("share: must be above 0% and at most 100%")
        if isinstance(self.min_side, bool) or not isinstance(self.min_side, int) or not 8 <= self.min_side <= 4096:
            raise ValueError("minimum side: must be from 8 to 4096 px")

    def to_json(self) -> dict:
        return {"share": self.share, "min_side": self.min_side}

    @classmethod
    def from_json(cls, data) -> BlurSettings:
        try:
            return cls(float(data["share"]), data["min_side"])
        except (KeyError, TypeError, ValueError, OverflowError) as e:
            raise ValueError(f"not Blurry settings: {data!r}") from e


#: A scored box, ready to rank: (key, entry_order, line, cls, side, lap, cr), where lap is the
#: tiled Laplacian ratio (higher is sharper) and cr Crété-Roffet (higher is blurrier).
#: A plain tuple of plain values, which the garbage collector stops tracking (a subclass, even
#: a NamedTuple, stays tracked): a build keeps hundreds of thousands, and as tracked objects
#: every full collection walked them all -- 200-280 ms each, the window waiting (2026-10-27).
KEY, ORDER, LINE, CLS, SIDE, LAP, CR = range(7)


def candidate(key: str, entry_order: int, line: int, cls: int, side: int, lap: float, cr: float) -> tuple:
    return (key, entry_order, line, cls, side, lap, cr)


def _z(values: np.ndarray) -> np.ndarray:
    """Robust z-scores. Over half a group equal (a still camera's duplicate frames) leaves
    the MAD 0: the mean absolute deviation stands in, scaled alike for normal data."""
    med = np.median(values)
    dev = np.abs(values - med)
    scale = MAD_SCALE * float(np.median(dev)) or 1.2533 * float(dev.mean())
    return (values - med) / max(scale, 1e-6)


def rank(candidates: list[tuple], share: float) -> tuple[dict[str, tuple[float, float]], set[str]]:
    """{key: (z, rank)} of the first `ceil(share · n)` of each group of at least MIN_PEERS,
    blurriest first; and the keys of the groups too small to rank."""
    groups: dict[tuple[int, int], list[tuple]] = defaultdict(list)
    for c in candidates:
        groups[(c[CLS], octave(c[SIDE]))].append(c)
    listed, small = {}, set()
    for members in groups.values():
        n = len(members)
        if n < MIN_PEERS:
            small.update(c[KEY] for c in members)
            continue
        z = (_z(np.array([c[LAP] for c in members])) + _z(-np.array([c[CR] for c in members]))) / 2
        # numpy, not sorted(): a Python sort of a 150k group held the GIL 78 ms in one go
        order = np.lexsort((np.array([c[LINE] for c in members]), np.array([c[ORDER] for c in members]), z))
        for place, i in enumerate(order[:math.ceil(share * n - 1e-9)]):
            listed[members[i][KEY]] = (float(z[i]), place / n)
    return listed, small


BREATHE = 64            #: images between pauses: the GUI thread's turn at the GIL
#: Images per Scored batch: the GUI thread writes each, and 500 images' took 202 ms (2026-10-27).
SCORE_BATCH = 50


@dataclass(frozen=True)
class Blurry:
    """A queue of the blurriest boxes of each class and size in the images its scope
    selects (docs/design/2026-10-27-blurry.md#the-queue)."""

    scope: ImageFilter = field(default_factory=ImageFilter)
    settings: BlurSettings = field(default_factory=BlurSettings)
    needs_model: ClassVar[bool] = False

    def __post_init__(self):
        if self.scope.needs_model:              # built without one, it would stay empty for good
            raise ValueError("Model — a Blurry queue is built without a model: turn it off")

    def _scores(self, entry, ctx: BuildContext, boxes, new: list) -> tuple[dict, tuple[int, int]] | None:
        """({rect: (lap, cr)}, the size the rects are of) for the image's boxes, from the cache
        or a decode (its row then appended to `new`); None when it cannot be decoded."""
        try:
            stamp = image_stamp(entry.path)
        except OSError:
            stamp = None
        size = ctx.size(entry)
        cached = None if stamp is None or size is None or ctx.sharpness is None else ctx.sharpness.get(entry.rel, stamp)
        if cached is not None:
            rects = {box_rect(b, *size) for b in boxes}
            have = {tuple(row[:4]): row[4:] for row in cached}
            if all(r in have for r in rects if r is not None and min(r[2] - r[0], r[3] - r[1]) >= MIN_SCORED):
                return have, size
        grey = read_grey(entry.path)
        if grey is None:
            return None
        scored = score_image(grey, boxes)
        if stamp is not None:
            new.append((entry.rel, stamp, scored))
        return {tuple(row[:4]): row[4:] for row in scored}, (grey.shape[1], grey.shape[0])

    def build(self, ctx: BuildContext, emit, cancelled=lambda: False, *,
              batch: int = 500, interval: float = 0.2, progress=None) -> bool:
        """Score, rank, then stream the listed boxes blurriest first. New scores go out as
        `Scored` batches, a cancelled build's included. False when cancelled part-way."""
        images, last = ctx.dataset.images, time.monotonic()
        candidates, where, new = [], {}, []
        for n, entry in enumerate(images, 1):          # n - 1: the entry's place, kept in `where`
            if cancelled():
                if new:
                    emit(Scored(new))
                return False
            if n % BREATHE == 0:
                time.sleep(0.0005)
            if len(new) >= SCORE_BATCH:
                emit(Scored(new))
                new = []
            if progress is not None and time.monotonic() - last >= interval:
                progress(n - 1, len(images))
                last = time.monotonic()
            if not self.scope.matches(entry, ctx):
                continue
            labels = ctx.labels(entry)
            if labels.state is LabelState.ERROR:
                ctx.count("labels unreadable", entry)
                continue
            lines = [(i, line) for i, line in labels.boxes if not line.is_polygon]
            if not lines:
                continue
            found = self._scores(entry, ctx, [line.bbox for _, line in lines], new)
            if found is None:
                ctx.count("cannot decode", entry)
                continue
            scores, (w, h) = found
            for i, line in lines:
                rect = box_rect(line.bbox, w, h)
                side = 0 if rect is None else min(rect[2] - rect[0], rect[3] - rect[1])
                if side < self.settings.min_side:
                    ctx.count_box("too small", entry, i)
                    continue
                lap, cr = scores[rect]
                if lap is None:
                    ctx.count_box("flat", entry, i)
                    continue
                key = f"{entry.rel}#{i}#blurry"
                candidates.append(candidate(key, entry.order, i, line.cls_id, side, lap, cr))
                where[key] = (n - 1, line.raw.rstrip("\r\n"), *line.bbox)   # plain values: untracked, as Candidate
        if new:
            emit(Scored(new))
        if progress is not None:
            progress(len(images), len(images))
        listed, small = rank(candidates, self.settings.share)
        for c in candidates:
            if c[KEY] in small:
                ctx.count_box("too few peers", images[where[c[KEY]][0]], c[LINE])
        items = []
        for c in candidates:
            if c[KEY] not in listed:
                continue
            pos, text, *box = where[c[KEY]]
            entry, i, box = images[pos], c[LINE], tuple(box)
            if (entry.rel, text, "blurry") in ctx.dismissed:
                continue                            # a peer still: it only leaves the list
            z, place = listed[c[KEY]]
            finding = BlurFinding(line=i, text=text, kind="blurry", score=place, label_cls=c[CLS],
                                  label_box=box, z=z, group=octave_name(octave(c[SIDE])))
            items.append(QueueItem(c[KEY], entry, rank=(place, z, entry.order, i),
                                   focus=LineRef(i, c[CLS], box), finding=finding))
        items.sort(key=lambda item: item.sort_key)
        for start in range(0, len(items), batch):
            if cancelled():
                return False
            emit(items[start:start + batch])
        return True

    def still(self, entry, items: list[QueueItem], ctx: BuildContext) -> set[str]:
        """The keys of one image's `items` whose line is still in the file, as it was."""
        texts = {line.raw.rstrip("\r\n") for line in ctx.labels(entry).lines}
        return {it.key for it in items if it.finding.text in texts}

    def holds(self, item: QueueItem, ctx: BuildContext) -> bool:
        return item.key in self.still(item.entry, [item], ctx)

    def highlight(self, labels, dataset, seen=None) -> frozenset[int]:
        return frozenset()          # a box is shown by its focus, as a finding is

    def highlight_predictions(self, labels, dataset, seen=None) -> frozenset[int]:
        return frozenset()

    def describe(self, dataset: Dataset) -> str:
        text = f"blurry: {self.settings.share * 100:g}% of each class and size, ≥ {self.settings.min_side} px"
        return text if self.scope == ImageFilter() else f"{text} of {self.scope.describe(dataset)}"

    def to_json(self) -> dict:
        return {"source": "blurry", "scope": self.scope.to_json(), "settings": self.settings.to_json()}

    @classmethod
    def from_json(cls, data) -> Blurry:
        try:
            return cls(ImageFilter.from_json(data["scope"]), BlurSettings.from_json(data["settings"]))
        except (KeyError, TypeError) as e:
            raise ValueError(f"not a blurry queue: {data!r}") from e
