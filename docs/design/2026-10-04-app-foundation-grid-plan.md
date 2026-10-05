# Slice 1d: the queue grid — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish slice 1. `G` switches the queue panel to a grid of thumbnails with their label boxes drawn on them; mark page marks every tile in view; `↑` `↓` move by a row. Fix the two minor findings deferred from plan 1b.

**Architecture:** One `QListView` shows the queue as a list or, with a wrapping flow, a fixed grid size and a tile delegate, as a grid. There is one selection model, so the cursor still has one mirror. Thumbnails go through the existing `ImageCache`, given a decode function that scales as it reads and a `want(paths)` that cancels decodes for tiles that left the view. A tile reads its labels when it is painted, so it never shows stale boxes.

**Tech Stack:** PySide6 6.6 (conda base), pytest-qt (offscreen), and the merged slices 1a–1c.

**Spec:** [2026-10-04-app-foundation.md](2026-10-04-app-foundation.md). This plan implements:
- the Window section's queue grid: `G`, thumbnails with boxes, mark page, the 64 MB thumbnail cache, and `↑` `↓` by row;
- review marks set by mark page, from its Review marks section;
- two new rows in its Performance targets.

The earlier plans are [the core](2026-10-04-app-foundation-core-plan.md), [the viewer](2026-10-04-app-foundation-ui-plan.md) and [editing](2026-10-04-app-foundation-editing-plan.md).

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base, PySide6 6.6.0). Bare `python3` can be another conda env ([environment.md](../knowledge/environment.md#python)). Install nothing.
- **Threads** ([landmine 3](../../CLAUDE.md#landmines)): thumbnails decode on their own pool of two workers. Workers get a path and return an image; they never touch a widget. The GUI thread never waits on them.
- **One owner** ([landmine 2](../../CLAUDE.md#landmines)): a tile reads its labels through `Session.labels` each time it is painted and keeps nothing. Mark page goes through `Session.mark_reviewed`; nothing else writes review marks.
- **Verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines); the `run-and-verify-ui` skill): grid tests read pixels back from `grab()` and check tile geometry against the viewport, not widget state alone.
- **Every setting survives every launch path** ([landmine 7](../../CLAUDE.md#landmines)): the grid toggle and both panel widths are settings, bound through `bind_toggle` or written on change and at close.
- **The disk is nearly full** ([landmine 9](../../CLAUDE.md#landmines)): the measurement reads pvn-vehicle in place, and its app state goes to a temporary folder.
- **Tests write only to temporary folders** (landmine 10).
- **`src/deeplabeling/core/` stays Qt-free.** Its one change, `Queue.fail`, is pure Python.
- **PySide6 keeps every lambda connected to a signal** ([environment.md](../knowledge/environment.md#pyside6-and-numpy)): connections made per job or per tile use bound methods.
- **Doc rules:** one fact, one home; a command over a restatement; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice1-grid` from `main`. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit. The `-o addopts=` is there because the project's `-q` plus another `-q` hides the summary line.
- **pytest-qt habits:** `qtbot.waitUntil` takes a callback returning a bool. Window shortcuts need an active window, which `start` in `tests/ui/drive.py` provides. A script run outside `tests/` sets `QT_QPA_PLATFORM=offscreen` itself.

## Review Focus

These are the inputs the spec implies that are most likely to hurt someone using the grid. Each has a named test in the task that owns the code:

1. **A real-sized queue, with the cursor deep inside it.** Switching views or resizing the panel must keep the current tile in view, and finding the tiles in view must not walk the whole queue. *(Task 3 `test_switching_view_shows_the_current_item_in_the_new_one`, `test_a_resized_grid_keeps_the_current_tile_in_view`; Task 5 measures it on pvn-vehicle.)*
2. **Scrolling fast through the grid.** Decodes for tiles that left the view are cancelled, so the tiles now in view are not queued behind them, and no tile out of view is decoded. *(Task 2 `test_wanting_other_tiles_cancels_the_decodes_no_longer_in_view`; Task 3 `test_only_the_tiles_in_view_are_decoded`.)*
3. **Mark page with a tile cut by the viewport's edge.** Only tiles wholly in view are marked, never one the user could not see. *(Task 3 `test_mark_page_marks_exactly_the_tiles_fully_in_view`.)*
4. **Labels a tile cannot draw cleanly:** a box past the image's edge, an unknown class, a polygon, an undecodable image. Each tile draws inside itself, and its caption stays visible. *(Task 3 `test_a_box_outside_the_image_stays_inside_its_tile`, `test_a_tile_with_its_thumbnail_shows_its_caption`.)*
5. **Relaunching in the grid.** The grid comes back at its width, and the list keeps its own. *(Task 4 `test_the_grid_and_its_width_survive_a_relaunch`.)*

## Found while building this plan

The plan's code was built and run in a scratch copy of `main` before it was written down: 531 tests pass. Every task was then dry-run on a fresh copy, and pvn-vehicle (45k images) was measured. Along the way:

- **One view does both modes.** A spike laid out 45k rows, growing in batches of 500. A wrapping list took 1.4 s in all, and Qt's icon mode 2.9 s. Toggling one view between the modes takes 59 ms on pvn-vehicle.
- **Switching views with the cursor mid-queue left it about a million pixels out of view.** The view scrolled by the layout it still had, and `setCurrentIndex` to the item already current scrolls nowhere. The fix lays the view out (`doItemsLayout()`) and then scrolls explicitly.
- **Widening the dock reflows the grid from one column to three, and the old scroll offset then shows other tiles.** After a resize, the grid lays out again and brings the current tile back.
- **A box past the image's edge** (the fixture's `cx = 1.4`) **was drawn outside its tile.** The first fix clipped the boxes and also clipped the caption painted after them. Boxes are now clipped inside their own `save()`/`restore()`, and a pixel test checks the caption.
- **Thumbnails are cheap.** A scaled JPEG decode takes 0.7 ms on pvn-vehicle, against 1.1 ms for a full one.

## Decisions this plan makes

The spec leaves these open; each is pinned by a test, and Task 5 writes the design-level ones into the spec.

- **Mark page marks the tiles wholly in view: what was seen, nothing more.** It is a button on the panel, shown only in the grid, and an action with no key (listed in `?` help).
- **`↓` `↑` are separate from `→` `←`.** In the grid they move by a row. With no row there, the cursor stays and the status bar says so, as at either end of the queue.
- **The grid toggle persists**, and the list and the grid each keep their own panel width. The grid's default width, 560 px, fits three tiles.
- **A tile** is a 176 × 150 cell: the thumbnail fitted into 160 × 120, then the caption (✓, the file name, the badge). Boxes are 1 px, 2 px when highlighted and dashed for an unknown class. A tile that cannot be decoded says so.
- **A failed queue build** keeps the items that came, settles the cursor, and the chip and the panel title say "build failed" instead of "building…" forever.
- **Undo or redo with no dataset open** says "nothing to undo" or "nothing to redo", as with an empty history.
- **Two new performance targets:** the first page of thumbnails, and a page after a jump, each ≤ 1 s.

## Left for later

- **Slice 2** (model assist) is next ([Slices](2026-10-04-app-foundation.md#slices)).
- **Plan 1c's open question and minor findings** are not in this plan. The question is whether a drawn box stays selected, which makes drawing a box inside it move it instead. The minors are in plan 1c's final report.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/queue.py`, `src/deeplabeling/ui/session.py`, `state_bar.py`, `queue_panel.py` | a failed build says so; undo without a dataset | 1 |
| `src/deeplabeling/ui/images.py`, `session.py` | thumbnails decoded at display size; `want` cancels what left the view | 2 |
| `src/deeplabeling/ui/queue_panel.py`, `session.py` | the grid: tiles, the tiles in view, mark page | 3 |
| `src/deeplabeling/ui/main_window.py`, `keymap.py`, `settings_ui.py`, `queue_panel.py` | `G`, the widths, `↑` `↓` by row, the mark page action | 4 |
| `tools/measure_ui.py`, the spec, `CLAUDE.md`, the `run-and-verify-ui` skill | the measurement and the docs | 5 |

UI tests live in `tests/ui/`. Their basenames are unique across `tests/`, and they import shared helpers as `from fixtures import …` and `from drive import …`.

---

### Task 1: A failed queue build says so; undo without a dataset

**Files:**
- Modify: `src/deeplabeling/core/queue.py`, `src/deeplabeling/ui/session.py`, `src/deeplabeling/ui/state_bar.py`, `src/deeplabeling/ui/queue_panel.py`
- Test: `tests/core/test_queue.py`, `tests/ui/test_session.py`, `tests/ui/test_state_bar.py`, `tests/fixtures.py`

**Interfaces:**
- Consumes: `Queue.finish` (plan 1a) and `Session._built` (plan 1b).
- Produces:
  - `Queue.failed`: the reason a build stopped, or `None`;
  - `Queue.fail(why)`, which keeps the items that came and settles the cursor as `finish()` does;
  - `Session.progress_text() -> str`: `""` once built, `" · building…"` while it builds, or `" · build failed"`;
  - `Session.undo()` and `Session.redo()` with no dataset open say "nothing to undo" or "nothing to redo";
  - in `tests/fixtures.py`, `Broken`, a queue condition whose test raises `OSError("the disk went away")`.

- [ ] **Step 1: Branch, and commit this plan**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout main && git pull --ff-only && git checkout -b slice1-grid
git add docs/design/2026-10-04-app-foundation-grid-plan.md
git commit -m "docs: the slice 1d queue grid plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

In `tests/fixtures.py`, replace:

```python
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

```

with:

```python
from pathlib import Path
from typing import ClassVar

import cv2
import numpy as np
import yaml
from PIL import Image

from deeplabeling.core.queue import Condition

```

Append to `tests/fixtures.py`:

```python
@dataclass(frozen=True)
class Broken(Condition):
    """A condition whose test raises, as a build meets an unreadable disk."""

    kind: ClassVar[str] = "broken"
    needs_labels: ClassVar[bool] = False

    def test(self, entry, ctx):
        raise OSError("the disk went away")

    def describe(self, dataset):
        return "broken"

    def to_json(self):
        return {"kind": self.kind}
```

Append to `tests/core/test_queue.py`:

```python
def test_a_failed_build_keeps_what_came_and_settles_the_cursor(dataset):
    q = Queue(ImageFilter(), follow=dataset.images[5])
    q.extend(all_items(dataset)[:3])
    q.fail("OSError: the disk went away")
    assert len(q) == 3 and q.complete and q.failed == "OSError: the disk went away"
    assert q.cursor == dataset.images[2].rel            # the followed item never came
```

In `tests/ui/test_session.py`, replace:

```python
from fixtures import FakePrompter, assert_only_changed, open_session, wait_decoded
```

with:

```python
from fixtures import Broken, FakePrompter, assert_only_changed, open_session, wait_decoded
```

Append to `tests/ui/test_session.py`:

```python
def test_undo_and_redo_with_no_dataset_open_say_there_is_nothing_to_do(qtbot):
    s = Session(FakePrompter())
    said = record(s.status)
    s.undo()
    s.redo()
    assert said == [("nothing to undo",), ("nothing to redo",)]


def test_a_build_that_fails_says_so_and_stops_building(qtbot, session):
    notices = record(session.notice)
    with qtbot.waitSignal(session.queueDone, timeout=5000):
        session.set_queue(ImageFilter(conditions=(Broken(),)))
    assert session.queue.complete and session.queue.failed == "OSError: the disk went away"
    assert session.progress_text() == " · build failed"
    assert ("error", "building the queue failed: OSError: the disk went away", None) in notices
```

In `tests/ui/test_state_bar.py`, replace:

```python
from deeplabeling.ui.session import Session
from deeplabeling.ui.state_bar import StateBar
from fixtures import FakePrompter
```

with:

```python
from deeplabeling.core.queue import ImageFilter
from deeplabeling.ui.session import Session
from deeplabeling.ui.state_bar import StateBar
from fixtures import Broken, FakePrompter
```

Append to `tests/ui/test_state_bar.py`:

```python
def test_the_queue_chip_says_building_and_then_nothing_or_failed(qtbot, session):
    bar = shown(qtbot, StateBar(session), 1400)
    assert not bar.queue.full_text.endswith("…")
    with qtbot.waitSignal(session.queueDone, timeout=5000):
        session.set_queue(ImageFilter(conditions=(Broken(),)))
    assert bar.queue.full_text == "Queue: broken · 0 · 0 left · build failed"
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_queue.py -k failed_build`
Expected: 1 failed, 35 deselected. It fails on `AttributeError: 'Queue' object has no attribute 'fail'`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_session.py tests/ui/test_state_bar.py -k "no_dataset_open or fails_says or building_and_then"`
Expected: 3 failed, 36 deselected. Undo raises `RuntimeError: no dataset is open`, and the two build tests time out after 5 s, because a failed build never says it is done.

- [ ] **Step 4: Settle a failed build, and undo without a dataset**

In `src/deeplabeling/core/queue.py`, replace:

```python
        self.stale: set[str] = set()
        self.complete = False
```

with:

```python
        self.stale: set[str] = set()
        self.complete = False
        self.failed: str | None = None      #: why the build stopped early, if it failed
```

In `src/deeplabeling/core/queue.py`, replace:

```python
    def current(self) -> QueueItem | None:
```

with:

```python
    def fail(self, why: str) -> None:
        """The build stopped with an error. The items that came stay, and the queue is
        settled as if complete: nothing waits for items that will not come."""
        self.failed = why
        self.finish()

    def current(self) -> QueueItem | None:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            failed=lambda why: self.notice.emit("error", f"building the queue failed: {why}", None))
```

with:

```python
            failed=lambda why: self._build_failed(queue, why))
```

In `src/deeplabeling/ui/session.py`, replace:

```python
    def _built(self, queue: Queue, finished: bool) -> None:
        if queue is not self.queue or not finished:
            return
        before = queue.cursor
        queue.finish()
```

with:

```python
    def _build_failed(self, queue: Queue, why: str) -> None:
        self.notice.emit("error", f"building the queue failed: {why}", None)
        self._built(queue, True, failed=why)

    def _built(self, queue: Queue, finished: bool, failed: str | None = None) -> None:
        if queue is not self.queue or not finished:
            return
        before = queue.cursor
        if failed is None:
            queue.finish()
        else:
            queue.fail(failed)
```

In `src/deeplabeling/ui/session.py`, replace:

```python
    def left(self) -> int:
```

with:

```python
    def progress_text(self) -> str:
        """How the queue's build stands, for the chip and the panel: "" once built."""
        queue = self.queue
        if queue is None or (queue.complete and queue.failed is None):
            return ""
        return " · build failed" if queue.failed is not None else " · building…"

    def left(self) -> int:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
    def _step(self, *, undo: bool) -> None:
        ws = self._require()
        edit = ws.history.peek_undo() if undo else ws.history.peek_redo()
```

with:

```python
    def _step(self, *, undo: bool) -> None:
        ws = self.workspace
        edit = None if ws is None else ws.history.peek_undo() if undo else ws.history.peek_redo()
```

In `src/deeplabeling/ui/state_bar.py`, replace:

```python
                building = "" if q.complete else " · building…"
                self.queue.set_full_text(f"Queue: {q.source.describe(d)} · {len(q):,} · "
                                         f"{session.left():,} left{building}")
```

with:

```python
                self.queue.set_full_text(f"Queue: {q.source.describe(d)} · {len(q):,} · "
                                         f"{session.left():,} left{session.progress_text()}")
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
            building = "" if queue.complete else " · building…"
            self.title.setText(f"Queue · {len(queue):,}{building}")
```

with:

```python
            self.title.setText(f"Queue · {len(queue):,}{self._session.progress_text()}")
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_queue.py tests/ui/test_session.py tests/ui/test_state_bar.py`
Expected: 75 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 506 passed.

```bash
git add src tests
git commit -m "ui: a failed queue build says so; undo with no dataset says there is nothing to undo" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Thumbnails, decoded at display size for the tiles in view

**Files:**
- Modify: `src/deeplabeling/ui/images.py` (replaced whole), `src/deeplabeling/ui/session.py`
- Test: `tests/ui/test_images.py` (replaced whole)

**Interfaces:**
- Consumes: `Jobs` and `Handle` (plan 1b); `ImageCache` (plan 1b), which this task extends.
- Produces in `deeplabeling.ui.images`:
  - `THUMB_PX = 160` and `THUMB_BYTES = 64 MiB`;
  - `decode_thumb(path, longest=THUMB_PX) -> QImage`: EXIF applied, never enlarged; raises `ValueError` like `decode_image`;
  - `ImageCache(jobs, limit_bytes=..., decode=decode_image, parent=None)`, which takes the decode function, and gains `.want(paths)`. That keeps these paths, and cancels every other decode still waiting. A cancelled job skips its decode.
- Produces in `Session`: `.thumbs`, an `ImageCache` of thumbnails on its own two workers. It is cleared when the dataset closes.

- [ ] **Step 1: Write the failing tests**

Replace `tests/ui/test_images.py` with:

```python
import threading

import pytest

from deeplabeling.ui.images import ImageCache, decode_image, decode_thumb
from deeplabeling.ui.workers import Jobs
from fixtures import make_exif_rotated_image, make_image


def test_decoding_applies_exif_rotation(ds):
    image = decode_image(ds.img("camB/rot.jpg"))
    assert (image.width(), image.height()) == (48, 64)


def test_an_unreadable_image_raises(ds):
    with pytest.raises(ValueError):
        decode_image(ds.img("bad/corrupt.jpg"))


def test_kept_images_are_decoded_and_served(qtbot, ds):
    cache = ImageCache(Jobs(2))
    with qtbot.waitSignals([cache.ready, cache.ready], timeout=5000):
        cache.keep([ds.img("camA/0001.jpg"), ds.img("camA/0002.jpg")])
    assert cache.get(ds.img("camA/0001.jpg")).width() == 64
    assert cache.error(ds.img("camA/0001.jpg")) is None


def test_an_undecodable_image_is_an_error_not_an_image(qtbot, ds):
    cache = ImageCache(Jobs(1))
    with qtbot.waitSignal(cache.failed, timeout=5000) as caught:
        cache.request(ds.img("bad/corrupt.jpg"))
    assert caught.args[0] == ds.img("bad/corrupt.jpg")
    assert cache.get(ds.img("bad/corrupt.jpg")) is None and cache.error(ds.img("bad/corrupt.jpg"))


def test_the_budget_evicts_old_images_but_never_kept_ones(qtbot, tmp_path):
    paths = [tmp_path / f"{i}.png" for i in range(4)]
    for p in paths:
        make_image(p, 100, 100)                       # 40 KB decoded each
    cache = ImageCache(Jobs(1), limit_bytes=60_000)
    for p in paths[:3]:
        with qtbot.waitSignal(cache.ready, timeout=5000):
            cache.request(p)
    assert cache.cached_bytes <= 60_000 and cache.get(paths[2]) is not None
    with qtbot.waitSignal(cache.ready, timeout=5000):
        cache.keep([paths[3], paths[2]])
    assert cache.get(paths[3]) is not None and cache.get(paths[2]) is not None


def test_a_decode_finishing_after_clear_is_ignored(qtbot, ds):
    jobs = Jobs(1)
    cache = ImageCache(jobs)
    ready = []
    cache.ready.connect(ready.append)
    cache.request(ds.img("camA/0001.jpg"))
    cache.clear()
    jobs.wait(5000)
    qtbot.wait(50)
    assert ready == [] and cache.get(ds.img("camA/0001.jpg")) is None


def test_a_thumbnail_is_decoded_at_display_size_and_keeps_its_aspect(tmp_path):
    make_image(tmp_path / "big.jpg", 640, 480)
    thumb = decode_thumb(tmp_path / "big.jpg")
    assert (thumb.width(), thumb.height()) == (160, 120)


def test_a_thumbnail_applies_exif_rotation(tmp_path):
    make_exif_rotated_image(tmp_path / "rot.jpg", 640, 480)
    thumb = decode_thumb(tmp_path / "rot.jpg")
    assert (thumb.width(), thumb.height()) == (120, 160)


def test_a_small_image_is_not_enlarged(ds):
    thumb = decode_thumb(ds.img("camA/0001.jpg"))
    assert (thumb.width(), thumb.height()) == (64, 48)


def test_an_unreadable_thumbnail_raises(ds):
    with pytest.raises(ValueError):
        decode_thumb(ds.img("bad/corrupt.jpg"))


def test_wanting_other_tiles_cancels_the_decodes_no_longer_in_view(qtbot, ds):
    gate = threading.Event()

    def slow(path):
        gate.wait(5)
        return decode_image(path)

    jobs = Jobs(1)
    cache = ImageCache(jobs, decode=slow)
    a, b, c = ds.img("camA/0001.jpg"), ds.img("camA/0002.jpg"), ds.img("camA/0003.jpg")
    ready = []
    cache.ready.connect(ready.append)
    cache.want([a, b])
    cache.want([c])                                 # scrolled: a and b left the view
    gate.set()
    qtbot.waitUntil(lambda: cache.get(c) is not None, timeout=5000)
    jobs.wait(5000)
    qtbot.wait(20)
    assert ready == [c] and cache.get(a) is None and cache.get(b) is None


def test_the_session_keeps_thumbnails_until_the_dataset_closes(qtbot, session, ds):
    path = ds.img("camA/0001.jpg")
    with qtbot.waitSignal(session.thumbs.ready, timeout=5000):
        session.thumbs.want([path])
    assert session.thumbs.get(path).width() == 64
    session.close()
    assert session.thumbs.get(path) is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_images.py`
Expected: `ImportError: cannot import name 'decode_thumb' from 'deeplabeling.ui.images'`.

- [ ] **Step 3: Decode thumbnails, and cancel what left the view**

Replace `src/deeplabeling/ui/images.py` with:

```python
"""Decoding images and thumbnails on workers, into caches bounded in bytes
(docs/design/2026-10-04-app-foundation.md#window)."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QImageReader

from .workers import Handle, Jobs

THUMB_PX = 160                  #: a thumbnail's longer side, at most
THUMB_BYTES = 64 * 2**20        #: the thumbnail cache's budget (the spec)


def decode_image(path) -> QImage:
    """Decode with EXIF orientation applied, as the size function in caches.md does.

    QImageReader.size() reports the stored, unrotated size; only the decoded image
    has the displayed one. Raises ValueError when the file is not a readable image.
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or "not an image")
    return image


def decode_thumb(path, longest: int = THUMB_PX) -> QImage:
    """A thumbnail at most `longest` px on its longer side, EXIF orientation applied.

    The decoder scales as it reads (a JPEG at a fraction of its size), so a page of
    tiles costs little; an image smaller than that is never enlarged. The stored size
    is scaled: rotation keeps the longer side. Raises ValueError like decode_image.
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > longest:
        reader.setScaledSize(size.scaled(longest, longest, Qt.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or "not an image")
    return image


class ImageCache(QObject):
    """Decoded images by path. The images it is told to keep -- the current one and
    its neighbours, or the tiles in view -- are decoded first and never evicted; the
    rest go oldest first once the cache is over its byte budget."""

    ready = Signal(object)          # path
    failed = Signal(object, str)    # path, why

    def __init__(self, jobs: Jobs, limit_bytes: int = 512 * 2**20,
                 decode: Callable[[Path], QImage] = decode_image, parent=None):
        super().__init__(parent)
        self._jobs = jobs
        self._limit = limit_bytes
        self._decode = decode
        self._images: OrderedDict[Path, QImage] = OrderedDict()
        self._errors: dict[Path, str] = {}
        self._pending: dict[Path, Handle] = {}
        self._keep: set[Path] = set()
        self._bytes = 0

    @property
    def cached_bytes(self) -> int:
        return self._bytes

    def get(self, path) -> QImage | None:
        path = Path(path)
        image = self._images.get(path)
        if image is not None:
            self._images.move_to_end(path)
        return image

    def error(self, path) -> str | None:
        return self._errors.get(Path(path))

    def keep(self, paths: Iterable) -> None:
        """Decode these, in this order, and keep them whatever the budget."""
        paths = [Path(p) for p in paths]
        self._keep = set(paths)
        for path in paths:
            self.request(path)
        self._evict()

    def want(self, paths: Iterable) -> None:
        """Keep these and cancel every other decode still waiting: the tiles in view,
        when a scroll has taken the earlier ones out of it."""
        paths = [Path(p) for p in paths]
        wanted = set(paths)
        for path in [p for p in self._pending if p not in wanted]:
            self._pending.pop(path).cancel()
        self.keep(paths)

    def request(self, path) -> None:
        path = Path(path)
        if path in self._images or path in self._errors or path in self._pending:
            return
        decode = self._decode
        self._pending[path] = self._jobs.start(
            lambda emit, cancelled, p=path: None if cancelled() else decode(p),
            done=lambda image, p=path: self._decoded(p, image),
            failed=lambda why, p=path: self._failed(p, why))

    def clear(self) -> None:
        for job in self._pending.values():
            job.cancel()
        self._pending.clear()
        self._images.clear()
        self._errors.clear()
        self._keep = set()
        self._bytes = 0

    def _decoded(self, path: Path, image: QImage) -> None:
        if self._pending.pop(path, None) is None:
            return                                  # cleared while decoding
        self._images[path] = image
        self._bytes += image.sizeInBytes()
        self._evict()
        self.ready.emit(path)

    def _failed(self, path: Path, why: str) -> None:
        if self._pending.pop(path, None) is None:
            return
        self._errors[path] = why
        self.failed.emit(path, why)

    def _evict(self) -> None:
        while self._bytes > self._limit:
            victim = next((p for p in self._images if p not in self._keep), None)
            if victim is None:
                break
            self._bytes -= self._images.pop(victim).sizeInBytes()
```

In `src/deeplabeling/ui/session.py`, replace:

```python
from .images import ImageCache
```

with:

```python
from .images import THUMB_BYTES, ImageCache, decode_thumb
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self.images = ImageCache(Jobs(2), parent=self)
```

with:

```python
        self.images = ImageCache(Jobs(2), parent=self)
        self.thumbs = ImageCache(Jobs(2), THUMB_BYTES, decode=decode_thumb, parent=self)
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self.io.cancel_all()
        self.images.clear()
```

with:

```python
        self.io.cancel_all()
        self.images.clear()
        self.thumbs.clear()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_images.py`
Expected: 12 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 512 passed.

```bash
git add src/deeplabeling/ui tests/ui
git commit -m "ui: thumbnails decoded at display size; a scroll cancels the decodes it left behind" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The grid in the queue panel, and mark page

**Files:**
- Modify: `src/deeplabeling/ui/queue_panel.py` (replaced whole), `src/deeplabeling/ui/session.py`
- Create: `tests/ui/test_grid.py`
- Test: `tests/ui/test_session.py`

**Interfaces:**
- Consumes:
  - Task 1: `Session.progress_text`;
  - Task 2: `Session.thumbs`, with `.want`, `.get`, `.error`, `ready` and `failed`;
  - plan 1b: `box_views`, `Session.badge` and `Session.labels`.
- Produces in `deeplabeling.ui.queue_panel`:
  - `TILE = QSize(176, 150)`, `THUMB_AREA` and `WANT_MS = 30`;
  - `tile_thumb_rect(cell: QRect, thumb: QSize) -> QRect`, where a thumbnail is drawn in a cell;
  - `tile_text(session, item) -> str`, such as `"✓ 0001.jpg · 2 boxes"`;
  - `TileDelegate(session)`;
  - on `QueuePanel`: `.grid` (bool), `.set_grid(on)`, `.columns() -> int` (1 in the list), `.visible_keys(partial=False) -> list[str]`, `.mark_page()` and `.mark_button`.
- Produces in `Session`: `.mark_reviewed(keys) -> int`, the number newly marked. It reports in the status bar: "marked 2 images reviewed", or "these were all reviewed already".

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_grid.py`:

```python
"""The queue as a grid of thumbnails: shown, read back from its pixels, and driven
(the run-and-verify-ui skill)."""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor

from deeplabeling.ui.queue_panel import QueuePanel, tile_text, tile_thumb_rect


@pytest.fixture
def grid(qtbot, session):
    """A panel two tiles wide, a row and a half of tiles high."""
    p = QueuePanel(session)
    qtbot.addWidget(p)
    p.set_grid(True)
    p.resize(420, 300)
    p.show()
    qtbot.waitUntil(p.isVisible)
    return p


def tile(panel, row):
    return panel.view.visualRect(panel.model.index(row))


def shot(panel):
    return panel.view.viewport().grab().toImage()


def colours_near(image, x, y, radius=2):
    return [QColor(image.pixel(x + dx, y + dy)) for dx in range(-radius, radius + 1)
            for dy in range(-radius, radius + 1)]


def test_a_tile_shows_the_thumbnail_with_its_label_boxes(qtbot, grid):
    thumb = tile_thumb_rect(tile(grid, 0), QSize(64, 48))
    assert thumb.size() == QSize(160, 120)                  # 64 x 48, drawn at the tile's size
    # The frame's green block covers x and y 12-50 %; the person box's top edge runs at
    # y 35 %, x 40-60 %, in #e6194b.
    qtbot.waitUntil(lambda: any(c.green() > 150 and c.red() < 60
                                for c in colours_near(shot(grid), thumb.x() + 50, thumb.y() + 30)))
    edge = colours_near(shot(grid), thumb.x() + 80, thumb.y() + 42)
    assert any(c.red() > 200 and c.green() < 80 and 40 < c.blue() < 120 for c in edge)


def test_a_tile_with_its_thumbnail_shows_its_caption(qtbot, grid, session):
    qtbot.waitUntil(lambda: session.thumbs.get(session.queue.items[0].entry.path) is not None)
    qtbot.wait(20)
    image, cell = shot(grid), tile(grid, 0)
    below = tile_thumb_rect(cell, QSize(64, 48)).bottom() + 6
    light = sum(QColor(image.pixel(x, y)).lightness() > 170
                for x in range(cell.left() + 8, cell.left() + 120) for y in range(below, cell.bottom() - 2))
    assert light > 30                                       # "0001.jpg · 2 boxes" is drawn


def test_a_box_outside_the_image_stays_inside_its_tile(qtbot, grid, session):
    grid.resize(490, 300)                                   # two columns, then empty space
    qtbot.waitUntil(lambda: grid.columns() == 2)
    row = session.queue.index_of("bad/images/ok.jpg")       # its line 3 is centred at x 1.4
    assert row % 2 == 1                                     # the right-hand column
    session.go_to("bad/images/ok.jpg")                      # which brings its tile into view
    qtbot.waitUntil(lambda: session.thumbs.get(session.queue.items[row].entry.path) is not None)
    qtbot.wait(20)
    thumb = tile_thumb_rect(tile(grid, row), QSize(64, 48))
    beyond = thumb.x() + int(1.3 * 160)                     # the box's left edge, past the tile
    assert tile(grid, row).right() < beyond < grid.view.viewport().width()
    image = shot(grid)
    assert not any(c.red() > 200 and c.green() < 80 and 40 < c.blue() < 120
                   for c in colours_near(image, beyond, thumb.y() + 60))


def test_a_tile_names_its_file_its_badge_and_whether_it_is_reviewed(session):
    item = session.queue.items[0]
    assert tile_text(session, item) == "0001.jpg · 2 boxes"
    session.toggle_reviewed()
    assert tile_text(session, item) == "✓ 0001.jpg · 2 boxes"


def test_the_grid_is_laid_out_in_columns_that_follow_the_width(qtbot, grid):
    assert grid.columns() == 2
    assert tile(grid, 1).top() == tile(grid, 0).top() and tile(grid, 2).top() > tile(grid, 0).top()
    grid.resize(620, 300)
    qtbot.waitUntil(lambda: grid.columns() == 3)
    qtbot.waitUntil(lambda: tile(grid, 2).top() == tile(grid, 0).top())


def test_the_grid_mirrors_the_cursor_and_a_click_moves_it(qtbot, grid, session):
    session.move(3)
    assert grid.view.currentIndex().row() == 3
    assert grid.view.viewport().rect().contains(tile(grid, 3))
    qtbot.mouseClick(grid.view.viewport(), Qt.LeftButton, pos=tile(grid, 2).center())
    assert session.current().key == session.queue.items[2].key


def test_switching_view_shows_the_current_item_in_the_new_one(qtbot, session):
    panel = QueuePanel(session)
    qtbot.addWidget(panel)
    panel.resize(420, 300)
    panel.show()
    qtbot.waitUntil(panel.isVisible)
    session.go_to(session.queue.items[-1].key)              # in view in the list, a page down in the grid
    panel.set_grid(True)
    qtbot.wait(20)
    assert panel.view.viewport().rect().contains(tile(panel, len(session.queue) - 1))
    session.go_to(session.queue.items[0].key)
    panel.set_grid(False)
    qtbot.wait(20)
    assert panel.view.viewport().rect().contains(tile(panel, 0))


def test_a_resized_grid_keeps_the_current_tile_in_view(qtbot, grid, session):
    session.go_to(session.queue.items[7].key)
    assert grid.view.viewport().rect().contains(tile(grid, 7))
    grid.resize(620, 300)                                   # two columns become three
    qtbot.waitUntil(lambda: grid.columns() == 3)
    qtbot.waitUntil(lambda: grid.view.viewport().rect().contains(tile(grid, 7)), timeout=1000)


def test_the_current_tile_is_framed(qtbot, grid, session):
    session.move(1)
    qtbot.wait(10)
    image = shot(grid)
    current, other = tile(grid, 1), tile(grid, 0)
    frame = QColor(image.pixel(current.left() + 2, current.center().y()))
    plain = QColor(image.pixel(other.left() + 2, other.center().y()))
    assert frame != plain and frame.blue() > 150


def test_only_the_tiles_in_view_are_decoded(qtbot, grid, session):
    in_view = grid.visible_keys(partial=True)
    assert 0 < len(in_view) < len(session.queue)
    paths = {item.key: item.entry.path for item in session.queue.items}
    qtbot.waitUntil(lambda: all(session.thumbs.get(paths[k]) is not None
                                or session.thumbs.error(paths[k]) for k in in_view))
    assert session.thumbs.get(session.queue.items[-1].entry.path) is None
    grid.view.scrollToBottom()
    qtbot.waitUntil(lambda: session.thumbs.get(session.queue.items[-1].entry.path) is not None)


def test_mark_page_marks_exactly_the_tiles_fully_in_view(qtbot, grid, session):
    whole, partly = grid.visible_keys(), grid.visible_keys(partial=True)
    assert len(whole) == 2 and len(partly) == 4             # one row whole, one cut by the edge
    grid.mark_page()
    assert session.workspace.review.keys() == frozenset(whole)
    assert grid.title.text() == "Queue · 15"


def test_mark_page_is_offered_only_in_the_grid(qtbot, grid):
    assert grid.mark_button.isVisible() and grid.mark_button.width() > 0
    grid.set_grid(False)
    assert not grid.mark_button.isVisible() and not grid.grid
    grid.mark_page()                                        # the list has no page to mark
    assert len(grid._session.workspace.review.keys()) == 0


def test_the_list_comes_back_as_it_was(qtbot, grid, session):
    session.move(4)
    grid.set_grid(False)
    assert grid.view.currentIndex().row() == 4 and grid.columns() == 1
    rect = tile(grid, 4)
    assert rect.width() > 300 and rect.height() < 40            # a list row again
    assert grid.view.viewport().rect().contains(rect.center())
```

Append to `tests/ui/test_session.py`:

```python
def test_marking_many_marks_each_once_and_says_how_many(session):
    said = record(session.status)
    keys = [item.key for item in session.queue.items[:3]]
    session.toggle_reviewed()                               # the first is reviewed already
    assert session.mark_reviewed(keys) == 2
    assert session.workspace.review.keys() == frozenset(keys)
    assert said[-1] == ("marked 2 images reviewed",)
    assert session.mark_reviewed(keys) == 0 and said[-1] == ("these were all reviewed already",)
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_grid.py`
Expected: `ImportError: cannot import name 'tile_text' from 'deeplabeling.ui.queue_panel'`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_session.py -k marking_many`
Expected: 1 failed, 33 deselected. It fails on `AttributeError: 'Session' object has no attribute 'mark_reviewed'`.

- [ ] **Step 3: Mark many at once**

In `src/deeplabeling/ui/session.py`, replace:

```python
    def _review_changed(self, keys: list[str]) -> None:
```

with:

```python
    def mark_reviewed(self, keys) -> int:
        """Mark these images reviewed (the grid's mark page); how many were not already."""
        ws = self.workspace
        if ws is None:
            return 0
        newly = [key for key in keys if ws.review.mark(key)]
        if newly:
            self._review_changed(newly)
            self.status.emit(f"marked {len(newly)} image{'' if len(newly) == 1 else 's'} reviewed")
        else:
            self.status.emit("these were all reviewed already")
        return len(newly)

    def _review_changed(self, keys: list[str]) -> None:
```

- [ ] **Step 4: Write the grid**

Replace `src/deeplabeling/ui/queue_panel.py` with:

```python
"""The queue panel (docs/design/2026-10-04-app-foundation.md#window): the queue as a
virtualised list, or as a grid of thumbnails with their label boxes drawn on them. One
view shows both, so there is one selection, and it mirrors the session's cursor -- there
is no second notion of the current item."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.queue import QueueItem
from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .images import THUMB_PX
from .session import Session

TILE = QSize(176, 150)                      #: one grid cell
THUMB_AREA = QRect(8, 6, THUMB_PX, 120)     #: where a cell's thumbnail goes, within it
TILE_BG, TILE_TEXT, TILE_CURRENT = "#3a3a3a", "#e0e0e0", "#4a90d9"
WANT_MS = 30                                #: thumbnails are wanted this long after a scroll


def tile_thumb_rect(cell: QRect, thumb: QSize) -> QRect:
    """Where a thumbnail of size `thumb` is drawn in a grid cell: fitted to the
    thumbnail area, its aspect kept, centred."""
    area = THUMB_AREA.translated(cell.topLeft())
    rect = QRect(QPoint(0, 0), thumb.scaled(area.size(), Qt.KeepAspectRatio))
    rect.moveCenter(area.center())
    return rect


def tile_text(session: Session, item: QueueItem) -> str:
    """A tile's caption: the reviewed tick, the file name and the badge."""
    tick = "✓ " if session.workspace.review.is_marked(item.key) else ""
    return f"{tick}{Path(item.key).name} · {session.badge(item)}"


class QueueModel(QAbstractListModel):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self._rows = 0
        session.queueReset.connect(self._reset)
        session.closed.connect(self._reset)
        session.queueGrew.connect(self._grew)
        session.itemsChanged.connect(self._changed)
        self._reset()                               # a queue may already be built

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self._rows

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        queue = self._session.queue
        if not index.isValid() or queue is None or index.row() >= len(queue):
            return None
        item = queue.items[index.row()]
        if role == Qt.DisplayRole:
            return self._session.describe_item(item)
        if role == Qt.ToolTipRole:
            return str(item.entry.path)
        if role == Qt.UserRole:
            return item.key
        return None

    def _reset(self) -> None:
        self.beginResetModel()
        queue = self._session.queue
        self._rows = len(queue) if queue is not None else 0
        self.endResetModel()

    def _grew(self) -> None:
        n = len(self._session.queue)
        if n > self._rows:
            self.beginInsertRows(QModelIndex(), self._rows, n - 1)
            self._rows = n
            self.endInsertRows()

    def _changed(self, keys) -> None:
        queue = self._session.queue
        if queue is None:
            return
        for key in keys:
            row = queue.index_of(key)
            if row is not None and row < self._rows:
                index = self.index(row)
                self.dataChanged.emit(index, index)


class TileDelegate(QStyledItemDelegate):
    """Paints one grid tile: the thumbnail, its label boxes in their class colours, and
    the caption. Labels are read as the tile is painted, so it never shows old boxes."""

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session

    def sizeHint(self, option, index) -> QSize:
        return TILE

    def paint(self, painter, option, index) -> None:
        session = self._session
        queue = session.queue
        if queue is None or session.workspace is None or index.row() >= len(queue):
            return
        item, cell = queue.items[index.row()], option.rect
        painter.save()
        painter.fillRect(cell.adjusted(2, 2, -2, -2), QColor(TILE_BG))
        if option.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor(TILE_CURRENT), 3))
            painter.drawRect(cell.adjusted(3, 3, -4, -4))
        painter.setPen(QColor(TILE_TEXT))
        thumb = session.thumbs.get(item.entry.path)
        if thumb is None:
            why = session.thumbs.error(item.entry.path)
            painter.drawText(THUMB_AREA.translated(cell.topLeft()), Qt.AlignCenter,
                             "cannot decode" if why else "…")
        else:
            target = tile_thumb_rect(cell, thumb.size())
            painter.drawImage(target, thumb)
            self._draw_boxes(painter, item, target)
        caption = QRect(cell.x() + 8, cell.y() + THUMB_AREA.bottom() + 4, cell.width() - 16,
                        cell.height() - THUMB_AREA.bottom() - 8)
        painter.setPen(QColor(TILE_TEXT))
        painter.drawText(caption, Qt.AlignLeft | Qt.AlignVCenter,
                         option.fontMetrics.elidedText(tile_text(session, item), Qt.ElideMiddle,
                                                       caption.width()))
        painter.restore()

    def _draw_boxes(self, painter, item: QueueItem, target: QRect) -> None:
        session, ws = self._session, self._session.workspace
        labels = session.labels(item.entry)
        highlight = session.queue.source.highlight(labels, ws.dataset)
        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setClipRect(target)             # a box past the image's edge stays in its tile
        for view in box_views(labels, ws.dataset, (target.width(), target.height()),
                              ws.root_settings.get(CLASS_COLORS), highlight):
            pen = QPen(QColor(view.color), 2 if view.highlighted else 1)
            if not view.known:
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            if view.polygon:
                painter.drawPolygon(QPolygonF([QPointF(target.x() + x, target.y() + y)
                                               for x, y in view.polygon]))
            else:
                x1, y1, x2, y2 = view.rect
                painter.drawRect(QRectF(target.x() + x1, target.y() + y1, x2 - x1, y2 - y1))
        painter.restore()


class QueuePanel(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self.grid = False
        self.title = QLabel()
        self.mark_button = QToolButton()
        self.mark_button.setText("Mark page")
        self.mark_button.setToolTip("Mark every tile in view reviewed")
        self.mark_button.setFocusPolicy(Qt.NoFocus)
        self.mark_button.clicked.connect(self.mark_page)
        self.mark_button.hide()
        self.model = QueueModel(session, self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setFocusPolicy(Qt.NoFocus)         # arrows belong to the window's actions
        self._rows = self.view.itemDelegate()
        self._tiles = TileDelegate(session, self.view)
        # The view's current row drives the cursor, however the mouse got there (a drag
        # across rows moves it without a click); following the cursor does not count.
        self._following = False
        self.view.selectionModel().currentChanged.connect(self._picked)
        header = QHBoxLayout()
        header.addWidget(self.title, 1)
        header.addWidget(self.mark_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(header)
        layout.addWidget(self.view, 1)
        for signal in (session.queueReset, session.queueGrew, session.queueDone, session.closed):
            signal.connect(self._retitle)
        # Follow cursor moves only. Following every batch scrolled the view as each one
        # arrived, re-laying out every row so far: 5 s of a 9 s launch on pvn-vehicle.
        session.cursorChanged.connect(self._follow)
        # Thumbnails are decoded only for the tiles in view: wanted a moment after the
        # view moves, and a scroll cancels those that left it.
        self._want = QTimer(self)
        self._want.setSingleShot(True)
        self._want.setInterval(WANT_MS)
        self._want.timeout.connect(self._want_thumbs)
        # A resized grid re-flows into other columns, and the same scroll offset then
        # shows other tiles: once the size settles, the current tile is brought back.
        self._refollow = QTimer(self)
        self._refollow.setSingleShot(True)
        self._refollow.setInterval(0)
        self._refollow.timeout.connect(self._relayout)
        self.view.verticalScrollBar().valueChanged.connect(self._want_soon)
        session.queueReset.connect(self._want_soon)
        session.queueGrew.connect(self._want_soon)
        session.thumbs.ready.connect(self._thumb_arrived)
        session.thumbs.failed.connect(self._thumb_arrived)
        self._retitle()
        self._follow()

    # -- list or grid -------------------------------------------------------------------

    def set_grid(self, on: bool) -> None:
        """Show the queue as a grid of thumbnails, or as a list. One view does both."""
        self.grid = on
        view = self.view
        view.setFlow(QListView.LeftToRight if on else QListView.TopToBottom)
        view.setWrapping(on)
        view.setResizeMode(QListView.Adjust if on else QListView.Fixed)
        view.setGridSize(TILE if on else QSize())
        view.setItemDelegate(self._tiles if on else self._rows)
        self.mark_button.setVisible(on)
        self._relayout()
        self._want_soon()

    def _relayout(self) -> None:
        # Lay the view out now: scrolling to the cursor before then would scroll by the
        # old geometry, leaving the current item out of sight.
        self.view.doItemsLayout()
        self._follow()

    def columns(self) -> int:
        """Tiles per grid row; 1 in the list."""
        if not self.grid:
            return 1
        return max(1, self.view.viewport().width() // TILE.width())

    def _visible_rows(self, partial: bool) -> list[int]:
        area = self.view.viewport().rect()
        first = self.view.indexAt(QPoint(1, 1))
        rows = []
        for row in range(first.row() if first.isValid() else 0, self.model.rowCount()):
            rect = self.view.visualRect(self.model.index(row))
            if rect.top() > area.bottom():
                break                               # rows run in reading order
            if area.intersects(rect) if partial else area.contains(rect):
                rows.append(row)
        return rows

    def visible_keys(self, partial: bool = False) -> list[str]:
        """The items wholly in view, or (partial) at least partly in view."""
        queue = self._session.queue
        if queue is None:
            return []
        return [queue.items[row].key for row in self._visible_rows(partial) if row < len(queue)]

    def mark_page(self) -> None:
        """Mark every tile wholly in view reviewed: what was seen, nothing more."""
        if self.grid and self._session.workspace is not None:
            self._session.mark_reviewed(self.visible_keys())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.grid:
            self._refollow.start()
        self._want_soon()

    def _want_soon(self, *_) -> None:
        if self.grid:
            self._want.start()

    def _want_thumbs(self) -> None:
        queue = self._session.queue
        if self.grid and queue is not None:
            self._session.thumbs.want([queue.items[row].entry.path
                                       for row in self._visible_rows(partial=True) if row < len(queue)])

    def _thumb_arrived(self, *_) -> None:
        if self.grid:
            self.view.viewport().update()

    # -- the title and the cursor ----------------------------------------------------------

    def _retitle(self) -> None:
        queue = self._session.queue
        if queue is None:
            self.title.setText("Queue")
        else:
            self.title.setText(f"Queue · {len(queue):,}{self._session.progress_text()}")

    def _follow(self) -> None:
        queue = self._session.queue
        row = queue.position() if queue is not None else None
        if row is None or row >= self.model.rowCount():
            self.view.clearSelection()
            return
        self._following = True
        try:
            index = self.model.index(row)
            if self.view.currentIndex() == index:
                self.view.scrollTo(index)           # a new layout: the same item, elsewhere
            else:
                self.view.setCurrentIndex(index)    # which also scrolls to it
        finally:
            self._following = False

    def _picked(self, current, previous) -> None:
        if self._following or not current.isValid():
            return
        key = current.data(Qt.UserRole)
        item = self._session.current()
        if item is None or item.key != key:
            self._session.go_to(key)
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_grid.py tests/ui/test_session.py tests/ui/test_panels.py`
Expected: 59 passed.

- [ ] **Step 6: Look at it**

Run, from the repository root:

```bash
SHOT=$(mktemp -d) && QT_QPA_PLATFORM=offscreen DEEPLABELING_STATE_DIR=$SHOT/state PYTHONPATH=src:tests:tests/ui /home/sonnn/miniconda3/bin/python3 - "$SHOT" <<'EOF'
import sys, time
from pathlib import Path
from PySide6.QtWidgets import QApplication
app = QApplication([])
from deeplabeling.ui.queue_panel import QueuePanel
from deeplabeling.ui.session import Session
from fixtures import FakePrompter, build_dataset
shot = Path(sys.argv[1])
ds = build_dataset(shot / "ds")
s = Session(FakePrompter()); s.open(ds.yaml)
for _ in range(300):
    app.processEvents(); time.sleep(0.01)
    if s.queue is not None and s.queue.complete:
        break
panel = QueuePanel(s); panel.set_grid(True); panel.resize(560, 640); panel.show()
s.move(1); s.toggle_reviewed()
for _ in range(100):
    app.processEvents(); time.sleep(0.01)
panel.grab().save(str(shot / "grid.png"))
print(shot / "grid.png")
s.close()
EOF
```

Open the printed PNG. Expected:
- three columns of tiles, each with its thumbnail, its label boxes drawn thin in their class colours, and a caption such as `0001.jpg · 2 boxes`;
- the second tile framed in blue and captioned `✓ 0002.jpg · negative`;
- `rot.jpg` shown upright as a portrait;
- `corrupt.jpg` reading "cannot decode";
- no box drawn outside its tile;
- a "Mark page" button beside the title.

- [ ] **Step 7: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 526 passed.

```bash
git add src/deeplabeling/ui tests/ui
git commit -m "ui: the queue as a grid of thumbnails with their boxes; mark page marks the tiles in view" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `G`, the panel's widths, and `↑` `↓` by row

**Files:**
- Modify: `src/deeplabeling/ui/main_window.py`, `src/deeplabeling/ui/keymap.py`, `src/deeplabeling/ui/settings_ui.py`, `src/deeplabeling/ui/queue_panel.py`
- Test: `tests/ui/test_grid.py`, `tests/ui/test_keymap.py`

**Interfaces:**
- Consumes: Task 3's `QueuePanel.set_grid`, `.columns()`, `.mark_page()` and `.grid`; `bind_toggle` (plan 1b); `QMainWindow.resizeDocks`.
- Produces in `deeplabeling.ui.settings_ui`, all global:
  - `SHOW_GRID`, default False;
  - `QUEUE_LIST_WIDTH`, default 280;
  - `QUEUE_GRID_WIDTH`, default 560;
  - widths are positive ints.
- Produces in `deeplabeling.ui.keymap`:
  - `next` (`Right`) and `previous` (`Left`), which lose `Down` and `Up`;
  - new `down` (`Down`) and `up` (`Up`), which move by `QueuePanel.columns()`;
  - `toggle_grid` (`G`), checkable;
  - `mark_page`, with no key, enabled only in the grid.
- Produces in `QueuePanel`: `.grid_button`, which the window gives the `toggle_grid` action.
- Produces in `MainWindow`: `._grid_changed(on)`, `._show_grid(on)` and `._remember_queue_width(grid)`. The current view's width is written when the view changes and at close.

- [ ] **Step 1: Write the failing tests**

In `tests/ui/test_grid.py`, replace:

```python
from deeplabeling.ui.queue_panel import QueuePanel, tile_text, tile_thumb_rect
```

with:

```python
from deeplabeling.ui.queue_panel import QueuePanel, tile_text, tile_thumb_rect
from deeplabeling.ui.settings_ui import QUEUE_GRID_WIDTH, SHOW_GRID
from drive import start
```

Append to `tests/ui/test_grid.py`:

```python
# -- in the window ------------------------------------------------------------------------


@pytest.fixture
def window(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)])
    yield w
    w.close()


def near(width, want, slack=6):
    return abs(width - want) <= slack


def test_g_shows_the_grid_at_its_width_and_the_list_at_its_own(qtbot, window):
    dock, panel = window.queue_dock, window.queue_panel
    qtbot.waitUntil(lambda: near(dock.width(), 280))
    qtbot.keyClick(window, Qt.Key_G)
    assert panel.grid and panel.mark_button.isVisible() and window.actions["mark_page"].isEnabled()
    qtbot.waitUntil(lambda: near(dock.width(), 560))
    assert window.session.settings.get(SHOW_GRID) is True
    qtbot.keyClick(window, Qt.Key_G)
    assert not panel.grid and not panel.mark_button.isVisible()
    assert not window.actions["mark_page"].isEnabled()
    qtbot.waitUntil(lambda: near(dock.width(), 280))


def test_the_grid_and_its_width_survive_a_relaunch(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_G)
    window.resizeDocks([window.queue_dock], [720], Qt.Horizontal)
    qtbot.waitUntil(lambda: near(window.queue_dock.width(), 720))
    window.close()
    assert window.session.settings.get(QUEUE_GRID_WIDTH) == window.queue_dock.width()
    again = start(qtbot, [str(ds.yaml)])
    assert again.queue_panel.grid and again.actions["toggle_grid"].isChecked()
    qtbot.waitUntil(lambda: near(again.queue_dock.width(), 720))
    qtbot.keyClick(again, Qt.Key_G)                         # the list has kept its own width
    qtbot.waitUntil(lambda: near(again.queue_dock.width(), 280))
    again.close()


def test_down_and_up_move_by_a_row_in_the_grid_and_by_one_in_the_list(qtbot, window):
    queue = window.session.queue
    qtbot.keyClick(window, Qt.Key_Down)
    assert queue.position() == 1
    qtbot.keyClick(window, Qt.Key_G)
    qtbot.waitUntil(lambda: window.queue_panel.columns() == 3)
    qtbot.keyClick(window, Qt.Key_Down)
    assert queue.position() == 4
    qtbot.keyClick(window, Qt.Key_Right)
    assert queue.position() == 5
    qtbot.keyClick(window, Qt.Key_Up)
    assert queue.position() == 2
    qtbot.keyClick(window, Qt.Key_Up)                       # no row above: it stays put
    assert queue.position() == 2


def test_the_mark_page_button_marks_the_tiles_in_view(qtbot, window):
    qtbot.keyClick(window, Qt.Key_G)
    qtbot.waitUntil(lambda: near(window.queue_dock.width(), 560))
    in_view = window.queue_panel.visible_keys()
    assert in_view
    qtbot.mouseClick(window.queue_panel.mark_button, Qt.LeftButton)
    assert window.session.workspace.review.keys() == frozenset(in_view)
    assert window.state_bar.reviewed.full_text == f"Reviewed {len(in_view)} / 15"


def test_the_grid_button_in_the_panel_is_the_g_toggle(qtbot, window):
    button = window.queue_panel.grid_button
    assert button.isVisible() and not button.isChecked()
    qtbot.mouseClick(button, Qt.LeftButton)
    assert window.queue_panel.grid and button.isChecked() and window.actions["toggle_grid"].isChecked()
```

In `tests/ui/test_keymap.py`, replace:

```python
    assert dialog.table.item(2, 1).text().startswith("Done & next")
```

with:

```python
    assert dialog.table.item(4, 1).text().startswith("Done & next")
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_grid.py`
Expected: `ImportError: cannot import name 'QUEUE_GRID_WIDTH' from 'deeplabeling.ui.settings_ui'`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_keymap.py`
Expected: 1 failed, 3 passed: the help's fifth row is still "Mark negative".

- [ ] **Step 3: The settings, the keys and the panel's grid button**

In `src/deeplabeling/ui/settings_ui.py`, replace:

```python
def _is_source(v) -> bool:
```

with:

```python
def _is_width(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _is_source(v) -> bool:
```

In `src/deeplabeling/ui/settings_ui.py`, replace:

```python
SHOW_CROSSHAIR = define("view.crosshair", "global", False, lambda v: isinstance(v, bool))
```

with:

```python
SHOW_CROSSHAIR = define("view.crosshair", "global", False, lambda v: isinstance(v, bool))
SHOW_GRID = define("view.queue_grid", "global", False, lambda v: isinstance(v, bool))
#: The queue panel's width in each view: the grid widens it, the list takes its own back.
QUEUE_LIST_WIDTH = define("window.queue_list_width", "global", 280, _is_width)
QUEUE_GRID_WIDTH = define("window.queue_grid_width", "global", 560, _is_width)
```

In `src/deeplabeling/ui/keymap.py`, replace:

```python
    ActionSpec("next", "Next item", ("Right", "Down")),
    ActionSpec("previous", "Previous item", ("Left", "Up")),
```

with:

```python
    ActionSpec("next", "Next item", ("Right",)),
    ActionSpec("previous", "Previous item", ("Left",)),
    ActionSpec("down", "Next item; in the grid, the item below", ("Down",)),
    ActionSpec("up", "Previous item; in the grid, the item above", ("Up",)),
```

In `src/deeplabeling/ui/keymap.py`, replace:

```python
    ActionSpec("toggle_crosshair", "Crosshair", (), checkable=True),
```

with:

```python
    ActionSpec("toggle_crosshair", "Crosshair", (), checkable=True),
    ActionSpec("toggle_grid", "Grid", ("G",), checkable=True),
    ActionSpec("mark_page", "Mark page: mark every tile in view reviewed (in the grid)", ()),
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
        self.mark_button.hide()
```

with:

```python
        self.mark_button.hide()
        self.grid_button = QToolButton()           # the window gives it the G action
        self.grid_button.setFocusPolicy(Qt.NoFocus)
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
        header.addWidget(self.mark_button)
```

with:

```python
        header.addWidget(self.mark_button)
        header.addWidget(self.grid_button)
```

- [ ] **Step 4: The window: `G`, the widths, and the row keys**

In `src/deeplabeling/ui/main_window.py`, replace:

```python
from .settings_ui import (RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_LABELS, WINDOW_GEOMETRY, WINDOW_STATE,
                          bind_toggle)
```

with:

```python
from .settings_ui import (QUEUE_GRID_WIDTH, QUEUE_LIST_WIDTH, RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_GRID,
                          SHOW_LABELS, WINDOW_GEOMETRY, WINDOW_STATE, bind_toggle)
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
            "next": lambda: session.move(1),
            "previous": lambda: session.move(-1),
```

with:

```python
            "next": lambda: session.move(1),
            "previous": lambda: session.move(-1),
            "down": lambda: session.move(self.queue_panel.columns()),
            "up": lambda: session.move(-self.queue_panel.columns()),
            "mark_page": self.queue_panel.mark_page,
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        self.panels_menu = layers.addMenu("Panels")     # a closed dock comes back from here
```

with:

```python
        bind_toggle(self.actions["toggle_grid"], session.settings, SHOW_GRID, self._grid_changed)
        self.queue_panel.grid_button.setDefaultAction(self.actions["toggle_grid"])
        self.panels_menu = layers.addMenu("Panels")     # a closed dock comes back from here
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        self._restore_layout()
        self.show_current()
```

with:

```python
        self._restore_layout()
        self._show_grid(self.actions["toggle_grid"].isChecked())
        self.show_current()
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
    def _update_status(self) -> None:
```

with:

```python
    def _grid_changed(self, on: bool) -> None:
        """G: keep the width the panel had for the view it leaves, then show the other
        view at its own width."""
        self._remember_queue_width(not on)
        self._show_grid(on)
        self.session.saver.schedule()

    def _show_grid(self, on: bool) -> None:
        self.queue_panel.set_grid(on)
        self.actions["mark_page"].setEnabled(on)
        width = self.session.settings.get(QUEUE_GRID_WIDTH if on else QUEUE_LIST_WIDTH)
        self.resizeDocks([self.queue_dock], [width], Qt.Horizontal)

    def _remember_queue_width(self, grid: bool) -> None:
        if self.queue_dock.isVisible() and not self.queue_dock.isFloating():
            self.session.settings.set(QUEUE_GRID_WIDTH if grid else QUEUE_LIST_WIDTH, self.queue_dock.width())

    def _update_status(self) -> None:
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
    def closeEvent(self, event) -> None:
        settings = self.session.settings
```

with:

```python
    def closeEvent(self, event) -> None:
        settings = self.session.settings
        self._remember_queue_width(self.queue_panel.grid)
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_grid.py tests/ui/test_keymap.py tests/ui/test_main_window.py`
Expected: 43 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 531 passed.

```bash
git add src/deeplabeling/ui tests/ui
git commit -m "ui: G switches the queue to the grid at its own width; up and down move by a row" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Measure the grid on pvn-vehicle, and the docs

**Files:**
- Modify:
  - `tools/measure_ui.py`;
  - `docs/design/2026-10-04-app-foundation.md` (the status line, the queue panel paragraph and the performance table);
  - `CLAUDE.md` (the status line);
  - `.claude/skills/run-and-verify-ui/SKILL.md` (the lessons).

**Interfaces:**
- Consumes: `launch`, `MainWindow.actions["toggle_grid"]`, `QueuePanel.visible_keys` and `Session.thumbs`.
- Produces: two more lines from the read-only `tools/measure_ui.py DATA.yaml --class NAME`.

- [ ] **Step 1: Measure the grid**

In `tools/measure_ui.py`, replace:

```python
    _, first_pass = build(ImageFilter(conditions=(HasClass((args.cls,)),)))
```

with:

```python
    def page_shown() -> bool:
        """Every tile at least partly in view has its thumbnail, or its error."""
        paths = [s.queue.items[s.queue.index_of(key)].entry.path
                 for key in window.queue_panel.visible_keys(partial=True)]
        return bool(paths) and all(s.thumbs.get(p) is not None or s.thumbs.error(p) for p in paths)

    t0 = time.perf_counter()
    window.actions["toggle_grid"].trigger()
    rows.append(("the grid: the first page of thumbnails", time.perf_counter() - t0 + wait(app, page_shown),
                 "≤ 1 s"))
    far = s.queue.items[len(s.queue) // 2].key
    t0 = time.perf_counter()
    s.go_to(far)
    rows.append(("the grid: a page after a jump", time.perf_counter() - t0
                 + wait(app, lambda: far in window.queue_panel.visible_keys() and page_shown()), "≤ 1 s"))
    window.actions["toggle_grid"].trigger()                     # the builds below, as before

    _, first_pass = build(ImageFilter(conditions=(HasClass((args.cls,)),)))
```

- [ ] **Step 2: Measure on the real dataset (read-only)**

Run: `/home/sonnn/miniconda3/bin/python3 tools/measure_ui.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml --class bus_l`

Expected: ten lines, each within its target. The two new ones, measured on 2026-10-05 while this plan was built, were:

| Line | Measured |
|---|---|
| the grid: the first page of thumbnails | 237 ms |
| the grid: a page after a jump | 65 ms |

A line over its target is a finding: profile it (`cProfile` around the action) and fix it, or record it in the spec with its measured value. It is never dropped. Afterwards, `ls ~/.cache | grep measure-ui` must print nothing.

- [ ] **Step 3: Update the spec, the status line and the UI skill**

In `docs/design/2026-10-04-app-foundation.md`, replace:

```markdown
**Status:** approved 2026-10-04 · slices 1a (the core), 1b (the viewer) and 1c (editing) implemented; the amendments found while building them are folded in; 1d (the queue grid) next
```

with:

```markdown
**Status:** approved 2026-10-04 · slice 1 implemented: 1a (the core), 1b (the viewer), 1c (editing) and 1d (the queue grid); the amendments found while building them are folded in; slice 2 (model assist) next
```

In `docs/design/2026-10-04-app-foundation.md`, replace:

```markdown
to a grid of thumbnails with their label boxes drawn on them, and widens the panel to the
last grid width. In the grid, **mark page** marks every visible tile. Thumbnails decode at
display size on workers, only for visible rows, into a cache bounded in bytes (64 MB).
```

with:

```markdown
to a grid of thumbnails with their label boxes drawn on them, and widens the panel to the
last grid width; the list keeps its own width, and the view and both widths persist. In the
grid, **mark page** (a button on the panel) marks every tile wholly in view: what was seen,
nothing more. Thumbnails decode at display size on workers, only for visible rows, into a
cache bounded in bytes (64 MB).
```

The new performance row takes **today's measured values** in its third column; the ones shown below are from 2026-10-05.

In `docs/design/2026-10-04-app-foundation.md`, replace:

```markdown
| a class condition over 45k label files, cold / warm cache | ≤ 30 s / ≤ 5 s, streaming | 4.4 s / 0.69 s |
```

with:

```markdown
| a class condition over 45k label files, cold / warm cache | ≤ 30 s / ≤ 5 s, streaming | 4.4 s / 0.69 s |
| the grid: the first page of thumbnails / a page after a jump | ≤ 1 s / ≤ 1 s | 237 ms / 65 ms (2026-10-05) |
```

In `CLAUDE.md`, replace:

```markdown
**Status:** slice 1's core, its viewer UI and editing on the canvas are built; the queue
grid (plan 1d) is next. The design and the plans are in [docs/design/](docs/design/).
```

with:

```markdown
**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 (model assist) is next. The design and the plans are in
[docs/design/](docs/design/).
```

Append to `.claude/skills/run-and-verify-ui/SKILL.md`:

```markdown
Lessons from building the grid (plan 1d):

- **A 15-item fixture hides what 45k items show.** Switching to the grid with the cursor
  mid-queue left it a million pixels out of view, and finding the tiles in view cost 60 ms
  a call during the switch; neither showed in the fixture. Run a UI change on the real
  dataset (`tools/measure_ui.py`, read-only) before calling it done.
- **A list view scrolls by the layout it has.** After changing its flow or grid size, call
  `doItemsLayout()` before `scrollTo()`; and `setCurrentIndex` to the current index
  scrolls nowhere, so scroll explicitly.
- **A painter clip outlives the drawing it was for.** Wrap a clipped part of a delegate's
  paint in `save()`/`restore()`, or everything painted after it is clipped too.
```

- [ ] **Step 4: Check the docs and run everything**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 531 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/measure_ui.py docs CLAUDE.md .claude/skills/run-and-verify-ui/SKILL.md
git commit -m "ui: measure the grid on pvn-vehicle; docs: slice 1 is built" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short
```

Expected: `git status --short` prints nothing.
