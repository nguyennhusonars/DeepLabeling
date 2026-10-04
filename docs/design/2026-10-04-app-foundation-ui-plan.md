# Slice 1b: the viewer UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Qt window for slice 1 on top of the merged core. It opens a dataset by every launch path and shows layout A: the state bar, the queue, the canvas, the inspector and the notice strip. It pages through a queue, marks images reviewed or negative, undoes and redoes, persists every setting, and meets the spec's performance targets.

**Architecture:** One `Session` (a `QObject` on the GUI thread) owns the open `Workspace`, the current `Queue`, the worker pools, the image cache and the debounced saver. Every widget reads from the session and calls its methods; no widget touches the store, the editor or a file. Dialogs go through a prompter, so tests answer them with `FakePrompter`. Workers are `QRunnable`s that report by queued signal and never touch a widget. Canvas editing (draw, select, move, reclassify) is plan 1c.

**Tech Stack:** PySide6 6.6 (conda base), pytest-qt (offscreen), and the core from plan 1a.

**Spec:** [2026-10-04-app-foundation.md](2026-10-04-app-foundation.md). This plan implements its Window section, except editing and the grid; its State and settings section (the launch paths and settings binding); its Errors rows that reach the UI; its Testing section's UI items; its Performance targets; and its "Notes for plan 1b". The core plan is [2026-10-04-app-foundation-core-plan.md](2026-10-04-app-foundation-core-plan.md).

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base, PySide6 6.6.0). Bare `python3` can be another conda env ([environment.md](../knowledge/environment.md#python)). Install nothing.
- **Threads** ([landmine 3](../../CLAUDE.md#landmines)): the `Session` is created, and opens datasets, on the GUI thread, which therefore owns the `LabelStore` write path. Workers get immutable inputs, report by queued signal, never write a file and never touch a widget. The GUI thread never waits on a worker, except in `Session.close`, which waits at most 2 s for cancelled jobs.
- **One owner** ([landmine 2](../../CLAUDE.md#landmines)): widgets never keep labels. They read them through `Session.labels` when they draw and redraw on `labelsChanged`. Every label change goes through `Session.apply`, `mark_negative`, `undo` or `redo`.
- **Verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines); the `run-and-verify-ui` skill): UI tests assert geometry, visibility and pixels read back from `grab()`, not widget state alone.
- **`src/deeplabeling/core/` stays Qt-free.** The one core change, `Queue.index_of`, is pure Python.
- **Tests write only to temporary folders** (landmine 10); the autouse `state_dir` fixture already guards the real `.deeplabeling/`. The measurement tool reads the real dataset only, with app state in a temporary folder.
- **Doc rules:** one fact, one home; a command over a restatement; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice1-ui` from `main`. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit. The `-o addopts=` is there because the project's `-q` plus another `-q` hides the summary line.
- **pytest-qt habits:** `qtbot.waitUntil` takes a callback returning a bool. Window shortcuts need `with qtbot.waitActive(w): w.show(); w.activateWindow()`. Keep a test widget's parent alive for the whole test.

## Review Focus

These are the inputs the spec implies that are most likely to hurt someone using the app. Each has a named test in the task that owns the code:

1. **A queue rebuilt while the previous build still runs.** The old build's late batches must never land in the new queue. *(Task 3 `test_a_superseded_build_never_feeds_the_new_queue`.)*
2. **The label file of the image on screen is changed outside the app.** The change must appear without a click: the spec's "an edit made outside the app appears on screen". *(Task 3 `test_an_outside_edit_to_the_image_on_screen_is_noticed_unasked`; Task 7 `test_an_outside_edit_appears_on_the_canvas`.)*
3. **Holding the arrow key.** Decodes of skipped images finish late; the canvas must end on the current image, never a late one. *(Task 7 `test_rapid_paging_ends_on_the_current_image`.)*
4. **Closing the window while the queue build and the id count still run.** The window must close cleanly and the root's lock must be freed. *(Task 7 `test_closing_while_jobs_run_frees_the_root`.)*
5. **An image whose label file another image shares.** It must say "read-only" wherever it is shown, and every edit to it must be refused. *(Task 3 `test_badges`; Task 5 `test_the_inspector_says_a_shared_label_file_is_read_only`; the core's store tests refuse the edit.)*

## Found while building this plan

The plan's code was built and run in a scratch copy before it was written down: 419 tests pass, and every performance target is met on pvn-vehicle. Along the way:

- **`QImageReader.size()` is the stored, unrotated size;** only the decoded image has the displayed one. The UI takes every size from the decoded image.
- **The first launch on pvn-vehicle took 7.4 s.** The queue list scrolled to the cursor on every batch of a building queue, re-laying out every row so far (5.2 s of it). The state bar also recounted the whole queue per batch (about 1 s). Fixed in Tasks 5 and 6, each pinned by a test. Launch now takes 1.1 s.
- **A field named `size` on a widget shadows `QWidget.size()`,** and broke every caller that measured the inspector. Its fields are `*_label`.
- **The store only notices an outside edit when the file is next read,** so the session re-reads the current image's label file every 1.5 s (`WATCH_MS`). That costs one `stat`, unless the file changed.
- **`/tmp` is tmpfs on this machine,** so edit timings there are meaningless. The measurement writes its timed edits under `~/.cache`.

## Left for plan 1c

These spec items are not in this plan. Each is either editing, or part of the canvas that only editing needs:

- **Editing with the mouse:** drawing, click-to-select and cycling, Shift+click, moving, resizing and handles.
- **Editing keys:** `1`–`0` reclassify, the `C` class picker, `Del`, `Tab`, `Ctrl+A`, `Esc`, and `Ctrl+C` / `Ctrl+V`.
- **The inspector acting:** the class palette and the box list act on the selection.
- **The grid** (`G`), mark page, and crop tiles.
- **The crosshair layer.**

One simplification in this plan: the status line shows when the last edit was written as a clock time (`written 17:20:31`), not the spec's `written 0.2 s ago`, which would need a ticking timer.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/ui/__init__.py`, `classes.py`, `boxes.py` | class colours and hotkeys; what the canvas draws, computed without Qt | 1 |
| `src/deeplabeling/ui/workers.py`, `images.py`, `settings_ui.py` | jobs on pool threads; the decoded-image cache; global settings, the saver, binding | 2 |
| `src/deeplabeling/core/queue.py` (one method), `src/deeplabeling/ui/session.py`, `tests/fixtures.py` (append), `tests/ui/conftest.py` | the GUI thread's hold on one dataset; the fake prompter | 3 |
| `src/deeplabeling/ui/canvas.py` | the frame, boxes, captions, zoom and pan | 4 |
| `src/deeplabeling/ui/notices.py`, `queue_panel.py`, `inspector.py` | the notice strip; the queue list; the inspector | 5 |
| `src/deeplabeling/ui/state_bar.py`, `queue_editor.py`, `keymap.py` | the chips; the queue dialog; the action registry and help | 6 |
| `src/deeplabeling/ui/prompter.py`, `main_window.py`, `src/deeplabeling/__main__.py`, `tests/test_smoke.py`, the init plan's one citation | the real dialogs; layout A; every launch path | 7 |
| `tools/measure_ui.py`, the spec's performance table, `CLAUDE.md`, `environment.md`, the `run-and-verify-ui` skill | the measurement and the docs | 8 |

UI tests live in `tests/ui/`. Their basenames are unique across `tests/`, and they import shared helpers as `from fixtures import …`.

---

### Task 1: Class colours and what the canvas draws

**Files:**
- Create: `src/deeplabeling/ui/__init__.py`, `src/deeplabeling/ui/classes.py`, `src/deeplabeling/ui/boxes.py`
- Test: `tests/ui/test_boxes.py`

**Interfaces:**
- Consumes: from the core, `Dataset` (with `names`, `known`), `ImageLabels` (with `boxes`), `norm_to_px`, and `stack_counts` with `DUPLICATES`.
- Produces in `deeplabeling.ui.classes`:
  - `PALETTE`, `UNKNOWN = "#9e9e9e"` and `DEFAULT_HOTKEYS = "1234567890"`;
  - `ClassInfo(cls_id, name, color, hotkey)`;
  - `class_color(cls_id, name, overrides) -> str`;
  - `class_infos(dataset, colors, hotkeys) -> list[ClassInfo]`;
  - `text_color(background) -> str`.
- Produces in `deeplabeling.ui.boxes`:
  - `BoxView(index, rect, polygon, color, caption, known, highlighted)`;
  - `box_views(labels, dataset, size, colors, highlight=frozenset()) -> list[BoxView]`.

- [ ] **Step 1: Branch, and commit this plan**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout main && git pull --ff-only && git checkout -b slice1-ui
git add docs/design/2026-10-04-app-foundation-ui-plan.md
git commit -m "docs: the slice 1b viewer UI plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/ui/test_boxes.py`:

```python
import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.store import LabelStore
from deeplabeling.ui.boxes import box_views
from deeplabeling.ui.classes import PALETTE, UNKNOWN, class_infos, text_color

SIZE = (100, 50)


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


def views(dataset, ds, name, **kw):
    labels = LabelStore(dataset).get(ds.img(name))
    return {v.index: v for v in box_views(labels, dataset, SIZE, kw.pop("colors", {}), **kw)}


def test_captions_name_the_class_and_count_stacked_boxes(dataset, ds):
    v = views(dataset, ds, "bad/ok.jpg")
    assert {i: v[i].caption for i in v} == {
        0: "car x4", 1: "#99? x2", 2: "#-1? x2", 3: "person",
        5: "person x4", 6: "person x4", 10: "person x4"}


def test_an_id_outside_the_names_is_grey_and_unknown(dataset, ds):
    v = views(dataset, ds, "bad/ok.jpg")
    assert not v[1].known and v[1].color == UNKNOWN
    assert v[0].known and v[0].color == PALETTE[1]


def test_boxes_are_in_image_pixels(dataset, ds):
    assert views(dataset, ds, "bad/ok.jpg")[0].rect == pytest.approx((40, 20, 60, 30))


def test_a_polygon_keeps_its_points(dataset, ds):
    v = views(dataset, ds, "seg/poly1.jpg")
    points = [c for point in v[0].polygon for c in point]
    assert points == pytest.approx([10, 5, 20, 5, 20, 10, 10, 10])
    assert v[0].rect == pytest.approx((10, 5, 20, 10))


def test_colour_overrides_and_highlight(dataset, ds):
    v = views(dataset, ds, "bad/ok.jpg", colors={"car": "#123456"}, highlight=frozenset({3}))
    assert v[0].color == "#123456"
    assert v[3].highlighted and not v[0].highlighted


def test_without_names_captions_are_ids(ds):
    folder = Dataset.open(ds.root / "camA/images")
    labels = LabelStore(folder).get(ds.img("camA/0001.jpg"))
    assert [v.caption for v in box_views(labels, folder, SIZE, {})] == ["0", "1"]


def test_class_infos_give_default_and_chosen_hotkeys(dataset):
    infos = class_infos(dataset, {"bus_l": "#000000"}, {"car": "q"})
    assert [(i.name, i.hotkey) for i in infos] == [("person", "1"), ("car", "q"), ("bus_m", "3"), ("bus_l", "4")]
    assert infos[3].color == "#000000"


def test_text_colour_contrasts():
    assert text_color("#000075") == "#ffffff" and text_color("#fffac8") == "#000000"
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_boxes.py`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.ui'`.

- [ ] **Step 4: Write the modules**

Create `src/deeplabeling/ui/__init__.py`:

```python
"""DeepLabeling's Qt user interface, built on deeplabeling.core.

Widgets talk to one Session; they never touch the core's store, editor or files
directly (docs/design/2026-10-04-app-foundation.md#architecture).
"""
```

Create `src/deeplabeling/ui/classes.py`:

```python
"""Class colours and hotkeys, keyed by class name so every yaml of a root shares them
(docs/design/2026-10-04-app-foundation.md#dataset)."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.dataset import Dataset

#: Distinct colours for class ids, in id order; no greys, which mean "unknown class".
PALETTE = (
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6",
    "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324", "#fffac8", "#800000",
    "#aaffc3", "#808000", "#ffd8b1", "#000075", "#ffe119", "#a9a9f5",
)
#: A class id the dataset's names do not cover.
UNKNOWN = "#9e9e9e"
#: Hotkeys of the first ten classes; past the tenth, the class picker (plan 1c).
DEFAULT_HOTKEYS = "1234567890"


@dataclass(frozen=True)
class ClassInfo:
    cls_id: int
    name: str
    color: str
    hotkey: str     #: "" when the class has none


def class_color(cls_id: int, name: str, overrides: dict[str, str]) -> str:
    """The colour of a class: the user's choice for its name, else the palette's."""
    return overrides.get(name) or PALETTE[cls_id % len(PALETTE)]


def class_infos(dataset: Dataset, colors: dict[str, str], hotkeys: dict[str, str]) -> list[ClassInfo]:
    """Every class of the dataset, with the colour and hotkey in force."""
    out = []
    for cls_id, name in enumerate(dataset.names):
        default = DEFAULT_HOTKEYS[cls_id] if cls_id < len(DEFAULT_HOTKEYS) else ""
        out.append(ClassInfo(cls_id, name, class_color(cls_id, name, colors),
                             hotkeys.get(name, default)))
    return out


def text_color(background: str) -> str:
    """Black or white, whichever reads better on `background` (#rrggbb)."""
    r, g, b = (int(background[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#ffffff"
```

Create `src/deeplabeling/ui/boxes.py`:

```python
"""What the canvas draws for an image's labels, computed without Qt so it is tested
headless (docs/design/2026-10-04-app-foundation.md#window)."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.dataset import Dataset
from ..core.geometry import norm_to_px
from ..core.overlap import DUPLICATES, stack_counts
from ..core.store import ImageLabels
from .classes import UNKNOWN, class_color


@dataclass(frozen=True)
class BoxView:
    index: int                                  #: the line's index in the label file
    rect: tuple[float, float, float, float]     #: (x1, y1, x2, y2) in image pixels
    polygon: tuple[tuple[float, float], ...]    #: a polygon's points in pixels; () for a box
    color: str                                  #: #rrggbb
    caption: str                                #: "car", "car x2", "#13?"
    known: bool                                 #: False: an id the names do not cover
    highlighted: bool                           #: a queue condition matched this box


def box_views(labels: ImageLabels, dataset: Dataset, size: tuple[int, int],
              colors: dict[str, str], highlight: frozenset[int] = frozenset()) -> list[BoxView]:
    """One view per parsed line. A box stacked on others captions the count (`car x2`):
    identical rectangles otherwise draw as one. An id outside the names is drawn grey
    and captioned `#id?`, never dropped."""
    w, h = size
    boxes = labels.boxes
    stack = stack_counts([(line.cls_id, line.bbox) for _, line in boxes], *DUPLICATES)
    views = []
    for pos, (index, line) in enumerate(boxes):
        cls_id = line.cls_id
        known = dataset.known(cls_id)
        if not known:
            base, color = f"#{cls_id}?", UNKNOWN
        elif dataset.names:
            base = dataset.names[cls_id]
            color = class_color(cls_id, base, colors)
        else:
            base = str(cls_id)
            color = class_color(cls_id, base, colors)
        caption = f"{base} x{stack[pos]}" if pos in stack else base
        polygon = ()
        if line.is_polygon:
            polygon = tuple((x * w, y * h) for x, y in zip(line.coords[0::2], line.coords[1::2]))
        views.append(BoxView(index, norm_to_px(line.bbox, w, h), polygon, color, caption,
                             known, index in highlight))
    return views
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_boxes.py`
Expected: 8 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: all pass.

```bash
git add src/deeplabeling/ui tests/ui
git commit -m "ui: class colours and the box view model" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Workers, the image cache and global settings

**Files:**
- Create: `src/deeplabeling/ui/workers.py`, `src/deeplabeling/ui/images.py`, `src/deeplabeling/ui/settings_ui.py`
- Test: `tests/ui/test_workers.py`, `tests/ui/test_images.py`, `tests/ui/test_settings_ui.py`

**Interfaces:**
- Consumes: from the core, `JsonFile`, `Settings`, `Setting` and `define` (settings), and `state_dir` (state).
- Produces in `deeplabeling.ui.workers`:
  - `JobFn`, which is `fn(emit, cancelled) -> result`;
  - `JobSignals`, with the signals `batch(object)`, `done(object)`, `failed(str)` and `finished()`;
  - `Job(fn)`, with `.cancel()` and `.cancelled`;
  - `Jobs(threads)`, with `.start(fn, *, batch=None, done=None, failed=None) -> Job`, `.cancel_all()` and `.wait(msecs=-1) -> bool`.
- Produces in `deeplabeling.ui.images`:
  - `decode_image(path) -> QImage`, which raises `ValueError` for an unreadable file;
  - `ImageCache(jobs, limit_bytes=512 * 2**20)`, with the signals `ready(path)` and `failed(path, why)`, and `.get(path)`, `.error(path)`, `.keep(paths)`, `.request(path)`, `.clear()` and `.cached_bytes`.
- Produces in `deeplabeling.ui.settings_ui`:
  - the global settings `LAST_SOURCE`, `RECENT`, `WINDOW_GEOMETRY`, `WINDOW_STATE`, `SHOW_LABELS` and `SHOW_CAPTIONS`, plus `RECENT_MAX = 8`;
  - `global_settings() -> (JsonFile, Settings)` and `remember_source(settings, source, labels)`;
  - `Saver(save, delay_ms=2000)`, with `.schedule()`, `.flush()` and `.pending`;
  - `bind_toggle(action, settings, setting, changed)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_workers.py`:

```python
import threading
import time

from deeplabeling.ui.workers import Jobs


def run(qtbot, jobs, fn, **slots):
    job = jobs.start(fn, **slots)
    with qtbot.waitSignal(job.signals.finished, timeout=5000):
        pass
    return job


def test_a_result_arrives_on_the_gui_thread(qtbot):
    jobs, got = Jobs(1), []
    run(qtbot, jobs, lambda emit, cancelled: threading.get_ident(),
        done=lambda worker: got.append((worker, threading.get_ident())))
    qtbot.waitUntil(lambda: bool(got))
    worker, receiver = got[0]
    assert worker != receiver == threading.get_ident()


def test_batches_arrive_in_order_before_the_result(qtbot):
    jobs, got = Jobs(1), []

    def fn(emit, cancelled):
        for i in range(5):
            emit(i)
        return "end"

    run(qtbot, jobs, fn, batch=got.append, done=got.append)
    qtbot.waitUntil(lambda: len(got) == 6)
    assert got == [0, 1, 2, 3, 4, "end"]


def test_a_job_that_raises_reports_and_does_not_finish_with_a_result(qtbot):
    jobs, done, failed = Jobs(1), [], []

    def fn(emit, cancelled):
        raise OSError("disk gone")

    run(qtbot, jobs, fn, done=done.append, failed=failed.append)
    qtbot.waitUntil(lambda: bool(failed))
    assert done == [] and failed == ["OSError: disk gone"]


def test_a_cancelled_job_reports_nothing_and_is_released(qtbot):
    jobs, done = Jobs(1), []
    started = threading.Event()

    def fn(emit, cancelled):
        started.set()
        while not cancelled():
            time.sleep(0.001)
        return "too late"

    job = jobs.start(fn, done=done.append)
    started.wait(5)
    with qtbot.waitSignal(job.signals.finished, timeout=5000):
        jobs.cancel_all()
    qtbot.wait(20)
    assert done == [] and jobs._live == set()
```

Create `tests/ui/test_images.py`:

```python
import pytest

from deeplabeling.ui.images import ImageCache, decode_image
from deeplabeling.ui.workers import Jobs
from fixtures import make_image


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
```

Create `tests/ui/test_settings_ui.py`:

```python
from PySide6.QtGui import QAction

from deeplabeling.ui.settings_ui import (
    LAST_SOURCE,
    RECENT,
    RECENT_MAX,
    SHOW_LABELS,
    Saver,
    bind_toggle,
    global_settings,
    remember_source,
)


def test_global_settings_live_in_the_state_folder(state_dir):
    file, _ = global_settings()
    assert file.path == state_dir / "settings.json"


def test_remembering_a_source_puts_it_first_once():
    _, settings = global_settings()
    remember_source(settings, "/a.yaml", None)
    remember_source(settings, "/b", "/b_labels")
    remember_source(settings, "/a.yaml", None)
    assert settings.get(LAST_SOURCE) == {"source": "/a.yaml", "labels": None}
    assert settings.get(RECENT) == [{"source": "/a.yaml", "labels": None},
                                    {"source": "/b", "labels": "/b_labels"}]


def test_the_recent_list_is_capped():
    _, settings = global_settings()
    for i in range(RECENT_MAX + 3):
        remember_source(settings, f"/{i}.yaml", None)
    assert len(settings.get(RECENT)) == RECENT_MAX


def test_the_saver_waits_then_saves_once(qtbot):
    saved = []
    saver = Saver(lambda: saved.append(1), delay_ms=20)
    saver.schedule()
    saver.schedule()
    assert saved == [] and saver.pending
    qtbot.waitUntil(lambda: saved == [1], timeout=2000)
    saver.schedule()
    saver.flush()
    assert saved == [1, 1] and not saver.pending


def test_a_toggle_is_seeded_from_the_setting_and_writes_back(qtbot):
    file, settings = global_settings()
    settings.set(SHOW_LABELS, False)
    action, seen = QAction(), []
    bind_toggle(action, settings, SHOW_LABELS, seen.append)
    assert not action.isChecked()
    action.setChecked(True)
    assert settings.get(SHOW_LABELS) is True and seen == [True] and file.dirty
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_workers.py tests/ui/test_images.py tests/ui/test_settings_ui.py`
Expected: `ModuleNotFoundError` for `deeplabeling.ui.workers`, `.images` and `.settings_ui`.

- [ ] **Step 3: Write the modules**

Create `src/deeplabeling/ui/workers.py`:

```python
"""Background jobs (docs/design/2026-10-04-app-foundation.md#architecture).

A job gets immutable inputs, reports through queued signals, never writes a file and
never touches a widget. The GUI thread never waits on one (CLAUDE.md landmine 3).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

#: fn(emit, cancelled) -> result. `emit` sends a batch to the GUI thread; `cancelled`
#: says whether to stop early.
JobFn = Callable[[Callable[[object], None], Callable[[], bool]], object]


class JobSignals(QObject):
    batch = Signal(object)
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()


class Job(QRunnable):
    """Runs one function on a pool thread. It is created on the GUI thread, so its
    signals reach GUI-thread receivers through queued connections."""

    def __init__(self, fn: JobFn):
        super().__init__()
        self.setAutoDelete(False)       # Jobs keeps the Python object alive instead
        self.signals = JobSignals()
        self._fn = fn
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:
        try:
            result = self._fn(self.signals.batch.emit, self._cancel.is_set)
        except Exception as e:                      # a worker that raises stops alone
            if not self.cancelled:
                self.signals.failed.emit(f"{type(e).__name__}: {e}")
        else:
            if not self.cancelled:
                self.signals.done.emit(result)
        finally:
            self.signals.finished.emit()


class Jobs:
    """A pool of worker threads that keeps every job alive until it finishes."""

    def __init__(self, threads: int):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(threads)
        self._live: set[Job] = set()

    def start(self, fn: JobFn, *, batch: Callable[[object], None] | None = None,
              done: Callable[[object], None] | None = None,
              failed: Callable[[str], None] | None = None) -> Job:
        job = Job(fn)
        if batch is not None:
            job.signals.batch.connect(batch)
        if done is not None:
            job.signals.done.connect(done)
        if failed is not None:
            job.signals.failed.connect(failed)
        job.signals.finished.connect(lambda j=job: self._live.discard(j))
        self._live.add(job)
        self.pool.start(job)
        return job

    def cancel_all(self) -> None:
        for job in list(self._live):
            job.cancel()

    def wait(self, msecs: int = -1) -> bool:
        """Block until the pool is idle. For shutdown and tests, never for the GUI."""
        return self.pool.waitForDone(msecs)
```

Create `src/deeplabeling/ui/images.py`:

```python
"""Decoding images on workers, into a cache bounded in bytes
(docs/design/2026-10-04-app-foundation.md#window)."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QImageReader

from .workers import Job, Jobs


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


class ImageCache(QObject):
    """Decoded images by path. The images it is told to keep -- the current one and
    its neighbours -- are decoded first and never evicted; the rest go oldest first
    once the cache is over its byte budget."""

    ready = Signal(object)          # path
    failed = Signal(object, str)    # path, why

    def __init__(self, jobs: Jobs, limit_bytes: int = 512 * 2**20, parent=None):
        super().__init__(parent)
        self._jobs = jobs
        self._limit = limit_bytes
        self._images: OrderedDict[Path, QImage] = OrderedDict()
        self._errors: dict[Path, str] = {}
        self._pending: dict[Path, Job] = {}
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

    def request(self, path) -> None:
        path = Path(path)
        if path in self._images or path in self._errors or path in self._pending:
            return
        self._pending[path] = self._jobs.start(
            lambda emit, cancelled, p=path: decode_image(p),
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

Create `src/deeplabeling/ui/settings_ui.py`:

```python
"""Global settings, saving, and binding widgets to settings
(docs/design/2026-10-04-app-foundation.md#state-and-settings)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction

from ..core.settings import JsonFile, Setting, Settings, define
from ..core.state import state_dir


def _is_source(v) -> bool:
    return (isinstance(v, dict) and isinstance(v.get("source"), str)
            and (v.get("labels") is None or isinstance(v.get("labels"), str)))


#: {"source": yaml or image folder, "labels": label folder or None}
LAST_SOURCE = define("app.last_source", "global", None, lambda v: v is None or _is_source(v))
RECENT = define("app.recent", "global", [], lambda v: isinstance(v, list) and all(map(_is_source, v)))
WINDOW_GEOMETRY = define("window.geometry", "global", "", lambda v: isinstance(v, str))
WINDOW_STATE = define("window.state", "global", "", lambda v: isinstance(v, str))
SHOW_LABELS = define("view.labels", "global", True, lambda v: isinstance(v, bool))
SHOW_CAPTIONS = define("view.captions", "global", True, lambda v: isinstance(v, bool))

RECENT_MAX = 8


def global_settings() -> tuple[JsonFile, Settings]:
    file = JsonFile(state_dir() / "settings.json")
    return file, Settings(file, "global")


def remember_source(settings: Settings, source: str, labels: str | None) -> None:
    """Record an opened dataset as the last one and at the top of the recent list."""
    entry = {"source": source, "labels": labels}
    settings.set(LAST_SOURCE, entry)
    settings.set(RECENT, ([entry] + [e for e in settings.get(RECENT) if e != entry])[:RECENT_MAX])


class Saver(QObject):
    """Saves a moment after the last change (atomic writes, debounced), or at once on flush."""

    def __init__(self, save: Callable[[], None], delay_ms: int = 2000, parent=None):
        super().__init__(parent)
        self._save = save
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(save)

    @property
    def pending(self) -> bool:
        return self._timer.isActive()

    def schedule(self) -> None:
        self._timer.start()

    def flush(self) -> None:
        self._timer.stop()
        self._save()


def bind_toggle(action: QAction, settings: Settings, setting: Setting,
                changed: Callable[[bool], None]) -> None:
    """The one way a checkable control meets a setting: seeded from the value the logic
    reads, and every change written back (CLAUDE.md landmine 7)."""
    action.setCheckable(True)
    action.setChecked(settings.get(setting))

    def on_toggled(value: bool) -> None:
        settings.set(setting, bool(value))
        changed(bool(value))

    action.toggled.connect(on_toggled)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_workers.py tests/ui/test_images.py tests/ui/test_settings_ui.py`
Expected: 15 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: all pass.

```bash
git add src/deeplabeling/ui tests/ui
git commit -m "ui: worker jobs, the decoded-image cache, global settings" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The session

**Files:**
- Modify: `src/deeplabeling/core/queue.py` (add `Queue.index_of`), `tests/core/test_queue.py` (append), `tests/fixtures.py` (append)
- Create: `src/deeplabeling/ui/session.py`, `tests/ui/conftest.py`
- Test: `tests/ui/test_session.py`

**Interfaces:**
- Consumes:
  - from the core, `Workspace` with its `QUEUE_SOURCE` and `QUEUE_CURSOR` settings and `OpenCancelled`; `DatasetError` and `Locked`; `ImageFilter`, `Queue`, `QueueItem` and `BuildContext`; `CreateEmpty`, `Intent` and `Refused`; `LabelState`; `count_out_of_range`;
  - from Task 2, `Jobs`, `ImageCache`, `Saver`, `global_settings` and `remember_source`.
- Produces: in `deeplabeling.core.queue`, `Queue.index_of(key) -> int | None`.
- Produces in `deeplabeling.ui.session`:
  - `OUT_OF_RANGE` and `WATCH_MS = 1500`;
  - `Prompter`, a Protocol with `confirm_taxonomy(...) -> bool` and `error(title, text)`;
  - `Session(prompter)`.
    - Signals:
      - lifecycle: `opened`, `closed`;
      - labels and review: `labelsChanged(tuple[Path, ...])`, `historyChanged`, `reviewChanged`;
      - the queue: `queueReset`, `queueGrew`, `queueDone`, `itemsChanged(list[str])`, `cursorChanged`;
      - messages: `notice(level, text, image)`, `standing(key, text)`, `status(text)`.
    - Attributes: `prompter`, `settings_file`, `settings`, `workspace`, `queue`, `io`, `images` and `saver`.
    - Opening and closing: `.open(source, labels=None) -> bool`, `.current_source()` and `.close()`.
    - The queue and its cursor: `.set_queue(source, follow=None)`, `.context()`, `.current()`, `.move(delta) -> bool`, `.go_to(key) -> bool`, `.go_to_text(text) -> bool`, `.check_current()` and `.left()`.
    - What the panels show: `.labels(entry)`, `.badge(item)`, `.describe_item(item)` and `.reviewed_counts() -> (marked, total)`.
    - Actions: `.done_and_next()`, `.toggle_reviewed()`, `.apply(intent) -> Edit | None`, `.mark_negative()`, `.undo()` and `.redo()`.
- Produces in `tests/fixtures.py`:
  - `FakePrompter(*, taxonomy=True, yaml=None, folders=(), queue=None, text=None)`, with `.errors` and `.asked`;
  - `open_session(qtbot, source, prompter=None, **kw)`.
- Produces: the `session` fixture in `tests/ui/conftest.py`.

- [ ] **Step 1: The failing test for `Queue.index_of`**

Append to `tests/core/test_queue.py`:

```python
def test_index_of_finds_a_row_by_key(dataset):
    q = Queue(ImageFilter())
    q.extend(all_items(dataset)[:3])
    assert q.index_of(dataset.images[2].rel) == 2 and q.index_of("nope") is None
```

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_queue.py`
Expected: 1 failed, `AttributeError: 'Queue' object has no attribute 'index_of'`.

- [ ] **Step 2: Add `Queue.index_of`**

In `src/deeplabeling/core/queue.py`, after the `position` method, add:

```python
    def index_of(self, key: str) -> int | None:
        """The row of the item with this key, or None when it is not in the queue."""
        return self._pos.get(key)
```

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_queue.py`
Expected: all pass.

- [ ] **Step 3: Write the shared test helpers and the failing session tests**

Append to `tests/fixtures.py`:

```python
class FakePrompter:
    """Answers the UI's dialogs from preset values and records what was asked."""

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
        self.asked: list[tuple] = []

    def confirm_taxonomy(self, *args):
        self.asked.append(("taxonomy",) + args)
        return self.taxonomy

    def error(self, title, text):
        self.errors.append((title, text))

    def choose_yaml(self):
        self.asked.append(("yaml",))
        return None if self.yaml is None else str(self.yaml)

    def choose_folder(self, title):
        self.asked.append(("folder", title))
        return str(self.folders.pop(0)) if self.folders else None

    def edit_queue(self, dataset, current):
        self.asked.append(("queue", current))
        return self.queue

    def ask_text(self, title, label):
        self.asked.append(("text", title))
        return self.text


def open_session(qtbot, source, prompter=None, **kw):
    """A Session with `source` open and its first queue fully built."""
    from deeplabeling.ui.session import Session

    s = Session(prompter or FakePrompter())
    with qtbot.waitSignal(s.queueDone, timeout=5000):
        assert s.open(source, **kw)
    return s
```

Create `tests/ui/conftest.py`:

```python
import pytest

from fixtures import open_session


@pytest.fixture
def session(qtbot, ds):
    """The edge-case dataset open in a Session, its queue built; closed afterwards."""
    s = open_session(qtbot, ds.yaml)
    yield s
    s.close()
```

Create `tests/ui/test_session.py`:

```python
import pytest
import yaml

from deeplabeling.core.edits import AddBox, Intent
from deeplabeling.core.queue import HasClass, ImageFilter
from deeplabeling.ui.session import OUT_OF_RANGE, Session
from fixtures import FakePrompter, assert_only_changed, open_session

BOX = (0.5, 0.5, 0.2, 0.2)


def record(signal):
    got = []
    signal.connect(lambda *args: got.append(args))
    return got


def test_opening_builds_every_image_and_starts_on_the_first(session, ds):
    assert len(session.queue) == 15 and session.queue.complete
    assert session.current().key == "camA/images/0001.jpg"
    assert session.reviewed_counts() == (0, 15)


def test_ids_the_yaml_does_not_name_raise_a_standing_notice(qtbot, ds):
    s = Session(FakePrompter())
    with qtbot.waitSignal(s.standing, timeout=5000,
                          check_params_cb=lambda key, text: key == OUT_OF_RANGE and bool(text)) as caught:
        s.open(ds.yaml)
    assert "2 boxes in 1 images" in caught.args[1] and "data.yaml" in caught.args[1]
    s.close()


def test_paging_marks_nothing(session):
    for _ in range(3):
        assert session.move(1)
    session.move(-1)
    assert session.workspace.review.count() == 0


def test_done_and_next_marks_and_moves(session):
    session.done_and_next()
    assert session.workspace.review.is_marked("camA/images/0001.jpg")
    assert session.current().key == "camA/images/0002.jpg" and session.left() == 14


def test_the_end_of_the_queue_is_said_not_passed(session):
    status = record(session.status)
    session.go_to(session.queue.items[-1].key)
    assert not session.move(1)
    assert status[-1] == ("the end of the queue",)


def test_toggle_reviewed(session):
    session.toggle_reviewed()
    assert session.workspace.review.is_marked("camA/images/0001.jpg")
    session.toggle_reviewed()
    assert not session.workspace.review.is_marked("camA/images/0001.jpg")


def test_mark_negative_creates_an_empty_file_and_undo_removes_it(session, ds):
    session.go_to("camA/images/0003.jpg")
    before = ds.snapshot()
    changed = record(session.labelsChanged)
    session.mark_negative()
    assert_only_changed(before, ds.snapshot(), {"camA/labels/0003.txt"})
    assert ds.lbl("camA/0003").read_bytes() == b""
    assert changed == [((ds.img("camA/0003.jpg"),),)]
    assert session.workspace.review.is_marked("camA/images/0003.jpg")   # an edit marks
    session.undo()
    assert not ds.lbl("camA/0003").exists()
    session.redo()
    assert ds.lbl("camA/0003").read_bytes() == b""


def test_mark_negative_on_a_labelled_image_is_refused_visibly(session, ds):
    notices = record(session.notice)
    before = ds.snapshot()
    session.mark_negative()
    assert_only_changed(before, ds.snapshot(), set())
    level, text, image = notices[-1]
    assert level == "error" and "already has a label file" in text and image == ds.img("camA/0001.jpg")


def test_undo_goes_to_the_image_it_changes(session, ds):
    session.go_to("camA/images/0003.jpg")
    session.mark_negative()
    session.go_to("seg/images/poly1.jpg")
    session.undo()
    assert session.current().key == "camA/images/0003.jpg"


def test_an_undecodable_image_is_never_edited(qtbot, session, ds):
    with qtbot.waitSignal(session.images.failed, timeout=5000):
        session.go_to("bad/images/corrupt.jpg")
    notices, before = record(session.notice), ds.snapshot()
    session.apply(Intent(ds.img("bad/corrupt.jpg"), (AddBox(0, BOX),), "draw"))
    assert_only_changed(before, ds.snapshot(), set())
    assert "cannot be decoded" in notices[-1][1]


def test_a_queue_and_its_cursor_survive_a_reopen(qtbot, ds):
    s = open_session(qtbot, ds.yaml)
    with qtbot.waitSignal(s.queueDone, timeout=5000):
        s.set_queue(ImageFilter(conditions=(HasClass(("bus_m",)),)))
    assert [it.key for it in s.queue.items] == [
        "camA/images/sub/0005.jpg", "camB/images/0001.jpg", "camB/images/rot.jpg"]
    s.go_to("camB/images/0001.jpg")
    s.close()
    again = open_session(qtbot, ds.yaml)
    assert again.queue.source == ImageFilter(conditions=(HasClass(("bus_m",)),))
    assert again.current().key == "camB/images/0001.jpg"
    again.close()


def test_an_item_that_stops_matching_is_marked_not_removed(qtbot, session, ds):
    with qtbot.waitSignal(session.queueDone, timeout=5000):
        session.set_queue(ImageFilter(conditions=(HasClass(("car",)),)))
    changed = record(session.itemsChanged)
    ds.lbl("camA/0001").write_bytes(b"0 0.5 0.5 0.2 0.2\n")       # no car left
    session.labels(session.current().entry)                         # the store notices
    assert "camA/images/0001.jpg" in session.queue.stale and "camA/images/0001.jpg" in session.queue
    assert ["camA/images/0001.jpg"] in [args[0] for args in changed]
    assert session.badge(session.current()) == "1 box · no longer matches"


def test_badges(session):
    by_key = {it.key: it for it in session.queue.items}
    assert session.badge(by_key["camA/images/0001.jpg"]) == "2 boxes"
    assert session.badge(by_key["camA/images/0002.jpg"]) == "negative"
    assert session.badge(by_key["camA/images/0003.jpg"]) == "missing"
    assert session.badge(by_key["camB/images/twin.jpg"]) == "shared"
    assert session.describe_item(by_key["camA/images/0002.jpg"]).startswith("· camA/images/0002.jpg")


def test_go_to_by_number_or_name(session):
    assert session.go_to_text("3") and session.current().key == "camA/images/0003.jpg"
    assert session.go_to_text("POLY") and session.current().key == "seg/images/poly1.jpg"
    status = record(session.status)
    assert not session.go_to_text("nothing like it")
    assert "no item matches" in status[-1][0]


def test_a_root_already_open_is_refused_and_the_first_stays_open(qtbot, session, ds):
    prompter = FakePrompter()
    second = Session(prompter)
    assert not second.open(ds.yaml)
    assert "already open" in prompter.errors[0][1] and second.workspace is None
    assert session.workspace is not None


def test_a_failed_open_reopens_the_previous_dataset(qtbot, session, ds):
    assert not session.open(ds.root / "nowhere.yaml")
    assert session.prompter.errors and session.current_source()[0] == str(ds.yaml)


def test_declining_a_new_taxonomy_opens_nothing_and_says_nothing(qtbot, ds):
    open_session(qtbot, ds.yaml).close()
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data["names"] = ["a", "b"]
    other = ds.root / "other.yaml"
    other.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    prompter = FakePrompter(taxonomy=False)
    s = Session(prompter)
    assert not s.open(other)
    assert s.workspace is None and prompter.errors == [] and prompter.asked[0][0] == "taxonomy"


def test_the_reviewed_count_covers_this_datasets_images_only(session):
    session.workspace.review.mark("data_UK/images/elsewhere.jpg")
    session.toggle_reviewed()
    assert session.reviewed_counts() == (1, 15)


def test_a_failing_build_becomes_a_notice(qtbot, session):
    class Boom(ImageFilter):
        def build(self, ctx, emit, cancelled=lambda: False, **kw):
            raise RuntimeError("boom")

    with qtbot.waitSignal(session.notice, timeout=5000) as caught:
        session.set_queue(Boom())
    assert caught.args[0] == "error" and "RuntimeError: boom" in caught.args[1]


def test_closing_saves_and_frees_the_root(qtbot, ds, state_dir):
    s = open_session(qtbot, ds.yaml)
    s.done_and_next()
    s.close()
    assert list(state_dir.glob("datasets/*/review.json"))
    open_session(qtbot, ds.yaml).close()


def test_a_superseded_build_never_feeds_the_new_queue(qtbot, session):
    with qtbot.waitSignal(session.queueDone, timeout=5000):
        session.set_queue(ImageFilter(conditions=(HasClass(("car",)),)))
        session.set_queue(ImageFilter(conditions=(HasClass(("bus_m",)),)))
    qtbot.wait(100)                         # let any late batch of the first build arrive
    assert [it.key for it in session.queue.items] == [
        "camA/images/sub/0005.jpg", "camB/images/0001.jpg", "camB/images/rot.jpg"]


def test_an_outside_edit_to_the_image_on_screen_is_noticed_unasked(qtbot, session, ds):
    ds.lbl("camA/0001").write_bytes(b"3 0.5 0.5 0.1 0.1\n")
    with qtbot.waitSignal(session.labelsChanged, timeout=5000) as caught:
        pass                                # nothing touches the file: the watch must
    assert caught.args[0] == (ds.img("camA/0001.jpg"),)


def test_a_full_disk_while_opening_says_why(qtbot, ds, monkeypatch):
    from deeplabeling.core import workspace

    def full_disk(self):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(workspace.DatasetLock, "acquire", full_disk)
    prompter = FakePrompter()
    s = Session(prompter)
    assert not s.open(ds.yaml)
    assert s.workspace is None and "No space left" in prompter.errors[0][1]
```

- [ ] **Step 4: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_session.py`
Expected: collection error, `ModuleNotFoundError: No module named 'deeplabeling.ui.session'`.

- [ ] **Step 5: Write the session**

Create `src/deeplabeling/ui/session.py`:

```python
"""The GUI thread's hold on one open dataset: the workspace, its queue, the jobs that
feed them, and every action that changes labels or review marks
(docs/design/2026-10-04-app-foundation.md).

Widgets read from the session and call its methods; they never reach into the core's
store, editor or files. Dialogs go through a Prompter, so tests answer them without a
modal event loop. The session is created, and opens datasets, on the GUI thread, which
therefore owns the LabelStore's write path (spec: Notes for plan 1b).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.dataset import DatasetError, ImageEntry
from ..core.edits import CreateEmpty, Edit, Intent, Refused
from ..core.queue import BuildContext, ImageFilter, Queue, QueueItem
from ..core.state import Locked
from ..core.store import ImageLabels, LabelState
from ..core.taxonomy import count_out_of_range
from ..core.workspace import QUEUE_CURSOR, QUEUE_SOURCE, OpenCancelled, Workspace
from .images import ImageCache
from .settings_ui import Saver, global_settings, remember_source
from .workers import Jobs

#: The key of the standing notice about ids the yaml does not name.
OUT_OF_RANGE = "out-of-range"
#: How often the image on screen has its label file re-checked for outside changes.
WATCH_MS = 1500


class Prompter(Protocol):
    """The dialogs the session needs. The window's prompter adds the ones it needs."""

    def confirm_taxonomy(self, last_source: str, last_names: list[str],
                         source: str, names: tuple[str, ...]) -> bool: ...

    def error(self, title: str, text: str) -> None: ...


class Session(QObject):
    opened = Signal()
    closed = Signal()
    labelsChanged = Signal(object)      # tuple[Path, ...]: images whose label file changed
    historyChanged = Signal()
    reviewChanged = Signal()
    queueReset = Signal()               # a new queue replaced the old one
    queueGrew = Signal()                # items were appended to the queue
    queueDone = Signal()                # the queue finished building
    itemsChanged = Signal(object)       # list[str]: keys whose badge or tick may differ
    cursorChanged = Signal()
    notice = Signal(str, str, object)   # level, text, image Path or None
    standing = Signal(str, str)         # key, text: a notice that stays; "" removes it
    status = Signal(str)                # a passing message for the status bar
    _reloaded = Signal(object)          # emitted from any thread, delivered queued

    def __init__(self, prompter: Prompter, parent=None):
        super().__init__(parent)
        self.prompter = prompter
        self.settings_file, self.settings = global_settings()
        self.workspace: Workspace | None = None
        self.queue: Queue | None = None
        self.io = Jobs(2)
        self.images = ImageCache(Jobs(2), parent=self)
        self.saver = Saver(self._save, parent=self)
        self._build = None
        self._by_rel: dict[str, ImageEntry] = {}
        self._reloaded.connect(lambda image: self.labelsChanged.emit((image,)))
        self.labelsChanged.connect(self._recheck)
        # The store notices an outside edit when its file is next read; reading the one on
        # screen now and then (a stat, unless it changed) makes it appear without a click.
        self._watch = QTimer(self)
        self._watch.setInterval(WATCH_MS)
        self._watch.timeout.connect(self.check_current)
        self._watch.start()

    # -- opening and closing -----------------------------------------------

    def open(self, source, labels=None) -> bool:
        """Open a dataset, closing the current one first (a root opens once). If the new
        one cannot be opened, the previous one is reopened."""
        previous = self.current_source()
        self.close()
        if self._open(source, labels, quiet=False):
            return True
        if previous is not None:
            self._open(*previous, quiet=True)
        return False

    def current_source(self) -> tuple[str, str | None] | None:
        if self.workspace is None:
            return None
        dataset = self.workspace.dataset
        return str(dataset.source), str(dataset.labels) if dataset.labels else None

    def _open(self, source, labels, *, quiet: bool) -> bool:
        try:
            ws = Workspace.open(source, labels, confirm_taxonomy=self.prompter.confirm_taxonomy,
                                on_labels_changed=self.labelsChanged.emit,
                                on_history_changed=self.historyChanged.emit,
                                on_reload=self._reloaded.emit)
        except OpenCancelled:
            return False
        except (DatasetError, Locked, OSError) as e:
            if not quiet:
                self.prompter.error("Cannot open the dataset", str(e))
            return False
        self.workspace = ws
        self._by_rel = {e.rel: e for e in ws.dataset.images}
        remember_source(self.settings, *self.current_source())
        self.saver.schedule()
        self.opened.emit()
        for warning in ws.warnings:
            self.notice.emit("warning", warning, None)
        if ws.dataset.missing:
            listed = ", ".join(str(p) for p in ws.dataset.missing)
            self.notice.emit("warning", f"listed in {ws.dataset.source.name} but missing: {listed}", None)
        self._count_out_of_range()
        self._restore_queue()
        return True

    def close(self) -> None:
        ws = self.workspace
        if ws is None:
            return
        self.io.cancel_all()
        self.images.clear()
        self.io.wait(2000)
        self.workspace, self.queue, self._build, self._by_rel = None, None, None, {}
        try:
            ws.close()
        except OSError as e:
            self.prompter.error("Could not save the review marks", str(e))
        self._save()
        self.closed.emit()
        self.standing.emit(OUT_OF_RANGE, "")

    def _save(self) -> None:
        try:
            if self.workspace is not None:
                self.workspace.save()
            self.settings_file.save()
        except OSError as e:
            self.notice.emit("error", f"could not save settings: {e}", None)

    def _require(self) -> Workspace:
        if self.workspace is None:
            raise RuntimeError("no dataset is open")
        return self.workspace

    # -- the queue -----------------------------------------------------------

    def _restore_queue(self) -> None:
        opening = self._require().opening_settings
        try:
            stored = opening.get(QUEUE_SOURCE)
            source = ImageFilter.from_json(stored) if stored else ImageFilter()
        except ValueError:
            source = ImageFilter()
        cursor = opening.get(QUEUE_CURSOR)
        self.set_queue(source, follow=self._by_rel.get(cursor) if cursor else None)

    def set_queue(self, source: ImageFilter, follow: ImageEntry | None = None) -> None:
        """Rebuild the queue from `source`, keeping the cursor on its image if it is still in."""
        ws = self._require()
        if self._build is not None:
            self._build.cancel()
        if follow is None and self.current() is not None:
            follow = self.current().entry
        queue = self.queue = Queue(source, follow=follow)
        ws.opening_settings.set(QUEUE_SOURCE, source.to_json())
        self.saver.schedule()
        self.queueReset.emit()
        self.cursorChanged.emit()
        ctx = self.context()
        self._build = self.io.start(
            lambda emit, cancelled: source.build(ctx, emit, cancelled),
            batch=lambda items: self._grew(queue, items),
            done=lambda finished: self._built(queue, finished),
            failed=lambda why: self.notice.emit("error", f"building the queue failed: {why}", None))

    def context(self) -> BuildContext:
        ws = self._require()
        return BuildContext(ws.dataset, ws.store, ws.review.keys())

    def _grew(self, queue: Queue, items: list[QueueItem]) -> None:
        if queue is not self.queue:
            return                                  # a cancelled build's last batch
        before = queue.cursor
        queue.extend(items)
        self.queueGrew.emit()
        if queue.cursor != before:
            self._cursor_moved()

    def _built(self, queue: Queue, finished: bool) -> None:
        if queue is not self.queue or not finished:
            return
        before = queue.cursor
        queue.finish()
        self.queueDone.emit()
        if queue.cursor != before:
            self._cursor_moved()

    def current(self) -> QueueItem | None:
        return self.queue.current() if self.queue is not None else None

    def move(self, delta: int) -> bool:
        if self.queue is None or not self.queue.move(delta):
            if self.queue is not None and len(self.queue):
                self.status.emit("the end of the queue" if delta > 0 else "the start of the queue")
            return False
        self._cursor_moved()
        return True

    def go_to(self, key: str) -> bool:
        if self.queue is None or not self.queue.go_to(key):
            return False
        self._cursor_moved()
        return True

    def go_to_text(self, text: str) -> bool:
        """Go to an item by its 1-based number, or the first whose path contains the text."""
        if self.queue is None or not text.strip():
            return False
        text = text.strip()
        if text.isdigit() and 1 <= int(text) <= len(self.queue):
            return self.go_to(self.queue.items[int(text) - 1].key)
        match = next((it.key for it in self.queue.items if text.lower() in it.key.lower()), None)
        if match is None:
            self.status.emit(f"no item matches “{text}”")
            return False
        return self.go_to(match)

    def _cursor_moved(self) -> None:
        item = self.current()
        if item is not None and self.workspace is not None:
            self.workspace.opening_settings.set(QUEUE_CURSOR, item.key)
            self.saver.schedule()
            self.workspace.store.pin(item.entry.path)
            i, items = self.queue.position(), self.queue.items
            self.images.keep([items[j].entry.path for j in (i, i + 1, i + 2, i - 1)
                              if 0 <= j < len(items)])
        self.cursorChanged.emit()

    def check_current(self) -> None:
        """Re-read the current image's label file; a change is reported as labelsChanged."""
        item = self.current()
        if item is not None and self.workspace is not None:
            self.workspace.store.get(item.entry.path)

    def left(self) -> int:
        if self.queue is None or self.workspace is None:
            return 0
        return self.queue.left(self.workspace.review.is_marked)

    # -- what the panels show ------------------------------------------------

    def labels(self, entry: ImageEntry) -> ImageLabels:
        return self._require().store.get(entry.path)

    def badge(self, item: QueueItem) -> str:
        labels = self.labels(item.entry)
        if labels.state is LabelState.ERROR:
            text = "unreadable"
        elif labels.state is LabelState.SHARED:
            text = "shared"
        elif labels.raw is None:
            text = "missing"
        elif labels.negative:
            text = "negative"
        else:
            n = len(labels.boxes)
            text = f"{n} box" if n == 1 else f"{n} boxes"
        if self.queue is not None and item.key in self.queue.stale:
            text += " · no longer matches"
        return text

    def describe_item(self, item: QueueItem) -> str:
        tick = "✓" if self._require().review.is_marked(item.key) else "·"
        return f"{tick} {item.key}  —  {self.badge(item)}"

    def reviewed_counts(self) -> tuple[int, int]:
        """Marks among THIS dataset's images: yamls sharing a root list different folders."""
        ws = self._require()
        marks = ws.review.marks
        return sum(1 for e in ws.dataset.images if e.rel in marks), len(ws.dataset.images)

    # -- review marks --------------------------------------------------------

    def done_and_next(self) -> None:
        item = self.current()
        if item is None:
            return
        if self._require().review.mark(item.key):
            self._review_changed([item.key])
        self.move(1)

    def toggle_reviewed(self) -> None:
        item = self.current()
        if item is None:
            return
        self._require().review.toggle(item.key)
        self._review_changed([item.key])

    def _review_changed(self, keys: list[str]) -> None:
        self.saver.schedule()
        self.reviewChanged.emit()
        self.itemsChanged.emit(keys)

    # -- edits -----------------------------------------------------------------

    def apply(self, intent: Intent) -> Edit | None:
        """Every label change goes through here; a refusal becomes a notice."""
        ws = self._require()
        rel = ws.dataset.entry(intent.image).rel
        why = self.images.error(intent.image)
        if why is not None:
            self.notice.emit("error", f"{rel}: the image cannot be decoded ({why}), "
                             "so its labels are not edited", intent.image)
            return None
        try:
            edit = ws.editor.apply(intent)
        except Refused as e:
            self.notice.emit("error", f"{rel}: {e}", intent.image)
            return None
        if edit is not None:
            self._review_changed([rel])
        return edit

    def mark_negative(self) -> None:
        item = self.current()
        if item is not None:
            self.apply(Intent(item.entry.path, (CreateEmpty(),), "mark negative"))

    def undo(self) -> None:
        self._step(undo=True)

    def redo(self) -> None:
        self._step(undo=False)

    def _step(self, *, undo: bool) -> None:
        ws = self._require()
        edit = ws.history.peek_undo() if undo else ws.history.peek_redo()
        if edit is None:
            self.status.emit("nothing to undo" if undo else "nothing to redo")
            return
        image = edit.images[0]
        rel = ws.dataset.entry(image).rel
        if self.queue is not None and rel in self.queue:
            self.go_to(rel)                         # the change happens in view
        try:
            (ws.editor.undo if undo else ws.editor.redo)()
        except Refused as e:
            self.notice.emit("error", str(e), image)
            return
        self.status.emit(f"{'undid' if undo else 'redid'} {edit.description}: {rel}")

    def _recheck(self, images) -> None:
        if self.queue is None or self.workspace is None:
            return
        ctx, keys = self.context(), []
        for image in images:
            try:
                entry = self.workspace.dataset.entry(image)
            except KeyError:
                continue
            self.queue.recheck(entry, ctx)
            keys.append(entry.rel)
        self.itemsChanged.emit(keys)

    # -- the taxonomy guard ----------------------------------------------------

    def _count_out_of_range(self) -> None:
        ws = self._require()
        dataset, store = ws.dataset, ws.store

        def found(result) -> None:
            if self.workspace is ws and result is not None:
                self.standing.emit(OUT_OF_RANGE, result.message(dataset))

        self.io.start(lambda emit, cancelled: count_out_of_range(dataset, store, cancelled),
                      done=found,
                      failed=lambda why: self.notice.emit("error", f"checking class ids failed: {why}", None))
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_session.py`
Expected: 23 passed. `test_an_outside_edit_to_the_image_on_screen_is_noticed_unasked` waits for the 1.5 s watch.

- [ ] **Step 7: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: all pass.

```bash
git add src/deeplabeling/core/queue.py src/deeplabeling/ui/session.py tests/core/test_queue.py tests/fixtures.py tests/ui
git commit -m "ui: the session, the GUI thread's hold on one dataset" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The canvas

**Files:**
- Create: `src/deeplabeling/ui/canvas.py`
- Test: `tests/ui/test_canvas.py`

**Interfaces:**
- Consumes: `BoxView` (Task 1) and `text_color` (Task 1).
- Produces in `deeplabeling.ui.canvas`:
  - `BACKGROUND`;
  - `CaptionItem(text, color)`, with `.text` and `.color`;
  - `Canvas`, with the properties `.image_size` and `.message`, the attributes `.show_labels` and `.show_captions`, and the methods `.set_image(image | None, message="")`, `.set_boxes(views)`, `.set_layers(*, labels, captions)`, `.caption_items()`, `.fit()` and `.zoom_by(factor)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_canvas.py`:

```python
"""What the canvas shows, read back from its pixels (the run-and-verify-ui skill)."""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

from deeplabeling.ui.boxes import BoxView
from deeplabeling.ui.canvas import Canvas

GREY = QColor(80, 80, 80)
RED = BoxView(0, (50, 25, 150, 75), (), "#ff0000", "car", True, False)


def grey_image(w=200, h=100):
    image = QImage(w, h, QImage.Format_RGB32)
    image.fill(GREY)
    return image


@pytest.fixture
def canvas(qtbot):
    c = Canvas()
    qtbot.addWidget(c)
    c.resize(400, 300)
    c.show()
    qtbot.waitUntil(c.isVisible)
    return c


def shot(canvas):
    return canvas.viewport().grab().toImage()


def pixel(canvas, x, y, image=None):
    image = image or shot(canvas)
    return QColor(image.pixel(canvas.mapFromScene(QPointF(x, y))))


def is_red(c):
    return c.red() > 200 and c.green() < 80 and c.blue() < 80


def near(canvas, x, y, image=None, radius=2):
    """The pixels within `radius` of a scene point: a line on a pixel boundary is
    antialiased across two pixels, so one exact pixel can be half its colour."""
    image = image or shot(canvas)
    centre = canvas.mapFromScene(QPointF(x, y))
    return [QColor(image.pixel(centre.x() + dx, centre.y() + dy))
            for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)]


def test_a_box_is_drawn_in_its_colour_where_it_is(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    assert any(map(is_red, near(canvas, 100, 25))) and any(map(is_red, near(canvas, 150, 50)))
    assert pixel(canvas, 100, 50) == GREY


def test_the_caption_sits_on_a_plate_inside_the_top_edge(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    corner = canvas.mapFromScene(QPointF(50, 25))
    assert is_red(QColor(shot(canvas).pixel(corner + QPoint(4, 6))))
    [caption] = canvas.caption_items()
    assert caption.text == "car" and caption.isVisible()
    assert canvas.viewport().rect().contains(corner + QPoint(int(caption.boundingRect().width()) - 1, 6))


def test_an_unknown_class_is_drawn_grey_and_dashed(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BoxView(1, (50, 25, 150, 75), (), "#9e9e9e", "#99?", False, False)])
    image = shot(canvas)
    x = canvas.mapFromScene(QPointF(150, 50)).x()
    top, bottom = canvas.mapFromScene(QPointF(150, 35)).y(), canvas.mapFromScene(QPointF(150, 70)).y()
    # across the line only, row by row: dashes read near the pen's grey, gaps near the image's
    edge = [max(QColor(image.pixel(x + dx, y)).red() for dx in range(-2, 3)) for y in range(top, bottom)]
    assert any(v > 140 for v in edge) and any(v <= 110 for v in edge)


def test_a_highlighted_box_is_drawn_thicker(canvas):
    def thickness(view):
        canvas.set_image(grey_image())
        canvas.set_boxes([view])
        image = shot(canvas)
        x = canvas.mapFromScene(QPointF(120, 25)).x()
        y0 = canvas.mapFromScene(QPointF(120, 25)).y()
        return sum(is_red(QColor(image.pixel(x, y))) for y in range(y0 - 6, y0 + 7))

    plain = thickness(RED)
    thick = thickness(BoxView(0, RED.rect, (), "#ff0000", "car", True, True))
    assert thick > plain >= 1


def test_a_polygon_is_drawn_by_its_points(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BoxView(0, (20, 10, 60, 50), ((20, 10), (60, 10), (20, 50)), "#ff0000", "car", True, False)])
    assert is_red(pixel(canvas, 40, 30))           # on the diagonal
    assert pixel(canvas, 55, 45) == GREY           # inside the extent, outside the triangle


def test_layers_hide_the_labels_or_only_the_captions(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    canvas.set_layers(labels=True, captions=False)
    assert canvas.caption_items() == [] and is_red(pixel(canvas, 100, 25))
    canvas.set_layers(labels=False, captions=True)
    assert not is_red(pixel(canvas, 100, 25))


def test_no_image_shows_why(canvas):
    canvas.set_image(None, "cannot decode bad/images/corrupt.jpg")
    assert canvas.message == "cannot decode bad/images/corrupt.jpg" and canvas.image_size is None
    origin = canvas.mapFromScene(QPointF(0, 0))
    assert canvas.viewport().rect().contains(origin)
    image = shot(canvas)
    light = sum(QColor(image.pixel(origin.x() + dx, origin.y() + dy)).red() > 150
                for dx in range(0, 120) for dy in range(0, 14))
    assert light > 20


def test_a_new_image_drops_the_old_boxes(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    canvas.set_image(grey_image())
    assert canvas.caption_items() == [] and not is_red(pixel(canvas, 100, 25))


def test_fit_and_zoom(canvas):
    canvas.set_image(grey_image())
    assert canvas.transform().m11() == pytest.approx(2.0, rel=0.05)
    canvas.zoom_by(2)
    assert canvas.transform().m11() == pytest.approx(4.0, rel=0.05)
    canvas.fit()
    assert canvas.transform().m11() == pytest.approx(2.0, rel=0.05)


def test_resizing_refits_until_the_user_zooms(qtbot, canvas):
    canvas.set_image(grey_image())
    canvas.resize(800, 600)
    qtbot.waitUntil(lambda: canvas.transform().m11() == pytest.approx(4.0, rel=0.05))
    canvas.zoom_by(1.5)
    scale = canvas.transform().m11()
    canvas.resize(400, 300)
    qtbot.wait(20)
    assert canvas.transform().m11() == pytest.approx(scale)


def send(widget, kind, button, pos):
    buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else button
    event = QMouseEvent(kind, QPointF(pos), widget.mapToGlobal(QPointF(pos)), button, buttons, Qt.NoModifier)
    QApplication.sendEvent(widget, event)


def test_a_middle_drag_pans(canvas):
    canvas.set_image(grey_image())
    canvas.zoom_by(4)
    before = canvas.horizontalScrollBar().value()
    vp = canvas.viewport()
    send(vp, QEvent.MouseButtonPress, Qt.MiddleButton, QPoint(200, 150))
    send(vp, QEvent.MouseMove, Qt.MiddleButton, QPoint(150, 150))
    send(vp, QEvent.MouseButtonRelease, Qt.MiddleButton, QPoint(150, 150))
    assert canvas.horizontalScrollBar().value() == before + 50
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_canvas.py`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.ui.canvas'`.

- [ ] **Step 3: Write the canvas**

Create `src/deeplabeling/ui/canvas.py`:

```python
"""The canvas: the whole frame and its labels (docs/design/2026-10-04-app-foundation.md#window).

Scene coordinates are image pixels. Plan 1b draws and navigates; plan 1c adds editing.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from .boxes import BoxView
from .classes import text_color

BACKGROUND = "#2b2b2b"


class CaptionItem(QGraphicsItem):
    """A caption on a solid plate, inside its box's top edge. It ignores the view's
    zoom, so it stays readable; the plate keeps it legible on any image."""

    def __init__(self, text: str, color: str):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.text, self.color = text, QColor(color)
        self._font = QFont()
        self._font.setPointSize(9)
        metrics = QFontMetricsF(self._font)
        self._rect = QRectF(0, 0, metrics.horizontalAdvance(text) + 6, metrics.height() + 2)

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.fillRect(self._rect, self.color)
        painter.setPen(QColor(text_color(self.color.name())))
        painter.setFont(self._font)
        painter.drawText(self._rect.adjusted(3, 0, -3, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text)


class Canvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor(BACKGROUND))
        self.setFocusPolicy(Qt.NoFocus)             # keys belong to the window's actions
        self._pixmap = QGraphicsPixmapItem()
        self._pixmap.setTransformationMode(Qt.SmoothTransformation)
        self.scene().addItem(self._pixmap)
        self._message = QGraphicsSimpleTextItem()
        self._message.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self._message.setBrush(QColor("#e0e0e0"))
        self.scene().addItem(self._message)
        self._items: list[QGraphicsItem] = []
        self._views: list[BoxView] = []
        self._size: tuple[int, int] | None = None
        self.show_labels = True
        self.show_captions = True
        self._fitted = True
        self._pan_from = None

    # -- what is shown -----------------------------------------------------------

    @property
    def image_size(self) -> tuple[int, int] | None:
        return self._size

    @property
    def message(self) -> str:
        return self._message.text() if self._message.isVisible() else ""

    def set_image(self, image: QImage | None, message: str = "") -> None:
        """Show an image, fitted to the view; or no image and a message saying why."""
        self._views = []
        self._clear()
        if image is None:
            self._pixmap.setPixmap(QPixmap())
            self._size = None
            self._message.setText(message)
            self._message.setVisible(bool(message))
            self.scene().setSceneRect(QRectF(0, 0, 1, 1))
            self.resetTransform()
            self._message.setPos(0, 0)
            self.centerOn(0, 0)
            return
        self._message.setVisible(False)
        self._pixmap.setPixmap(QPixmap.fromImage(image))
        self._size = (image.width(), image.height())
        self.scene().setSceneRect(QRectF(0, 0, image.width(), image.height()))
        self.fit()

    def set_boxes(self, views: list[BoxView]) -> None:
        self._views = list(views)
        self._redraw()

    def set_layers(self, *, labels: bool, captions: bool) -> None:
        self.show_labels, self.show_captions = labels, captions
        self._redraw()

    def caption_items(self) -> list[CaptionItem]:
        return [it for it in self._items if isinstance(it, CaptionItem)]

    def _clear(self) -> None:
        for item in self._items:
            self.scene().removeItem(item)
        self._items = []

    def _redraw(self) -> None:
        self._clear()
        if not self.show_labels or self._size is None:
            return
        for view in self._views:
            self._draw(view)

    def _draw(self, view: BoxView) -> None:
        pen = QPen(QColor(view.color))
        pen.setCosmetic(True)                       # the same width at every zoom
        pen.setWidth(4 if view.highlighted else 2)
        if not view.known:
            pen.setStyle(Qt.DashLine)
        x1, y1, x2, y2 = view.rect
        if view.polygon:
            shape = self.scene().addPolygon(QPolygonF([QPointF(x, y) for x, y in view.polygon]), pen)
        else:
            shape = self.scene().addRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)), pen)
        shape.setZValue(1)
        self._items.append(shape)
        if self.show_captions:
            caption = CaptionItem(view.caption, view.color)
            caption.setPos(x1, y1)
            caption.setZValue(2)
            self.scene().addItem(caption)
            self._items.append(caption)

    # -- zoom and pan --------------------------------------------------------------

    def fit(self) -> None:
        if self._size is not None:
            self.fitInView(self._pixmap, Qt.KeepAspectRatio)
            self._fitted = True

    def zoom_by(self, factor: float) -> None:
        if self._size is not None:
            self.scale(factor, factor)
            self._fitted = False

    def wheelEvent(self, event) -> None:
        self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fitted:
            self.fit()

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = event.position().toPoint()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pan_from is not None:
            point = event.position().toPoint()
            delta, self._pan_from = point - self._pan_from, point
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._fitted = False
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_from is not None and event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)
```

- [ ] **Step 4: Run the tests to see them pass, three times**

Run: `for i in 1 2 3; do /home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_canvas.py; done`
Expected: 11 passed, each time. Pixel tests that pass only sometimes are a finding, not noise.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: all pass.

```bash
git add src/deeplabeling/ui/canvas.py tests/ui/test_canvas.py
git commit -m "ui: the canvas draws the frame, boxes and captions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The notice strip, the queue panel and the inspector

**Files:**
- Create: `src/deeplabeling/ui/notices.py`, `src/deeplabeling/ui/queue_panel.py`, `src/deeplabeling/ui/inspector.py`
- Test: `tests/ui/test_notices.py`, `tests/ui/test_panels.py`

**Interfaces:**
- Consumes: `Session` (Task 3); `box_views` and `class_infos` (Task 1); `CLASS_COLORS` and `CLASS_HOTKEYS` (core workspace); `LabelState`.
- Produces in `deeplabeling.ui.notices`:
  - `COLORS` and `MAX_ROWS = 6`;
  - `NoticeRow`, with the signal `dismissed`, and `.level`, `.text`, `.image`, `.key`, `.label` and `.close_button`;
  - `NoticeStrip`, with `.add(level, text, image=None, key=None)`, `.texts()`, `.clear_image(images)`, `.clear_key(key)`, `.clear()` and `.rows`.
- Produces in `deeplabeling.ui.queue_panel`: `QueueModel(session)`, and `QueuePanel(session)` with `.title`, `.model` and `.view`.
- Produces in `deeplabeling.ui.inspector`:
  - `swatch(color)`;
  - `Inspector(session)`, with `.path_label`, `.size_label`, `.state_label`, `.unparsed_label`, `.reviewed_label`, `.classes`, `.boxes` and `.refresh()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_notices.py`:

```python
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from deeplabeling.ui.notices import MAX_ROWS, NoticeStrip


@pytest.fixture
def strip(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    s = NoticeStrip()
    layout.addWidget(s)
    layout.addWidget(QWidget(), 1)
    host.resize(600, 300)
    host.show()
    qtbot.waitUntil(host.isVisible)
    yield s                 # the generator frame keeps `host`, the strip's parent, alive


def test_a_notice_is_visible_with_its_text(qtbot, strip):
    assert not strip.isVisible()
    strip.add("error", "camA/images/0001.jpg: this image already has a label file")
    qtbot.waitUntil(strip.isVisible)
    [row] = strip.rows
    assert row.label.isVisible() and row.label.text().endswith("already has a label file")
    assert row.geometry().height() > 0 and strip.rect().contains(row.geometry())


def test_newest_first_and_only_so_many(strip):
    for i in range(MAX_ROWS + 2):
        strip.add("info", f"n{i}")
    assert strip.texts() == [f"n{i}" for i in range(MAX_ROWS + 1, 1, -1)]


def test_a_keyed_notice_replaces_its_predecessor_and_empty_text_removes_it(strip):
    strip.add("warning", "12 boxes have ids ≥ 4", key="out-of-range")
    strip.add("warning", "3 boxes have ids ≥ 4", key="out-of-range")
    assert strip.texts() == ["3 boxes have ids ≥ 4"]
    strip.add("warning", "", key="out-of-range")
    assert strip.texts() == [] and not strip.isVisible()


def test_a_successful_edit_clears_that_images_refusals_only(strip):
    a, b = Path("/d/a.jpg"), Path("/d/b.jpg")
    strip.add("error", "a refused", image=a)
    strip.add("error", "b refused", image=b)
    strip.add("warning", "standing", image=a, key="k")
    strip.clear_image([a])
    assert strip.texts() == ["standing", "b refused"]


def test_dismissing_removes_and_an_empty_strip_hides(qtbot, strip):
    strip.add("error", "refused")
    qtbot.mouseClick(strip.rows[0].close_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: not strip.isVisible())
    assert strip.rows == []
```

Create `tests/ui/test_panels.py`:

```python
"""The queue panel and the inspector, shown and read back."""

import pytest
from PySide6.QtCore import Qt

from deeplabeling.ui.inspector import Inspector
from deeplabeling.ui.queue_panel import QueuePanel


@pytest.fixture
def panel(qtbot, session):
    p = QueuePanel(session)
    qtbot.addWidget(p)
    p.resize(360, 500)
    p.show()
    qtbot.waitUntil(p.isVisible)
    return p


@pytest.fixture
def inspector(qtbot, session):
    i = Inspector(session)
    qtbot.addWidget(i)
    i.resize(320, 600)
    i.show()
    qtbot.waitUntil(i.isVisible)
    return i


def row_text(panel, row):
    return panel.model.index(row).data(Qt.DisplayRole)


def test_the_panel_lists_the_queue_with_badges(panel):
    assert panel.model.rowCount() == 15 and panel.title.text() == "Queue · 15"
    assert row_text(panel, 0) == "· camA/images/0001.jpg  —  2 boxes"
    assert row_text(panel, 2) == "· camA/images/0003.jpg  —  missing"
    rect = panel.view.visualRect(panel.model.index(0))
    assert rect.height() > 0 and panel.view.viewport().rect().contains(rect.center())


def test_the_selection_follows_the_cursor(panel, session):
    session.move(3)
    assert panel.view.currentIndex().row() == 3


def test_clicking_a_row_moves_the_cursor(qtbot, panel, session):
    rect = panel.view.visualRect(panel.model.index(4))
    qtbot.mouseClick(panel.view.viewport(), Qt.LeftButton, pos=rect.center())
    assert session.current().key == "camA/images/sub/0005.jpg"


def test_a_reviewed_row_shows_its_tick(panel, session):
    session.done_and_next()
    assert row_text(panel, 0).startswith("✓ camA/images/0001.jpg")


def test_the_inspector_describes_the_current_image(qtbot, inspector, session):
    qtbot.waitUntil(lambda: inspector.size_label.text() == "64 × 48")
    assert inspector.path_label.text() == "camA/images/0001.jpg"
    assert inspector.state_label.text() == "2 boxes" and inspector.reviewed_label.text() == "not yet"
    assert [inspector.classes.item(i).text() for i in range(4)] == [
        "1   person   1", "2   car   1", "3   bus_m   0", "4   bus_l   0"]
    qtbot.waitUntil(lambda: inspector.boxes.count() == 2)
    assert inspector.boxes.item(0).text() == "person   13 × 14 px"


def test_the_inspector_follows_the_cursor_and_marks(qtbot, inspector, session):
    session.go_to("camA/images/0003.jpg")
    assert inspector.state_label.text() == "no label file"
    session.toggle_reviewed()
    assert inspector.reviewed_label.text() != "not yet"


def test_the_inspector_says_when_an_image_cannot_be_decoded(qtbot, inspector, session):
    session.go_to("bad/images/corrupt.jpg")
    qtbot.waitUntil(lambda: inspector.size_label.text().startswith("cannot decode"))


def test_new_rows_do_not_scroll_the_list(panel, session, monkeypatch):
    calls = []
    monkeypatch.setattr(panel.view, "scrollTo", lambda *a: calls.append(a))
    for _ in range(5):
        session.queueGrew.emit()           # a building queue grows; the cursor stays
    assert calls == []
    session.move(1)
    assert len(calls) == 1


def test_the_inspector_says_a_shared_label_file_is_read_only(qtbot, inspector, session):
    session.go_to("camB/images/twin.jpg")
    assert inspector.state_label.text().startswith("read-only: another image uses the same label file")
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_notices.py tests/ui/test_panels.py`
Expected: `ModuleNotFoundError` for `deeplabeling.ui.notices`, `.queue_panel` and `.inspector`.

- [ ] **Step 3: Write the widgets**

Create `src/deeplabeling/ui/notices.py`:

```python
"""The notice strip (docs/design/2026-10-04-app-foundation.md#window): every refusal and
error stays above the canvas until it is dismissed, or the next edit of its image
succeeds. Progress never comes here -- in the legacy app, a refusal shown in the status
bar was overwritten by progress within 150 ms."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

COLORS = {"error": "#5c1f1f", "warning": "#5c4a1f", "info": "#1f3a5c"}
#: The most notices shown at once; older ones go first.
MAX_ROWS = 6


class NoticeRow(QFrame):
    dismissed = Signal(object)

    def __init__(self, level: str, text: str, image: Path | None, key: str | None, parent=None):
        super().__init__(parent)
        self.level, self.text, self.image, self.key = level, text, image, key
        self.setObjectName("notice")
        self.setStyleSheet(f"#notice {{ background: {COLORS.get(level, COLORS['info'])}; }}"
                           " QLabel { color: #f0f0f0; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 4, 3)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        close = QToolButton()
        close.setText("×")
        close.setAutoRaise(True)
        close.setFocusPolicy(Qt.NoFocus)
        close.clicked.connect(lambda: self.dismissed.emit(self))
        layout.addWidget(self.label, 1)
        layout.addWidget(close)
        self.close_button = close


class NoticeStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(1)
        self.rows: list[NoticeRow] = []
        self.hide()

    def add(self, level: str, text: str, image: Path | None = None, key: str | None = None) -> None:
        """Show a notice, newest first. A keyed notice replaces the one with its key;
        a keyed notice with no text just removes it."""
        if key is not None:
            self.clear_key(key)
        if not text:
            return
        row = NoticeRow(level, text, image, key, self)
        row.dismissed.connect(self._remove)
        self.rows.insert(0, row)
        self._layout.insertWidget(0, row)
        row.show()              # a layout shows a new child of a visible parent only later
        while len(self.rows) > MAX_ROWS:
            self._remove(self.rows[-1])
        self.show()

    def texts(self) -> list[str]:
        return [row.text for row in self.rows]

    def clear_image(self, images: Iterable[Path]) -> None:
        images = set(images)
        for row in [r for r in self.rows if r.image is not None and r.image in images and r.key is None]:
            self._remove(row)

    def clear_key(self, key: str) -> None:
        for row in [r for r in self.rows if r.key == key]:
            self._remove(row)

    def clear(self) -> None:
        for row in list(self.rows):
            self._remove(row)

    def _remove(self, row: NoticeRow) -> None:
        if row in self.rows:
            self.rows.remove(row)
            self._layout.removeWidget(row)
            row.deleteLater()
        if not self.rows:
            self.hide()
```

Create `src/deeplabeling/ui/queue_panel.py`:

```python
"""The queue panel (docs/design/2026-10-04-app-foundation.md#window): a virtualised list
of the queue, whose selection mirrors the session's cursor -- there is no second notion
of the current item. Plan 1c adds the grid."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtWidgets import QAbstractItemView, QLabel, QListView, QVBoxLayout, QWidget

from .session import Session


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


class QueuePanel(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self.title = QLabel()
        self.model = QueueModel(session, self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setFocusPolicy(Qt.NoFocus)         # arrows belong to the window's actions
        self.view.clicked.connect(lambda index: session.go_to(index.data(Qt.UserRole)))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.title)
        layout.addWidget(self.view, 1)
        for signal in (session.queueReset, session.queueGrew, session.queueDone, session.closed):
            signal.connect(self._retitle)
        # Follow cursor moves only. Following every batch scrolled the view as each one
        # arrived, re-laying out every row so far: 5 s of a 9 s launch on pvn-vehicle.
        session.cursorChanged.connect(self._follow)
        self._retitle()
        self._follow()

    def _retitle(self) -> None:
        queue = self._session.queue
        if queue is None:
            self.title.setText("Queue")
        else:
            building = "" if queue.complete else " · building…"
            self.title.setText(f"Queue · {len(queue):,}{building}")

    def _follow(self) -> None:
        queue = self._session.queue
        row = queue.position() if queue is not None else None
        if row is None or row >= self.model.rowCount():
            self.view.clearSelection()
            return
        self.view.setCurrentIndex(self.model.index(row))     # which also scrolls to it
```

Create `src/deeplabeling/ui/inspector.py`:

```python
"""The inspector (docs/design/2026-10-04-app-foundation.md#window): the current image, its
classes and its boxes. Read-only in plan 1b; plan 1c makes the palette and the box list
act on the selection."""

from __future__ import annotations

import time
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QFormLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..core.store import LabelState
from ..core.workspace import CLASS_COLORS, CLASS_HOTKEYS
from .boxes import box_views
from .classes import class_infos
from .session import Session


def swatch(color: str) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class Inspector(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label = (
            QLabel() for _ in range(5))
        for label in self._fields():
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form = QFormLayout()
        form.addRow("Image", self.path_label)
        form.addRow("Size", self.size_label)
        form.addRow("Labels", self.state_label)
        form.addRow("Unparsable lines", self.unparsed_label)
        form.addRow("Reviewed", self.reviewed_label)
        self.classes = QListWidget()
        self.boxes = QListWidget()
        for widget in (self.classes, self.boxes):
            widget.setFocusPolicy(Qt.NoFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(form)
        layout.addWidget(QLabel("Classes"))
        layout.addWidget(self.classes, 1)
        layout.addWidget(QLabel("Boxes"))
        layout.addWidget(self.boxes, 1)
        for signal in (session.cursorChanged, session.reviewChanged, session.opened, session.closed):
            signal.connect(self.refresh)
        session.labelsChanged.connect(lambda images: self.refresh())
        session.images.ready.connect(self._image_event)
        session.images.failed.connect(lambda path, why: self._image_event(path))
        self.refresh()

    def _fields(self) -> tuple[QLabel, ...]:
        # *_label names: a field called `size` would shadow QWidget.size()
        return (self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label)

    def _image_event(self, path) -> None:
        item = self._session.current()
        if item is not None and item.entry.path == path:
            self.refresh()

    def refresh(self) -> None:
        session, item = self._session, self._session.current()
        self.classes.clear()
        self.boxes.clear()
        if session.workspace is None or item is None:
            for label in self._fields():
                label.setText("—")
            return
        ws, entry = session.workspace, item.entry
        labels = session.labels(entry)
        image, why = session.images.get(entry.path), session.images.error(entry.path)
        self.path_label.setText(entry.rel)
        self.size_label.setText(f"cannot decode: {why}" if why else
                          f"{image.width()} × {image.height()}" if image is not None else "decoding…")
        self.state_label.setText(self._state_text(labels))
        self.unparsed_label.setText(str(labels.unparsed))
        marked = ws.review.marked_at(entry.rel)
        self.reviewed_label.setText(time.strftime("%Y-%m-%d %H:%M", time.localtime(marked)) if marked else "not yet")
        colors = ws.root_settings.get(CLASS_COLORS)
        counts = Counter(line.cls_id for _, line in labels.boxes)
        for info in class_infos(ws.dataset, colors, ws.root_settings.get(CLASS_HOTKEYS)):
            row = QListWidgetItem(swatch(info.color), f"{info.hotkey or ' '}   {info.name}   {counts.get(info.cls_id, 0)}")
            self.classes.addItem(row)
        if image is not None:
            for view in box_views(labels, ws.dataset, (image.width(), image.height()), colors):
                x1, y1, x2, y2 = view.rect
                self.boxes.addItem(QListWidgetItem(swatch(view.color),
                                                   f"{view.caption}   {round(x2 - x1)} × {round(y2 - y1)} px"))

    @staticmethod
    def _state_text(labels) -> str:
        if labels.state is LabelState.ERROR:
            return labels.error
        if labels.state is LabelState.SHARED:
            return f"read-only: {labels.error}"
        if labels.raw is None:
            return "no label file"
        if labels.negative:
            return "negative sample (no boxes)"
        n = len(labels.boxes)
        return f"{n} box" if n == 1 else f"{n} boxes"
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_notices.py tests/ui/test_panels.py`
Expected: 14 passed. Two of them pin the plan's findings:
- `test_new_rows_do_not_scroll_the_list`: following every batch made launch take 7.4 s.
- `test_the_panel_lists_the_queue_with_badges`: the panel is built over an already-built queue.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: all pass.

```bash
git add src/deeplabeling/ui tests/ui
git commit -m "ui: the notice strip, the queue panel and the inspector" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The state bar, the queue editor and the keymap

**Files:**
- Create: `src/deeplabeling/ui/state_bar.py`, `src/deeplabeling/ui/queue_editor.py`, `src/deeplabeling/ui/keymap.py`
- Test: `tests/ui/test_state_bar.py`, `tests/ui/test_queue_editor.py`, `tests/ui/test_keymap.py`

**Interfaces:**
- Consumes: `Session` (Task 3); `HasClass`, `ImageFilter`, `LabelStateIs`, `NameContains` and `Reviewed` (core queue); `Dataset`.
- Produces in `deeplabeling.ui.state_bar`:
  - `REFRESH_MS = 250`;
  - `Chip`, with `.full_text` and `.set_full_text(text)`;
  - `StateBar(session)`, with the chips `.dataset`, `.queue`, `.layers` and `.reviewed`, `.refresh()`, and the coalescing timer `._soon`.
- Produces in `deeplabeling.ui.queue_editor`:
  - `CLASS_MODES`, `LABEL_MODES` and `REVIEW_MODES`;
  - `QueueEditor(dataset, current)`, with the widgets `.splits` (a dict), `.class_mode`, `.classes`, `.label_mode`, `.review_mode` and `.name`, and `.filter() -> ImageFilter`.
- Produces in `deeplabeling.ui.keymap`:
  - `ActionSpec(id, text, keys, checkable=False)` and `ACTIONS`;
  - `build_actions(window, handlers) -> dict[str, QAction]`;
  - `help_rows()`;
  - `HelpDialog`, with `.table`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_state_bar.py`:

```python
import pytest
from PySide6.QtCore import QPoint, QRect

from deeplabeling.ui.session import Session
from deeplabeling.ui.state_bar import StateBar
from fixtures import FakePrompter


def shown(qtbot, widget, width=900):
    qtbot.addWidget(widget)
    widget.resize(width, 40)
    widget.show()
    qtbot.waitUntil(widget.isVisible)
    return widget


def chips(bar):
    return (bar.dataset, bar.queue, bar.layers, bar.reviewed)


def test_the_chips_say_what_is_in_force(qtbot, session):
    bar = shown(qtbot, StateBar(session), 1400)
    assert bar.dataset.full_text == "ds · data.yaml · train + val · 15 images"
    assert bar.queue.full_text == "Queue: all images · 15 · 15 left"
    assert bar.reviewed.full_text == "Reviewed 0 / 15"
    assert bar.layers.full_text == "Layers: none"
    session.done_and_next()
    assert bar.reviewed.full_text == "Reviewed 1 / 15"
    assert bar.queue.full_text == "Queue: all images · 15 · 14 left"


def test_without_a_dataset_the_chip_invites_one(qtbot):
    bar = shown(qtbot, StateBar(Session(FakePrompter())))
    assert bar.dataset.full_text == "No dataset · open one"


def test_a_narrow_bar_elides_but_shows_every_chip(qtbot, session):
    bar = shown(qtbot, StateBar(session), 420)
    for chip in chips(bar):
        rect = QRect(chip.mapTo(bar, QPoint(0, 0)), chip.size())
        assert chip.isVisible() and chip.width() >= 40 and bar.rect().contains(rect)
        assert chip.toolTip() == chip.full_text
    assert bar.dataset.text().endswith("…")


def test_a_growing_queue_refreshes_the_bar_at_most_once_per_interval(qtbot, session, monkeypatch):
    bar = shown(qtbot, StateBar(session), 1400)
    refreshes = []
    monkeypatch.setattr(bar, "refresh", lambda: refreshes.append(1))
    bar._soon.timeout.disconnect()
    bar._soon.timeout.connect(bar.refresh)
    for _ in range(20):
        session.queueGrew.emit()
    assert refreshes == []
    qtbot.waitUntil(lambda: refreshes == [1], timeout=2000)
```

Create `tests/ui/test_queue_editor.py`:

```python
import pytest
from PySide6.QtCore import Qt

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.queue import HasClass, ImageFilter, LabelStateIs, NameContains, Reviewed
from deeplabeling.ui.queue_editor import QueueEditor


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


def editor(qtbot, dataset, current):
    dialog = QueueEditor(dataset, current)
    qtbot.addWidget(dialog)
    return dialog


@pytest.mark.parametrize("current", [
    ImageFilter(),
    ImageFilter(("val",), (HasClass(("car", "bus_l")), LabelStateIs("boxes"),
                           Reviewed(False), NameContains("cam"))),
    ImageFilter(conditions=(HasClass(("person",), present=False), LabelStateIs("missing"))),
])
def test_the_editor_is_seeded_from_the_queue_in_force(qtbot, dataset, current):
    assert editor(qtbot, dataset, current).filter() == current


def test_choosing_has_without_a_class_adds_no_condition(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.class_mode.setCurrentText("has")
    assert dialog.filter() == ImageFilter()


def test_the_widgets_build_the_filter(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.splits["train"].setChecked(False)
    dialog.class_mode.setCurrentText("lacks")
    dialog.classes.item(1).setCheckState(Qt.Checked)
    dialog.review_mode.setCurrentText("not reviewed")
    dialog.name.setText("  seg ")
    assert dialog.filter() == ImageFilter(("val",), (HasClass(("car",), present=False),
                                                     Reviewed(False), NameContains("seg")))
```

Create `tests/ui/test_keymap.py`:

```python
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QWidget

from deeplabeling.ui.keymap import ACTIONS, HelpDialog, build_actions, help_rows


def test_action_ids_are_unique_and_no_key_is_bound_twice():
    ids = [spec.id for spec in ACTIONS]
    keys = [QKeySequence(k).toString() for spec in ACTIONS for k in spec.keys]
    assert len(ids) == len(set(ids)) and len(keys) == len(set(keys))


def test_a_shortcut_runs_its_handler(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    hits = []
    handlers = {spec.id: (lambda i=spec.id: hits.append(i)) for spec in ACTIONS if not spec.checkable}
    actions = build_actions(host, handlers)
    with qtbot.waitActive(host):        # window shortcuts need the active window
        host.show()
        host.activateWindow()
    qtbot.keyClick(host, Qt.Key_K)
    qtbot.keyClick(host, Qt.Key_Space)
    qtbot.keyClick(host, Qt.Key_Z, Qt.ControlModifier)
    assert hits == ["toggle_reviewed", "done_next", "undo"]
    assert actions["toggle_labels"].shortcut() == QKeySequence("L")


def test_every_handler_is_required():
    with pytest.raises(KeyError):
        build_actions(QWidget(), {})


def test_the_help_lists_every_action(qtbot):
    dialog = HelpDialog()
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == len(ACTIONS) == len(help_rows())
    assert dialog.table.item(2, 1).text().startswith("Done & next")
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_state_bar.py tests/ui/test_queue_editor.py tests/ui/test_keymap.py`
Expected: `ModuleNotFoundError` for `deeplabeling.ui.state_bar`, `.queue_editor` and `.keymap`.

- [ ] **Step 3: Write the modules**

Create `src/deeplabeling/ui/state_bar.py`:

```python
"""The state bar (docs/design/2026-10-04-app-foundation.md#window): a row of chips, always
visible, each showing a setting in force; clicking a chip changes it."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QMenu, QSizePolicy, QToolButton, QWidget

from .session import Session

#: The fewest milliseconds between refreshes while a queue builds.
REFRESH_MS = 250


class Chip(QToolButton):
    """Its whole text when it fits, elided when not, and the whole text as its tooltip:
    a chip squeezed by a narrow window still shows that its setting exists."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAutoRaise(False)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._full = ""

    @property
    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 28, hint.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(48, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        room = max(self.width() - 20, 16)
        self.setText(self.fontMetrics().elidedText(self._full, Qt.ElideRight, room))


class StateBar(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self.dataset, self.queue, self.layers, self.reviewed = Chip(), Chip(), Chip(), Chip()
        self.dataset.setPopupMode(QToolButton.InstantPopup)
        self.dataset.setMenu(QMenu(self.dataset))
        self.layers.setPopupMode(QToolButton.InstantPopup)
        self.layers.setMenu(QMenu(self.layers))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        for chip, stretch in ((self.dataset, 3), (self.queue, 4), (self.layers, 1), (self.reviewed, 1)):
            layout.addWidget(chip, stretch)
        for signal in (session.opened, session.closed, session.queueReset,
                       session.queueDone, session.reviewChanged):
            signal.connect(self.refresh)
        # A building queue grows every 0.2 s, and each refresh counts what is left across
        # the whole queue; while it builds, refresh at most every REFRESH_MS.
        self._soon = QTimer(self)
        self._soon.setSingleShot(True)
        self._soon.setInterval(REFRESH_MS)
        self._soon.timeout.connect(self.refresh)
        session.queueGrew.connect(self._soon.start)
        self.refresh()

    def refresh(self) -> None:
        session, ws = self._session, self._session.workspace
        if ws is None:
            self.dataset.set_full_text("No dataset · open one")
            self.queue.set_full_text("Queue: —")
            self.reviewed.set_full_text("Reviewed —")
        else:
            d = ws.dataset
            self.dataset.set_full_text(f"{d.root.name} · {d.source.name} · {' + '.join(d.splits)}"
                                       f" · {len(d.images):,} images")
            q = session.queue
            if q is None:
                self.queue.set_full_text("Queue: —")
            else:
                building = "" if q.complete else " · building…"
                self.queue.set_full_text(f"Queue: {q.source.describe(d)} · {len(q):,} · "
                                         f"{session.left():,} left{building}")
            marked, total = session.reviewed_counts()
            self.reviewed.set_full_text(f"Reviewed {marked:,} / {total:,}")
        shown = [a.text().lower() for a in self.layers.menu().actions() if a.isChecked()]
        self.layers.set_full_text("Layers: " + (", ".join(shown) if shown else "none"))
```

Create `src/deeplabeling/ui/queue_editor.py`:

```python
"""The queue editor: splits and conditions for slice 1's one source, ImageFilter
(docs/design/2026-10-04-app-foundation.md#queue). It is seeded from the queue in
force, so it never shows a filter the queue is not using (CLAUDE.md landmine 7)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.dataset import Dataset
from ..core.queue import HasClass, ImageFilter, LabelStateIs, NameContains, Reviewed

CLASS_MODES = ("any class", "has", "lacks")
LABEL_MODES = ("any", "missing", "negative", "boxes")
REVIEW_MODES = ("any", "reviewed", "not reviewed")


class QueueEditor(QDialog):
    def __init__(self, dataset: Dataset, current: ImageFilter, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Queue")
        self.splits = {name: QCheckBox(name) for name in dataset.splits}
        split_row = QWidget()
        row = QHBoxLayout(split_row)
        row.setContentsMargins(0, 0, 0, 0)
        for box in self.splits.values():
            row.addWidget(box)
        self.class_mode = QComboBox()
        self.class_mode.addItems(CLASS_MODES)
        self.classes = QListWidget()
        for name in dataset.names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.classes.addItem(item)
        self.label_mode = QComboBox()
        self.label_mode.addItems(LABEL_MODES)
        self.review_mode = QComboBox()
        self.review_mode.addItems(REVIEW_MODES)
        self.name = QLineEdit()
        form = QFormLayout()
        form.addRow("Splits", split_row)
        form.addRow("Classes", self.class_mode)
        form.addRow("", self.classes)
        form.addRow("Label file", self.label_mode)
        form.addRow("Reviewed", self.review_mode)
        form.addRow("Name contains", self.name)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._seed(current)

    def _seed(self, current: ImageFilter) -> None:
        for name, box in self.splits.items():
            box.setChecked(not current.splits or name in current.splits)
        for condition in current.conditions:
            if isinstance(condition, HasClass):
                self.class_mode.setCurrentText("has" if condition.present else "lacks")
                for i in range(self.classes.count()):
                    item = self.classes.item(i)
                    item.setCheckState(Qt.Checked if item.text() in condition.names else Qt.Unchecked)
            elif isinstance(condition, LabelStateIs):
                self.label_mode.setCurrentText(condition.state)
            elif isinstance(condition, Reviewed):
                self.review_mode.setCurrentText("reviewed" if condition.value else "not reviewed")
            elif isinstance(condition, NameContains):
                self.name.setText(condition.text)

    def filter(self) -> ImageFilter:
        """The queue the dialog describes. All splits checked means every split."""
        checked = tuple(name for name, box in self.splits.items() if box.isChecked())
        splits = () if len(checked) == len(self.splits) else checked
        conditions = []
        names = tuple(self.classes.item(i).text() for i in range(self.classes.count())
                      if self.classes.item(i).checkState() == Qt.Checked)
        if self.class_mode.currentText() != "any class" and names:
            conditions.append(HasClass(names, present=self.class_mode.currentText() == "has"))
        if self.label_mode.currentText() != "any":
            conditions.append(LabelStateIs(self.label_mode.currentText()))
        if self.review_mode.currentText() != "any":
            conditions.append(Reviewed(self.review_mode.currentText() == "reviewed"))
        if self.name.text().strip():
            conditions.append(NameContains(self.name.text().strip()))
        return ImageFilter(splits, tuple(conditions))
```

Create `src/deeplabeling/ui/keymap.py`:

```python
"""The one registry of actions and their keys (docs/design/2026-10-04-app-foundation.md#window).

The help dialog is generated from it, so the help cannot drift from the keys. Shortcuts
are window-wide; Qt keeps them quiet while a text field has focus. Plan 1c adds the
editing actions here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QDialog, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


@dataclass(frozen=True)
class ActionSpec:
    id: str
    text: str
    keys: tuple[str, ...]
    checkable: bool = False         #: bound to a setting by its owner, not to a handler


ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec("next", "Next item", ("Right", "Down")),
    ActionSpec("previous", "Previous item", ("Left", "Up")),
    ActionSpec("done_next", "Done & next: mark reviewed, go to the next item", ("Space",)),
    ActionSpec("toggle_reviewed", "Toggle reviewed", ("K",)),
    ActionSpec("mark_negative", "Mark negative (an image with no label file and no boxes)", ("N",)),
    ActionSpec("undo", "Undo", ("Ctrl+Z",)),
    ActionSpec("redo", "Redo", ("Ctrl+Shift+Z", "Ctrl+Y")),
    ActionSpec("fit", "Fit the image to the view", ("F",)),
    ActionSpec("zoom_in", "Zoom in", ("+", "=")),
    ActionSpec("zoom_out", "Zoom out", ("-",)),
    ActionSpec("toggle_labels", "Labels", ("L",), checkable=True),
    ActionSpec("toggle_captions", "Captions", ("T",), checkable=True),
    ActionSpec("go_to", "Go to an item by number or name", ("Ctrl+G",)),
    ActionSpec("help", "Shortcut help", ("?",)),
)


def build_actions(window: QWidget, handlers: Mapping[str, Callable[[], None]]) -> dict[str, QAction]:
    """One QAction per spec, added to `window`. Every non-checkable spec needs a handler."""
    actions = {}
    for spec in ACTIONS:
        action = QAction(spec.text, window)
        action.setShortcuts([QKeySequence(key) for key in spec.keys])
        action.setShortcutContext(Qt.WindowShortcut)
        if not spec.checkable:
            handler = handlers[spec.id]
            action.triggered.connect(lambda checked=False, h=handler: h())
        window.addAction(action)
        actions[spec.id] = action
    return actions


def help_rows() -> list[tuple[str, str]]:
    """(keys, what they do) for every action, in registry order."""
    return [(", ".join(QKeySequence(k).toString(QKeySequence.NativeText) for k in spec.keys),
             spec.text + (" (on / off)" if spec.checkable else "")) for spec in ACTIONS]


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shortcuts")
        rows = help_rows()
        self.table = QTableWidget(len(rows), 2)
        self.table.setHorizontalHeaderLabels(["Keys", "Action"])
        for i, (keys, text) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(keys))
            self.table.setItem(i, 1, QTableWidgetItem(text))
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        self.resize(560, 420)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_state_bar.py tests/ui/test_queue_editor.py tests/ui/test_keymap.py`
Expected: 13 passed. `test_a_growing_queue_refreshes_the_bar_at_most_once_per_interval` pins the second launch-time finding.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: all pass.

```bash
git add src/deeplabeling/ui tests/ui
git commit -m "ui: the state bar, the queue editor and the keymap" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The main window and every launch path

**Files:**
- Create: `src/deeplabeling/ui/prompter.py`, `src/deeplabeling/ui/main_window.py`
- Replace: `src/deeplabeling/__main__.py`, `tests/test_smoke.py`
- Modify: `docs/design/2026-10-02-project-init-plan.md` (one citation)
- Test: `tests/ui/test_main_window.py`, `tests/ui/test_launch.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces in `deeplabeling.ui.prompter`:
  - `taxonomy_question(last_source, last_names, source, names) -> str`;
  - `QtPrompter(parent=None)`, with `confirm_taxonomy`, `error`, `choose_yaml`, `choose_folder(title)`, `edit_queue(dataset, current)` and `ask_text(title, label)`.
- Produces in `deeplabeling.ui.main_window`:
  - `MIN_SIZE = (1024, 640)`;
  - `MainWindow(session, prompter)`.
    - Parts: `.state_bar`, `.notices`, `.canvas`, `.queue_panel`, `.queue_dock`, `.inspector`, `.inspector_dock` and `.status_text`.
    - `.actions`, a dict keyed by `ActionSpec.id`.
    - Methods: `.show_current()`, `.open_yaml()`, `.open_folder()`, `.edit_queue()`, `.go_to()` and `.show_help()`.
- Produces in `deeplabeling.__main__`: `parse_args(argv)`, `launch(argv, prompter=None) -> MainWindow` and `main(argv=None) -> int`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_main_window.py`:

```python
"""The assembled window, driven by keys and read back from what is on screen
(the run-and-verify-ui skill; CLAUDE.md landmine 4)."""

from itertools import combinations

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLineEdit

from deeplabeling.__main__ import launch
from deeplabeling.core.queue import HasClass, ImageFilter
from deeplabeling.ui.settings_ui import SHOW_LABELS
from fixtures import FakePrompter


def start(qtbot, argv, prompter=None):
    w = launch(argv, prompter or FakePrompter())
    qtbot.addWidget(w)
    w.resize(1440, 900)
    with qtbot.waitActive(w):
        w.show()
        w.activateWindow()
    if w.session.workspace is not None:
        qtbot.waitUntil(lambda: w.session.queue is not None and w.session.queue.complete)
        qtbot.waitUntil(lambda: w.canvas.image_size is not None)
    return w


@pytest.fixture
def window(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)])
    yield w
    w.close()


def on_screen(window, widget) -> QRect:
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


@pytest.mark.parametrize("size", [(1024, 640), (1920, 1080)])
def test_every_part_is_visible_inside_the_window_and_apart(qtbot, window, size):
    window.resize(*size)
    qtbot.waitUntil(lambda: (window.width(), window.height()) == size)
    window.notices.add("error", "a refusal stays here")
    parts = {"state bar": window.state_bar, "notices": window.notices, "canvas": window.canvas,
             "queue": window.queue_panel.view, "inspector": window.inspector}
    rects = {}
    for name, widget in parts.items():
        qtbot.waitUntil(widget.isVisible)
        rect = on_screen(window, widget)
        assert rect.width() > 0 and rect.height() > 0, name
        assert window.rect().contains(rect), name
        rects[name] = rect
    for a, b in combinations(rects, 2):
        assert not rects[a].intersects(rects[b]), (a, b)
    for chip in (window.state_bar.dataset, window.state_bar.queue,
                 window.state_bar.layers, window.state_bar.reviewed):
        assert chip.isVisible() and chip.width() >= 40
        assert window.rect().contains(on_screen(window, chip))


def test_the_canvas_shows_the_current_image_and_its_boxes(window):
    assert window.canvas.image_size == (64, 48)
    shot = window.canvas.viewport().grab().toImage()
    centre = window.canvas.mapFromScene(QPointF(32, 16.8))      # the person box's top edge
    near = [QColor(shot.pixel(centre.x() + dx, centre.y() + dy)) for dx in (-2, 0, 2) for dy in range(-2, 3)]
    assert any(c.red() > 200 and c.green() < 80 and 40 < c.blue() < 120 for c in near)  # #e6194b
    assert [c.text for c in window.canvas.caption_items()] == ["person", "car"]


def test_arrow_keys_page_without_marking(qtbot, window):
    for key in (Qt.Key_Right, Qt.Key_Right, Qt.Key_Down, Qt.Key_Left):
        qtbot.keyClick(window, key)
    assert window.session.current().key == "camA/images/0003.jpg"
    assert window.session.workspace.review.count() == 0
    assert window.status_text.text().startswith("camA/images/0003.jpg · ")


def test_space_marks_and_moves_and_k_toggles(qtbot, window):
    qtbot.keyClick(window, Qt.Key_Space)
    assert window.session.current().key == "camA/images/0002.jpg"
    assert window.state_bar.reviewed.full_text == "Reviewed 1 / 15"
    qtbot.keyClick(window, Qt.Key_K)
    assert window.state_bar.reviewed.full_text == "Reviewed 2 / 15"


def test_n_marks_a_missing_image_negative_and_ctrl_z_takes_it_back(qtbot, window, ds):
    window.session.go_to("camA/images/0003.jpg")
    qtbot.keyClick(window, Qt.Key_N)
    assert ds.lbl("camA/0003").read_bytes() == b""
    assert "↶ 1" in window.status_text.text()
    qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert not ds.lbl("camA/0003").exists()


def test_a_refusal_appears_in_the_visible_notice_strip(qtbot, window):
    qtbot.keyClick(window, Qt.Key_N)                # camA/0001 already has labels
    qtbot.waitUntil(window.notices.isVisible)
    row = next(r for r in window.notices.rows if "already has a label file" in r.text)
    assert row.label.isVisible() and window.rect().contains(on_screen(window, row.label))


def test_ids_the_yaml_does_not_name_stay_on_screen(qtbot, window):
    qtbot.waitUntil(lambda: any("does not name" in t for t in window.notices.texts()))
    assert window.notices.isVisible()


def test_an_undecodable_image_says_so_on_the_canvas_and_the_strip(qtbot, window):
    window.session.go_to("bad/images/corrupt.jpg")
    qtbot.waitUntil(lambda: window.canvas.message.startswith("Cannot decode bad/images/corrupt.jpg"))
    assert any("cannot be decoded" in t for t in window.notices.texts())


def test_layers_toggle_from_their_keys_and_persist(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_L)
    assert not window.canvas.show_labels and window.canvas.caption_items() == []
    assert window.session.settings.get(SHOW_LABELS) is False
    assert window.state_bar.layers.full_text == "Layers: captions"
    qtbot.keyClick(window, Qt.Key_T)
    assert window.state_bar.layers.full_text == "Layers: none"
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert not again.actions["toggle_labels"].isChecked() and not again.canvas.show_labels
    again.close()


def test_zoom_keys(qtbot, window):
    scale = window.canvas.transform().m11()
    qtbot.keyClick(window, Qt.Key_Equal)
    assert window.canvas.transform().m11() > scale
    qtbot.keyClick(window, Qt.Key_F)
    assert window.canvas.transform().m11() == pytest.approx(scale)
    qtbot.keyClick(window, Qt.Key_Minus)
    assert window.canvas.transform().m11() < scale


def test_ctrl_g_goes_to_an_item(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)], FakePrompter(text="poly"))
    qtbot.keyClick(w, Qt.Key_G, Qt.ControlModifier)
    assert w.session.current().key == "seg/images/poly1.jpg"
    w.close()


def test_the_queue_chip_edits_the_queue(qtbot, ds):
    chosen = ImageFilter(conditions=(HasClass(("bus_m",)),))
    w = start(qtbot, [str(ds.yaml)], FakePrompter(queue=chosen))
    with qtbot.waitSignal(w.session.queueDone, timeout=5000):
        qtbot.mouseClick(w.state_bar.queue, Qt.LeftButton)
    assert len(w.session.queue) == 3
    assert w.state_bar.queue.full_text.startswith("Queue: has bus_m · 3 · 3 left")
    w.close()


def test_the_help_key_shows_every_shortcut(qtbot, window):
    qtbot.keyClick(window, Qt.Key_Question)
    qtbot.waitUntil(lambda: window._help is not None and window._help.isVisible())


def test_no_shortcut_fires_while_a_text_field_has_focus(qtbot, window):
    field = QLineEdit()
    window.statusBar().addWidget(field)
    field.show()
    field.setFocus()
    qtbot.waitUntil(field.hasFocus)
    qtbot.keyClick(field, Qt.Key_K)
    qtbot.keyClick(field, Qt.Key_Space)
    assert window.session.workspace.review.count() == 0 and field.text() == "k "


def test_an_outside_edit_appears_on_the_canvas(qtbot, window, ds):
    assert [c.text for c in window.canvas.caption_items()] == ["person", "car"]
    ds.lbl("camA/0001").write_bytes(b"3 0.5 0.5 0.1 0.1\n")
    qtbot.waitUntil(lambda: [c.text for c in window.canvas.caption_items()] == ["bus_l"], timeout=5000)


def test_rapid_paging_ends_on_the_current_image(qtbot, window):
    for _ in range(9):
        qtbot.keyClick(window, Qt.Key_Right)
    current = window.session.current()
    assert current.key == "weird/images/имя пробел.jpg"
    qtbot.waitUntil(lambda: window._shown == current.entry.path)
    qtbot.wait(200)                         # late decodes of skipped images arrive
    assert window._shown == current.entry.path
    assert window.status_text.text().startswith(current.key)


def test_closing_while_jobs_run_frees_the_root(qtbot, ds):
    w = launch([str(ds.yaml)], FakePrompter())
    qtbot.addWidget(w)
    w.show()
    w.close()                               # the queue build and the id count are running
    assert w.session.workspace is None
    again = start(qtbot, [str(ds.yaml)])    # the lock is free
    again.close()
```

Create `tests/ui/test_launch.py`:

```python
"""Every launch path reaches Session.open and restores the same per-dataset settings
(docs/design/2026-10-04-app-foundation.md#state-and-settings)."""

import shutil

import pytest

from deeplabeling.__main__ import launch, parse_args
from deeplabeling.core.queue import HasClass, ImageFilter
from deeplabeling.ui.prompter import QtPrompter, taxonomy_question
from fixtures import FakePrompter

BUS_M = ImageFilter(conditions=(HasClass(("bus_m",)),))


def start(qtbot, argv, prompter=None):
    w = launch(argv, prompter or FakePrompter())
    qtbot.addWidget(w)
    if w.session.workspace is not None:
        qtbot.waitUntil(lambda: w.session.queue is not None and w.session.queue.complete)
    return w


def leave_with_queue(qtbot, w, source):
    with qtbot.waitSignal(w.session.queueDone, timeout=5000):
        w.session.set_queue(source)
    w.close()


def test_arguments():
    args = parse_args(["/d/images", "--labels", "/d/lbl"])
    assert (args.dataset, args.labels) == ("/d/images", "/d/lbl")
    assert parse_args([]).dataset is None


def test_a_yaml_on_the_command_line(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)])
    assert w.session.current_source() == (str(ds.yaml), None)
    leave_with_queue(qtbot, w, BUS_M)
    again = start(qtbot, [str(ds.yaml)])
    assert again.session.queue.source == BUS_M
    again.close()


def test_an_image_folder_with_a_label_folder(qtbot, ds):
    frames, labels = ds.root / "frames", ds.root / "frame_labels"
    w = start(qtbot, [str(frames), "--labels", str(labels)])
    assert w.session.current_source() == (str(frames), str(labels))
    assert len(w.session.queue) == 1
    leave_with_queue(qtbot, w, ImageFilter(conditions=(HasClass(("0",), present=False),)))
    again = start(qtbot, [str(frames), "--labels", str(labels)])
    assert again.session.queue.source.conditions[0].present is False
    again.close()


def test_no_argument_reopens_the_last_dataset(qtbot, ds):
    leave_with_queue(qtbot, start(qtbot, [str(ds.yaml)]), BUS_M)
    w = start(qtbot, [])
    assert w.session.current_source() == (str(ds.yaml), None) and w.session.queue.source == BUS_M
    w.close()


def test_no_argument_and_the_last_dataset_gone_asks_for_one(qtbot, ds, tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(ds.root / "camA", copy / "camA")
    yml = copy / "data.yaml"
    yml.write_text(f"path: {copy}\ntrain: [camA/images]\nnames: [person, car]\n")
    start(qtbot, [str(yml)]).close()
    shutil.rmtree(copy)
    prompter = FakePrompter(yaml=ds.yaml)
    w = start(qtbot, [], prompter)
    qtbot.waitUntil(lambda: ("yaml",) in prompter.asked)
    qtbot.waitUntil(lambda: w.session.workspace is not None)
    assert w.session.current_source() == (str(ds.yaml), None)
    w.close()


def test_the_dataset_chip_opens_a_yaml_and_restores_its_settings(qtbot, ds):
    leave_with_queue(qtbot, start(qtbot, [str(ds.yaml)]), BUS_M)
    prompter = FakePrompter(yaml=ds.yaml)
    w = launch([str(ds.root / "camA/images")], prompter)
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.session.queueDone, timeout=5000):
        w.open_yaml()
    assert w.session.current_source() == (str(ds.yaml), None) and w.session.queue.source == BUS_M
    w.close()


def test_an_image_folder_without_images_in_its_path_asks_for_its_labels(qtbot, ds):
    prompter = FakePrompter(folders=[ds.root / "frames", ds.root / "frame_labels"])
    w = start(qtbot, [str(ds.yaml)], prompter)
    with qtbot.waitSignal(w.session.queueDone, timeout=5000):
        w.open_folder()
    assert w.session.current_source() == (str(ds.root / "frames"), str(ds.root / "frame_labels"))
    assert [a for a in prompter.asked if a[0] == "folder"] == [
        ("folder", "Image folder"), ("folder", "Label folder for these images")]
    w.close()


def test_a_dataset_that_cannot_open_says_why(qtbot, ds):
    prompter = FakePrompter()
    w = start(qtbot, [str(ds.root / "frames")], prompter)
    assert w.session.workspace is None
    assert "label folder" in prompter.errors[0][1]
    assert w.canvas.message.startswith("No dataset is open")
    w.close()


def test_the_real_taxonomy_question_names_both_yamls(monkeypatch):
    text = taxonomy_question("/d/data_13class.yaml", ["a"] * 13, "/d/data_7class.yaml", ("b",) * 7)
    assert "data_13class.yaml (13 classes" in text and "data_7class.yaml (7 classes" in text
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    assert QtPrompter().confirm_taxonomy("/d/a.yaml", ["a"], "/d/b.yaml", ("b",)) is True
```

Replace `tests/test_smoke.py` with:

```python
"""The window must be VISIBLE and render pixels, not merely exist.

The legacy app twice shipped a feature whose tests passed on widget state while
the user could not see it. Assert what is on screen.
"""

from deeplabeling.__main__ import launch
from fixtures import FakePrompter


def test_the_main_window_is_visible_and_titled(qtbot):
    window = launch([], FakePrompter())             # no dataset and no last one
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    assert window.windowTitle() == "DeepLabeling"
    assert window.width() >= 1024 and window.height() >= 640
    window.close()


def test_the_window_renders_pixels(qtbot):
    window = launch([], FakePrompter())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    image = window.grab().toImage()
    assert not image.isNull()
    assert (image.width(), image.height()) == (window.width(), window.height())
    window.close()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_main_window.py tests/ui/test_launch.py tests/test_smoke.py`
Expected: `ImportError: cannot import name 'launch' from 'deeplabeling.__main__'`.

- [ ] **Step 3: Write the prompter, the window and the entry point**

Create `src/deeplabeling/ui/prompter.py`:

```python
"""The real dialogs behind the Prompter the session and window use. Tests answer the same
calls with tests/fixtures.py's FakePrompter, so no test waits on a modal loop."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from ..core.dataset import Dataset
from ..core.queue import ImageFilter
from .queue_editor import QueueEditor


def _names(names) -> str:
    names = list(names)
    return ", ".join(names[:6]) + (", …" if len(names) > 6 else "")


def taxonomy_question(last_source: str, last_names, source: str, names) -> str:
    return (f"These label files were last opened with {Path(last_source).name} "
            f"({len(last_names)} classes: {_names(last_names)}).\n\n"
            f"You are opening them with {Path(source).name} "
            f"({len(names)} classes: {_names(names)}).\n\n"
            "A label file's ids mean one class list. Under the wrong one every name shown is "
            "wrong, and every edit writes wrong ids. Open with the new class list?")


class QtPrompter:
    def __init__(self, parent=None):
        self.parent = parent

    def confirm_taxonomy(self, last_source, last_names, source, names) -> bool:
        answer = QMessageBox.question(self.parent, "A different class list",
                                      taxonomy_question(last_source, last_names, source, names),
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes

    def error(self, title: str, text: str) -> None:
        QMessageBox.warning(self.parent, title, text)

    def choose_yaml(self) -> str | None:
        path, _ = QFileDialog.getOpenFileName(self.parent, "Open a dataset yaml", "",
                                              "Dataset yaml (*.yaml *.yml)")
        return path or None

    def choose_folder(self, title: str) -> str | None:
        return QFileDialog.getExistingDirectory(self.parent, title) or None

    def edit_queue(self, dataset: Dataset, current: ImageFilter) -> ImageFilter | None:
        dialog = QueueEditor(dataset, current, self.parent)
        return dialog.filter() if dialog.exec() == QDialog.Accepted else None

    def ask_text(self, title: str, label: str) -> str | None:
        text, ok = QInputDialog.getText(self.parent, title, label)
        return text if ok else None
```

Create `src/deeplabeling/ui/main_window.py`:

```python
"""The main window: layout A (docs/design/2026-10-04-app-foundation.md#window).

The state bar spans the top; the queue is docked left and the inspector right; the
notice strip sits above the canvas. Everything shown comes from the Session.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget

from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .canvas import Canvas
from .inspector import Inspector
from .keymap import HelpDialog, build_actions
from .notices import NoticeStrip
from .queue_panel import QueuePanel
from .session import Session
from .settings_ui import RECENT, SHOW_CAPTIONS, SHOW_LABELS, WINDOW_GEOMETRY, WINDOW_STATE, bind_toggle
from .state_bar import StateBar

MIN_SIZE = (1024, 640)


class MainWindow(QMainWindow):
    def __init__(self, session: Session, prompter, parent=None):
        super().__init__(parent)
        self.session, self.prompter = session, prompter
        self.setWindowTitle("DeepLabeling")
        self.setMinimumSize(*MIN_SIZE)
        self.resize(1440, 900)
        self.state_bar = StateBar(session)
        self.setMenuWidget(self.state_bar)          # spans the window, above the docks
        self.notices = NoticeStrip()
        self.canvas = Canvas()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.notices)
        layout.addWidget(self.canvas, 1)
        self.setCentralWidget(central)
        self.queue_panel = QueuePanel(session)
        self.queue_dock = self._dock("Queue", "queue", self.queue_panel, Qt.LeftDockWidgetArea)
        self.inspector = Inspector(session)
        self.inspector_dock = self._dock("Inspector", "inspector", self.inspector, Qt.RightDockWidgetArea)
        self.resizeDocks([self.queue_dock, self.inspector_dock], [280, 280], Qt.Horizontal)
        self.status_text = QLabel()
        self.statusBar().addWidget(self.status_text, 1)
        self._shown: Path | None = None
        self._written: float | None = None
        self._help: HelpDialog | None = None
        self.actions = build_actions(self, {
            "next": lambda: session.move(1),
            "previous": lambda: session.move(-1),
            "done_next": session.done_and_next,
            "toggle_reviewed": session.toggle_reviewed,
            "mark_negative": session.mark_negative,
            "undo": session.undo,
            "redo": session.redo,
            "fit": self.canvas.fit,
            "zoom_in": lambda: self.canvas.zoom_by(1.25),
            "zoom_out": lambda: self.canvas.zoom_by(0.8),
            "go_to": self.go_to,
            "help": self.show_help,
        })
        layers = self.state_bar.layers.menu()
        for key, setting in (("toggle_labels", SHOW_LABELS), ("toggle_captions", SHOW_CAPTIONS)):
            bind_toggle(self.actions[key], session.settings, setting, self._layers_changed)
            layers.addAction(self.actions[key])
        self._layers_changed()
        self.state_bar.dataset.menu().aboutToShow.connect(self._fill_dataset_menu)
        self.state_bar.queue.clicked.connect(self.edit_queue)
        session.cursorChanged.connect(self.show_current)
        session.opened.connect(self.show_current)
        session.closed.connect(self._closed)
        session.images.ready.connect(self._image_event)
        session.images.failed.connect(lambda path, why: self._image_event(path))
        session.labelsChanged.connect(self._labels_changed)
        session.historyChanged.connect(self._history_changed)
        session.reviewChanged.connect(self._update_status)
        session.notice.connect(lambda level, text, image: self.notices.add(level, text, image))
        session.standing.connect(lambda key, text: self.notices.add("warning", text, key=key))
        session.status.connect(lambda text: self.statusBar().showMessage(text, 4000))
        self._restore_layout()
        self.show_current()

    def _dock(self, title: str, name: str, widget: QWidget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)                    # saveState needs a name per dock
        dock.setWidget(widget)
        widget.setMinimumWidth(160)
        self.addDockWidget(area, dock)
        return dock

    # -- what is shown ---------------------------------------------------------------

    def show_current(self) -> None:
        session, item = self.session, self.session.current()
        if session.workspace is None:
            self._shown = None
            self.canvas.set_image(None, "No dataset is open: click the dataset chip to open one.")
        elif item is None:
            self._shown = None
            building = session.queue is not None and not session.queue.complete
            self.canvas.set_image(None, "Building the queue…" if building else "No images in this queue.")
        else:
            path = item.entry.path
            image, why = session.images.get(path), session.images.error(path)
            if why is not None:
                self._shown = None
                self.canvas.set_image(None, f"Cannot decode {item.key}: {why}")
                self.notices.add("error", f"{item.key}: the image cannot be decoded ({why}); "
                                 "its labels are not edited", image=path, key=f"decode:{item.key}")
            elif image is None:
                self._shown = None
                self.canvas.set_image(None, "Loading…")
            else:
                if self._shown != path:
                    self.canvas.set_image(image)
                    self._shown = path
                self._show_boxes()
        self._update_status()

    def _show_boxes(self) -> None:
        session, item = self.session, self.session.current()
        if item is None or self.canvas.image_size is None:
            return
        ws = session.workspace
        labels = session.labels(item.entry)
        highlight = session.queue.source.highlight(labels, ws.dataset)
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
                                        ws.root_settings.get(CLASS_COLORS), highlight))

    def _image_event(self, path) -> None:
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self.show_current()

    def _labels_changed(self, images) -> None:
        self.notices.clear_image(images)
        item = self.session.current()
        if item is not None and item.entry.path in set(images):
            self._show_boxes()
        self._update_status()

    def _history_changed(self) -> None:
        self._written = time.time()
        self._update_status()

    def _closed(self) -> None:
        self.notices.clear()
        self.show_current()

    def _layers_changed(self, _=None) -> None:
        self.canvas.set_layers(labels=self.actions["toggle_labels"].isChecked(),
                               captions=self.actions["toggle_captions"].isChecked())
        self.session.saver.schedule()
        self.state_bar.refresh()

    def _update_status(self) -> None:
        session, item = self.session, self.session.current()
        if item is None or session.workspace is None:
            self.status_text.setText("")
            return
        parts = [item.key]
        if self.canvas.image_size is not None and self._shown == item.entry.path:
            parts.append("{} × {}".format(*self.canvas.image_size))
        parts.append(f"item {session.queue.position() + 1:,} / {len(session.queue):,}")
        if self._written is not None:
            parts.append("written " + time.strftime("%H:%M:%S", time.localtime(self._written)))
        parts.append(f"↶ {session.workspace.history.depth}")
        self.status_text.setText(" · ".join(parts))

    # -- what the chips and keys do --------------------------------------------------

    def _fill_dataset_menu(self) -> None:
        menu = self.state_bar.dataset.menu()
        menu.clear()
        menu.addAction("Open dataset yaml…", self.open_yaml)
        menu.addAction("Open image folder…", self.open_folder)
        recent = self.session.settings.get(RECENT)
        if recent:
            menu.addSeparator()
        for entry in recent:
            name = Path(entry["source"])
            menu.addAction(f"{name.name} — {name.parent}",
                           lambda e=entry: self.session.open(e["source"], e["labels"]))

    def open_yaml(self) -> None:
        path = self.prompter.choose_yaml()
        if path:
            self.session.open(path)

    def open_folder(self) -> None:
        folder = self.prompter.choose_folder("Image folder")
        if not folder:
            return
        labels = None
        if "images" not in Path(folder).resolve().parts:
            labels = self.prompter.choose_folder("Label folder for these images")
            if not labels:
                return
        self.session.open(folder, labels)

    def edit_queue(self) -> None:
        if self.session.queue is None:
            return
        current = self.session.queue.source
        chosen = self.prompter.edit_queue(self.session.workspace.dataset, current)
        if chosen is not None and chosen != current:
            self.session.set_queue(chosen)

    def go_to(self) -> None:
        text = self.prompter.ask_text("Go to", "Item number, or part of its path:")
        if text:
            self.session.go_to_text(text)

    def show_help(self) -> None:
        self._help = HelpDialog(self)
        self._help.show()

    # -- the window's own state ----------------------------------------------------------

    def _restore_layout(self) -> None:
        settings = self.session.settings
        geometry, state = settings.get(WINDOW_GEOMETRY), settings.get(WINDOW_STATE)
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
        if state:
            self.restoreState(QByteArray.fromBase64(state.encode()))

    def closeEvent(self, event) -> None:
        settings = self.session.settings
        settings.set(WINDOW_GEOMETRY, bytes(self.saveGeometry().toBase64()).decode())
        settings.set(WINDOW_STATE, bytes(self.saveState().toBase64()).decode())
        self.session.close()
        self.session.saver.flush()
        super().closeEvent(event)
```

Replace `src/deeplabeling/__main__.py` with:

```python
"""Entry point: `python -m deeplabeling [DATASET] [--labels LABEL_DIR]`.

Every launch path reaches Session.open (docs/design/2026-10-04-app-foundation.md#state-and-settings):
a yaml, an image folder with an optional label folder, the last dataset when no argument
is given, or the open dialog when there is no last dataset or it is gone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.prompter import QtPrompter
from .ui.session import Session
from .ui.settings_ui import LAST_SOURCE


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="deeplabeling",
                                     description="Label and clean YOLO datasets.")
    parser.add_argument("dataset", nargs="?", help="a dataset yaml, or a folder of images")
    parser.add_argument("--labels", help="the label folder, for an image folder whose path "
                                         "has no 'images' folder in it")
    return parser.parse_args(argv)


def launch(argv: list[str], prompter=None) -> MainWindow:
    """Build the window and open what the arguments, or the last session, say."""
    args = parse_args(argv)
    prompter = prompter if prompter is not None else QtPrompter()
    session = Session(prompter)
    window = MainWindow(session, prompter)
    if isinstance(prompter, QtPrompter):
        prompter.parent = window
    if args.dataset:
        session.open(args.dataset, args.labels)
    else:
        last = session.settings.get(LAST_SOURCE)
        if last is not None and Path(last["source"]).exists():
            session.open(last["source"], last["labels"])
        else:
            QTimer.singleShot(0, window.open_yaml)
    return window


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = launch(sys.argv[1:] if argv is None else argv)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Fix the one doc citation of the removed `build_window`**

In `docs/design/2026-10-02-project-init-plan.md` (an executed plan, kept as history), replace the line:

````markdown
- Produces: `src/deeplabeling/__main__.py::build_window` → `QMainWindow` titled "DeepLabeling"; `src/deeplabeling/__main__.py::main` → `int` exit code.
````

with:

````markdown
- Produces: `build_window()` in `src/deeplabeling/__main__.py` → `QMainWindow` titled "DeepLabeling" (plan 1b replaced it with `src/deeplabeling/__main__.py::launch`); `src/deeplabeling/__main__.py::main` → `int` exit code.
````

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py -q`
Expected: no output, exit 0.

- [ ] **Step 5: Run the tests to see them pass, three times**

Run: `for i in 1 2 3; do /home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_main_window.py tests/ui/test_launch.py tests/test_smoke.py; done`
Expected: 29 passed, each time.

- [ ] **Step 6: Look at the window**

Save one screenshot at each size, and **open both and look**; the `run-and-verify-ui` skill requires it:

```bash
cat > /tmp/shot_1b.py <<'EOF'
import os, sys, tempfile
os.environ["DEEPLABELING_STATE_DIR"] = tempfile.mkdtemp(); os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path[:0] = ["src", "tests"]
from PySide6.QtWidgets import QApplication
from fixtures import FakePrompter, build_dataset
from deeplabeling.__main__ import launch
app = QApplication([])
ds = build_dataset(__import__("pathlib").Path(tempfile.mkdtemp()) / "ds")
w = launch([str(ds.yaml)], FakePrompter()); w.show()
for _ in range(200): app.processEvents(); __import__("time").sleep(0.01)
for size in ((1440, 900), (1024, 640)):
    w.resize(*size)
    for _ in range(20): app.processEvents()
    w.grab().save(f"/tmp/shot_1b_{size[0]}.png")
w.close()
EOF
/home/sonnn/miniconda3/bin/python3 /tmp/shot_1b.py
```

Expected: the two PNGs it saves in /tmp (shot_1b_1440.png and shot_1b_1024.png) both show:
- the four state-bar chips across the top;
- the queue list on the left, with ticks and badges;
- the notice strip with the out-of-range warning;
- the frame with the person and car boxes on captioned plates;
- the inspector on the right;
- the status line.

At 1024 px, chips may be elided ("…") but none may be missing.

- [ ] **Step 7: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: all pass.

```bash
git add src/deeplabeling tests docs/design/2026-10-02-project-init-plan.md
git commit -m "ui: the main window in layout A, and every launch path" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Measure the performance targets, and update the docs

**Files:**
- Create: `tools/measure_ui.py`
- Modify:
  - `docs/design/2026-10-04-app-foundation.md` (the performance table);
  - `CLAUDE.md` (the status line);
  - `docs/knowledge/environment.md` (`/tmp` is tmpfs);
  - `.claude/skills/run-and-verify-ui/SKILL.md` (the lessons).

**Interfaces:**
- Consumes: `launch` (Task 7); the session's queue and image cache; `Workspace` and edits from the core.
- Produces: the read-only tool `tools/measure_ui.py DATA.yaml --class NAME`.

- [ ] **Step 1: Write the measurement tool**

Create `tools/measure_ui.py`:

```python
#!/usr/bin/env python3
"""Measure slice 1's performance targets on a real dataset, read-only
(docs/design/2026-10-04-app-foundation.md#performance-targets).

App state goes to a temporary folder, so neither the dataset nor the real
.deeplabeling/ is written. The one write it times -- an edit -- goes to a small
dataset generated in that same temporary folder.

  /home/sonnn/miniconda3/bin/python3 tools/measure_ui.py DATA.yaml --class bus_l
"""

from __future__ import annotations

import argparse
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Answers:
    """A prompter for an unattended run: open whatever is asked, stop on any error."""

    def confirm_taxonomy(self, *args):
        return True

    def error(self, title, text):
        raise SystemExit(f"{title}: {text}")

    def choose_yaml(self):
        return None


def wait(app, condition, timeout=600.0) -> float:
    """Seconds until `condition()` holds, processing Qt events meanwhile."""
    start = time.perf_counter()
    while not condition():
        app.processEvents()
        if time.perf_counter() - start > timeout:
            raise SystemExit("timed out")
        time.sleep(0.0005)
    return time.perf_counter() - start


def edit_times(n: int = 50) -> list[float]:
    """Milliseconds per applied edit, on a generated one-image dataset."""
    from PIL import Image

    from deeplabeling.core.edits import AddBox, DeleteLine, Intent
    from deeplabeling.core.workspace import Workspace

    # On the home filesystem, not /tmp: /tmp is tmpfs here, where fsync costs nothing.
    root = Path(tempfile.mkdtemp(prefix="measure-ui-edit-", dir=Path.home() / ".cache"))
    (root / "images").mkdir(parents=True)
    Image.new("RGB", (64, 48)).save(root / "images" / "a.jpg")
    ws = Workspace.open(root / "images", confirm_taxonomy=lambda *a: True)
    image, times = root / "images" / "a.jpg", []
    for i in range(n):
        labels = ws.store.get(image)
        op = AddBox(0, (0.5, 0.5, 0.2, 0.2)) if i % 2 == 0 else DeleteLine(labels.ref(labels.boxes[0][0]))
        start = time.perf_counter()
        ws.editor.apply(Intent(image, (op,), "measure"))
        times.append((time.perf_counter() - start) * 1000)
    ws.close()
    shutil.rmtree(root)
    return times


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    ap.add_argument("--class", dest="cls", required=True, help="a class name for the class-condition queue")
    args = ap.parse_args(argv)
    tmp = tempfile.mkdtemp(prefix="measure-ui-")
    os.environ["DEEPLABELING_STATE_DIR"] = str(Path(tmp) / "state")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))

    from PIL import Image
    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch
    from deeplabeling.core.queue import HasClass, ImageFilter

    app = QApplication.instance() or QApplication(sys.argv[:1])
    rows = []

    start = time.perf_counter()
    window = launch([str(args.yaml)], Answers())
    window.resize(1440, 900)
    window.show()
    s = window.session
    wait(app, lambda: window.canvas.image_size is not None)
    rows.append(("launch to the first image shown", time.perf_counter() - start, "≤ 3 s"))

    def build(source):
        t0 = time.perf_counter()
        s.set_queue(source)
        first = wait(app, lambda: len(s.queue) > 0)
        complete = time.perf_counter() - t0 + wait(app, lambda: s.queue.complete)
        return first, complete

    first, complete = build(ImageFilter())
    rows.append(("an all-images queue: first items", first, "≤ 1 s"))
    rows.append(("an all-images queue: complete", complete, "≤ 3 s"))

    shown = []
    for _ in range(10):
        nxt = s.queue.items[s.queue.position() + 1].entry.path
        wait(app, lambda: s.images.get(nxt) is not None)            # prefetched
        t0 = time.perf_counter()
        s.move(1)
        shown.append(time.perf_counter() - t0 + wait(app, lambda: window._shown == nxt))
    rows.append(("next image, prefetched (max of 10)", max(shown), "≤ 100 ms"))

    big = None
    for item in s.queue.items[len(s.queue.items) // 2:]:
        with Image.open(item.entry.path) as im:
            if im.size[0] >= 4000:
                big = item
                break
    if big is not None:
        t0 = time.perf_counter()
        s.go_to(big.key)
        rows.append((f"an image not prefetched, {big.entry.path.name}",
                     time.perf_counter() - t0 + wait(app, lambda: window._shown == big.entry.path), "≤ 300 ms"))

    _, first_pass = build(ImageFilter(conditions=(HasClass((args.cls,)),)))
    rows.append((f"has {args.cls}: first pass after open", first_pass, "≤ 30 s"))
    _, warm = build(ImageFilter(conditions=(HasClass((args.cls,)),)))
    rows.append((f"has {args.cls}: warm", warm, "≤ 5 s"))
    window.close()

    edits = edit_times()
    rows.append(("one edit applied and written (max of 50)", max(edits) / 1000, "≤ 20 ms"))

    for name, seconds, target in rows:
        shown = f"{seconds * 1000:.0f} ms" if seconds < 1 else f"{seconds:.2f} s"
        print(f"{name:45s} {shown:>10s}   target {target}")
    print(f"median edit {statistics.median(edits):.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Measure on the real dataset (read-only)**

Run: `/home/sonnn/miniconda3/bin/python3 tools/measure_ui.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml --class bus_l`

Expected: eight lines, each within its target. The values measured on 2026-10-04 while this plan was built were:

| Line | Measured |
|---|---|
| launch to the first image shown | 1.08 s |
| all-images queue: first items / complete | 115 ms / 297 ms |
| next image, prefetched | 1 ms |
| an image not prefetched | 48 ms |
| has bus_l: first pass / warm | 4.3 s / 0.79 s |
| one edit | 1 ms |

A line over its target is a finding: profile it and fix it, or record it in the spec with its measured value. It is never dropped. Afterwards, `ls ~/.cache | grep measure-ui` must print nothing, because the tool removes its edit folder.

- [ ] **Step 3: Record the measurements in the spec**

In `docs/design/2026-10-04-app-foundation.md`, **Performance targets**, replace the paragraph and table with the block below. Put **today's measured values** in the third column; the ones shown are from 2026-10-04.

````markdown
Measured on `data_13class.yaml`, on this machine, during the slice 1 build. A missed
target is recorded with its measured value, not quietly dropped.

| Action | Target | Measured 2026-10-04 |
|---|---|---|
| launch to the first image shown | ≤ 3 s | 1.08 s |
| next image, prefetched 1920×1080 JPEG | ≤ 100 ms | 1 ms, the worst of 10 |
| next image, not prefetched 4096×2336 | ≤ 300 ms | 48 ms, a frame at least 4000 px wide |
| one edit applied and written | ≤ 20 ms | 1 ms, the worst of 50 (ext4 on NVMe) |
| an *all images* queue: first items / complete | ≤ 1 s / ≤ 3 s | 115 ms / 297 ms |
| a class condition over 45k label files, cold / warm cache | ≤ 30 s / ≤ 5 s, streaming | 4.3 s / 0.79 s |

- "Cold" is the first pass after opening, while the open-time count of unnamed class ids
  reads every label file too; the OS page cache was warm.
- Before two fixes in plan 1b, launch took 7.4 s and the all-images queue 3.9 s: the queue
  list scrolled to the cursor on every batch of a building queue, re-laying out every row
  so far, and the state bar recounted the whole queue per batch.
- Reproduce, read-only (app state goes to a temporary folder):

```sh
/home/sonnn/miniconda3/bin/python3 tools/measure_ui.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml --class bus_l
```
````

- [ ] **Step 4: Update the status line, the environment and the UI skill**

In `CLAUDE.md`, replace:

```markdown
**Status:** slice 1's headless core is built (`src/deeplabeling/core/`); its Qt UI is
next. The design and the plans are in [docs/design/](docs/design/).
```

with:

```markdown
**Status:** slice 1's core and its viewer UI are built; editing on the canvas (plan 1c)
is next. The design and the plans are in [docs/design/](docs/design/).
```

In `docs/knowledge/environment.md`, **Disk**, after the bullet ending "read in place, never copied.", add:

```markdown
- `/tmp` is tmpfs (`df -hT /tmp`), where `fsync` costs nothing: time a file write on the
  home filesystem instead. `tools/measure_ui.py` writes its timed edits under `~/.cache`.
```

At the end of `.claude/skills/run-and-verify-ui/SKILL.md`, append:

```markdown
Lessons from building the viewer (plan 1b):

- **Window shortcuts need the active window.** `with qtbot.waitActive(window): window.show();
  window.activateWindow()` before `qtbot.keyClick`. A synthetic `?` is `Qt.Key_Question`
  with no modifier; a real keyboard reports both forms, a synthetic event only the one sent.
- **`qtbot.waitUntil` wants a bool**: `lambda: bool(items)`, not `lambda: items`.
- **Hold the parent.** A host widget only handed to `qtbot.addWidget` was collected with its
  children mid-test; keep it alive in the fixture (`yield` inside it).
- **A child added to a visible layout is shown on a later event.** Call its `show()`, or
  wait for `isVisible()`, before asserting on it.
- **Read pixels near a line, not on it.** A 2 px cosmetic line on a pixel boundary is
  antialiased across two pixels: sample a small neighbourhood
  (`tests/ui/test_canvas.py::near`).
- **Never name a widget attribute after a QWidget method.** `self.size = QLabel()` broke
  `widget.size()` for everything that measured the widget.
- **A slow UI is profiled, not guessed.** `cProfile` around the action; work done per batch
  in a slot on a growing queue was the culprit last time (see the spec's performance table).
```

- [ ] **Step 5: Check the docs and run everything**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tools/measure_ui.py docs CLAUDE.md .claude/skills/run-and-verify-ui/SKILL.md
git commit -m "ui: measure the performance targets; docs match the viewer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short
```

Expected: `git status --short` prints nothing.
