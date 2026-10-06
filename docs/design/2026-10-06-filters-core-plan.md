# Slice 3a: the filters core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build slice 3's Qt-free core:
- one header-only, EXIF-aware image size function, and its cache;
- typed ranges;
- three new conditions of `ImageFilter`: box size on the same box as the class, overlap between labels, and Label/Prediction IoU;
- stack counts at IoU ≥ 0.9.

**Architecture:**
- **The conditions** are frozen dataclasses in `core/queue.py`, like slice 1's, and run in slice 1's streaming build.
- **What a condition needs beyond the label file** comes from `BuildContext`:
  - an image's size, from `core/imagesize.py`;
  - the loaded model's rows, through a `ModelSnapshot`;
  - a counter of what could not be settled.
- **Each condition's highlight** reads what the view knows, through `Seen`.
- **The disagreement rules** live in `core/disagree.py`, the overlap rule in slice 1's `core/overlap.py`.

Plan 3b puts it all on screen.

**Tech Stack:** Python 3.10 (conda base), Pillow (header reads only), sqlite3 through slice 2's store, pytest.

**Spec:** [2026-10-06-filters.md](2026-10-06-filters.md). This plan implements:
- its *Conditions*;
- *Building and keeping current*, except the triggers;
- the core rows of its *Performance targets*.

Plan 3b builds the queue editor, the chip, the canvas, waiting for the model, rebuilds and rechecks, and the window's measurements.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)). Pillow is already a dependency (`pyproject.toml`).
- **`src/deeplabeling/core/` imports no Qt, nor ultralytics or torch.** `tests/core/test_core_imports_no_qt.py` and `tests/core/test_inference.py` check it.
- **Never decode an image to learn its size** ([caches.md](../knowledge/caches.md#image-sizes)). A test refuses `PIL.Image.Image.load`.
- **Ranges are inclusive, never swapped and never clamped** (`legacy/yolo_labeling/core/ranges.py::range_error`). A reversed range is refused by name.
- **Unmapped is inconclusive, and an upper bound never removes a prediction from matching** ([landmines 5 and 6](../../CLAUDE.md#landmines)).
- **The disk is nearly full** ([landmine 9](../../CLAUDE.md#landmines)). The measurement reads pvn-vehicle in place and writes nothing.
- **Tests write only to temporary folders** ([landmine 10](../../CLAUDE.md#landmines)).
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice3-filters`, which already holds the spec. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone hunting with these filters. Each has a named test:

1. **A phone photo rotated by EXIF, under a size in px.** Its width and height must be the frame as shown, not as stored. *(Task 2 `test_pixels_are_the_frame_as_shown_after_exif_rotation`; Task 1 `test_a_quarter_turn_in_exif_swaps_width_and_height`.)*
2. **An image whose header cannot be read, under a size in px.** It does not match and is counted. A size in % still answers for it from the label file. *(Task 2 `test_an_image_without_a_readable_size_does_not_match_and_is_counted`.)*
3. **An upper confidence bound.** It must never turn a label the model sees at 0.97 into "unseen". *(Task 4 `test_an_upper_bound_never_removes_a_prediction_from_matching`.)*
4. **A prediction of an unmapped class.** It sees the label it covers, but it is never "nobody labelled". *(Task 4 `test_a_label_no_prediction_overlaps_is_unseen`, which covers `weird/`, and `test_a_mapped_prediction_no_label_overlaps_was_labelled_by_nobody`, which covers `camA/0003`.)*
5. **"Never inferred" against "inferred, nothing found".** The first is counted and left out; the second is evaluated. *(Task 4 `test_images_never_inferred_are_counted_and_those_inferred_empty_are_evaluated`.)*

## Found while building this plan

The plan's code was built in a scratch copy first, and its suite ran green there (734 passed). `tools/measure_filters.py` then ran on `data_13class.yaml`, read-only:
- a size in px took 9.96 s cold and 0.94 s warm;
- a size in % took 0.62 s;
- overlap took 1.84–3.45 s;
- first items arrived in 69–762 ms.

Every core target was met.

- **Stack counts already existed.** Slice 1's `core/overlap.py` counts boxes at IoU 0.99–1.00, with the predicate the canvas shares. This plan moves that one constant to 0.9, as the spec decides, and renames it `STACKED`.
- **0.1 × 100 is 10.000000000000002.** A box exactly at a range's end would fall outside it, so ends are compared within `EPS` = 1e-9. Label files hold six decimals.
- **An overlap counts every parsed line, including class ids the yaml does not name.** The gauntlet's `99` and `-1` lines overlap each other at IoU 1.0, and they are what the file holds.
- **The overlap counts differ from matching.md's dated figures** (1, 47 and 282 images, against 8, 123 and 570). Those counted every label file a recursive walk finds ([datasets.md](../knowledge/datasets.md#counting)), not the yaml's images.

## Decisions this plan makes

- **`highlight` gains a third argument, `seen: Seen`**, with a default: the image's size, the model's predictions and its class map. Slice 1's callers are unchanged, and plan 3b passes what the window knows. `highlight_predictions` is its twin for the predictions layer.
- **Conditions run by `cost`:**
  - 0, nothing read;
  - 1, the label file;
  - 2, an image header;
  - 3, the store.

  `needs_labels` stays, as the default's input.
- **`BuildContext.unsettled` is a `Counter`** that one build or recheck owns: `could not be sized`, `not inferred`, `no model`.
- **A `Boxes` with no class means any class.** A class the yaml does not name matches nothing, as slice 1's class condition does.
- **The model condition without a model counts `no model`.** Plan 3b never builds without one; the core still answers.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/imagesize.py`, `workspace.py` | `image_size`, `ImageSizes`; the workspace's cache | 1 |
| `src/deeplabeling/core/ranges.py`, `queue.py` | `range_error`; `Seen`, `BuildContext.size`/`count`/`unsettled`, `cost`, `Boxes` | 2 |
| `src/deeplabeling/core/overlap.py`, `queue.py`, `ui/boxes.py` | `STACKED` at 0.9; `Overlap` | 3 |
| `src/deeplabeling/core/disagree.py`, `queue.py` | the disagreement rules; `ModelSnapshot`, `ModelDisagrees`, `highlight_predictions`, `needs_model` | 4 |
| `tools/measure_filters.py`, the spec, `caches.md`, `CLAUDE.md` | the measurement; the status | 5 |

---

### Task 1: Image sizes from the header

**Files:**
- Create: `src/deeplabeling/core/imagesize.py`, `tests/core/test_imagesize.py`
- Modify: `src/deeplabeling/core/workspace.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `image_size(path) -> (width, height) | None`, as shown: EXIF orientations 5–8 swap width and height. `None` means not a readable image.
  - `ImageSizes().get(path)`: cached per path, stamped with the file's `(st_size, st_mtime_ns)`, failures cached too. It is thread-safe.
  - `Workspace.sizes: ImageSizes`.

- [ ] **Step 1: Commit this plan, on the spec's branch**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout slice3-filters
git add docs/design/2026-10-06-filters-core-plan.md
git commit -m "docs: the slice 3a filters core plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/core/test_imagesize.py`:

```python
"""Image sizes from the file header, EXIF orientation honoured, never decoded
(docs/knowledge/caches.md#image-sizes)."""

import threading

from PIL import Image

from deeplabeling.core import imagesize
from deeplabeling.core.imagesize import ImageSizes, image_size
from fixtures import make_image


def test_a_size_is_width_by_height(ds):
    assert image_size(ds.img("camA/0001.jpg")) == (64, 48)


def test_a_quarter_turn_in_exif_swaps_width_and_height(ds):
    assert image_size(ds.img("camB/rot.jpg")) == (48, 64)       # stored 64 x 48, orientation 6


def test_a_file_that_is_no_image_has_no_size(ds):
    assert image_size(ds.img("bad/corrupt.jpg")) is None
    assert image_size(ds.root / "nowhere.jpg") is None


def test_the_pixels_are_never_decoded(ds, monkeypatch):
    def refuse(self):
        raise AssertionError("decoded")

    monkeypatch.setattr(Image.Image, "load", refuse)
    assert image_size(ds.img("camB/rot.jpg")) == (48, 64)


def test_sizes_are_served_from_the_cache_while_the_file_is_unchanged(ds, monkeypatch):
    sizes, calls = ImageSizes(), []
    real = imagesize.image_size
    monkeypatch.setattr(imagesize, "image_size", lambda path: calls.append(path) or real(path))
    path = ds.img("camA/0001.jpg")
    assert sizes.get(path) == sizes.get(path) == (64, 48)
    assert len(calls) == 1
    make_image(path, 80, 60)                                     # replaced: a new stamp
    assert sizes.get(path) == (80, 60) and len(calls) == 2


def test_an_unreadable_size_is_cached_too_and_a_missing_file_is_none(ds, monkeypatch):
    sizes, calls = ImageSizes(), []
    real = imagesize.image_size
    monkeypatch.setattr(imagesize, "image_size", lambda path: calls.append(path) or real(path))
    assert sizes.get(ds.img("bad/corrupt.jpg")) is None and sizes.get(ds.img("bad/corrupt.jpg")) is None
    assert len(calls) == 1
    assert sizes.get(ds.root / "nowhere.jpg") is None


def test_many_threads_share_one_cache(ds):
    sizes, seen, errors = ImageSizes(), [], []

    def ask():
        try:
            for _ in range(50):
                seen.append(sizes.get(ds.img("camA/0001.jpg")))
        except Exception as e:                                  # pragma: no cover - the failure
            errors.append(e)

    threads = [threading.Thread(target=ask) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and set(seen) == {(64, 48)}


def test_a_workspace_keeps_one_cache_for_its_dataset(ds):
    from deeplabeling.core.workspace import Workspace

    ws = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    try:
        assert isinstance(ws.sizes, ImageSizes) and ws.sizes.get(ds.img("camB/rot.jpg")) == (48, 64)
    finally:
        ws.close()
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_imagesize.py`
Expected: `cannot import name 'imagesize'`.

- [ ] **Step 4: Read sizes from headers, and give the workspace a cache**

Create `src/deeplabeling/core/imagesize.py`:

```python
"""Image sizes from the file header, EXIF orientation honoured: never a decode
(docs/knowledge/caches.md#image-sizes). A size condition over 45k frames reads 45k
headers; decoding them instead cost minutes."""

from __future__ import annotations

import threading
from pathlib import Path

from PIL import Image

ORIENTATION = 274                   #: the EXIF orientation tag
QUARTER_TURNS = {5, 6, 7, 8}        #: orientations shown turned a quarter: width and height swap


def image_size(path) -> tuple[int, int] | None:
    """(width, height) as the image is shown, or None when it is not a readable image."""
    try:
        with Image.open(path) as im:             # reads the header only
            width, height = im.size
            turn = im.getexif().get(ORIENTATION)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None
    return (height, width) if turn in QUARTER_TURNS else (width, height)


class ImageSizes:
    """The open dataset's image sizes, kept in memory, each stamped with its file's size
    and mtime: an image replaced on disk is read again. Safe across threads: a queue
    build asks from a worker while the GUI asks for the image on screen."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sizes: dict[Path, tuple[tuple[int, int], tuple[int, int] | None]] = {}

    def get(self, path) -> tuple[int, int] | None:
        path = Path(path)
        try:
            st = path.stat()
        except OSError:
            return None
        stamp = (st.st_size, st.st_mtime_ns)
        with self._lock:
            hit = self._sizes.get(path)
        if hit is not None and hit[0] == stamp:
            return hit[1]
        size = image_size(path)
        with self._lock:
            self._sizes[path] = (stamp, size)
        return size
```

In `src/deeplabeling/core/workspace.py`, replace:

```python

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

```

with:

```python

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

```

In `src/deeplabeling/core/workspace.py`, replace:

```python
from .editor import Editor
from .history import History
from .predstore import STORE_NAME, PredictionStore
from .review import ReviewMarks
```

with:

```python
from .editor import Editor
from .history import History
from .imagesize import ImageSizes
from .predstore import STORE_NAME, PredictionStore
from .review import ReviewMarks
```

In `src/deeplabeling/core/workspace.py`, replace:

```python
    editor: Editor
    predictions: PredictionStore

    @classmethod
```

with:

```python
    editor: Editor
    predictions: PredictionStore
    sizes: ImageSizes = field(default_factory=ImageSizes)   #: its images' sizes, read from headers

    @classmethod
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_imagesize.py tests/core/test_workspace.py tests/core/test_core_imports_no_qt.py`
Expected: 21 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 692 passed.

```bash
git add src/deeplabeling/core/imagesize.py src/deeplabeling/core/workspace.py tests/core/test_imagesize.py
git commit -m "core: image sizes from the header, EXIF orientation honoured, cached per dataset" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Ranges, and box size on the same box as the class

**Files:**
- Create: `src/deeplabeling/core/ranges.py`, `tests/core/test_ranges.py`, `tests/core/test_conditions.py`
- Modify: `src/deeplabeling/core/queue.py`

**Interfaces:**
- Consumes: from Task 1, `ImageSizes` and `image_size`.
- Produces:
  - `range_error(lo, hi, name, *, lo_min=0.0, hi_max=1.0, open_ends=False) -> str | None`.
  - In `deeplabeling.core.queue`:
    - `UNITS = ("px", "%")` and `EPS = 1e-9`;
    - `Seen(size=None)` and `NOTHING_SEEN`;
    - `BuildContext(dataset, store, reviewed, sizes=None, unsettled=Counter())`, with `.size(entry)` and `.count(what)`;
    - `Condition.cost` and `Condition.highlight(labels, dataset, seen=NOTHING_SEEN)`;
    - `Boxes(names=(), w=(lo, hi), h=(lo, hi), unit="px")`, of kind `"boxes"`, where an end of `None` is open. Its JSON is `{"kind", "names", "w", "h", "unit"}`. It refuses an unusable range with `ValueError(range_error(...))`.
    - `ImageFilter.highlight(labels, dataset, seen=NOTHING_SEEN)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_ranges.py`:

```python
"""Typed ranges: never swapped, never clamped; refused by name
(`legacy/yolo_labeling/core/ranges.py::range_error`)."""

from deeplabeling.core.ranges import range_error


def test_a_usable_range_has_no_error_and_a_point_is_a_range():
    assert range_error(0.5, 1.0, "IoU") is None and range_error(0.7, 0.7, "IoU") is None


def test_a_reversed_range_is_refused_by_name_not_swapped():
    assert range_error(0.9, 0.5, "IoU") == "IoU: 0.9 is above 0.5: put the lower end first"


def test_ends_outside_their_bounds_are_refused_not_clamped():
    assert range_error(-0.1, 0.5, "IoU") == "IoU: the lower end cannot be below 0"
    assert range_error(0.5, 1.2, "confidence") == "confidence: the upper end cannot be above 1"


def test_open_ends_only_where_allowed():
    assert range_error(None, 0.5, "IoU") == "IoU: both ends must be numbers"
    assert range_error(None, 30, "width", hi_max=None, open_ends=True) is None
    assert range_error(10, None, "width", hi_max=100, open_ends=True) is None
    assert range_error(10, 120, "width", hi_max=100, open_ends=True) == "width: the upper end cannot be above 100"
```

Create `tests/core/test_conditions.py`:

```python
"""Slice 3's queue conditions (docs/design/2026-10-06-filters.md#conditions)."""

import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.imagesize import ImageSizes
from deeplabeling.core.queue import (
    Boxes,
    BuildContext,
    ImageFilter,
    NameContains,
    Seen,
    condition_from_json,
)
from deeplabeling.core.store import LabelStore


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


@pytest.fixture
def ctx(dataset):
    return BuildContext(dataset, LabelStore(dataset), frozenset(), sizes=ImageSizes())


def keys(condition, ctx, *more):
    batches = []
    assert ImageFilter(conditions=(condition, *more)).build(ctx, batches.append)
    return [item.key for batch in batches for item in batch]


# camA/0001 (64 x 48): a person 20% x 30% (12.8 x 14.4 px) and a car 10% x 10% (6.4 x 4.8 px).

def test_size_and_class_hold_on_the_same_box(ctx):
    assert "camA/images/0001.jpg" in keys(Boxes(("car",), w=(None, 10), unit="%"), ctx)
    assert "camA/images/0001.jpg" not in keys(Boxes(("person",), w=(None, 10), unit="%"), ctx)


def test_both_ends_are_inclusive(ctx):
    exact = Boxes(("car",), w=(10, 10), h=(10, 10), unit="%")
    assert "camA/images/0001.jpg" in keys(exact, ctx)
    assert "camA/images/0001.jpg" in keys(Boxes(("car",), w=(6.4, 6.4), h=(4.8, 4.8), unit="px"), ctx)


def test_no_class_means_any_class_and_an_unknown_class_matches_nothing(ctx):
    assert "camA/images/0001.jpg" in keys(Boxes((), w=(20, 20), unit="%"), ctx)
    assert keys(Boxes(("truck",), w=(0, None), unit="%"), ctx) == []


def test_pixels_are_the_frame_as_shown_after_exif_rotation(ctx):
    # camB/0001 (64 x 48) and camB/rot (shown 48 x 64) hold the same bus_m line: 15% x 15%.
    found = keys(Boxes(("bus_m",), w=(7, 8), h=(9, 10), unit="px"), ctx)
    assert "camB/images/rot.jpg" in found and "camB/images/0001.jpg" not in found


def test_an_image_without_a_readable_size_does_not_match_and_is_counted(ctx):
    assert "bad/images/corrupt.jpg" not in keys(Boxes((), w=(0, None), unit="px"), ctx)
    assert ctx.unsettled["could not be sized"] == 1
    assert "bad/images/corrupt.jpg" in keys(Boxes((), w=(0, None), unit="%"), ctx)    # % needs no size


def test_the_cheapest_condition_goes_first_so_skipped_images_are_not_counted(ctx):
    keys(Boxes((), w=(0, None), unit="px"), ctx, NameContains("camA"))
    assert ctx.unsettled == {}


def test_the_highlight_is_the_boxes_that_matched(ctx, dataset):
    labels = ctx.labels(dataset.entry(dataset.root / "camA/images/0001.jpg"))
    assert Boxes((), w=(None, 10), unit="%").highlight(labels, dataset) == {1}
    px = Boxes((), w=(None, 7), unit="px")
    assert px.highlight(labels, dataset, Seen(size=(64, 48))) == {1}
    assert px.highlight(labels, dataset) == frozenset()         # pixels, with no size known


@pytest.mark.parametrize("condition, text", [
    (Boxes(("car",), w=(10, 30), unit="px"), "has a car 10–30 px wide"),
    (Boxes(("car", "bus_m"), h=(None, 5), unit="%"), "has a car or bus_m ≤ 5% high"),
    (Boxes((), w=(50, None), h=(0.5, 2), unit="%"), "has a box ≥ 50% wide, 0.5–2% high"),
])
def test_a_size_reads_as_words(condition, text, dataset):
    assert condition.describe(dataset) == text


def test_a_size_survives_its_json(dataset):
    for condition in (Boxes(("car",), w=(10, 30), unit="px"), Boxes((), h=(None, 5), unit="%")):
        assert condition_from_json(condition.to_json()) == condition


@pytest.mark.parametrize("kw, why", [
    (dict(w=(30, 10)), "width: 30 is above 10: put the lower end first"),
    (dict(h=(-1, 5)), "height: the lower end cannot be below 0"),
    (dict(w=(10, 120), unit="%"), "width: the upper end cannot be above 100"),
    (dict(unit="cm"), "unknown size unit 'cm'"),
])
def test_an_unusable_size_is_refused(kw, why):
    with pytest.raises(ValueError, match=why):
        Boxes((), **kw)
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_ranges.py tests/core/test_conditions.py`
Expected: `No module named 'deeplabeling.core.ranges'`.

- [ ] **Step 3: Ranges, the context's size and counter, cost order, and `Boxes`**

Create `src/deeplabeling/core/ranges.py`:

```python
"""Ranges typed by a person: inclusive at both ends, never swapped and never clamped
(`legacy/yolo_labeling/core/ranges.py::range_error`). People edit one end at a time, so a
reversed range is a normal state while typing; it is refused, by name, when used."""

from __future__ import annotations


def range_error(lo, hi, name: str, *, lo_min: float = 0.0, hi_max: float | None = 1.0,
                open_ends: bool = False) -> str | None:
    """Why [lo, hi] is not a usable range, or None. An end may be None (open) only with
    `open_ends`; `hi_max` None means no upper bound."""
    if not open_ends and (lo is None or hi is None):
        return f"{name}: both ends must be numbers"
    if lo is not None and lo < lo_min:
        return f"{name}: the lower end cannot be below {lo_min:g}"
    if hi is not None and hi_max is not None and hi > hi_max:
        return f"{name}: the upper end cannot be above {hi_max:g}"
    if lo is not None and hi is not None and lo > hi:
        return f"{name}: {lo:g} is above {hi:g}: put the lower end first"
    return None
```

In `src/deeplabeling/core/queue.py`, replace:

```python

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import ClassVar

from .dataset import Dataset, ImageEntry
from .store import ImageLabels, LabelState, LabelStore

LABEL_STATES = ("missing", "negative", "boxes")


```

with:

```python

import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import ClassVar

from .dataset import Dataset, ImageEntry
from .imagesize import ImageSizes, image_size
from .ranges import range_error
from .store import ImageLabels, LabelState, LabelStore

LABEL_STATES = ("missing", "negative", "boxes")
UNITS = ("px", "%")
EPS = 1e-9          #: label files hold six decimals; a size at a range's end is inside it


```

In `src/deeplabeling/core/queue.py`, replace:

```python
    store: LabelStore
    reviewed: frozenset[str]        #: review-mark keys, snapshotted before the build

    def labels(self, entry: ImageEntry) -> ImageLabels:
        return self.store.get(entry.path)


```

with:

```python
    store: LabelStore
    reviewed: frozenset[str]        #: review-mark keys, snapshotted before the build
    sizes: ImageSizes | None = None     #: the open dataset's size cache, when there is one
    #: Images a condition could not settle ("could not be sized", "not inferred"), counted
    #: for the queue chip. One build or recheck owns it; it is never shared across threads.
    unsettled: Counter = field(default_factory=Counter)

    def labels(self, entry: ImageEntry) -> ImageLabels:
        return self.store.get(entry.path)

    def size(self, entry: ImageEntry) -> tuple[int, int] | None:
        """The image's size as shown, from its header; None when it cannot be read."""
        return self.sizes.get(entry.path) if self.sizes is not None else image_size(entry.path)

    def count(self, what: str) -> None:
        self.unsettled[what] += 1


@dataclass(frozen=True)
class Seen:
    """What a view knows of an image besides its labels, for a condition's highlight."""

    size: tuple[int, int] | None = None     #: as shown: what a size in px is scaled by


NOTHING_SEEN = Seen()


```

In `src/deeplabeling/core/queue.py`, replace:

```python
    needs_labels: ClassVar[bool] = True

    def test(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        raise NotImplementedError
```

with:

```python
    needs_labels: ClassVar[bool] = True

    @property
    def cost(self) -> int:
        """Conditions run cheapest first: 0 asks nothing of the disk, 1 reads the label
        file, 2 an image header, 3 the prediction store."""
        return 1 if self.needs_labels else 0

    def test(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        raise NotImplementedError
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        raise NotImplementedError

    def highlight(self, labels: ImageLabels, dataset: Dataset) -> frozenset[int]:
        """Line indices of the boxes that made the condition hold."""
        return frozenset()
```

with:

```python
        raise NotImplementedError

    def highlight(self, labels: ImageLabels, dataset: Dataset, seen: Seen = NOTHING_SEEN) -> frozenset[int]:
        """Line indices of the boxes that made the condition hold."""
        return frozenset()
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        return ("has " if self.present else "lacks ") + " or ".join(self.names)

    def highlight(self, labels, dataset):
        if not self.present:
            return frozenset()
```

with:

```python
        return ("has " if self.present else "lacks ") + " or ".join(self.names)

    def highlight(self, labels, dataset, seen=NOTHING_SEEN):
        if not self.present:
            return frozenset()
```

In `src/deeplabeling/core/queue.py`, replace:

```python


def condition_from_json(data) -> Condition:
    try:
```

with:

```python


def _in(value: float, bounds: tuple[float | None, float | None]) -> bool:
    lo, hi = bounds
    return (lo is None or value >= lo - EPS) and (hi is None or value <= hi + EPS)


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
                         and _in(line.bbox[2] * sx, self.w) and _in(line.bbox[3] * sy, self.h))

    def test(self, entry, ctx):
        size = None
        if self.unit == "px":
            size = ctx.size(entry)
            if size is None:
                ctx.count("could not be sized")
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


def condition_from_json(data) -> Condition:
    try:
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        if kind == "name":
            return NameContains(str(data["text"]))
    except (KeyError, TypeError) as e:
        raise ValueError(f"not a queue condition: {data!r}") from e
```

with:

```python
        if kind == "name":
            return NameContains(str(data["text"]))
        if kind == "boxes":
            return Boxes(tuple(str(n) for n in data["names"]), tuple(data["w"]), tuple(data["h"]),
                         str(data["unit"]))
    except (KeyError, TypeError) as e:
        raise ValueError(f"not a queue condition: {data!r}") from e
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        if self.splits and entry.split not in self.splits:
            return False
        cheap_first = sorted(self.conditions, key=lambda c: c.needs_labels)
        return all(c.test(entry, ctx) for c in cheap_first)

    def highlight(self, labels: ImageLabels, dataset: Dataset) -> frozenset[int]:
        found: frozenset[int] = frozenset()
        for condition in self.conditions:
            found |= condition.highlight(labels, dataset)
        return found

```

with:

```python
        if self.splits and entry.split not in self.splits:
            return False
        cheap_first = sorted(self.conditions, key=lambda c: c.cost)
        return all(c.test(entry, ctx) for c in cheap_first)

    def highlight(self, labels: ImageLabels, dataset: Dataset, seen: Seen = NOTHING_SEEN) -> frozenset[int]:
        found: frozenset[int] = frozenset()
        for condition in self.conditions:
            found |= condition.highlight(labels, dataset, seen)
        return found

```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_ranges.py tests/core/test_conditions.py tests/core/test_queue.py`
Expected: 55 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 711 passed.

```bash
git add src/deeplabeling/core/ranges.py src/deeplabeling/core/queue.py tests/core/test_ranges.py tests/core/test_conditions.py
git commit -m "core: a box-size condition, class and size on the same box, in px or % of the frame" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Overlap between labels, and stack counts at 0.9

**Files:**
- Modify: `src/deeplabeling/core/overlap.py`, `src/deeplabeling/core/queue.py`, `src/deeplabeling/ui/boxes.py`, `tests/core/test_overlap.py`, `tests/core/test_conditions.py`

**Interfaces:**
- Consumes: slice 1's `core/overlap.py` (`SCOPES`, `stack_counts`); from Task 2, `range_error` and `Seen`.
- Produces:
  - `STACKED = ("any", 0.9, 1.0)`, which replaces `DUPLICATES`: what every caption's `×N` counts.
  - `Overlap(scope="different", lo=0.5, hi=1.0)`, of kind `"overlap"`, whose test and highlight are one predicate. Its JSON is `{"kind", "scope", "lo", "hi"}`.
  - `SCOPE_WORDS`, for its description.

- [ ] **Step 1: Write the failing tests**

In `tests/core/test_conditions.py`, replace:

```python
    ImageFilter,
    NameContains,
    Seen,
    condition_from_json,
```

with:

```python
    ImageFilter,
    NameContains,
    Overlap,
    Seen,
    condition_from_json,
```

In `tests/core/test_conditions.py`, replace:

```python
    with pytest.raises(ValueError, match=why):
        Boxes((), **kw)
```

with:

```python
    with pytest.raises(ValueError, match=why):
        Boxes((), **kw)


# bad/ok holds the gauntlet: lines 5, 6 and 10 are one class-0 box three times, line 0 is a
# class-1 box on the same spot, and lines 1 (class 99) and 2 (class -1) are one smaller box twice.

@pytest.mark.parametrize("scope, lines", [("same", {5, 6, 10}), ("different", {0, 1, 2, 5, 6, 10}),
                                          ("any", {0, 1, 2, 5, 6, 10})])
def test_overlapping_labels_by_scope_and_the_highlight_is_what_counted(scope, lines, ctx, dataset):
    condition = Overlap(scope, 0.99, 1.0)
    assert keys(condition, ctx) == ["bad/images/ok.jpg"]
    labels = ctx.labels(dataset.entry(dataset.root / "bad/images/ok.jpg"))
    assert condition.highlight(labels, dataset) == lines


def test_a_range_that_excludes_identical_boxes_finds_none_of_them(ctx):
    assert keys(Overlap("any", 0.5, 0.98), ctx) == []


def test_an_overlap_reads_as_words_and_survives_its_json(dataset):
    condition = Overlap("same", 0.99, 1.0)
    assert condition.describe(dataset) == "labels overlapping, same class, IoU 0.99–1.00"
    assert Overlap("different", 0.5, 1.0).describe(dataset) == "labels overlapping, different classes, IoU 0.50–1.00"
    assert condition_from_json(condition.to_json()) == condition


@pytest.mark.parametrize("args, why", [
    (("both", 0.5, 1.0), "unknown overlap scope 'both'"),
    (("same", 0.9, 0.5), "IoU: 0.9 is above 0.5: put the lower end first"),
    (("same", 0.5, 1.5), "IoU: the upper end cannot be above 1"),
])
def test_an_unusable_overlap_is_refused(args, why):
    with pytest.raises(ValueError, match=why):
        Overlap(*args)
```

In `tests/core/test_overlap.py`, replace:

```python
import pytest

from deeplabeling.core.overlap import DUPLICATES, iou_in_range, pair_counts, stack_counts

A = (0.5, 0.5, 0.2, 0.2)
```

with:

```python
import pytest

from deeplabeling.core.overlap import STACKED, iou_in_range, pair_counts, stack_counts

A = (0.5, 0.5, 0.2, 0.2)
```

In `tests/core/test_overlap.py`, replace:

```python

def test_identical_boxes_are_counted():
    assert stack_counts([(0, A), (0, A), (1, FAR)], *DUPLICATES) == {0: 2, 1: 2}


def test_three_identical_boxes_each_read_three():
    assert stack_counts([(0, A), (0, A), (2, A)], *DUPLICATES) == {0: 3, 1: 3, 2: 3}


```

with:

```python

def test_identical_boxes_are_counted():
    assert stack_counts([(0, A), (0, A), (1, FAR)], *STACKED) == {0: 2, 1: 2}


def test_three_identical_boxes_each_read_three():
    assert stack_counts([(0, A), (0, A), (2, A)], *STACKED) == {0: 3, 1: 3, 2: 3}


```

In `tests/core/test_overlap.py`, replace:

```python
    with pytest.raises(ValueError):
        pair_counts("both", 0, 0)
```

with:

```python
    with pytest.raises(ValueError):
        pair_counts("both", 0, 0)


def test_boxes_count_as_stacked_from_an_iou_of_0_9():
    near, apart = (0.5083, 0.5, 0.2, 0.2), (0.5162, 0.5, 0.2, 0.2)     # IoU 0.92 and 0.85 with A
    assert stack_counts([(0, A), (1, near)], *STACKED) == {0: 2, 1: 2}
    assert stack_counts([(0, A), (1, apart)], *STACKED) == {}
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_overlap.py tests/core/test_conditions.py`
Expected: `cannot import name 'STACKED'`.

- [ ] **Step 3: The overlap condition; the stack count at 0.9**

In `src/deeplabeling/core/queue.py`, replace:

```python
from .dataset import Dataset, ImageEntry
from .imagesize import ImageSizes, image_size
from .ranges import range_error
from .store import ImageLabels, LabelState, LabelStore
```

with:

```python
from .dataset import Dataset, ImageEntry
from .imagesize import ImageSizes, image_size
from .overlap import SCOPES, stack_counts
from .ranges import range_error
from .store import ImageLabels, LabelState, LabelStore
```

In `src/deeplabeling/core/queue.py`, replace:

```python


def condition_from_json(data) -> Condition:
    try:
```

with:

```python


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


def condition_from_json(data) -> Condition:
    try:
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        if kind == "name":
            return NameContains(str(data["text"]))
        if kind == "boxes":
            return Boxes(tuple(str(n) for n in data["names"]), tuple(data["w"]), tuple(data["h"]),
```

with:

```python
        if kind == "name":
            return NameContains(str(data["text"]))
        if kind == "overlap":
            return Overlap(str(data["scope"]), float(data["lo"]), float(data["hi"]))
        if kind == "boxes":
            return Boxes(tuple(str(n) for n in data["names"]), tuple(data["w"]), tuple(data["h"]),
```

In `src/deeplabeling/core/overlap.py`, replace:

```python
SCOPES = ("any", "same", "different")

#: What slice 1's canvas counts: exact duplicates, of any class.
DUPLICATES = ("any", 0.99, 1.0)


```

with:

```python
SCOPES = ("any", "same", "different")

#: What the canvas counts on every caption (`car ×2`): boxes drawn nearly on top of each
#: other, of any class (docs/design/2026-10-06-filters.md#stack-counts). Below 0.9 the
#: rectangles are visibly apart, and the count would mark ordinary occlusion.
STACKED = ("any", 0.9, 1.0)


```

In `src/deeplabeling/ui/boxes.py`, replace:

```python
from ..core.dataset import Dataset
from ..core.geometry import norm_to_px
from ..core.overlap import DUPLICATES, stack_counts
from ..core.store import ImageLabels
from .classes import UNKNOWN, class_color
```

with:

```python
from ..core.dataset import Dataset
from ..core.geometry import norm_to_px
from ..core.overlap import STACKED, stack_counts
from ..core.store import ImageLabels
from .classes import UNKNOWN, class_color
```

In `src/deeplabeling/ui/boxes.py`, replace:

```python
    w, h = size
    boxes = labels.boxes
    stack = stack_counts([(line.cls_id, line.bbox) for _, line in boxes], *DUPLICATES)
    views = []
    for pos, (index, line) in enumerate(boxes):
```

with:

```python
    w, h = size
    boxes = labels.boxes
    stack = stack_counts([(line.cls_id, line.bbox) for _, line in boxes], *STACKED)
    views = []
    for pos, (index, line) in enumerate(boxes):
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_overlap.py tests/core/test_conditions.py tests/ui/test_boxes.py`
Expected: 52 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 720 passed.

```bash
git add src/deeplabeling/core/overlap.py src/deeplabeling/core/queue.py src/deeplabeling/ui/boxes.py tests/core/test_overlap.py tests/core/test_conditions.py
git commit -m "core: an overlap condition sharing the canvas's predicate; boxes count as stacked from IoU 0.9" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Where the model and the labels disagree

**Files:**
- Create: `src/deeplabeling/core/disagree.py`, `tests/core/test_disagree.py`
- Modify: `src/deeplabeling/core/queue.py`

**Interfaces:**
- Consumes:
  - from plan 2a: `ClassMap.translate`, `Prediction`, `FLOOR`, `PredictionStore.get` and `image_stamp`;
  - slice 1's `geometry.iou`.
- Produces:
  - In `deeplabeling.core.disagree`:
    - `checkable(cmap, dataset)`;
    - `unseen_labels(labels, preds, cmap, dataset, match_iou, conf_lo)`, which returns line indices;
    - `unlabelled_predictions(labels, preds, cmap, dataset, match_iou, conf_lo, conf_hi)`, which returns indices into `preds`.
  - In `deeplabeling.core.queue`:
    - `ModelSnapshot(key, store, class_map)`;
    - `BuildContext.model` and `.predictions(entry) -> list | None`;
    - `Seen(predictions=None, class_map=None)`;
    - `Condition.needs_model` and `Condition.highlight_predictions(labels, dataset, seen)`;
    - `ModelDisagrees(direction="unseen" | "unlabelled" | "either", match_iou=0.5, conf=(0.25, 1.0))`, of kind `"model"`, with a cost of 3. Its JSON is `{"kind", "direction", "match_iou", "conf"}`.
    - `ImageFilter.highlight_predictions` and `ImageFilter.needs_model`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_disagree.py`:

```python
"""Where the model and the labels disagree: the Label/Prediction IoU condition
(docs/design/2026-10-06-filters.md#labelprediction-iou, docs/knowledge/matching.md#the-iou-filter)."""

import pytest

from deeplabeling.core.classmap import ClassMap
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import PredictionStore, image_stamp
from deeplabeling.core.queue import (
    BuildContext,
    ImageFilter,
    ModelDisagrees,
    ModelSnapshot,
    Seen,
    condition_from_json,
)
from deeplabeling.core.store import LabelStore

KEY = "fake:best.pt"
MODEL = ("car", "person", "truck")          # car -> car (1), person -> person (0), truck: unmapped


def P(cls, box, conf):
    return Prediction(cls, box, conf)


ROWS = {
    "camA/images/0001.jpg": [P(1, (0.5, 0.5, 0.2, 0.3), 0.9)],      # sees the person; the car is unseen
    "camA/images/0002.jpg": [P(0, (0.8, 0.8, 0.1, 0.1), 0.95)],     # a car on a negative: unlabelled
    "camA/images/0003.jpg": [P(2, (0.5, 0.5, 0.1, 0.1), 0.9)],      # an unmapped truck: never unlabelled
    "camA/images/0004.JPG": [P(0, (0.8, 0.8, 0.1, 0.1), 0.3)],      # a weak car on nothing
    "camA/images/sub/0005.jpg": [],                                  # bus_m: the model cannot see it
    "camB/images/0001.jpg": [],                                      # bus_m, inferred, nothing found
    "camB/images/twin.jpg": [P(1, (0.5, 0.5, 0.1, 0.1), 0.97)],     # sees its person, above 0.9
    "weird/images/имя пробел.jpg": [P(2, (0.5, 0.5, 0.1, 0.1), 0.8)],   # an unmapped truck sees the person
}


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


@pytest.fixture
def cmap(dataset):
    return ClassMap.seeded(MODEL, dataset.names)


@pytest.fixture
def ctx(dataset, cmap, tmp_path):
    store = PredictionStore(tmp_path / "predictions.sqlite")
    for rel, preds in ROWS.items():
        store.put(KEY, rel, image_stamp(dataset.root / rel), preds)
    yield BuildContext(dataset, LabelStore(dataset), frozenset(), model=ModelSnapshot(KEY, store, cmap))
    store.close()


def keys(condition, ctx):
    batches = []
    assert ImageFilter(conditions=(condition,)).build(ctx, batches.append)
    return [item.key for batch in batches for item in batch]


def test_a_label_no_prediction_overlaps_is_unseen(ctx):
    assert keys(ModelDisagrees("unseen"), ctx) == ["camA/images/0001.jpg"]


def test_an_upper_bound_never_removes_a_prediction_from_matching(ctx):
    # twin's person is seen at 0.97; an upper bound of 0.9 must not make it unseen.
    assert keys(ModelDisagrees("unseen", conf=(0.25, 0.9)), ctx) == ["camA/images/0001.jpg"]


def test_a_mapped_prediction_no_label_overlaps_was_labelled_by_nobody(ctx):
    assert keys(ModelDisagrees("unlabelled"), ctx) == ["camA/images/0002.jpg", "camA/images/0004.JPG"]
    assert keys(ModelDisagrees("unlabelled", conf=(0.5, 1.0)), ctx) == ["camA/images/0002.jpg"]


def test_either_direction(ctx):
    assert keys(ModelDisagrees("either"), ctx) == [
        "camA/images/0001.jpg", "camA/images/0002.jpg", "camA/images/0004.JPG"]


def test_images_never_inferred_are_counted_and_those_inferred_empty_are_evaluated(ctx):
    keys(ModelDisagrees("unseen"), ctx)
    assert ctx.unsettled == {"not inferred": 7}


def test_without_a_model_nothing_matches_and_it_is_said(dataset):
    ctx = BuildContext(dataset, LabelStore(dataset), frozenset())
    assert keys(ModelDisagrees("unseen"), ctx) == [] and ctx.unsettled == {"no model": 15}


def test_the_highlights_are_the_unseen_labels_and_the_unlabelled_predictions(ctx, dataset, cmap):
    for rel, condition, lines, preds in (
            ("camA/images/0001.jpg", ModelDisagrees("unseen"), {1}, set()),
            ("camA/images/0002.jpg", ModelDisagrees("unlabelled"), set(), {0}),
            ("camA/images/0001.jpg", ModelDisagrees("unlabelled"), set(), set())):
        labels = ctx.labels(dataset.entry(dataset.root / rel))
        seen = Seen(predictions=ROWS[rel], class_map=cmap)
        assert condition.highlight(labels, dataset, seen) == lines
        assert condition.highlight_predictions(labels, dataset, seen) == preds
        assert condition.highlight(labels, dataset) == frozenset()          # no predictions known
    assert ImageFilter(conditions=(ModelDisagrees("unlabelled"),)).highlight_predictions(
        ctx.labels(dataset.entry(dataset.root / "camA/images/0002.jpg")), dataset,
        Seen(predictions=ROWS["camA/images/0002.jpg"], class_map=cmap)) == {0}


@pytest.mark.parametrize("condition, text", [
    (ModelDisagrees("unseen"), "labels the model does not see (IoU 0.50, conf ≥ 0.25)"),
    (ModelDisagrees("unlabelled", 0.6, (0.5, 0.9)), "predictions nobody labelled (IoU 0.60, conf 0.50–0.90)"),
    (ModelDisagrees("either"), "labels and predictions that disagree (IoU 0.50, conf 0.25–1.00)"),
])
def test_a_model_condition_reads_as_words_and_survives_its_json(condition, text, dataset):
    assert condition.describe(dataset) == text
    assert condition_from_json(condition.to_json()) == condition
    assert ImageFilter(conditions=(condition,)).needs_model


@pytest.mark.parametrize("kw, why", [
    (dict(direction="sideways"), "unknown direction 'sideways'"),
    (dict(match_iou=0.0), "matching IoU: must be above 0 and at most 1"),
    (dict(conf=(0.05, 1.0)), "confidence: the lower end cannot be below 0.1"),
    (dict(conf=(0.9, 0.5)), "confidence: 0.9 is above 0.5: put the lower end first"),
])
def test_an_unusable_model_condition_is_refused(kw, why):
    with pytest.raises(ValueError, match=why):
        ModelDisagrees(**kw)
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_disagree.py`
Expected: `cannot import name 'ModelDisagrees'`.

- [ ] **Step 3: The rules, and the condition that reads the model's rows**

In `src/deeplabeling/core/queue.py`, replace:

```python
from typing import ClassVar

from .dataset import Dataset, ImageEntry
from .imagesize import ImageSizes, image_size
from .overlap import SCOPES, stack_counts
from .ranges import range_error
from .store import ImageLabels, LabelState, LabelStore
```

with:

```python
from typing import ClassVar

from .classmap import ClassMap
from .dataset import Dataset, ImageEntry
from .disagree import unlabelled_predictions, unseen_labels
from .imagesize import ImageSizes, image_size
from .inference import FLOOR, Prediction
from .overlap import SCOPES, stack_counts
from .predstore import PredictionStore, image_stamp
from .ranges import range_error
from .store import ImageLabels, LabelState, LabelStore
```

In `src/deeplabeling/core/queue.py`, replace:

```python

@dataclass(frozen=True)
class BuildContext:
    dataset: Dataset
```

with:

```python

@dataclass(frozen=True)
class ModelSnapshot:
    """The loaded model, as a build reads it: its rows in the store and its class map."""

    key: str
    store: PredictionStore
    class_map: ClassMap


@dataclass(frozen=True)
class BuildContext:
    dataset: Dataset
```

In `src/deeplabeling/core/queue.py`, replace:

```python
    reviewed: frozenset[str]        #: review-mark keys, snapshotted before the build
    sizes: ImageSizes | None = None     #: the open dataset's size cache, when there is one
    #: Images a condition could not settle ("could not be sized", "not inferred"), counted
    #: for the queue chip. One build or recheck owns it; it is never shared across threads.
```

with:

```python
    reviewed: frozenset[str]        #: review-mark keys, snapshotted before the build
    sizes: ImageSizes | None = None     #: the open dataset's size cache, when there is one
    model: ModelSnapshot | None = None  #: the loaded model, when a condition asks for it
    #: Images a condition could not settle ("could not be sized", "not inferred"), counted
    #: for the queue chip. One build or recheck owns it; it is never shared across threads.
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        return self.sizes.get(entry.path) if self.sizes is not None else image_size(entry.path)

    def count(self, what: str) -> None:
        self.unsettled[what] += 1
```

with:

```python
        return self.sizes.get(entry.path) if self.sizes is not None else image_size(entry.path)

    def predictions(self, entry: ImageEntry) -> list[Prediction] | None:
        """The model's predictions for the image at the floor; None when it never looked,
        or the image has changed since (the store's stamp)."""
        try:
            stamp = image_stamp(entry.path)
        except OSError:
            return None
        return self.model.store.get(self.model.key, entry.rel, stamp)

    def count(self, what: str) -> None:
        self.unsettled[what] += 1
```

In `src/deeplabeling/core/queue.py`, replace:

```python

    size: tuple[int, int] | None = None     #: as shown: what a size in px is scaled by


```

with:

```python

    size: tuple[int, int] | None = None     #: as shown: what a size in px is scaled by
    predictions: list[Prediction] | None = None     #: the model's, at the floor, untranslated
    class_map: ClassMap | None = None


```

In `src/deeplabeling/core/queue.py`, replace:

```python
    kind: ClassVar[str]
    needs_labels: ClassVar[bool] = True

    @property
```

with:

```python
    kind: ClassVar[str]
    needs_labels: ClassVar[bool] = True
    needs_model: ClassVar[bool] = False

    @property
```

In `src/deeplabeling/core/queue.py`, replace:

```python
    def highlight(self, labels: ImageLabels, dataset: Dataset, seen: Seen = NOTHING_SEEN) -> frozenset[int]:
        """Line indices of the boxes that made the condition hold."""
        return frozenset()

```

with:

```python
    def highlight(self, labels: ImageLabels, dataset: Dataset, seen: Seen = NOTHING_SEEN) -> frozenset[int]:
        """Line indices of the boxes that made the condition hold."""
        return frozenset()

    def highlight_predictions(self, labels: ImageLabels, dataset: Dataset,
                              seen: Seen = NOTHING_SEEN) -> frozenset[int]:
        """Indices into `seen.predictions` of the predictions that made it hold."""
        return frozenset()

```

In `src/deeplabeling/core/queue.py`, replace:

```python


def condition_from_json(data) -> Condition:
    try:
```

with:

```python


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
            ctx.count("no model")
            return False
        preds = ctx.predictions(entry)
        if preds is None:
            ctx.count("not inferred")
            return False
        labels, cmap = ctx.labels(entry), ctx.model.class_map
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
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        if kind == "name":
            return NameContains(str(data["text"]))
        if kind == "overlap":
            return Overlap(str(data["scope"]), float(data["lo"]), float(data["hi"]))
```

with:

```python
        if kind == "name":
            return NameContains(str(data["text"]))
        if kind == "model":
            return ModelDisagrees(str(data["direction"]), float(data["match_iou"]),
                                  tuple(float(c) for c in data["conf"]))
        if kind == "overlap":
            return Overlap(str(data["scope"]), float(data["lo"]), float(data["hi"]))
```

In `src/deeplabeling/core/queue.py`, replace:

```python
            found |= condition.highlight(labels, dataset, seen)
        return found

    def build(self, ctx: BuildContext, emit: Callable[[list[QueueItem]], None],
```

with:

```python
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
```

Create `src/deeplabeling/core/disagree.py`:

```python
"""Where the model and the labels disagree, for the Label/Prediction IoU condition
(docs/knowledge/matching.md#the-iou-filter).

"The model does not see this label" is geometry against every prediction at or above the
lower confidence bound, mapped or not; "nobody labelled this" counts only predictions of a
class the dataset has, inside the confidence range. The upper bound never removes a
prediction from matching (docs/knowledge/matching.md#one-floor-and-per-kind-ceilings).
"""

from __future__ import annotations

from collections.abc import Sequence

from .classmap import ClassMap
from .dataset import Dataset
from .geometry import iou
from .inference import Prediction
from .store import ImageLabels


def checkable(cmap: ClassMap, dataset: Dataset) -> frozenset[int]:
    """The dataset classes some model class maps to: only their labels can be unseen
    (docs/knowledge/matching.md#the-checkable-class-guard)."""
    return frozenset(c for c in (cmap.translate(m, dataset) for m in range(len(cmap.model_names)))
                     if c is not None)


def unseen_labels(labels: ImageLabels, preds: Sequence[Prediction], cmap: ClassMap, dataset: Dataset,
                  match_iou: float, conf_lo: float) -> frozenset[int]:
    """Line indices of the labels no prediction at or above `conf_lo` overlaps at IoU >=
    `match_iou`, of any class, mapped or not."""
    seen_by = [p.box for p in preds if p.conf >= conf_lo]
    can_see = checkable(cmap, dataset)
    return frozenset(i for i, line in labels.boxes
                     if line.cls_id in can_see and not any(iou(line.bbox, b) >= match_iou for b in seen_by))


def unlabelled_predictions(labels: ImageLabels, preds: Sequence[Prediction], cmap: ClassMap,
                           dataset: Dataset, match_iou: float, conf_lo: float,
                           conf_hi: float) -> frozenset[int]:
    """Indices of the mapped predictions inside [conf_lo, conf_hi] that overlap no label
    at IoU >= `match_iou`."""
    boxes = [line.bbox for _, line in labels.boxes]
    return frozenset(k for k, p in enumerate(preds)
                     if conf_lo <= p.conf <= conf_hi and cmap.translate(p.cls, dataset) is not None
                     and not any(iou(p.box, b) >= match_iou for b in boxes))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_disagree.py tests/core/test_conditions.py tests/core/test_queue.py tests/core/test_inference.py tests/core/test_core_imports_no_qt.py`
Expected: 86 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 734 passed.

```bash
git add src/deeplabeling/core/disagree.py src/deeplabeling/core/queue.py tests/core/test_disagree.py
git commit -m "core: labels the model does not see, and predictions nobody labelled, as a queue condition" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The measurement, and the docs

**Files:**
- Create: `tools/measure_filters.py`
- Modify:
  - `docs/design/2026-10-06-filters.md` (the status, the chip's example, the measured core);
  - `docs/knowledge/caches.md` (where the one size function lives);
  - `CLAUDE.md` (the status).

**Interfaces:**
- Consumes: everything above.
- Produces: `tools/measure_filters.py DATA.yaml`. It prints the first-items and complete times of six builds, read-only.

- [ ] **Step 1: Write the script**

Create `tools/measure_filters.py`:

```python
#!/usr/bin/env python3
"""Measure slice 3's size and overlap conditions on a real dataset, read-only
(docs/design/2026-10-06-filters.md#performance-targets).

It opens the dataset and its label files directly: no app state, no lock, no write.
The model condition is measured with the window, where the model's rows are.

  /home/sonnn/miniconda3/bin/python3 tools/measure_filters.py DATA.yaml
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT / "src"))

    from deeplabeling.core.dataset import Dataset
    from deeplabeling.core.imagesize import ImageSizes
    from deeplabeling.core.queue import Boxes, BuildContext, ImageFilter, Overlap
    from deeplabeling.core.store import LabelStore

    dataset = Dataset.open(args.yaml)
    store, sizes = LabelStore(dataset), ImageSizes()
    print(f"{len(dataset.images):,} images")

    def build(condition):
        ctx = BuildContext(dataset, store, frozenset(), sizes=sizes)
        found, first, start = [], None, time.perf_counter()

        def emit(items):
            nonlocal first
            if first is None:
                first = time.perf_counter() - start
            found.extend(items)

        ImageFilter(conditions=(condition,)).build(ctx, emit)
        return first, time.perf_counter() - start, len(found), dict(ctx.unsettled)

    runs = [("a size in px, cold (headers and label files read)", Boxes((), w=(None, 10), unit="px")),
            ("the same, warm", Boxes((), w=(None, 10), unit="px")),
            ("a size in %", Boxes((), w=(None, 1), unit="%")),
            ("overlap, same class, IoU 0.9-1.0", Overlap("same", 0.9, 1.0)),
            ("overlap, different classes, IoU 0.5-1.0", Overlap("different", 0.5, 1.0)),
            ("overlap, any class, IoU 0.5-1.0", Overlap("any", 0.5, 1.0))]
    for name, condition in runs:
        first, total, n, unsettled = build(condition)
        first_text = "—" if first is None else f"{first * 1000:.0f} ms"
        print(f"{name:45s} first {first_text:>8s}   complete {total:6.2f} s   "
              f"{n:6,} images{'   ' + str(unsettled) if unsettled else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it once, read-only**

Run: `/home/sonnn/miniconda3/bin/python3 tools/measure_filters.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml`
Expected:
- `45,252 images`;
- six lines, each with a first-items time ≤ 1 s and a complete time within the targets (2026-10-06: a size in px 9.96 s cold and 0.94 s warm, in % 0.62 s, overlap 1.84–3.45 s);
- `git status` shows nothing new in the dataset.

A missed target is a finding: run it twice more, then record what was measured.

- [ ] **Step 3: Record the measurements, and update the status**

The table below holds the 2026-10-06 figures. Where your run's figures differ, write yours, with your date.

In `CLAUDE.md`, replace:

````markdown
**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. The design and the plans are in [docs/design/](docs/design/).

```sh
````

with:

````markdown
**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. Slice 3 (filters) has its core built; its UI (plan 3b) is next. The
design and the plans are in [docs/design/](docs/design/).

```sh
````

In `docs/design/2026-10-06-filters.md`, replace:

```markdown
# DeepLabeling — slice 3: filters

**Status:** approved 2026-10-06 · plans 3a (the core) and 3b (the UI) next
**Scope:** slice 3 of [the app foundation](2026-10-04-app-foundation.md#slices): box size,
overlap between labels and Label/Prediction IoU become conditions of the one queue source,
```

with:

```markdown
# DeepLabeling — slice 3: filters

**Status:** approved 2026-10-06 · plan 3a (the core) implemented; 3b (the UI) next
**Scope:** slice 3 of [the app foundation](2026-10-04-app-foundation.md#slices): box size,
overlap between labels and Label/Prediction IoU become conditions of the one queue source,
```

In `docs/design/2026-10-06-filters.md`, replace:

```markdown
It describes every condition in words, then what the build could not settle:
`has car 10–30 px wide · labels overlapping, same class, IoU 0.99–1.00`,
`labels the model does not see (IoU 0.5, conf ≥ 0.25) · 1,204 not inferred`,
`· waiting for the model`, `· 3 images could not be sized`.

```

with:

```markdown
It describes every condition in words, then what the build could not settle:
`has car 10–30 px wide · labels overlapping, same class, IoU 0.99–1.00`,
`labels the model does not see (IoU 0.50, conf ≥ 0.25) · 1,204 not inferred`,
`· waiting for the model`, `· 3 images could not be sized`.

```

In `docs/design/2026-10-06-filters.md`, replace:

```markdown
measured value, not quietly dropped.

| Action | Target |
|---|---|
| a size, overlap or model condition over 45k images: first items | ≤ 1 s |
| the same, complete: cold / warm caches | ≤ 30 s / ≤ 5 s, streaming |
| the image on screen while such a queue builds | as without one: [slice 1's targets](2026-10-04-app-foundation.md#performance-targets) |

## Testing
```

with:

````markdown
measured value, not quietly dropped.

| Action | Target | Measured 2026-10-06, the core alone (plan 3a) |
|---|---|---|
| a size, overlap or model condition over 45k images: first items | ≤ 1 s | 69–762 ms |
| the same, complete: cold / warm caches | ≤ 30 s / ≤ 5 s, streaming | a size in px: 9.96 s / 0.94 s; in %: 0.62 s; overlap: 1.84–3.45 s |
| the image on screen while such a queue builds | as without one: [slice 1's targets](2026-10-04-app-foundation.md#performance-targets) | plan 3b |

- "Cold" is the first build after opening, reading every image header and label file; the
  OS page cache was warm. The model condition is measured in plan 3b, with the model's rows.
- Reproduce the core's figures, read-only (no app state is written):

```sh
/home/sonnn/miniconda3/bin/python3 tools/measure_filters.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml
```

## Testing
````

In `docs/knowledge/caches.md`, replace:

```markdown
  indistinguishable from re-running the model.

**Rule:** never decode an image to learn its size; one size function, header-only and
EXIF-aware, for every caller.
```

with:

```markdown
  indistinguishable from re-running the model.

- DeepLabeling's one size function is `src/deeplabeling/core/imagesize.py::image_size`;
  `src/deeplabeling/core/imagesize.py::ImageSizes` caches it for the open dataset, stamped
  like the label cache.

**Rule:** never decode an image to learn its size; one size function, header-only and
EXIF-aware, for every caller.
```

- [ ] **Step 4: Check the docs, and run the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 734 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/measure_filters.py docs/design/2026-10-06-filters.md docs/knowledge/caches.md CLAUDE.md
git commit -m "docs: slice 3's core is built; its builds measured on pvn-vehicle" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
