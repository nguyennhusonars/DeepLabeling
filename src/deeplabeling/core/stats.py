"""The statistics of some images (docs/design/2026-10-07-bulk-and-stats.md#statistics): their
labels counted per split and class, their boxes' sizes in pixels, how many boxes each image
has, and where the boxes sit. Computed on a worker; Qt-free, so it is tested headless.

Pixel sizes come from the header-only, EXIF-aware size function
(docs/knowledge/caches.md#image-sizes), read only for images that have boxes. An image whose
header cannot be read is counted, and its boxes are left out of the pixel sizes, never guessed.
"""

from __future__ import annotations

import bisect
import math
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .dataset import ImageEntry
from .store import ImageLabels, LabelState

SIZE_EDGES = (8, 16, 32, 64, 128, 256)      #: √(w·h) in pixels; each bucket takes its lower end
SIZE_LABELS = ("< 8", "8–16", "16–32", "32–64", "64–128", "128–256", "≥ 256")
PER_IMAGE_MAX = 20                          #: boxes per image are counted 0 … 19, then 20 or more
GRID = 20                                   #: box centres, on a GRID × GRID grid of the frame
BREATHE, BREATHE_S = 256, 0.0005            #: a warm run is all Python: it pauses this often, this long
FILE_STATES = ("images", "with boxes", "negative", "missing", "unreadable", "shared", "unparsable lines")


def size_bucket(px: float) -> int:
    return bisect.bisect_right(SIZE_EDGES, px)


def _cell(v: float) -> int:
    """A normalised coordinate's grid cell; a centre outside the frame stays at its edge."""
    return min(max(int(v * GRID), 0), GRID - 1)


@dataclass
class Stats:
    splits: tuple[str, ...] = ()                                #: in the order the images met them
    files: Counter = field(default_factory=Counter)             #: (split, one of FILE_STATES) -> count
    boxes: Counter = field(default_factory=Counter)             #: (split, class id) -> boxes
    images_with: Counter = field(default_factory=Counter)       #: (split, class id) -> images with one
    polygons: Counter = field(default_factory=Counter)          #: (split, class id) -> polygons
    sizes: Counter = field(default_factory=Counter)             #: (class id, size bucket) -> boxes
    unsized: int = 0                                            #: images with boxes and no readable header
    malformed: int = 0                                          #: boxes with a size not finite and positive, or a centre not finite
    per_image: Counter = field(default_factory=Counter)         #: min(boxes, PER_IMAGE_MAX) -> images
    centres: Counter = field(default_factory=Counter)           #: (class id, x cell, y cell) -> boxes

    def classes(self) -> tuple[int, ...]:
        """Every class id a box has, the yaml's or not, in order."""
        return tuple(sorted({cls for (split, cls), n in self.boxes.items() if n}))

    def add(self, entry: ImageEntry, labels: ImageLabels, size_of: Callable[[Path], tuple[int, int] | None]) -> None:
        split = entry.split
        if split not in self.splits:
            self.splits += (split,)
        files = self.files
        files[(split, "images")] += 1
        if labels.state is LabelState.ERROR:
            files[(split, "unreadable")] += 1
        elif labels.state is LabelState.MISSING:
            files[(split, "missing")] += 1
        elif labels.negative:
            files[(split, "negative")] += 1
        if labels.state is LabelState.SHARED:
            files[(split, "shared")] += 1
        files[(split, "unparsable lines")] += labels.unparsed
        boxes = labels.boxes
        if labels.state is not LabelState.ERROR:        # an unreadable file's boxes are unknown, not none
            self.per_image[min(len(boxes), PER_IMAGE_MAX)] += 1
        if not boxes:
            return
        files[(split, "with boxes")] += 1
        size = size_of(entry.path)
        if size is None:
            self.unsized += 1
        seen = set()
        for _, line in boxes:
            cls = line.cls_id
            self.boxes[(split, cls)] += 1
            self.polygons[(split, cls)] += line.is_polygon
            seen.add(cls)
            cx, cy, w, h = line.bbox
            # A cleaning tool's input: a box the parser took but no size or place can be read from.
            placed, sized = math.isfinite(cx) and math.isfinite(cy), math.isfinite(w * h) and w > 0 and h > 0
            if not (placed and sized):
                self.malformed += 1
            if placed:
                self.centres[(cls, _cell(cx), _cell(cy))] += 1
            if sized and size is not None:
                self.sizes[(cls, size_bucket(math.sqrt(w * size[0] * h * size[1])))] += 1
        for cls in seen:
            self.images_with[(split, cls)] += 1


def stats_of(entries: Iterable[ImageEntry], labels_of: Callable[[Path], ImageLabels],
             size_of: Callable[[Path], tuple[int, int] | None], cancelled: Callable[[], bool] = lambda: False,
             *, progress: Callable[[int, int], None] | None = None, interval: float = 0.2) -> Stats | None:
    """The statistics of these images; None when cancelled part-way. `progress(done, total)`
    is told at most every `interval` seconds, and at the end."""
    entries = list(entries)
    stats, last = Stats(), time.monotonic()
    for n, entry in enumerate(entries, 1):
        if cancelled():
            return None
        stats.add(entry, labels_of(entry.path), size_of)
        if n % BREATHE == 0:
            time.sleep(BREATHE_S)                   # the GUI thread's turn at the GIL
        if progress is not None and time.monotonic() - last >= interval:
            progress(n, len(entries))
            last = time.monotonic()
    if progress is not None:
        progress(len(entries), len(entries))
    return stats
