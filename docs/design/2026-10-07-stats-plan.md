# Slice 5b: statistics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The statistics of the queue's images:
- computed on a worker;
- shown as four tables that copy as TSV, and four matplotlib charts;
- reached from the queue chip;
- with slice 5's targets measured.

**Architecture:**
- `core/stats.py` counts one image at a time into a `Stats` of `Counter`s, Qt-free:
  - per split and class;
  - the label files' states;
  - box sizes in pixels, from the header-only, EXIF-aware sizes;
  - boxes per image, and box centres on a 20 × 20 grid.

  A warm run is all Python, so it pauses briefly every 256 images to let the GUI thread have the GIL.
- `ui/statsview.py` turns a `Stats` into tables (a header and rows) and TSV, Qt-free.
- `ui/stats_dialog.py`:
  - runs the computation on `Session.io` and fills the tables;
  - draws the charts with matplotlib only when their tab shows, so drawing never holds up a recompute.
- The queue chip's menu gains *Statistics of this queue…*. `tools/measure_bulk_stats.py` measures statistics and reassign.

**Tech Stack:** Python 3.10 (conda base), PySide6, matplotlib 3.9 (already installed), pytest-qt; plan 5a.

**Spec:** [2026-10-07-bulk-and-stats.md](2026-10-07-bulk-and-stats.md). This plan implements:
- *Statistics*;
- the queue chip's Statistics entry;
- the *Performance targets*.

With it, slice 5 is built.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)).
- **`src/deeplabeling/core/` imports no Qt** (`tests/core/test_core_imports_no_qt.py`). matplotlib and numpy are imported in `stats_dialog.py` only when its charts are drawn.
- **The GUI thread never waits on the computation** ([landmine 3](../../CLAUDE.md#landmines)). It runs on `Session.io`, so closing the dataset cancels it.
- **One size function** ([caches.md](../knowledge/caches.md#image-sizes)). Pixel sizes come from `Workspace.sizes`. An image whose header cannot be read is counted, and its boxes are left out of the pixel figures.
- **A UI change is verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines)):
  - tables read back from their cells;
  - charts read back from their pixels;
  - geometry asserted, and a screenshot looked at.
- **The measurement is read-only on the real dataset** ([landmines 9 and 10](../../CLAUDE.md#landmines)):
  - app state goes to a temporary folder;
  - reassign is answered No;
  - its write is timed on a generated dataset in a temporary folder.
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice5-stats` from `main`. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone reading the statistics. Each has a named test:

1. **The edge-case dataset**: polygons, ids the yaml does not name, shared, negative, missing and unparsable files, an undecodable image. Every count is checked against counts made by hand. *(Task 1 `test_boxes_and_images_per_class_and_split`, `test_label_files_per_split`, `test_box_sizes_in_pixels_leave_out_only_the_image_whose_header_cannot_be_read`.)*
2. **A box centred outside the frame** (cx 1.4). It is counted in the edge column, not dropped. *(Task 1 `test_box_centres_on_a_grid_kept_inside_it`.)*
3. **Closing the dialog while it computes.** The computation is cancelled, and nothing is filled afterwards. *(Task 2 `test_while_it_reads_it_says_how_far_and_closing_cancels`.)*
4. **A recompute while the Charts tab shows.** The charts are redrawn for the new numbers, and only then. *(Task 2 `test_the_charts_are_drawn_when_their_tab_is_shown_not_when_the_numbers_come`.)*
5. **A queue whose build failed.** No statistics are offered for part of a queue. *(Task 3 `test_statistics_are_not_offered_on_a_queue_whose_build_failed`.)*

## Found while building this plan

The plan's code was built in a scratch copy first, and its suite ran green there (1017 passed).

- **A warm computation stalled the window for 177–223 ms.** It is pure Python on a worker (the caches hit), and it held the GIL. A probe placed the stalls mid-run, not in the GUI's own callbacks: `recompute()` took 7 ms and filling the tables 1–4 ms. A pause of 0.5 ms every 256 images brought the longest wait to 11–27 ms, for about 0.15 s more per run.
- **Drawing the charts as the numbers came took about 240 ms in one event-loop turn.** Charts now draw when their tab shows, or when they show and their numbers change.
- **√(w·h) does not change when a frame is turned:** w·h·W·H is symmetric. The EXIF-rotated frame therefore only checks that it is sized.
- **On a log axis, a bucket of a few boxes all but vanished** when matplotlib started the axis at the smallest count. The axis starts at 0.5.
- **The store counts a blank line as unparsable** (`ImageLabels.unparsed`), as the inspector shows it. The Label files table uses the same count.

## Decisions this plan makes

- **Statistics run on `Session.io`**, beside queue builds, so closing the dataset cancels them. The window is a child of the main window and closes with the dataset. A new one replaces the old one, which is deleted.
- **Pixel sizes are read only for images with boxes:** a negative or missing image needs no header.
- **Table numbers are plain integers**, so the TSV pastes into a spreadsheet in any locale.
- **The class selector applies to the size and centre charts.** The balance and per-image charts are always for all classes.
- **Save charts… draws them first if they are not drawn,** then writes the figure as one PNG at 100 dpi.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/stats.py` | `Stats`, `stats_of`, `size_bucket`, the buckets and grid | 1 |
| `src/deeplabeling/ui/statsview.py` | the four tables, and TSV | 2 |
| `src/deeplabeling/ui/stats_dialog.py`, `prompter.py` | the dialog; `choose_save_path` | 2 |
| `src/deeplabeling/ui/main_window.py` | *Statistics of this queue…* | 3 |
| `tools/measure_bulk_stats.py`, the spec, `CLAUDE.md` | the measurements; the status | 4 |

---

### Task 1: Counting a queue's images

**Files:**
- Create: `src/deeplabeling/core/stats.py`, `tests/core/test_stats.py`

**Interfaces:**
- Consumes: `ImageEntry.split`, `ImageLabels.state`/`.boxes`/`.negative`/`.unparsed`, `LabelLine.bbox`/`.is_polygon`, and `ImageSizes.get` (used by the tests).
- Produces, in `deeplabeling.core.stats`:
  - the constants `SIZE_EDGES`, `SIZE_LABELS`, `PER_IMAGE_MAX = 20`, `GRID = 20`, `FILE_STATES`, `BREATHE` and `BREATHE_S`;
  - `size_bucket(px)`;
  - `Stats`, with `.splits`, `.files`, `.boxes`, `.images_with`, `.polygons`, `.sizes`, `.unsized`, `.per_image`, `.centres`, `.classes()` and `.add(entry, labels, size_of)`;
  - `stats_of(entries, labels_of, size_of, cancelled, *, progress, interval) -> Stats | None`.

- [ ] **Step 1: Commit this plan, on a new branch**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout -b slice5-stats main
git add docs/design/2026-10-07-stats-plan.md
git commit -m "docs: the slice 5b plan, statistics" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/core/test_stats.py`:

```python
"""The statistics of a queue's images (docs/design/2026-10-07-bulk-and-stats.md#statistics),
checked against the edge-case dataset counted by hand."""

import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.imagesize import ImageSizes
from deeplabeling.core.stats import GRID, SIZE_LABELS, size_bucket, stats_of
from deeplabeling.core.store import LabelStore

PERSON, CAR, BUS_M, BUS_L = 0, 1, 2, 3


@pytest.fixture
def stats(ds):
    dataset = Dataset.open(ds.yaml)
    return stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)


def test_boxes_and_images_per_class_and_split(stats):
    assert stats.splits == ("train", "val")
    assert {k: v for k, v in stats.boxes.items() if v} == {
        ("train", PERSON): 4, ("train", CAR): 1, ("train", BUS_M): 3,
        ("val", PERSON): 8, ("val", CAR): 5, ("val", 99): 1, ("val", -1): 1}
    assert stats.images_with[("train", PERSON)] == 4 and stats.images_with[("val", PERSON)] == 5
    assert stats.images_with[("val", CAR)] == 5 and stats.images_with[("train", BUS_L)] == 0
    assert {k: v for k, v in stats.polygons.items() if v} == {("val", PERSON): 1, ("val", CAR): 2}
    assert stats.classes() == (-1, PERSON, CAR, BUS_M, 99)


def test_label_files_per_split(stats):
    assert {k: v for k, v in stats.files.items() if v} == {
        ("train", "images"): 10, ("train", "with boxes"): 7, ("train", "negative"): 1,
        ("train", "missing"): 2, ("train", "shared"): 2,
        ("val", "images"): 5, ("val", "with boxes"): 5, ("val", "unparsable lines"): 4}


def test_an_unreadable_label_file_is_counted(ds):
    dataset = Dataset.open(ds.yaml)
    ds.lbl("camA/0001").chmod(0o000)
    try:
        stats = stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)
    finally:
        ds.lbl("camA/0001").chmod(0o644)
    assert stats.files[("train", "unreadable")] == 1 and stats.boxes[("train", CAR)] == 0


def test_box_sizes_in_pixels_leave_out_only_the_image_whose_header_cannot_be_read(stats):
    small, medium = SIZE_LABELS.index("< 8"), SIZE_LABELS.index("8–16")
    assert {k: v for k, v in stats.sizes.items() if v} == {
        (PERSON, small): 4, (PERSON, medium): 7,            # bad/corrupt's person and car: unsized
        (CAR, small): 3, (CAR, medium): 2,
        (BUS_M, medium): 3,                                 # one of them on the EXIF-turned camB/rot
        (99, small): 1, (-1, small): 1}
    assert stats.unsized == 1


def test_the_size_buckets_take_their_lower_end(stats):
    assert [SIZE_LABELS[size_bucket(px)] for px in (0, 7.99, 8, 15.9, 16, 255.9, 256, 4000)] == [
        "< 8", "< 8", "8–16", "8–16", "16–32", "128–256", "≥ 256", "≥ 256"]


def test_boxes_per_image_with_twenty_or_more_together(stats):
    assert {k: v for k, v in stats.per_image.items() if v} == {0: 3, 1: 6, 2: 5, 7: 1}
    from deeplabeling.core.stats import PER_IMAGE_MAX
    assert PER_IMAGE_MAX == 20


def test_box_centres_on_a_grid_kept_inside_it(stats):
    assert GRID == 20
    person = {(x, y): n for (cls, x, y), n in stats.centres.items() if cls == PERSON and n}
    assert person == {(10, 10): 9, (8, 8): 1, (19, 10): 1, (3, 3): 1}     # cx 1.4 stays in the last column


def test_a_cancelled_computation_gives_nothing_and_progress_is_told(ds):
    dataset = Dataset.open(ds.yaml)
    told = []
    stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get, progress=lambda d, t: told.append((d, t)))
    assert told[-1] == (15, 15)
    assert stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get, cancelled=lambda: True) is None


def test_no_images_is_empty_stats(ds):
    stats = stats_of([], None, None)
    assert stats.splits == () and not stats.boxes and stats.classes() == ()


def test_a_long_computation_pauses_so_the_window_gets_the_gil(ds, monkeypatch):
    import deeplabeling.core.stats as stats_module

    dataset = Dataset.open(ds.yaml)
    pauses = []
    monkeypatch.setattr(stats_module, "BREATHE", 4)
    monkeypatch.setattr(stats_module.time, "sleep", lambda s: pauses.append(s))
    stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)
    assert len(pauses) == len(dataset.images) // 4 and all(0 < s <= 0.001 for s in pauses)
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_stats.py`
Expected: `No module named 'deeplabeling.core.stats'`.

- [ ] **Step 4: Count**

Create `src/deeplabeling/core/stats.py`:

```python
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
            self.centres[(cls, _cell(cx), _cell(cy))] += 1
            if size is not None:
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
```

- [ ] **Step 5: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_stats.py tests/core/test_core_imports_no_qt.py`
Expected: 11 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 998 passed.

```bash
git add src/deeplabeling/core/stats.py tests/core/test_stats.py
git commit -m "core: the statistics of some images, per split and class, sizes in pixels, centres and boxes per image" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The Statistics dialog

**Files:**
- Create: `src/deeplabeling/ui/statsview.py`, `src/deeplabeling/ui/stats_dialog.py`, `tests/ui/test_statsview.py`, `tests/ui/test_stats_dialog.py`
- Modify: `src/deeplabeling/ui/prompter.py`, `tests/fixtures.py`

**Interfaces:**
- Consumes:
  - from Task 1: `stats_of`, `Stats`, the constants;
  - from plan 5a: `Session.queue_images()`, `class_label`;
  - `Session.io`, `Workspace.store`, `Workspace.sizes`, `Session.closed`.
- Produces:
  - in `statsview`: `class_table(stats, names)`, `files_table(stats)`, `sizes_table(stats, names)`, `per_image_table(stats)`, each returning `(header, rows)`; `table_classes`; `tsv(header, rows)`;
  - `StatsDialog(session, prompter)`, with:
    - `.stats`, `.status`, `.tabs`, `.tables[name]`, `.charts`, `.canvas`, `.chart_class`, `.drawn_class`, `.drawn_for`;
    - `.copy()`, `.recompute()`, `.save_charts()`;
    - `.copy_button`, `.recompute_button`, `.save_button`;
  - `QtPrompter.choose_save_path(title, filter)`, and `FakePrompter(save_path=…)`.

- [ ] **Step 1: Write the failing tests**

In `tests/fixtures.py`, replace:

```python
    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None, cancel_at=None, accept_queue=True,
                 reassign=None, accept_reassign=True):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
```

with:

```python
    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None, cancel_at=None, accept_queue=True,
                 reassign=None, accept_reassign=True, save_path=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
```

In `tests/fixtures.py`, replace:

```python
        self.reassign = reassign            #: (from, to) the reassign dialog answers, or None
        self.accept_reassign = accept_reassign
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

with:

```python
        self.reassign = reassign            #: (from, to) the reassign dialog answers, or None
        self.accept_reassign = accept_reassign
        self.save_path = save_path          #: where a save dialog answers to save, or None
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

In `tests/fixtures.py`, replace:

```python
        self.asked.append(("reassign", tuple(names), tuple(unnamed_ids)))
        return self.reassign

    def confirm_reassign(self, text):
```

with:

```python
        self.asked.append(("reassign", tuple(names), tuple(unnamed_ids)))
        return self.reassign

    def choose_save_path(self, title, filter):
        self.asked.append(("save", title))
        return None if self.save_path is None else str(self.save_path)

    def confirm_reassign(self, text):
```

Create `tests/ui/test_statsview.py`:

```python
"""The statistics as tables, and as TSV (docs/design/2026-10-07-bulk-and-stats.md#the-dialog)."""

import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.imagesize import ImageSizes
from deeplabeling.core.stats import stats_of
from deeplabeling.core.store import LabelStore
from deeplabeling.ui.statsview import class_table, files_table, per_image_table, sizes_table, tsv

NAMES = ("person", "car", "bus_m", "bus_l")


@pytest.fixture
def stats(ds):
    dataset = Dataset.open(ds.yaml)
    return stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)


def test_the_classes_table_has_a_row_per_class_then_per_unnamed_id(stats):
    header, rows = class_table(stats, NAMES)
    assert header == ["class", "train boxes", "train images", "train polygons",
                      "val boxes", "val images", "val polygons"]
    assert rows == [["person", "4", "4", "0", "8", "5", "1"], ["car", "1", "1", "0", "5", "5", "2"],
                    ["bus_m", "3", "3", "0", "0", "0", "0"], ["bus_l", "0", "0", "0", "0", "0", "0"],
                    ["#-1?", "0", "0", "0", "1", "1", "0"], ["#99?", "0", "0", "0", "1", "1", "0"]]


def test_the_label_files_table_has_a_row_per_split(stats):
    header, rows = files_table(stats)
    assert header == ["split", "images", "with boxes", "negative", "missing", "unreadable", "shared",
                      "unparsable lines"]
    assert rows == [["train", "10", "7", "1", "2", "0", "2", "0"], ["val", "5", "5", "0", "0", "0", "0", "4"]]


def test_the_box_sizes_table_ends_with_the_images_it_could_not_size(stats):
    header, rows = sizes_table(stats, NAMES)
    assert header == ["class", "< 8", "8–16", "16–32", "32–64", "64–128", "128–256", "≥ 256"]
    assert rows[:3] == [["person", "4", "7", "0", "0", "0", "0", "0"], ["car", "3", "2", "0", "0", "0", "0", "0"],
                        ["bus_m", "0", "3", "0", "0", "0", "0", "0"]]
    assert rows[-1] == ["images whose header cannot be read: 1"]


def test_the_boxes_per_image_table_runs_to_twenty_or_more(stats):
    header, rows = per_image_table(stats)
    assert header == ["boxes", "images"] and len(rows) == 21
    assert rows[:3] == [["0", "3"], ["1", "6"], ["2", "5"]] and rows[7] == ["7", "1"] and rows[-1] == ["20+", "0"]


def test_a_table_copies_as_tab_separated_lines():
    assert tsv(["a", "b"], [["1", "2"], ["3"]]) == "a\tb\n1\t2\n3\n"
```

Create `tests/ui/test_stats_dialog.py`:

```python
"""The Statistics dialog: computed on a worker, shown as tables and charts
(docs/design/2026-10-07-bulk-and-stats.md#the-dialog)."""

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from deeplabeling.core.queue import ImageFilter, NameContains
from deeplabeling.ui.stats_dialog import StatsDialog
from fixtures import FakePrompter, open_session


@pytest.fixture
def prompter(tmp_path):
    return FakePrompter(save_path=tmp_path / "charts.png")


@pytest.fixture
def session(qtbot, ds, prompter):
    s = open_session(qtbot, ds.yaml, prompter)
    yield s
    s.close()


@pytest.fixture
def dialog(qtbot, session, prompter):
    d = StatsDialog(session, prompter)
    qtbot.addWidget(d)
    d.resize(900, 700)
    d.show()
    qtbot.waitUntil(lambda: d.stats is not None, timeout=10000)
    return d


def cells(table):
    return [[table.item(r, c).text() if table.item(r, c) else "" for c in range(table.columnCount())]
            for r in range(table.rowCount())]


def colours(widget):
    image = widget.grab().toImage()
    return {QColor(image.pixel(x, y)).name() for x in range(0, image.width(), 3) for y in range(0, image.height(), 3)}


def near(found, wanted, tol=24):
    w = QColor(wanted)
    return any(abs(c.red() - w.red()) + abs(c.green() - w.green()) + abs(c.blue() - w.blue()) < tol
               for c in map(QColor, found))


def test_it_names_the_queue_and_fills_its_tables(qtbot, dialog):
    assert dialog.windowTitle() == "Statistics — all images"
    assert dialog.status.text().startswith("15 images · computed ")
    assert cells(dialog.tables["Classes"])[0] == ["person", "4", "4", "0", "8", "5", "1"]
    assert cells(dialog.tables["Label files"])[1] == ["val", "5", "5", "0", "0", "0", "0", "4"]


def test_copy_puts_the_shown_table_on_the_clipboard_as_tsv(qtbot, dialog):
    dialog.tabs.setCurrentIndex(dialog.tabs.indexOf(dialog.tables["Boxes per image"]))
    dialog.copy()
    assert QApplication.clipboard().text().startswith("boxes\timages\n0\t3\n1\t6\n")


def test_the_charts_are_drawn(qtbot, dialog):
    dialog.tabs.setCurrentWidget(dialog.charts)
    qtbot.wait(50)
    found = colours(dialog.canvas)
    assert near(found, "#1f77b4") and near(found, "#ff7f0e")      # train and val bars
    assert near(found, "#440154")                                   # the heatmap's empty cells (viridis)


def test_one_class_narrows_the_sizes_and_the_centres(qtbot, dialog):
    dialog.tabs.setCurrentWidget(dialog.charts)
    dialog.chart_class.setCurrentText("bus_m")
    assert dialog.drawn_class == 2


def test_save_charts_writes_a_png(qtbot, dialog, prompter):
    dialog.save_charts()
    assert prompter.save_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_while_it_reads_it_says_how_far_and_closing_cancels(qtbot, session, prompter, monkeypatch):
    import deeplabeling.ui.stats_dialog as module

    gate = __import__("threading").Event()
    real = module.stats_of

    def slow(entries, labels_of, size_of, cancelled, *, progress):
        progress(3, 15)
        gate.wait(5)
        return real(entries, labels_of, size_of, cancelled, progress=progress)

    monkeypatch.setattr(module, "stats_of", slow)
    d = StatsDialog(session, prompter)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(lambda: d.status.text() == "reading 3 / 15", timeout=5000)
    d.close()
    gate.set()
    qtbot.waitUntil(lambda: d._job is None, timeout=5000)
    assert d.stats is None


def test_an_empty_queue_says_no_images_and_draws_no_charts(qtbot, session, prompter):
    session.set_queue(ImageFilter(conditions=(NameContains("nothing like this"),)))
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    d = StatsDialog(session, prompter)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(lambda: d.stats is not None, timeout=5000)
    assert d.status.text() == "no images" and d.canvas is None


def test_recompute_reads_again(qtbot, dialog, ds):
    ds.lbl("camA/0002").write_text("1 0.5 0.5 0.1 0.1\n")              # the negative gains a car
    first = dialog.stats
    dialog.recompute()
    qtbot.waitUntil(lambda: dialog.stats is not None and dialog.stats is not first, timeout=10000)
    assert cells(dialog.tables["Classes"])[1][1] == "2"


def test_its_parts_are_visible_inside_it(qtbot, dialog):
    rects = []
    for w in (dialog.status, dialog.tabs, dialog.copy_button, dialog.recompute_button, dialog.save_button):
        rect = QRect(w.mapTo(dialog, QPoint(0, 0)), w.size())
        assert w.isVisible() and dialog.rect().contains(rect) and w.width() > 0
        assert not any(rect.intersects(r) for r in rects)
        rects.append(rect)


def test_the_size_axis_starts_below_one_box_so_every_bar_shows(qtbot, dialog):
    dialog.tabs.setCurrentWidget(dialog.charts)
    sizes = dialog.canvas.figure.axes[1]
    assert sizes.get_yscale() == "log" and sizes.get_ylim()[0] < 1



def test_the_charts_are_drawn_when_their_tab_is_shown_not_when_the_numbers_come(qtbot, dialog):
    assert dialog.canvas is None                            # the tables show; matplotlib waits
    dialog.tabs.setCurrentWidget(dialog.charts)
    assert dialog.canvas is not None and dialog.drawn_class is None
    first = dialog.stats
    dialog.recompute()
    qtbot.waitUntil(lambda: dialog.stats is not first and dialog.stats is not None, timeout=10000)
    assert dialog.drawn_for is dialog.stats                 # its tab on show: redrawn for the new numbers
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_statsview.py tests/ui/test_stats_dialog.py`
Expected: `No module named 'deeplabeling.ui.statsview'`.

- [ ] **Step 3: Tables, TSV, the dialog and its charts**

Create `src/deeplabeling/ui/statsview.py`:

```python
"""The statistics as tables -- a header and rows of text -- and as TSV, computed without Qt so
they are tested headless (docs/design/2026-10-07-bulk-and-stats.md#the-dialog)."""

from __future__ import annotations

from ..core.stats import FILE_STATES, PER_IMAGE_MAX, SIZE_LABELS, Stats
from .reassign_dialog import class_label

Table = tuple[list[str], list[list[str]]]


def table_classes(stats: Stats, names) -> list[int]:
    """The yaml's classes, then every id its labels hold that it does not name."""
    return [*range(len(names)), *(cls for cls in stats.classes() if not 0 <= cls < len(names))]


def class_table(stats: Stats, names) -> Table:
    header = ["class"] + [f"{split} {what}" for split in stats.splits for what in ("boxes", "images", "polygons")]
    rows = [[class_label(cls, names)] + [str(counter[(split, cls)]) for split in stats.splits
                                         for counter in (stats.boxes, stats.images_with, stats.polygons)]
            for cls in table_classes(stats, names)]
    return header, rows


def files_table(stats: Stats) -> Table:
    return ["split", *FILE_STATES], [[split] + [str(stats.files[(split, state)]) for state in FILE_STATES]
                                     for split in stats.splits]


def sizes_table(stats: Stats, names) -> Table:
    rows = [[class_label(cls, names)] + [str(stats.sizes[(cls, b)]) for b in range(len(SIZE_LABELS))]
            for cls in table_classes(stats, names)]
    return ["class", *SIZE_LABELS], rows + [[f"images whose header cannot be read: {stats.unsized}"]]


def per_image_table(stats: Stats) -> Table:
    return ["boxes", "images"], [[str(n) if n < PER_IMAGE_MAX else f"{n}+", str(stats.per_image[n])]
                                 for n in range(PER_IMAGE_MAX + 1)]


def tsv(header: list[str], rows: list[list[str]]) -> str:
    return "".join("\t".join(row) + "\n" for row in [header, *rows])
```

Create `src/deeplabeling/ui/stats_dialog.py`:

```python
"""Statistics of this queue… (docs/design/2026-10-07-bulk-and-stats.md#statistics): computed
on a worker over the queue's images, shown as tables that copy as TSV and as four charts.

matplotlib (and numpy) are imported when the charts are first drawn, never at the app's start;
and the charts are drawn when their tab is shown, not when the numbers come in, so a
recompute never holds the window up for matplotlib.
"""

from __future__ import annotations

import time

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.stats import GRID, PER_IMAGE_MAX, SIZE_LABELS, stats_of
from .reassign_dialog import class_label
from .statsview import class_table, files_table, per_image_table, sizes_table, table_classes, tsv

TABLES = ("Classes", "Label files", "Box sizes", "Boxes per image")
ALL = "all classes"


class StatsDialog(QDialog):
    def __init__(self, session, prompter, parent=None):
        super().__init__(parent)
        self._session, self._prompter = session, prompter
        ws = session.workspace
        self._names = ws.dataset.names
        self.setWindowTitle(f"Statistics — {session.queue.source.describe(ws.dataset)}")
        self.stats = None
        self._job = None
        self.drawn_class: int | None = None         #: the class the size and centre charts show; None: all
        self.drawn_for = None                       #: the stats the charts were drawn from
        self.status = QLabel()
        self.tabs = QTabWidget()
        self.tables: dict[str, QTableWidget] = {}
        self._shown: dict[str, tuple] = {}          #: each table's (header, rows), as copied
        for name in TABLES:
            table = QTableWidget()
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.tables[name] = table
            self.tabs.addTab(table, name)
        self.charts = QWidget()
        self.chart_class = QComboBox()
        self.chart_class.currentIndexChanged.connect(lambda _: self._draw_if_shown(again=True))
        self.canvas = None                          #: the matplotlib canvas, once drawn
        self._chart_layout = QVBoxLayout(self.charts)
        row = QHBoxLayout()
        row.addWidget(QLabel("Class"))
        row.addWidget(self.chart_class, 1)
        self._chart_layout.addLayout(row)
        self.tabs.addTab(self.charts, "Charts")
        self.tabs.currentChanged.connect(lambda _: self._draw_if_shown())
        self.copy_button, self.recompute_button = QPushButton("Copy"), QPushButton("Recompute")
        self.save_button = QPushButton("Save charts…")
        self.copy_button.clicked.connect(self.copy)
        self.recompute_button.clicked.connect(self.recompute)
        self.save_button.clicked.connect(self.save_charts)
        QShortcut(QKeySequence.Copy, self, self.copy)
        buttons = QHBoxLayout()
        for button in (self.copy_button, self.recompute_button, self.save_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(buttons)
        session.closed.connect(self.close)         # its labels are the dataset's
        self.recompute()

    # -- computing -------------------------------------------------------------------------

    def recompute(self) -> None:
        """Read the queue's images again, on a worker; the tables and charts follow."""
        if self._job is not None:
            self._job.cancel()
        session = self._session
        ws, entries = session.workspace, session.queue_images()
        store, sizes = ws.store, ws.sizes
        self.status.setText(f"reading 0 / {len(entries):,}")
        token = []
        job = session.io.start(
            lambda emit, cancelled: stats_of(entries, store.get, sizes.get, cancelled,
                                             progress=lambda done, total: emit((done, total))),
            batch=lambda told: self._told(token, told),
            done=lambda stats: self._done(token, stats),
            failed=lambda why: self._failed(token, why))
        token.append(job)
        self._job = job

    def _told(self, token, told) -> None:
        if token and token[0] is self._job:
            self.status.setText(f"reading {told[0]:,} / {told[1]:,}")

    def _done(self, token, stats) -> None:
        if not token or token[0] is not self._job:
            return                                  # cancelled, or recomputed since
        self._job = None
        if stats is None:
            return
        self.stats = stats
        images = sum(stats.files[(split, "images")] for split in stats.splits)
        self.status.setText(f"{images:,} images · computed {time.strftime('%H:%M')}" if images else "no images")
        self._fill()

    def _failed(self, token, why: str) -> None:
        if token and token[0] is self._job:
            self._job = None
            self.status.setText(f"the statistics could not be computed: {why}")

    def closeEvent(self, event) -> None:
        if self._job is not None:
            self._job.cancel()
            self._job = None
        super().closeEvent(event)

    # -- showing ---------------------------------------------------------------------------

    def _fill(self) -> None:
        stats, names = self.stats, self._names
        for name, (header, rows) in zip(TABLES, (class_table(stats, names), files_table(stats),
                                                 sizes_table(stats, names), per_image_table(stats))):
            self._shown[name] = (header, rows)
            table = self.tables[name]
            table.clear()
            table.setColumnCount(len(header))
            table.setRowCount(len(rows))
            table.setHorizontalHeaderLabels(header)
            for r, row in enumerate(rows):
                for c, text in enumerate(row):
                    table.setItem(r, c, QTableWidgetItem(text))
            table.resizeColumnsToContents()
        self.chart_class.blockSignals(True)
        self.chart_class.clear()
        self.chart_class.addItem(ALL, None)
        for cls in table_classes(stats, names):
            self.chart_class.addItem(class_label(cls, names), cls)
        self.chart_class.blockSignals(False)
        self._draw_if_shown()

    def copy(self) -> None:
        """The table on show, as TSV."""
        table = self.tabs.currentWidget()
        name = next((n for n, t in self.tables.items() if t is table), None)
        if name in self._shown:
            QApplication.clipboard().setText(tsv(*self._shown[name]))

    def _draw_if_shown(self, again: bool = False) -> None:
        """Draw the charts if their tab is on show and they are not drawn from these numbers."""
        if self.tabs.currentWidget() is self.charts and (again or self.drawn_for is not self.stats):
            self._draw()

    def _draw(self) -> None:
        stats = self.stats
        if stats is None or not any(stats.files[(split, "images")] for split in stats.splits):
            return
        import numpy as np
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        if self.canvas is None:
            self.canvas = FigureCanvasQTAgg(Figure(figsize=(9, 6), layout="constrained"))
            self._chart_layout.addWidget(self.canvas, 1)
        cls = self.chart_class.currentData()
        self.drawn_class, self.drawn_for = cls, stats
        figure, names = self.canvas.figure, self._names
        figure.clear()
        balance, sizes, centres, per_image = figure.subplots(2, 2).flat
        classes = table_classes(stats, names)
        x = np.arange(len(classes))
        width = 0.8 / max(len(stats.splits), 1)
        for i, split in enumerate(stats.splits):
            balance.bar(x + i * width, [stats.boxes[(split, c)] for c in classes], width, label=split)
        balance.set_xticks(x + width * (len(stats.splits) - 1) / 2, [class_label(c, names) for c in classes],
                           rotation=45, ha="right")
        balance.set_title("Class balance")
        balance.legend()
        chosen = classes if cls is None else [cls]
        counts = [sum(stats.sizes[(c, b)] for c in chosen) for b in range(len(SIZE_LABELS))]
        sizes.bar(range(len(SIZE_LABELS)), counts)
        sizes.set_xticks(range(len(SIZE_LABELS)), SIZE_LABELS, rotation=45, ha="right")
        sizes.set_yscale("log", nonpositive="clip")
        sizes.set_ylim(bottom=0.5)                  # a bucket of one box still shows its bar
        sizes.set_title("Box sizes, √(w·h) px")
        grid = np.zeros((GRID, GRID))
        for (c, gx, gy), n in stats.centres.items():
            if c in chosen:
                grid[gy, gx] += n
        centres.imshow(grid, cmap="viridis", extent=(0, 1, 1, 0))
        centres.set_title("Box centres")
        per_image.bar(range(PER_IMAGE_MAX + 1), [stats.per_image[n] for n in range(PER_IMAGE_MAX + 1)])
        per_image.set_title(f"Boxes per image ({PER_IMAGE_MAX} = {PER_IMAGE_MAX} or more)")
        self.canvas.draw()

    def save_charts(self) -> None:
        if self.drawn_for is not self.stats:
            self._draw()                            # saved as they would show
        if self.canvas is None:
            return
        path = self._prompter.choose_save_path("Save charts", "PNG image (*.png)")
        if path:
            self.canvas.figure.savefig(path, dpi=100)
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
            dialog.deleteLater()

    def choose_weights(self) -> str | None:
        path, _ = QFileDialog.getOpenFileName(self.parent, "Load a model", "",
```

with:

```python
            dialog.deleteLater()

    def choose_save_path(self, title: str, filter: str) -> str | None:
        path, _ = QFileDialog.getSaveFileName(self.parent, title, "", filter)
        return path or None

    def choose_weights(self) -> str | None:
        path, _ = QFileDialog.getOpenFileName(self.parent, "Load a model", "",
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_statsview.py tests/ui/test_stats_dialog.py tests/ui/test_prompter.py`
Expected: 22 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 1014 passed.

- [ ] **Step 5: Look at it**

Screenshot `test_stats_dialog.py`'s `dialog` twice: on its first tab, then with the Charts tab shown. Write it as a temporary test in `tests/ui/`, save the PNGs outside the repository, and delete the test after. Expected:
- the status reads `15 images · computed HH:MM`;
- the Classes table reads person 4 4 0 8 5 1, through `#99?`;
- the charts show:
  - train and val bars per class;
  - every non-empty size bucket's bar on a log axis that starts below 1;
  - a heatmap with its brightest cell at the frame's centre;
  - the boxes-per-image histogram.

- [ ] **Step 6: Commit**

```bash
git add src/deeplabeling/ui/statsview.py src/deeplabeling/ui/stats_dialog.py src/deeplabeling/ui/prompter.py tests/fixtures.py tests/ui/test_statsview.py tests/ui/test_stats_dialog.py
git commit -m "ui: the Statistics dialog, its tables copied as TSV and its charts drawn when shown" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Statistics from the queue chip

**Files:**
- Modify: `src/deeplabeling/ui/main_window.py`, `tests/ui/test_queue_chip.py`

**Interfaces:**
- Consumes: Task 2's `StatsDialog`, and plan 5a's `MainWindow._fill_queue_menu` and `Session.queue_not_whole()`.
- Produces: *Statistics of this queue…* in the chip's menu, enabled when the queue is whole; `MainWindow.show_statistics()`; and `MainWindow.statistics`, the window on show.

- [ ] **Step 1: Write the failing tests**

In `tests/ui/test_queue_chip.py`, replace:

```python

def test_the_chip_offers_the_queue_s_actions(qtbot, window):
    assert list(menu(window)) == ["Edit queue…", "Reassign a class in this queue…"]
    assert all(action.isEnabled() for action in menu(window).values())

```

with:

```python

def test_the_chip_offers_the_queue_s_actions(qtbot, window):
    assert list(menu(window)) == ["Edit queue…", "Reassign a class in this queue…", "Statistics of this queue…"]
    assert all(action.isEnabled() for action in menu(window).values())

```

In `tests/ui/test_queue_chip.py`, replace:

```python
    window.session.queue.fail("could not read the store")
    assert not menu(window)["Reassign a class in this queue…"].isEnabled()
```

with:

```python
    window.session.queue.fail("could not read the store")
    assert not menu(window)["Reassign a class in this queue…"].isEnabled()



def test_statistics_open_from_the_menu_and_close_with_the_dataset(qtbot, window):
    menu(window)["Statistics of this queue…"].trigger()
    dialog = window.statistics
    qtbot.waitUntil(lambda: dialog.isVisible() and dialog.stats is not None, timeout=10000)
    assert dialog.windowTitle() == "Statistics — all images"
    window.session.close()
    assert not dialog.isVisible()


def test_a_second_statistics_window_replaces_the_first(qtbot, window):
    from deeplabeling.ui.stats_dialog import StatsDialog

    menu(window)["Statistics of this queue…"].trigger()
    menu(window)["Statistics of this queue…"].trigger()
    qtbot.waitUntil(lambda: len(window.findChildren(StatsDialog)) == 1, timeout=5000)


def test_statistics_are_not_offered_on_a_queue_whose_build_failed(qtbot, window):
    window.session.queue.fail("could not read the store")
    assert not menu(window)["Statistics of this queue…"].isEnabled()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_chip.py`
Expected: 4 failed, 5 passed: the menu has no Statistics entry yet.

- [ ] **Step 3: Offer Statistics from the chip**

In `src/deeplabeling/ui/main_window.py`, replace:

```python
from .queue_panel import QueuePanel
from .reassign import reassign_queue
from .session import Session
from .settings_ui import (QUEUE_GRID_WIDTH, QUEUE_LIST_WIDTH, RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_GRID,
```

with:

```python
from .queue_panel import QueuePanel
from .reassign import reassign_queue
from .stats_dialog import StatsDialog
from .session import Session
from .settings_ui import (QUEUE_GRID_WIDTH, QUEUE_LIST_WIDTH, RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_GRID,
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        self._written: float | None = None
        self._help: HelpDialog | None = None
        self.actions = build_actions(self, {
            "next": lambda: session.move(1),
```

with:

```python
        self._written: float | None = None
        self._help: HelpDialog | None = None
        self.statistics: StatsDialog | None = None
        self.actions = build_actions(self, {
            "next": lambda: session.move(1),
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        menu.clear()
        menu.addAction("Edit queue…", self.edit_queue).setEnabled(queue is not None)
        menu.addAction("Reassign a class in this queue…", self.reassign_queue).setEnabled(
            not self.session.queue_not_whole())

    def reassign_queue(self) -> None:
        reassign_queue(self.session)

    def load_model(self) -> None:
```

with:

```python
        menu.clear()
        menu.addAction("Edit queue…", self.edit_queue).setEnabled(queue is not None)
        whole = not self.session.queue_not_whole()
        menu.addAction("Reassign a class in this queue…", self.reassign_queue).setEnabled(whole)
        menu.addAction("Statistics of this queue…", self.show_statistics).setEnabled(whole)

    def reassign_queue(self) -> None:
        reassign_queue(self.session)

    def show_statistics(self) -> None:
        """A Statistics window for the queue in force; an earlier one makes way for it."""
        if self.statistics is not None:
            self.statistics.close()
            self.statistics.deleteLater()           # a child of the window until deleted
        self.statistics = StatsDialog(self.session, self.prompter, self)
        self.statistics.resize(900, 700)
        self.statistics.show()

    def load_model(self) -> None:
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_chip.py tests/ui/test_stats_dialog.py tests/ui/test_main_window.py`
Expected: 41 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 1017 passed.

```bash
git add src/deeplabeling/ui/main_window.py tests/ui/test_queue_chip.py
git commit -m "ui: Statistics of this queue, from the queue chip" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The measurements and the status

**Files:**
- Create: `tools/measure_bulk_stats.py`
- Modify: `docs/design/2026-10-07-bulk-and-stats.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: `measure_assist.py`'s `Answers` and `wait`; `MainWindow.show_statistics`, `StatsDialog`, `reassign_queue`, `Session`.
- Produces: the measured column of the spec's *Performance targets*, and the status.

- [ ] **Step 1: Write the measurement script**

Create `tools/measure_bulk_stats.py`:

```python
#!/usr/bin/env python3
"""Measure slice 5's performance targets (docs/design/2026-10-07-bulk-and-stats.md#performance-targets).

Read-only on the real dataset: app state goes to a temporary folder, deleted at the end.
Statistics are computed in the window over every image. Reassign looks over every image and
is answered No, so nothing is written. Its write is timed on a dataset generated in a
temporary folder -- --write-boxes images with one box each -- never on the real one.

  /home/sonnn/miniconda3/bin/python3 tools/measure_bulk_stats.py DATA.yaml [--write-boxes 10000]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from measure_assist import Answers, wait  # noqa: E402


class Progress:
    """A progress dialog nobody cancels."""

    def set(self, value):
        pass

    def cancelled(self):
        return False

    def close(self):
        pass


class Prompter(Answers):
    """Answers reassign with (from, to), then `confirm`; times the look and the write."""

    def __init__(self, choice, confirm):
        self.choice, self.confirm, self.asked_at = choice, confirm, None

    def progress(self, title, total):
        return Progress()

    def ask_reassign(self, names, unnamed_ids):
        return self.choice

    def confirm_reassign(self, text):
        self.asked_at = time.perf_counter()
        return self.confirm

    def confirm_queue_accept(self, text):
        return False


def generated(folder: Path, n: int) -> Path:
    """n images, each with one class-0 box, and their yaml."""
    images, labels = folder / "gen" / "images", folder / "gen" / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    import io

    from PIL import Image

    jpeg = io.BytesIO()
    Image.new("RGB", (64, 48)).save(jpeg, "JPEG")
    for i in range(n):
        (images / f"{i:06d}.jpg").write_bytes(jpeg.getvalue())
        (labels / f"{i:06d}.txt").write_text("0 0.500000 0.500000 0.100000 0.100000\n")
    yaml = folder / "gen.yaml"
    yaml.write_text(f"path: {folder}\ntrain: gen/images\nval: gen/images\nnames: [a, b]\n")
    return yaml


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    ap.add_argument("--write-boxes", type=int, default=10000)
    args = ap.parse_args(argv)
    tmp = tempfile.TemporaryDirectory(prefix="measure-bulk-stats-")
    os.environ["DEEPLABELING_STATE_DIR"] = str(Path(tmp.name) / "state")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch
    from deeplabeling.ui.reassign import reassign_queue
    from deeplabeling.ui.session import Session

    app = QApplication.instance() or QApplication(sys.argv[:1])
    rows = []
    prompter = Prompter((0, 1), confirm=False)
    window = launch([str(args.yaml)], prompter)
    window.resize(1440, 900)
    window.show()
    s = window.session
    wait(app, lambda: window.canvas.image_size is not None and s.queue is not None and s.queue.complete)
    images = len(s.queue_images())
    wait(app, lambda: s.io.pool.activeThreadCount() == 0, timeout=300)    # the open's id check, done

    def statistics(name: str) -> None:
        gaps, last = [], [time.perf_counter()]

        def tick():
            now = time.perf_counter()
            gaps.append(now - last[0])
            last[0] = now

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(5)
        t = time.perf_counter()
        if window.statistics is None:
            window.show_statistics()
        else:
            window.statistics.recompute()
        dialog = window.statistics
        total = wait(app, lambda: dialog._job is None and dialog.stats is not None, timeout=300)
        timer.stop()
        rows.append((f"statistics of {images:,} images, {name}: complete", total, "≤ 30 s cold, ≤ 5 s warm"))
        rows.append((f"statistics, {name}: the event loop's longest wait", max(gaps), "≤ 100 ms"))
        t = time.perf_counter()
        dialog.tabs.setCurrentWidget(dialog.charts)     # drawn as its tab shows: matplotlib's turn
        app.processEvents()
        rows.append((f"statistics, {name}: the charts drawn as their tab shows", time.perf_counter() - t, "≤ 1 s"))
        dialog.tabs.setCurrentIndex(0)                  # the next run computes with a table on show

    statistics("cold")                              # the image headers read for the first time
    statistics("warm")

    t = time.perf_counter()
    reassign_queue(s)
    wait(app, lambda: s.running is None and prompter.asked_at is not None, timeout=300)
    rows.append((f"reassign over {images:,} images: looking, answered No", prompter.asked_at - t, "≤ 30 s"))
    window.close()

    folder = Path(tmp.name) / "data"
    yaml = generated(folder, args.write_boxes)
    writer = Prompter((0, 1), confirm=True)
    session = Session(writer)
    session.open(str(yaml))
    wait(app, lambda: session.queue is not None and session.queue.complete, timeout=300)
    reassign_queue(session)
    wait(app, lambda: writer.asked_at is not None, timeout=300)
    wait(app, lambda: session.running is None, timeout=300)
    rows.append((f"reassign writing {args.write_boxes:,} boxes (generated dataset)", time.perf_counter() - writer.asked_at,
                 "≤ 30 s"))
    written = sum(1 for p in (folder / "gen" / "labels").iterdir() if p.read_text().startswith("1 "))
    session.close()

    for name, value, target in rows:
        shown = f"{value * 1000:.0f} ms" if value < 1 else f"{value:.2f} s"
        print(f"{name:72s} {shown:>10s}   target {target}")
    print(f"generated labels rewritten: {written:,} of {args.write_boxes:,}")
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Measure, read-only**

```sh
/home/sonnn/miniconda3/bin/python3 tools/measure_bulk_stats.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml
```

Expected: every row within its target, and `generated labels rewritten: 10,000 of 10,000`. The figures vary with the OS page cache. Record the measured values, not the ones below; a missed target is recorded with its value.

- [ ] **Step 3: Record the measurements and the status**

In `CLAUDE.md`, replace:

````markdown
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. Slice 4 is built: Find Bad, the labels the model disagrees with as a queue,
fixed a key at a time in the full frame or many at once in a grid of crops. Slice 5 has
bulk reassign built; its statistics (plan 5b) are next. The design and the plans are in
[docs/design/](docs/design/).

```sh
````

with:

````markdown
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. Slice 4 is built: Find Bad, the labels the model disagrees with as a queue,
fixed a key at a time in the full frame or many at once in a grid of crops. Slice 5 is
built: bulk reassign and statistics. Every slice of the foundation is built. The design and
the plans are in [docs/design/](docs/design/).

```sh
````

In `docs/design/2026-10-07-bulk-and-stats.md`, replace:

```markdown
# DeepLabeling — slice 5: bulk reassign and statistics

**Status:** approved 2026-10-07 · plan 5a (bulk reassign) implemented; 5b (statistics) next
**Scope:** slice 5 of [the app foundation](2026-10-04-app-foundation.md#slices), the last:
one class rewritten to another across a queue, as one edit; and the statistics of a queue,
```

with:

```markdown
# DeepLabeling — slice 5: bulk reassign and statistics

**Status:** approved 2026-10-07 · implemented: plans 5a (bulk reassign) and 5b (statistics)
**Scope:** slice 5 of [the app foundation](2026-10-04-app-foundation.md#slices), the last:
one class rewritten to another across a queue, as one edit; and the statistics of a queue,
```

In `docs/design/2026-10-07-bulk-and-stats.md`, replace:

```markdown
- **Tables**, one tab each — Classes, Label files, Box sizes, Boxes per image. Each copies
  as TSV (a button, or Ctrl+C).
- **Charts**, drawn with matplotlib from the result:
  - class balance: bars per class, train and val side by side;
  - box sizes: the buckets above, with a log count axis;
```

with:

```markdown
- **Tables**, one tab each — Classes, Label files, Box sizes, Boxes per image. Each copies
  as TSV (a button, or Ctrl+C).
- **Charts**, drawn with matplotlib from the result, when their tab is shown — never as
  the numbers come in, so a recompute does not hold the window up:
  - class balance: bars per class, train and val side by side;
  - box sizes: the buckets above, with a log count axis;
```

In `docs/design/2026-10-07-bulk-and-stats.md`, replace:

```markdown
measured value, not quietly dropped.

| Action | Target |
|---|---|
| reassign over 45k images: looking / writing 10k boxes | ≤ 30 s / ≤ 30 s, with progress, the window responsive |
| statistics over 45k images, complete: cold / warm | ≤ 30 s / ≤ 5 s |
| the window while statistics compute | the event loop never waits more than 100 ms |
| the dialog, its charts drawn, once the numbers are in | ≤ 1 s |

## Testing
```

with:

````markdown
measured value, not quietly dropped.

| Action | Target | Measured 2026-10-07 |
|---|---|---|
| reassign over 45k images: looking / writing 10k boxes | ≤ 30 s / ≤ 30 s, with progress, the window responsive | 529 ms / 925 ms (the write on a generated dataset) |
| statistics over 45k images, complete: cold / warm | ≤ 30 s / ≤ 5 s | 3.32 s / 1.56 s; cold was 8.2–9.6 s in two earlier runs that day |
| the window while statistics compute | the event loop never waits more than 100 ms | 17 ms cold, 11 ms warm |
| the dialog, its charts drawn, once the numbers are in | ≤ 1 s | 825 ms the first time (matplotlib imported), 221 ms after |

- "Cold" is the first computation after opening. The label files are already in the store
  by then — the open-time check of class ids reads every one — so cold reads the image
  headers; the OS page cache varied between runs.
- A warm computation is all Python on a worker, and held the GIL long enough to stall the
  window 177–223 ms; it pauses 0.5 ms every 256 images (`src/deeplabeling/core/stats.py::stats_of`).
- The reassign write is timed on a dataset generated in a temporary folder, never on the
  real one. Reproduce, read-only (app state goes to a temporary folder, deleted at the end):

```sh
/home/sonnn/miniconda3/bin/python3 tools/measure_bulk_stats.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml
```

## Testing
````

- [ ] **Step 4: Check the docs, run the full suite, and commit**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 1017 passed.

```bash
git add tools/measure_bulk_stats.py docs/design/2026-10-07-bulk-and-stats.md CLAUDE.md
git commit -m "docs: slice 5 is built; statistics and reassign measured" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
