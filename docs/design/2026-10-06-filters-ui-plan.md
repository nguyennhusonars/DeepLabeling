# Slice 3b: filters on screen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put plan 3a's conditions to work in the window:
- the session gives builds what they need, and says what a build could not settle;
- a model queue waits for its model, follows a model or class-map change, and takes in images as their predictions arrive;
- the canvas shows what matched, including predictions below the display threshold and `×N` stack counts;
- the queue editor gains its three rows;
- the window's builds are measured with the real model.

**Architecture:**
- **What a build is given:** `Session.context()` passes the dataset's size cache and, once a model is ready, a `ModelSnapshot`.
- **What a build left out:** the core records which images it left out, by kind. The queue keeps them, the chip counts them, and an image left out as not inferred joins the queue, in dataset order, when its predictions arrive.
- **What the canvas sees:** the window passes a `Seen` (the image size, the model's predictions and its class map) to the conditions' highlights.
- **The editor** builds `Boxes`, `Overlap` and `ModelDisagrees`, and refuses what it cannot build, by row and field.

**Tech Stack:** Python 3.10 (conda base), PySide6, pytest-qt; plan 3a's core, slice 2's model session.

**Spec:** [2026-10-06-filters.md](2026-10-06-filters.md). This plan implements:
- *Building and keeping current*: the session's part, waiting, rebuilds and late joins;
- *Window*: the queue editor, the queue chip and the canvas;
- the window rows of *Performance targets*.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)).
- **The GUI thread never waits on a build or on the model** ([landmine 3](../../CLAUDE.md#landmines)). Builds run on the session's jobs; predictions arrive through `ModelSession.ready`.
- **A UI change is verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines)): pixels for an emphasised prediction, captions as drawn, the editor's rows by their geometry.
- **Unmapped is inconclusive** ([landmine 5](../../CLAUDE.md#landmines)). An emphasised prediction comes only from plan 3a's rules.
- **Every setting survives every launch path** ([landmine 7](../../CLAUDE.md#landmines)). A model queue is restored after a relaunch and waits for the remembered model.
- **Tests never load a real model**, and write only to temporary folders ([landmines 8 and 10](../../CLAUDE.md#landmines)). The measurement reads pvn-vehicle in place, with app state in a temporary folder.
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice3-filters-ui`, from `main`. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone hunting with these filters. Each has a named test:

1. **Opening a dataset whose saved queue has a model condition.** The queue waits for the remembered model; it never silently drops the condition or comes up empty. *(Task 2 `test_a_model_queue_waits_for_the_remembered_model_after_a_relaunch`.)*
2. **A model queue on a store with few rows.** It must not stay empty for good: *Infer this queue* infers what it left out, and each image joins as its predictions arrive. *(Task 2 `test_inferring_a_model_queue_infers_what_it_left_out_and_each_joins_as_it_comes`, `test_an_image_left_out_joins_when_its_predictions_arrive`.)*
3. **A range typed reversed, as junk, or out of bounds, or a size with "lacks".** OK refuses, naming the row and the field, and the dialog keeps what was typed. *(Task 4 `test_ok_refuses_by_name_and_the_dialog_stays_open`.)*
4. **A prediction the queue found below the display threshold.** It must be visible, and acceptable with a double-click. *(Task 3 `test_a_prediction_nobody_labelled_is_emphasised_even_below_the_display_threshold`, `test_an_emphasised_prediction_can_be_accepted_with_a_double_click`.)*
5. **A threshold change while working in a model queue.** It must not rebuild the queue under the cursor, while a model switch or a class-map change must. *(Task 2 `test_a_model_switch_or_a_class_map_change_rebuilds_but_a_threshold_does_not`.)*

## Found while building this plan

The plan's code was built in a scratch copy first, and its suite ran green there (774 passed). Then `tools/measure_assist.py` ran with the real `yolo26n_vehicle` model on `data_13class.yaml`, read-only:
- the model condition, with 3,843 of 45,252 images inferred: first items in 231 ms, complete in 709 ms;
- a size in px, cold: complete in 8.62 s;
- the event loop never waited more than 48 ms while those queues built;
- `~/.config/Ultralytics/settings.json` kept its md5.

- **A model queue on a fresh store was empty for good.** With nothing on screen, nothing was inferred, and *Infer this queue* inferred only the queue's own, empty, list. On a model queue it now also infers the images the queue left out as not inferred. The spec says so after Task 5.
- **Predictions that arrived while a model queue was building were lost.** The queue learns what it left out only when the build ends. Such arrivals are now held and settled then.
- **The queue panel's model assumed a queue only grows at its end.** A row joining mid-queue comes with its own signal, `Session.itemInserted`.
- **`ImageFilter.describe` joins conditions with "and",** as slice 1 built it. Task 5 changes the spec's chip examples to match.

## Decisions this plan makes

- **What a build left out is kept by image, and by kind.** It lives in `BuildContext.left_out` and is copied to `Queue.left_out` when the build ends.
- **`waiting for the model` and `needs a model`** follow the model's state. The notice `this queue needs a model: load one` is given only when no model is loading.
- **A model queue is rebuilt when `(model key, class map)` changes.** A threshold change leaves it alone: the condition carries its own confidence range.
- **A prediction the queue found is added to the list the canvas draws, emphasised.** Editing accepts from that same list, so a double-click accepts it.
- **The editor's refusals show in the dialog itself,** prefixed by the row: `Box size — width: …`, `Overlapping labels — IoU: …`, `Model — confidence: …`. Its confidence default is the root's threshold.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/queue.py`, `src/deeplabeling/ui/session.py` | `left_out`; the context's sizes and model; the chip's counts | 1 |
| `src/deeplabeling/core/queue.py`, `ui/session.py`, `ui/queue_panel.py`, `ui/model.py` | `Queue.insert`, waiting, rebuilds, late joins; inferring a model queue | 2 |
| `src/deeplabeling/ui/boxes.py`, `canvas.py`, `main_window.py` | `Seen` for highlights; emphasised predictions; `×N` | 3 |
| `src/deeplabeling/ui/queue_editor.py`, `prompter.py`, `main_window.py` | the three rows, their refusals, the confidence default | 4 |
| `tools/measure_assist.py`, the spec, `CLAUDE.md` | the window's measurements; the status | 5 |

---

### Task 1: What a build is given, and what it could not settle

**Files:**
- Create: `tests/ui/test_filter_queue.py`
- Modify: `src/deeplabeling/core/queue.py`, `src/deeplabeling/ui/session.py`, `tests/core/test_conditions.py`

**Interfaces:**
- Consumes: from plan 3a, `BuildContext`, `ModelSnapshot` and `Workspace.sizes`; from slice 2, `ModelSession` (`state`, `key`, `class_map`).
- Produces:
  - `BuildContext.left_out: dict[str, set[str]]`, keyed `"could not be sized"`, `"not inferred"` and `"no model"`. `BuildContext.count(what, entry)` now takes the entry.
  - `Queue.left_out`, set from the build when it ends.
  - `Session.context()` with `sizes=ws.sizes`, and with `model=ModelSnapshot(...)` while a model is ready.
  - `Session.progress_text()`, which adds ` · N not inferred` and ` · N image(s) could not be sized` once built.

- [ ] **Step 1: Commit this plan, on its branch**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout -b slice3-filters-ui main
git add docs/design/2026-10-06-filters-ui-plan.md
git commit -m "docs: the slice 3b filters UI plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/core/test_conditions.py`:

```python
def test_a_build_names_the_images_it_could_not_settle(ctx):
    keys(Boxes((), w=(0, None), unit="px"), ctx)
    assert ctx.left_out == {"could not be sized": {"bad/images/corrupt.jpg"}}
```

Create `tests/ui/test_filter_queue.py`:

```python
"""Slice 3's conditions in the session: what a build is given, what it could not settle,
waiting for the model, and keeping a model queue current
(docs/design/2026-10-06-filters.md#building-and-keeping-current)."""

import pytest

from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import image_stamp
from deeplabeling.core.queue import Boxes, ImageFilter, ModelDisagrees
from fixtures import FakePredictor, open_session

CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.95)           # the model's car: nobody labelled it


@pytest.fixture
def weights(tmp_path):
    path = tmp_path / "best.pt"
    path.write_bytes(b"weights")
    return path


def load(qtbot, session, weights, **kw):
    session.model.factory = lambda path: FakePredictor(path, **kw)
    session.model.load(weights)
    qtbot.waitUntil(lambda: session.model.state == "ready", timeout=5000)


def built(qtbot, session, source):
    session.set_queue(source)
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    return [item.key for item in session.queue.items]


def test_a_build_is_given_the_dataset_s_size_cache(session):
    assert session.context().sizes is session.workspace.sizes


def test_a_build_is_given_the_model_once_it_is_ready(qtbot, session, weights):
    assert session.context().model is None
    load(qtbot, session, weights)
    model = session.context().model
    assert (model.key, model.store, model.class_map) == (
        "fake:best.pt", session.workspace.predictions, session.model.class_map)


def test_the_queue_says_what_its_build_could_not_settle(qtbot, session):
    built(qtbot, session, ImageFilter(conditions=(Boxes((), w=(0, None), unit="px"),)))
    assert session.queue.left_out == {"could not be sized": {"bad/images/corrupt.jpg"}}
    assert session.progress_text() == " · 1 image could not be sized"


def test_the_queue_counts_the_images_never_inferred(qtbot, session, weights):
    load(qtbot, session, weights, found={"0001.jpg": [CAR]})
    qtbot.waitUntil(lambda: all(session.model.predictions(session.queue.items[i].entry) is not None
                                for i in range(3)), timeout=5000)      # the screen's three
    keys = built(qtbot, session, ImageFilter(conditions=(ModelDisagrees("unlabelled"),)))
    assert keys == ["camA/images/0001.jpg"]
    assert session.progress_text() == " · 12 not inferred"
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_conditions.py tests/ui/test_filter_queue.py`
Expected: 5 failed, 24 passed.

- [ ] **Step 4: Record what was left out; give builds the sizes and the model**

In `src/deeplabeling/core/queue.py`, replace:

```python

import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
```

with:

```python

import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
```

In `src/deeplabeling/core/queue.py`, replace:

```python
    #: for the queue chip. One build or recheck owns it; it is never shared across threads.
    unsettled: Counter = field(default_factory=Counter)

    def labels(self, entry: ImageEntry) -> ImageLabels:
```

with:

```python
    #: for the queue chip. One build or recheck owns it; it is never shared across threads.
    unsettled: Counter = field(default_factory=Counter)
    #: The same, by image: which ones, so an image left out as not inferred can join the
    #: queue when its predictions arrive.
    left_out: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def labels(self, entry: ImageEntry) -> ImageLabels:
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        return self.model.store.get(self.model.key, entry.rel, stamp)

    def count(self, what: str) -> None:
        self.unsettled[what] += 1


```

with:

```python
        return self.model.store.get(self.model.key, entry.rel, stamp)

    def count(self, what: str, entry: ImageEntry) -> None:
        self.unsettled[what] += 1
        self.left_out[what].add(entry.rel)


```

In `src/deeplabeling/core/queue.py`, replace:

```python
            size = ctx.size(entry)
            if size is None:
                ctx.count("could not be sized")
                return False
        return bool(self._matching(ctx.labels(entry), ctx.dataset, size))
```

with:

```python
            size = ctx.size(entry)
            if size is None:
                ctx.count("could not be sized", entry)
                return False
        return bool(self._matching(ctx.labels(entry), ctx.dataset, size))
```

In `src/deeplabeling/core/queue.py`, replace:

```python
    def test(self, entry, ctx):
        if ctx.model is None:
            ctx.count("no model")
            return False
        preds = ctx.predictions(entry)
        if preds is None:
            ctx.count("not inferred")
            return False
        labels, cmap = ctx.labels(entry), ctx.model.class_map
```

with:

```python
    def test(self, entry, ctx):
        if ctx.model is None:
            ctx.count("no model", entry)
            return False
        preds = ctx.predictions(entry)
        if preds is None:
            ctx.count("not inferred", entry)
            return False
        labels, cmap = ctx.labels(entry), ctx.model.class_map
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        self.complete = False
        self.failed: str | None = None      #: why the build stopped early, if it failed
        self._pos: dict[str, int] = {}
        self._follow = follow       #: the item the cursor was on before a rebuild
```

with:

```python
        self.complete = False
        self.failed: str | None = None      #: why the build stopped early, if it failed
        #: What the build could not settle, by image ("not inferred", "could not be sized").
        self.left_out: dict[str, set[str]] = {}
        self._pos: dict[str, int] = {}
        self._follow = follow       #: the item the cursor was on before a rebuild
```

In `src/deeplabeling/ui/session.py`, replace:

```python
from ..core.dataset import DatasetError, ImageEntry
from ..core.edits import CreateEmpty, Edit, Intent, Refused
from ..core.queue import BuildContext, ImageFilter, Queue, QueueItem
from ..core.state import Locked
from ..core.store import ImageLabels, LabelState
```

with:

```python
from ..core.dataset import DatasetError, ImageEntry
from ..core.edits import CreateEmpty, Edit, Intent, Refused
from ..core.queue import BuildContext, ImageFilter, ModelSnapshot, Queue, QueueItem
from ..core.state import Locked
from ..core.store import ImageLabels, LabelState
```

In `src/deeplabeling/ui/session.py`, replace:

```python
#: How often the image on screen has its label file re-checked for outside changes.
WATCH_MS = 1500


```

with:

```python
#: How often the image on screen has its label file re-checked for outside changes.
WATCH_MS = 1500


#: What a build could not settle, as the queue chip says it.
UNSETTLED = {
    "could not be sized": lambda n: f"{n:,} image could not be sized" if n == 1 else f"{n:,} images could not be sized",
    "not inferred": lambda n: f"{n:,} not inferred",
}


```

In `src/deeplabeling/ui/session.py`, replace:

```python
            lambda emit, cancelled: source.build(ctx, emit, cancelled),
            batch=lambda items: self._grew(queue, items),
            done=lambda finished: self._built(queue, finished),
            failed=lambda why: self._build_failed(queue, why))

```

with:

```python
            lambda emit, cancelled: source.build(ctx, emit, cancelled),
            batch=lambda items: self._grew(queue, items),
            done=lambda finished: self._built(queue, finished, left_out=ctx.left_out),
            failed=lambda why: self._build_failed(queue, why))

```

In `src/deeplabeling/ui/session.py`, replace:

```python
        reused until they change: an import underneath the app reports thousands of
        changed files, and a fresh snapshot each time froze the GUI for seconds."""
        ws = self._require()
        if self._keys is None:
            self._keys = ws.review.keys()
        return BuildContext(ws.dataset, ws.store, self._keys)

    def _grew(self, queue: Queue, items: list[QueueItem]) -> None:
```

with:

```python
        reused until they change: an import underneath the app reports thousands of
        changed files, and a fresh snapshot each time froze the GUI for seconds."""
        ws, model = self._require(), self.model
        if self._keys is None:
            self._keys = ws.review.keys()
        snapshot = (ModelSnapshot(model.key, ws.predictions, model.class_map)
                    if model.state == "ready" and model.class_map is not None else None)
        return BuildContext(ws.dataset, ws.store, self._keys, sizes=ws.sizes, model=snapshot)

    def _grew(self, queue: Queue, items: list[QueueItem]) -> None:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self._built(queue, True, failed=why)

    def _built(self, queue: Queue, finished: bool, failed: str | None = None) -> None:
        if queue is not self.queue or not finished:
            return
        before = queue.cursor
        if failed is None:
```

with:

```python
        self._built(queue, True, failed=why)

    def _built(self, queue: Queue, finished: bool, failed: str | None = None, left_out=None) -> None:
        if queue is not self.queue or not finished:
            return
        if left_out:
            queue.left_out = {what: set(rels) for what, rels in left_out.items()}
        before = queue.cursor
        if failed is None:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        """How the queue's build stands, for the chip and the panel: "" once built."""
        queue = self.queue
        if queue is None or (queue.complete and queue.failed is None):
            return ""
        return " · build failed" if queue.failed is not None else " · building…"

    def left(self) -> int:
```

with:

```python
        """How the queue's build stands, for the chip and the panel: "" once built."""
        queue = self.queue
        if queue is None:
            return ""
        if queue.failed is not None:
            return " · build failed"
        if not queue.complete:
            return " · building…"
        return "".join(f" · {UNSETTLED[what](len(rels))}" for what, rels in sorted(queue.left_out.items())
                       if rels and what in UNSETTLED)

    def left(self) -> int:
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_conditions.py tests/core/test_disagree.py tests/ui/test_filter_queue.py tests/ui/test_session.py`
Expected: 78 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 746 passed.

```bash
git add src/deeplabeling/core/queue.py src/deeplabeling/ui/session.py tests/core/test_conditions.py tests/ui/test_filter_queue.py
git commit -m "ui: builds get the size cache and the loaded model; the chip says what a build left out" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Waiting for the model, rebuilding, and late joins

**Files:**
- Modify: `src/deeplabeling/core/queue.py`, `src/deeplabeling/ui/session.py`, `src/deeplabeling/ui/queue_panel.py`, `src/deeplabeling/ui/model.py`, `tests/core/test_queue.py`, `tests/ui/test_filter_queue.py`

**Interfaces:**
- Consumes: from Task 1, `Queue.left_out` and `Session.context()`; from plan 3a, `ImageFilter.needs_model`; from slice 2, `ModelSession.changed`, `ModelSession.ready` and `ModelSession.infer_queue`.
- Produces:
  - `Queue.insert(item) -> row | None`, in dataset order; `Queue.waiting`; `Queue.built_with`.
  - In `Session`:
    - `itemInserted(int)`;
    - `_model_identity()`, `_model_changed()` and `_predicted(path)`;
    - while a model queue waits, `progress_text()` reads ` · waiting for the model` or ` · needs a model`.
  - `QueueModel._inserted(row)`.
  - `ModelSession.infer_queue()`, which on a model queue also infers its not-inferred images.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_filter_queue.py`:

```python
UNLABELLED = ImageFilter(conditions=(ModelDisagrees("unlabelled"),))


def test_without_a_model_a_model_queue_is_empty_and_says_it_needs_one(qtbot, session, weights):
    with qtbot.waitSignal(session.notice) as said:
        session.set_queue(UNLABELLED)
    assert said.args[1] == "this queue needs a model: load one"
    assert len(session.queue) == 0 and session.progress_text() == " · needs a model"
    load(qtbot, session, weights, found={"0001.jpg": [CAR]})
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    assert session.queue.source == UNLABELLED


def test_while_the_model_loads_the_queue_waits_then_builds(qtbot, session, weights):
    import threading

    gate = threading.Event()
    session.model.factory = lambda path: (gate.wait(5), FakePredictor(path, found={"0001.jpg": [CAR]}))[1]
    session.model.load(weights)
    notices = []
    session.notice.connect(lambda level, text, image: notices.append(text))
    session.set_queue(UNLABELLED)
    assert session.progress_text() == " · waiting for the model" and notices == []
    gate.set()
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    assert len(session.queue) == 0 and session.progress_text() == " · 15 not inferred"


def test_inferring_a_model_queue_infers_what_it_left_out_and_each_joins_as_it_comes(qtbot, session, weights):
    load(qtbot, session, weights, found={"0001.jpg": [CAR]})
    built(qtbot, session, UNLABELLED)
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info"):
        session.model.infer_queue()
    assert [item.key for item in session.queue.items] == ["camA/images/0001.jpg", "camB/images/0001.jpg"]
    assert session.progress_text() == ""


def test_a_model_switch_or_a_class_map_change_rebuilds_but_a_threshold_does_not(qtbot, session, weights, tmp_path):
    load(qtbot, session, weights)
    built(qtbot, session, UNLABELLED)
    first = session.queue
    session.model.set_conf(0.5)
    assert session.queue is first
    session.model.set_class_map(session.model.class_map.with_target(0, None))
    assert session.queue is not first
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    second = session.queue
    other = tmp_path / "other.pt"
    other.write_bytes(b"other")
    session.model.load(other)
    qtbot.waitUntil(lambda: session.model.state == "ready" and session.queue is not second
                    and session.queue.complete, timeout=5000)


def test_an_image_left_out_joins_when_its_predictions_arrive(qtbot, session, weights):
    from deeplabeling.ui.queue_panel import QueuePanel

    load(qtbot, session, weights, found={"0001.jpg": [CAR]})
    qtbot.waitUntil(lambda: all(session.model.predictions(session.queue.items[i].entry) is not None
                                for i in range(3)), timeout=5000)
    panel = QueuePanel(session)
    qtbot.addWidget(panel)
    assert built(qtbot, session, UNLABELLED) == ["camA/images/0001.jpg"]
    ws = session.workspace
    for rel, preds in (("camB/images/0001.jpg", []), ("camA/images/0004.JPG", [CAR])):
        path = ws.dataset.root / rel
        ws.predictions.put(session.model.key, rel, image_stamp(path), preds)
        with qtbot.waitSignal(session.model.ready):
            session.model.ready.emit(path)                   # as the model's thread reports it
    assert [item.key for item in session.queue.items] == ["camA/images/0001.jpg", "camA/images/0004.JPG"]
    assert panel.model.rowCount() == 2 and session.progress_text() == " · 10 not inferred"


def test_a_model_queue_waits_for_the_remembered_model_after_a_relaunch(qtbot, ds, weights, monkeypatch):
    import deeplabeling.ui.model as model_module
    from drive import start

    monkeypatch.setattr(model_module, "UltralyticsPredictor",
                        lambda path: FakePredictor(path, found={"0001.jpg": [CAR]}))
    window = start(qtbot, [str(ds.yaml)])
    window.session.model.load(weights)
    qtbot.waitUntil(lambda: window.session.model.state == "ready", timeout=5000)
    window.session.set_queue(UNLABELLED)
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert again.session.queue.source == UNLABELLED
    qtbot.waitUntil(lambda: again.session.queue.complete and len(again.session.queue) == 1, timeout=5000)
    again.close()
```

Append to `tests/core/test_queue.py`:

```python
def test_an_item_inserted_after_the_build_takes_its_place_in_dataset_order(dataset):
    items = all_items(dataset)
    queue = Queue(ImageFilter())
    queue.extend([items[0], items[3]])
    queue.go_to(items[3].key)
    assert queue.insert(items[1]) == 1 and queue.insert(items[1]) is None
    assert [it.key for it in queue.items] == [items[0].key, items[1].key, items[3].key]
    assert queue.cursor == items[3].key and queue.index_of(items[3].key) == 2


def test_an_item_inserted_into_an_empty_queue_takes_the_cursor(dataset):
    queue = Queue(ImageFilter())
    queue.insert(all_items(dataset)[2])
    assert queue.cursor == all_items(dataset)[2].key
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_queue.py tests/ui/test_filter_queue.py`
Expected: 8 failed, 40 passed.

- [ ] **Step 3: Wait, rebuild, and take in late images**

In `src/deeplabeling/core/queue.py`, replace:

```python
        #: What the build could not settle, by image ("not inferred", "could not be sized").
        self.left_out: dict[str, set[str]] = {}
        self._pos: dict[str, int] = {}
        self._follow = follow       #: the item the cursor was on before a rebuild
```

with:

```python
        #: What the build could not settle, by image ("not inferred", "could not be sized").
        self.left_out: dict[str, set[str]] = {}
        self.waiting = False        #: a model condition waits for a model: nothing is built yet
        self.built_with = None      #: the model (key, class map) its build read, if any
        self._pos: dict[str, int] = {}
        self._follow = follow       #: the item the cursor was on before a rebuild
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        if self.cursor is None and self.items:
            self.cursor = self.items[0].key

    def finish(self) -> None:
```

with:

```python
        if self.cursor is None and self.items:
            self.cursor = self.items[0].key

    def insert(self, item: QueueItem) -> int | None:
        """Add an item after the build, in dataset order: an image whose predictions have
        arrived. Its row, or None when it is already there."""
        if item.key in self._pos:
            return None
        row = next((i for i, it in enumerate(self.items) if it.entry.order > item.entry.order), len(self.items))
        self.items.insert(row, item)
        for i in range(row, len(self.items)):
            self._pos[self.items[i].key] = i
        if self.cursor is None:
            self.cursor = item.key
        return row

    def finish(self) -> None:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
    itemsChanged = Signal(object)       # list[str]: keys whose badge or tick may differ
    cursorChanged = Signal()
    notice = Signal(str, str, object)   # level, text, image Path or None
    standing = Signal(str, str)         # key, text: a notice that stays; "" removes it
```

with:

```python
    itemsChanged = Signal(object)       # list[str]: keys whose badge or tick may differ
    cursorChanged = Signal()
    itemInserted = Signal(int)          # a row joined the queue after its build
    notice = Signal(str, str, object)   # level, text, image Path or None
    standing = Signal(str, str)         # key, text: a notice that stays; "" removes it
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self.running: Chunked | None = None         # a long write under way (ui/chunked.py)
        self._running_title = ""
        self.model = ModelSession(self, self)

    # -- opening and closing -----------------------------------------------
```

with:

```python
        self.running: Chunked | None = None         # a long write under way (ui/chunked.py)
        self._running_title = ""
        self._arrived: set[Path] = set()           # predictions that came while a model queue built
        self.model = ModelSession(self, self)
        self.model.changed.connect(self._model_changed)
        self.model.ready.connect(self._predicted)

    # -- opening and closing -----------------------------------------------
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self._follow = follow
        queue = self.queue = Queue(source, follow=follow)
        ws.opening_settings.set(QUEUE_SOURCE, source.to_json())
        self.saver.schedule()
        self.queueReset.emit()
        self.cursorChanged.emit()
        ctx = self.context()
        self._build = self.io.start(
```

with:

```python
        self._follow = follow
        queue = self.queue = Queue(source, follow=follow)
        queue.built_with = self._model_identity()
        self._arrived = set()
        ws.opening_settings.set(QUEUE_SOURCE, source.to_json())
        self.saver.schedule()
        self.queueReset.emit()
        self.cursorChanged.emit()
        if source.needs_model and queue.built_with is None:
            queue.waiting = True                    # built when a model is ready
            if self.model.state != "loading":
                self.notice.emit("warning", "this queue needs a model: load one", None)
            return
        ctx = self.context()
        self._build = self.io.start(
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            done=lambda finished: self._built(queue, finished, left_out=ctx.left_out),
            failed=lambda why: self._build_failed(queue, why))

    def context(self) -> BuildContext:
```

with:

```python
            done=lambda finished: self._built(queue, finished, left_out=ctx.left_out),
            failed=lambda why: self._build_failed(queue, why))

    def _model_identity(self):
        """What a model queue's build depends on: the model and its class map."""
        model = self.model
        return (model.key, model.class_map) if model.state == "ready" else None

    def _model_changed(self) -> None:
        """A model queue is rebuilt when the model or its class map changes, and built
        once a model it waited for is ready; a threshold change leaves it as it is."""
        queue = self.queue
        if (queue is not None and self.workspace is not None and queue.source.needs_model
                and self._model_identity() != queue.built_with):
            self.set_queue(queue.source)

    def _predicted(self, path) -> None:
        """Predictions arrived for an image: a model queue re-tests it, and an image it
        left out as not inferred joins it, in dataset order, if it now matches."""
        queue, ws = self.queue, self.workspace
        if queue is None or ws is None or not queue.source.needs_model:
            return
        try:
            entry = ws.dataset.entry(path)
        except KeyError:
            return
        if entry.rel in queue:
            self._recheck((path,))
            return
        if not queue.complete:
            if not queue.waiting:
                self._arrived.add(path)             # settled when the build has said what it left out
            return
        waiting = queue.left_out.get("not inferred")
        if not waiting or entry.rel not in waiting:
            return
        waiting.discard(entry.rel)
        if queue.source.matches(entry, self.context()):
            row = queue.insert(QueueItem(entry.rel, entry))
            if row is not None:
                self.itemInserted.emit(row)
        self.queueGrew.emit()

    def context(self) -> BuildContext:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        if queue.cursor != before:
            self._cursor_moved()

    def current(self) -> QueueItem | None:
```

with:

```python
        if queue.cursor != before:
            self._cursor_moved()
        arrived, self._arrived = self._arrived, set()
        for path in arrived:
            self._predicted(path)

    def current(self) -> QueueItem | None:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        if queue is None:
            return ""
        if queue.failed is not None:
            return " · build failed"
```

with:

```python
        if queue is None:
            return ""
        if queue.waiting:
            return " · waiting for the model" if self.model.state == "loading" else " · needs a model"
        if queue.failed is not None:
            return " · build failed"
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
        session.closed.connect(self._reset)
        session.queueGrew.connect(self._grew)
        session.itemsChanged.connect(self._changed)
        self._reset()                               # a queue may already be built
```

with:

```python
        session.closed.connect(self._reset)
        session.queueGrew.connect(self._grew)
        session.itemInserted.connect(self._inserted)
        session.itemsChanged.connect(self._changed)
        self._reset()                               # a queue may already be built
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
            self._rows = n
            self.endInsertRows()

    def _changed(self, keys) -> None:
```

with:

```python
            self._rows = n
            self.endInsertRows()

    def _inserted(self, row: int) -> None:
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows += 1
        self.endInsertRows()

    def _changed(self, keys) -> None:
```

In `src/deeplabeling/ui/model.py`, replace:

```python
        if self.state != "ready" or ws is None or queue is None or not queue.complete or self.passing:
            return
        items = [(item.entry.rel, item.entry.path) for item in queue.items]
        self.passing, self.pass_walked, self.pass_total = True, 0, len(items)
        self._worker.start_pass(ws.predictions, items)
```

with:

```python
        if self.state != "ready" or ws is None or queue is None or not queue.complete or self.passing:
            return
        # A model queue also needs the images it left out as not inferred: inferred, they
        # can join it (docs/design/2026-10-06-filters.md#building-and-keeping-current).
        waiting = queue.left_out.get("not inferred", set())
        items = [(e.rel, e.path) for e in ws.dataset.images if e.rel in queue or e.rel in waiting]
        self.passing, self.pass_walked, self.pass_total = True, 0, len(items)
        self._worker.start_pass(ws.predictions, items)
```

- [ ] **Step 4: Run the tests to see them pass, three times**

The model's thread is involved; three green runs in a row is the bar.

Run: `for i in 1 2 3; do /home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_queue.py tests/ui/test_filter_queue.py tests/ui/test_pass.py | tail -1; done`
Expected: three lines, each `58 passed`.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 754 passed.

```bash
git add src/deeplabeling/core/queue.py src/deeplabeling/ui/session.py src/deeplabeling/ui/queue_panel.py src/deeplabeling/ui/model.py tests/core/test_queue.py tests/ui/test_filter_queue.py
git commit -m "ui: a model queue waits for its model, follows a model or class-map change, and takes in images as they are inferred" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: What matched, on the canvas

**Files:**
- Create: `tests/ui/test_filter_view.py`
- Modify: `src/deeplabeling/ui/boxes.py`, `src/deeplabeling/ui/canvas.py`, `src/deeplabeling/ui/main_window.py`, `tests/ui/test_boxes.py`, `tests/ui/test_canvas.py`

**Interfaces:**
- Consumes: from plan 3a, `Seen`, `ImageFilter.highlight(labels, dataset, seen)` and `ImageFilter.highlight_predictions`; from slice 2, `Shown`, `ModelSession.predictions`/`shown`/`class_map`, and `Editing.show_predictions`.
- Produces:
  - `PredictionView.emphasised` (default False). An emphasised view is never faint, and is drawn with a 4 px pen.
  - `prediction_views(..., emphasised=frozenset())`.
  - Stack captions read `car ×2`.
  - `MainWindow._seen(item) -> Seen`. `MainWindow._prediction_views(item)` adds what the queue found, even below the display threshold.

- [ ] **Step 1: Write the failing tests**

In `tests/ui/test_boxes.py`, replace:

```python
    v = views(dataset, ds, "bad/ok.jpg")
    assert {i: v[i].caption for i in v} == {
        0: "car x4", 1: "#99? x2", 2: "#-1? x2", 3: "person",
        5: "person x4", 6: "person x4", 10: "person x4"}


```

with:

```python
    v = views(dataset, ds, "bad/ok.jpg")
    assert {i: v[i].caption for i in v} == {
        0: "car ×4", 1: "#99? ×2", 2: "#-1? ×2", 3: "person",
        5: "person ×4", 6: "person ×4", 10: "person ×4"}


```

In `tests/ui/test_boxes.py`, replace:

```python
    assert (car.caption, car.faint, car.index) == ("car 0.88", False, 0)
    assert (unmapped.caption, unmapped.color, unmapped.faint) == ("human? 0.50", UNKNOWN, True)
```

with:

```python
    assert (car.caption, car.faint, car.index) == ("car 0.88", False, 0)
    assert (unmapped.caption, unmapped.color, unmapped.faint) == ("human? 0.50", UNKNOWN, True)


def test_an_emphasised_prediction_is_never_faint(dataset):
    from deeplabeling.core.assist import Shown
    from deeplabeling.core.inference import Prediction
    from deeplabeling.ui.boxes import prediction_views

    covered = Shown(Prediction(0, (0.5, 0.5, 0.2, 0.2), 0.2), 1, False)      # not missing: faint
    [plain] = prediction_views([covered], dataset, SIZE, {}, ("car",))
    [marked] = prediction_views([covered], dataset, SIZE, {}, ("car",), emphasised=frozenset({0}))
    assert plain.faint and not plain.emphasised
    assert marked.emphasised and not marked.faint
```

Append to `tests/ui/test_canvas.py`:

```python
def test_an_emphasised_prediction_is_drawn_thicker(canvas):
    def thickness(view):
        canvas.set_image(grey_image())
        canvas.set_boxes([], predictions=[view])
        image = shot(canvas)
        x = canvas.mapFromScene(QPointF(120, 25)).x()
        y0 = canvas.mapFromScene(QPointF(120, 25)).y()
        return sum(QColor(image.pixel(x, y)).green() > 150 for y in range(y0 - 6, y0 + 7))

    plain = thickness(GREEN_PRED)
    thick = thickness(PredictionView(0, GREEN_PRED.rect, "#00ff00", "car 0.90", False, emphasised=True))
    assert thick > plain >= 1
```

Create `tests/ui/test_filter_view.py`:

```python
"""What a slice 3 queue shows on the canvas: the boxes and the predictions that made an
image match (docs/design/2026-10-06-filters.md#the-canvas)."""

import pytest
from PySide6.QtCore import Qt

import deeplabeling.ui.model as model_module
from deeplabeling.core.inference import Prediction
from deeplabeling.core.queue import Boxes, ImageFilter, ModelDisagrees
from drive import start, vp
from fixtures import CAMA_0001, FakePredictor, read_exact

WEAK_CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.2)          # nobody labelled it; below 0.25


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor",
                        lambda path: FakePredictor(path, found={"0001.jpg": [WEAK_CAR]}))
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    w.session.model.load(weights)
    qtbot.waitUntil(lambda: w.session.model.predictions(w.session.current().entry) is not None, timeout=5000)
    yield w
    w.close()


def queue(qtbot, window, *conditions):
    window.session.set_queue(ImageFilter(conditions=conditions))
    qtbot.waitUntil(lambda: window.session.queue.complete and window._shown is not None, timeout=5000)


def test_a_size_in_pixels_highlights_its_boxes_on_screen(qtbot, window):
    queue(qtbot, window, Boxes((), w=(None, 7), unit="px"))             # camA/0001's car, 6.4 px
    assert window.session.current().key == "camA/images/0001.jpg"
    assert {v.index: v.highlighted for v in window.canvas._views} == {0: False, 1: True}


def test_a_prediction_nobody_labelled_is_emphasised_even_below_the_display_threshold(qtbot, window):
    assert window.canvas._predictions == []                    # 0.2 is below the threshold, 0.25
    queue(qtbot, window, ModelDisagrees("unlabelled", conf=(0.1, 1.0)))
    [view] = window.canvas._predictions
    assert view.emphasised and view.caption == "car 0.20"
    assert [c.text for c in window.canvas.prediction_caption_items()] == ["car 0.20"]


def test_an_emphasised_prediction_can_be_accepted_with_a_double_click(qtbot, window, ds):
    queue(qtbot, window, ModelDisagrees("unlabelled", conf=(0.1, 1.0)))
    qtbot.mouseDClick(window.canvas.viewport(), Qt.LeftButton, pos=vp(window.canvas, 51.2, 38.4))
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_boxes.py tests/ui/test_canvas.py tests/ui/test_filter_view.py`
Expected: 6 failed, 50 passed.

- [ ] **Step 3: Highlight with what the window knows; emphasise what the queue found**

In `src/deeplabeling/ui/boxes.py`, replace:

```python
    polygon: tuple[tuple[float, float], ...]    #: a polygon's points in pixels; () for a box
    color: str                                  #: #rrggbb
    caption: str                                #: "car", "car x2", "#13?"
    known: bool                                 #: False: an id the names do not cover
    highlighted: bool                           #: a queue condition matched this box
```

with:

```python
    polygon: tuple[tuple[float, float], ...]    #: a polygon's points in pixels; () for a box
    color: str                                  #: #rrggbb
    caption: str                                #: "car", "car ×2", "#13?"
    known: bool                                 #: False: an id the names do not cover
    highlighted: bool                           #: a queue condition matched this box
```

In `src/deeplabeling/ui/boxes.py`, replace:

```python
def box_views(labels: ImageLabels, dataset: Dataset, size: tuple[int, int],
              colors: dict[str, str], highlight: frozenset[int] = frozenset()) -> list[BoxView]:
    """One view per parsed line. A box stacked on others captions the count (`car x2`):
    identical rectangles otherwise draw as one. An id outside the names is drawn grey
    and captioned `#id?`, never dropped."""
```

with:

```python
def box_views(labels: ImageLabels, dataset: Dataset, size: tuple[int, int],
              colors: dict[str, str], highlight: frozenset[int] = frozenset()) -> list[BoxView]:
    """One view per parsed line. A box stacked on others captions the count (`car ×2`):
    identical rectangles otherwise draw as one. An id outside the names is drawn grey
    and captioned `#id?`, never dropped."""
```

In `src/deeplabeling/ui/boxes.py`, replace:

```python
            base = str(cls_id)
            color = class_color(cls_id, base, colors)
        caption = f"{base} x{stack[pos]}" if pos in stack else base
        polygon = ()
        if line.is_polygon:
```

with:

```python
            base = str(cls_id)
            color = class_color(cls_id, base, colors)
        caption = f"{base} ×{stack[pos]}" if pos in stack else base
        polygon = ()
        if line.is_polygon:
```

In `src/deeplabeling/ui/boxes.py`, replace:

```python
    caption: str                                #: "car 0.82", or "truck? 0.40" when unmapped
    faint: bool                                 #: not missing: an accept would not add it


def prediction_views(shown: list[Shown], dataset: Dataset, size: tuple[int, int],
                     colors: dict[str, str], model_names: tuple[str, ...]) -> list[PredictionView]:
    """What the predictions layer draws (docs/design/2026-10-05-model-assist.md#the-predictions-layer)."""
    w, h = size
```

with:

```python
    caption: str                                #: "car 0.82", or "truck? 0.40" when unmapped
    faint: bool                                 #: not missing: an accept would not add it
    emphasised: bool = False                    #: a queue condition matched it: drawn thicker, never faint


def prediction_views(shown: list[Shown], dataset: Dataset, size: tuple[int, int],
                     colors: dict[str, str], model_names: tuple[str, ...],
                     emphasised: frozenset[int] = frozenset()) -> list[PredictionView]:
    """What the predictions layer draws (docs/design/2026-10-05-model-assist.md#the-predictions-layer)."""
    w, h = size
```

In `src/deeplabeling/ui/boxes.py`, replace:

```python
            name = dataset.names[s.cls] if s.cls < len(dataset.names) else str(s.cls)
            color, caption = class_color(s.cls, name, colors), f"{name} {s.pred.conf:.2f}"
        views.append(PredictionView(index, norm_to_px(s.pred.box, w, h), color, caption, not s.missing))
    return views
```

with:

```python
            name = dataset.names[s.cls] if s.cls < len(dataset.names) else str(s.cls)
            color, caption = class_color(s.cls, name, colors), f"{name} {s.pred.conf:.2f}"
        marked = index in emphasised
        views.append(PredictionView(index, norm_to_px(s.pred.box, w, h), color, caption,
                                    not s.missing and not marked, marked))
    return views
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
        pen = QPen(color)
        pen.setCosmetic(True)
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        x1, y1, x2, y2 = view.rect
```

with:

```python
        pen = QPen(color)
        pen.setCosmetic(True)
        pen.setWidth(4 if view.emphasised else 2)
        pen.setStyle(Qt.DashLine)
        x1, y1, x2, y2 = view.rect
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget

from ..core.workspace import CLASS_COLORS
from .boxes import box_views, prediction_views
```

with:

```python
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget

from ..core.assist import Shown
from ..core.queue import Seen
from ..core.workspace import CLASS_COLORS
from .boxes import box_views, prediction_views
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        ws = session.workspace
        labels = session.labels(item.entry)
        highlight = session.queue.source.highlight(labels, ws.dataset)
        self.editing.show(labels)
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
```

with:

```python
        ws = session.workspace
        labels = session.labels(item.entry)
        highlight = session.queue.source.highlight(labels, ws.dataset, self._seen(item))
        self.editing.show(labels)
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
                              predictions=self._prediction_views(item))

    def _prediction_views(self, item):
        """The predictions for the item on screen, as the canvas draws them; Editing keeps
        the same list, so what is accepted is what is drawn."""
        ws, model = self.session.workspace, self.session.model
        shown = model.shown(item.entry)
        self.editing.show_predictions(item.entry.path, shown)
        return prediction_views(shown or [], ws.dataset, self.canvas.image_size,
                                ws.root_settings.get(CLASS_COLORS), model.names)

    def _predictions_changed(self) -> None:
```

with:

```python
                              predictions=self._prediction_views(item))

    def _seen(self, item) -> Seen:
        """What the queue's conditions highlight from besides the labels."""
        model = self.session.model
        return Seen(size=self.canvas.image_size, predictions=model.predictions(item.entry),
                    class_map=model.class_map)

    def _prediction_views(self, item):
        """The predictions for the item on screen, as the canvas draws them; Editing keeps
        the same list, so what is accepted is what is drawn. Those the queue matched are
        emphasised, and drawn even below the display threshold: they are what it found."""
        session, ws, model = self.session, self.session.workspace, self.session.model
        shown, seen = model.shown(item.entry), self._seen(item)
        marked: list = []
        if session.queue is not None and seen.predictions is not None:
            indices = session.queue.source.highlight_predictions(session.labels(item.entry), ws.dataset, seen)
            marked = [seen.predictions[k] for k in sorted(indices)]
        if marked:
            shown = list(shown or [])
            drawn = [s.pred for s in shown]
            shown += [Shown(p, model.class_map.translate(p.cls, ws.dataset), True) for p in marked if p not in drawn]
        emphasised = frozenset(i for i, s in enumerate(shown or []) if s.pred in marked)
        self.editing.show_predictions(item.entry.path, shown)
        return prediction_views(shown or [], ws.dataset, self.canvas.image_size,
                                ws.root_settings.get(CLASS_COLORS), model.names, emphasised)

    def _predictions_changed(self) -> None:
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_boxes.py tests/ui/test_canvas.py tests/ui/test_filter_view.py tests/ui/test_accepting.py`
Expected: 67 passed.

- [ ] **Step 5: Look at it**

Build the `window` fixture of `tests/ui/test_filter_view.py` with `ModelDisagrees("unlabelled", conf=(0.1, 1.0))` as its queue. Save `window.canvas.viewport().grab()` and open the PNG. Expected: the weak `car 0.20` below the person is drawn dashed with a thick pen and its caption above it, although the display threshold is 0.25.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 759 passed.

```bash
git add src/deeplabeling/ui/boxes.py src/deeplabeling/ui/canvas.py src/deeplabeling/ui/main_window.py tests/ui/test_boxes.py tests/ui/test_canvas.py tests/ui/test_filter_view.py
git commit -m "ui: the canvas shows what a filter matched, a prediction it found emphasised even below the threshold; stacks read ×N" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The queue editor's rows

**Files:**
- Modify: `src/deeplabeling/ui/queue_editor.py`, `src/deeplabeling/ui/prompter.py`, `src/deeplabeling/ui/main_window.py`, `tests/fixtures.py`, `tests/ui/test_queue_editor.py`, `tests/ui/test_filter_view.py`

**Interfaces:**
- Consumes: from plan 3a, `Boxes`, `Overlap`, `ModelDisagrees` and `UNITS`; slice 1's `QueueEditor`.
- Produces:
  - `QueueEditor(dataset, current, parent=None, *, conf=0.25)`, with these members:
    - `size_w_lo`, `size_w_hi`, `size_h_lo`, `size_h_hi` and `size_unit`;
    - `overlap_mode`, `overlap_lo` and `overlap_hi`;
    - `model_mode`, `model_iou`, `model_lo` and `model_hi`;
    - `error`, a label;
    - `chosen`, the filter OK took;
    - `filter()`, which raises `ValueError` naming the row and the field;
    - `accept()`, which refuses and stays open.
  - `QtPrompter.edit_queue(dataset, current, conf=0.25)`, which returns `dialog.chosen`. `FakePrompter.edit_queue(dataset, current, conf=None)` records `("queue", current, conf)`.
  - `MainWindow.edit_queue` passes the root's threshold.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_filter_view.py`:

```python

def test_the_queue_editor_offers_the_root_s_threshold_as_the_model_s_confidence(qtbot, window):
    window.session.model.set_conf(0.4)
    window.edit_queue()
    assert window.prompter.asked[-1][2] == 0.4
```

In `tests/fixtures.py`, replace:

```python
        return str(self.folders.pop(0)) if self.folders else None

    def edit_queue(self, dataset, current):
        self.asked.append(("queue", current))
        return self.queue

```

with:

```python
        return str(self.folders.pop(0)) if self.folders else None

    def edit_queue(self, dataset, current, conf=None):
        self.asked.append(("queue", current, conf))
        return self.queue

```

In `tests/ui/test_queue_editor.py`, replace:

```python
import pytest
from PySide6.QtCore import Qt

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.queue import HasClass, ImageFilter, LabelStateIs, NameContains, Reviewed
from deeplabeling.ui.queue_editor import QueueEditor

```

with:

```python
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.queue import (
    Boxes,
    HasClass,
    ImageFilter,
    LabelStateIs,
    ModelDisagrees,
    NameContains,
    Overlap,
    Reviewed,
)
from deeplabeling.ui.queue_editor import QueueEditor

```

In `tests/ui/test_queue_editor.py`, replace:

```python


def editor(qtbot, dataset, current):
    dialog = QueueEditor(dataset, current)
    qtbot.addWidget(dialog)
    return dialog
```

with:

```python


def editor(qtbot, dataset, current, **kw):
    dialog = QueueEditor(dataset, current, **kw)
    qtbot.addWidget(dialog)
    return dialog
```

In `tests/ui/test_queue_editor.py`, replace:

```python
                           Reviewed(False), NameContains("cam"))),
    ImageFilter(conditions=(HasClass(("person",), present=False), LabelStateIs("missing"))),
])
def test_the_editor_is_seeded_from_the_queue_in_force(qtbot, dataset, current):
```

with:

```python
                           Reviewed(False), NameContains("cam"))),
    ImageFilter(conditions=(HasClass(("person",), present=False), LabelStateIs("missing"))),
    ImageFilter(conditions=(Boxes(("car", "bus_m"), w=(10, 30), unit="px"), Reviewed(False))),
    ImageFilter(conditions=(Boxes((), h=(None, 5), unit="%"), Overlap("same", 0.99, 1.0))),
    ImageFilter(conditions=(Overlap("different", 0.5, 1.0), ModelDisagrees("either", 0.6, (0.3, 0.9)))),
    ImageFilter(conditions=(ModelDisagrees("unseen"),)),
])
def test_the_editor_is_seeded_from_the_queue_in_force(qtbot, dataset, current):
```

In `tests/ui/test_queue_editor.py`, replace:

```python
    assert dialog.filter() == ImageFilter(("val",), (HasClass(("car",), present=False),
                                                     Reviewed(False), NameContains("seg")))
```

with:

```python
    assert dialog.filter() == ImageFilter(("val",), (HasClass(("car",), present=False),
                                                     Reviewed(False), NameContains("seg")))



def test_the_new_rows_build_their_conditions(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter(), conf=0.4)
    dialog.class_mode.setCurrentText("has")
    dialog.classes.item(1).setCheckState(Qt.Checked)
    dialog.size_w_hi.setText("10")
    dialog.size_unit.setCurrentText("%")
    dialog.overlap_mode.setCurrentText("same class")
    dialog.overlap_lo.setText("0.99")
    dialog.model_mode.setCurrentText("predictions nobody labelled")
    assert dialog.filter() == ImageFilter(conditions=(
        Boxes(("car",), w=(None, 10), unit="%"), Overlap("same", 0.99, 1.0),
        ModelDisagrees("unlabelled", 0.5, (0.4, 1.0))))


def test_a_size_with_any_class_is_a_size_of_any_box(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.size_h_lo.setText("100")
    assert dialog.filter() == ImageFilter(conditions=(Boxes((), h=(100, None), unit="px"),))


@pytest.mark.parametrize("setup, why", [
    (lambda d: (d.size_w_lo.setText("30"), d.size_w_hi.setText("10")),
     "Box size — width: 30 is above 10: put the lower end first"),
    (lambda d: d.size_w_lo.setText("abc"), "Box size — width: “abc” is not a number"),
    (lambda d: (d.class_mode.setCurrentText("lacks"), d.classes.item(0).setCheckState(Qt.Checked),
                d.size_w_hi.setText("10")),
     "Box size — a size is of boxes an image has: choose has, or any class"),
    (lambda d: (d.overlap_mode.setCurrentText("any class"), d.overlap_hi.setText("1.5")),
     "Overlapping labels — IoU: the upper end cannot be above 1"),
    (lambda d: (d.model_mode.setCurrentText("either"), d.model_lo.setText("0.05")),
     "Model — confidence: the lower end cannot be below 0.1"),
    (lambda d: (d.model_mode.setCurrentText("either"), d.model_iou.setText("")),
     "Model — matching IoU: “” is not a number"),
])
def test_ok_refuses_by_name_and_the_dialog_stays_open(qtbot, dataset, setup, why):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.show()
    setup(dialog)
    dialog.accept()
    assert dialog.isVisible() and dialog.result() != QDialog.Accepted
    assert dialog.error.text() == why and dialog.error.isVisible()


def test_ok_takes_what_the_rows_say_once_they_are_right(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.show()
    dialog.size_w_lo.setText("30")
    dialog.size_w_hi.setText("10")
    dialog.accept()
    dialog.size_w_lo.setText("5")
    dialog.accept()
    assert dialog.result() == QDialog.Accepted
    assert dialog.chosen == ImageFilter(conditions=(Boxes((), w=(5, 10), unit="px"),))


def test_every_row_is_visible_inside_the_dialog_and_none_overlaps(qtbot, dataset):
    from PySide6.QtCore import QPoint, QRect

    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    widgets = [dialog.size_w_lo, dialog.size_w_hi, dialog.size_h_lo, dialog.size_h_hi, dialog.size_unit,
               dialog.overlap_mode, dialog.overlap_lo, dialog.overlap_hi,
               dialog.model_mode, dialog.model_iou, dialog.model_lo, dialog.model_hi]
    rects = []
    for w in widgets:
        rect = QRect(w.mapTo(dialog, QPoint(0, 0)), w.size())
        assert w.isVisible() and w.width() >= 30 and dialog.rect().contains(rect)
        assert not any(rect.intersects(r) for r in rects)
        rects.append(rect)
    assert dialog.height() <= 800
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_editor.py tests/ui/test_filter_view.py`
Expected: 15 failed, 8 passed.

- [ ] **Step 3: The rows, their refusals, and the confidence default**

In `src/deeplabeling/ui/main_window.py`, replace:

```python
            return
        current = self.session.queue.source
        chosen = self.prompter.edit_queue(self.session.workspace.dataset, current)
        if chosen is not None:                      # the same filter again is a refresh
            self.session.set_queue(chosen)
```

with:

```python
            return
        current = self.session.queue.source
        chosen = self.prompter.edit_queue(self.session.workspace.dataset, current, self.session.model.conf)
        if chosen is not None:                      # the same filter again is a refresh
            self.session.set_queue(chosen)
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
"""The queue editor: splits and conditions for slice 1's one source, ImageFilter
(docs/design/2026-10-04-app-foundation.md#queue). It is seeded from the queue in
force, so it never shows a filter the queue is not using (CLAUDE.md landmine 7)."""

from __future__ import annotations

from PySide6.QtCore import Qt
```

with:

```python
"""The queue editor: splits and conditions for slice 1's one source, ImageFilter
(docs/design/2026-10-04-app-foundation.md#queue), with slice 3's box size, overlap and
model rows (docs/design/2026-10-06-filters.md#the-queue-editor). It is seeded from the
queue in force, so it never shows a filter the queue is not using (CLAUDE.md landmine 7).
A value it cannot use is refused when OK is pressed, by row and field, and the dialog stays
open with what was typed: never swapped, never clamped."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
```

with:

```python
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python

from ..core.dataset import Dataset
from ..core.queue import HasClass, ImageFilter, LabelStateIs, NameContains, Reviewed

CLASS_MODES = ("any class", "has", "lacks")
LABEL_MODES = ("any", "missing", "negative", "boxes")
REVIEW_MODES = ("any", "reviewed", "not reviewed")


class QueueEditor(QDialog):
    def __init__(self, dataset: Dataset, current: ImageFilter, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Queue")
```

with:

```python

from ..core.dataset import Dataset
from ..core.queue import (
    UNITS,
    Boxes,
    HasClass,
    ImageFilter,
    LabelStateIs,
    ModelDisagrees,
    NameContains,
    Overlap,
    Reviewed,
)

CLASS_MODES = ("any class", "has", "lacks")
LABEL_MODES = ("any", "missing", "negative", "boxes")
REVIEW_MODES = ("any", "reviewed", "not reviewed")
OVERLAP_MODES = {"off": None, "different classes": "different", "same class": "same", "any class": "any"}
MODEL_MODES = {"off": None, "labels the model does not see": "unseen",
               "predictions nobody labelled": "unlabelled", "either": "either"}


def _row(*widgets) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        layout.addWidget(w)
    return row


def _edit(text: str = "") -> QLineEdit:
    edit = QLineEdit(text)
    edit.setMinimumWidth(48)
    return edit


def _text(value) -> str:
    return "" if value is None else f"{value:g}"


def _number(edit: QLineEdit, name: str, *, blank: bool = False) -> float | None:
    """The number typed, None for a blank where a blank is an open end, else ValueError."""
    text = edit.text().strip()
    if not text and blank:
        return None
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise ValueError(f"{name}: “{text}” is not a number")
    return value


class QueueEditor(QDialog):
    def __init__(self, dataset: Dataset, current: ImageFilter, parent=None, *, conf: float = 0.25):
        super().__init__(parent)
        self.setWindowTitle("Queue")
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
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
```

with:

```python
        self.review_mode.addItems(REVIEW_MODES)
        self.name = QLineEdit()
        self.size_w_lo, self.size_w_hi, self.size_h_lo, self.size_h_hi = (_edit() for _ in range(4))
        self.size_unit = QComboBox()
        self.size_unit.addItems(UNITS)
        self.overlap_mode = QComboBox()
        self.overlap_mode.addItems(OVERLAP_MODES)
        self.overlap_lo, self.overlap_hi = _edit("0.5"), _edit("1")
        self.model_mode = QComboBox()
        self.model_mode.addItems(MODEL_MODES)
        self.model_iou, self.model_lo, self.model_hi = _edit("0.5"), _edit(f"{conf:g}"), _edit("1")
        self.error = QLabel()
        self.error.setStyleSheet("color: #e05252;")
        self.error.setWordWrap(True)
        self.error.hide()
        self.chosen: ImageFilter | None = None      #: what OK took
        form = QFormLayout()
        form.addRow("Splits", split_row)
        form.addRow("Classes", self.class_mode)
        form.addRow("", self.classes)
        form.addRow("Box size", _row(QLabel("W"), self.size_w_lo, QLabel("–"), self.size_w_hi,
                                     QLabel("H"), self.size_h_lo, QLabel("–"), self.size_h_hi, self.size_unit))
        form.addRow("Label file", self.label_mode)
        form.addRow("Reviewed", self.review_mode)
        form.addRow("Name contains", self.name)
        form.addRow("Overlapping labels", _row(self.overlap_mode, QLabel("IoU"), self.overlap_lo,
                                               QLabel("–"), self.overlap_hi))
        form.addRow("Model", self.model_mode)
        form.addRow("", _row(QLabel("matching IoU"), self.model_iou, QLabel("conf"), self.model_lo,
                             QLabel("–"), self.model_hi))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._seed(current)
```

with:

```python
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self._seed(current)
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
            box.setChecked(not current.splits or name in current.splits)
        for condition in current.conditions:
            if isinstance(condition, HasClass):
                self.class_mode.setCurrentText("has" if condition.present else "lacks")
                for i in range(self.classes.count()):
                    item = self.classes.item(i)
                    item.setCheckState(Qt.Checked if item.text() in condition.names else Qt.Unchecked)
            elif isinstance(condition, LabelStateIs):
                self.label_mode.setCurrentText(condition.state)
```

with:

```python
            box.setChecked(not current.splits or name in current.splits)
        for condition in current.conditions:
            if isinstance(condition, (HasClass, Boxes)):
                present = condition.present if isinstance(condition, HasClass) else True
                self.class_mode.setCurrentText(("has" if condition.names else "any class") if present else "lacks")
                for i in range(self.classes.count()):
                    item = self.classes.item(i)
                    item.setCheckState(Qt.Checked if item.text() in condition.names else Qt.Unchecked)
            if isinstance(condition, Boxes):
                for edit, value in zip((self.size_w_lo, self.size_w_hi, self.size_h_lo, self.size_h_hi),
                                       (*condition.w, *condition.h)):
                    edit.setText(_text(value))
                self.size_unit.setCurrentText(condition.unit)
            elif isinstance(condition, Overlap):
                self.overlap_mode.setCurrentText(next(k for k, v in OVERLAP_MODES.items() if v == condition.scope))
                self.overlap_lo.setText(_text(condition.lo))
                self.overlap_hi.setText(_text(condition.hi))
            elif isinstance(condition, ModelDisagrees):
                self.model_mode.setCurrentText(next(k for k, v in MODEL_MODES.items() if v == condition.direction))
                self.model_iou.setText(_text(condition.match_iou))
                self.model_lo.setText(_text(condition.conf[0]))
                self.model_hi.setText(_text(condition.conf[1]))
            elif isinstance(condition, LabelStateIs):
                self.label_mode.setCurrentText(condition.state)
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
                self.name.setText(condition.text)

    def filter(self) -> ImageFilter:
        """The queue the dialog describes. All splits checked means every split."""
        checked = tuple(name for name, box in self.splits.items() if box.isChecked())
        splits = () if len(checked) == len(self.splits) else checked
```

with:

```python
                self.name.setText(condition.text)

    def accept(self) -> None:
        """OK: take the queue the rows describe, or say why not and stay open."""
        try:
            self.chosen = self.filter()
        except ValueError as e:
            self.error.setText(str(e))
            self.error.show()
            return
        self.error.hide()
        super().accept()

    def filter(self) -> ImageFilter:
        """The queue the dialog describes. All splits checked means every split. ValueError,
        naming the row and the field, when a row cannot be used."""
        checked = tuple(name for name, box in self.splits.items() if box.isChecked())
        splits = () if len(checked) == len(self.splits) else checked
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
        names = tuple(self.classes.item(i).text() for i in range(self.classes.count())
                      if self.classes.item(i).checkState() == Qt.Checked)
        if self.class_mode.currentText() != "any class" and names:
            conditions.append(HasClass(names, present=self.class_mode.currentText() == "has"))
        if self.label_mode.currentText() != "any":
            conditions.append(LabelStateIs(self.label_mode.currentText()))
```

with:

```python
        names = tuple(self.classes.item(i).text() for i in range(self.classes.count())
                      if self.classes.item(i).checkState() == Qt.Checked)
        mode = self.class_mode.currentText()
        size = self._size()
        if size is not None:
            if mode == "lacks":
                raise ValueError("Box size — a size is of boxes an image has: choose has, or any class")
            conditions.append(self._made("Box size", Boxes, names if mode == "has" else (), *size))
        elif mode != "any class" and names:
            conditions.append(HasClass(names, present=mode == "has"))
        if self.label_mode.currentText() != "any":
            conditions.append(LabelStateIs(self.label_mode.currentText()))
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
        if self.name.text().strip():
            conditions.append(NameContains(self.name.text().strip()))
        return ImageFilter(splits, tuple(conditions))
```

with:

```python
        if self.name.text().strip():
            conditions.append(NameContains(self.name.text().strip()))
        scope = OVERLAP_MODES[self.overlap_mode.currentText()]
        if scope is not None:
            conditions.append(self._made("Overlapping labels", Overlap, scope, _number(self.overlap_lo, "IoU"),
                                         _number(self.overlap_hi, "IoU")))
        direction = MODEL_MODES[self.model_mode.currentText()]
        if direction is not None:
            conditions.append(self._made("Model", lambda: ModelDisagrees(
                direction, _number(self.model_iou, "matching IoU"),
                (_number(self.model_lo, "confidence"), _number(self.model_hi, "confidence")))))
        return ImageFilter(splits, tuple(conditions))

    def _size(self):
        """(w, h, unit) when any size end is typed, else None. ValueError for junk."""
        try:
            ends = [_number(e, name, blank=True) for e, name in ((self.size_w_lo, "width"), (self.size_w_hi, "width"),
                                                                 (self.size_h_lo, "height"), (self.size_h_hi, "height"))]
        except ValueError as e:
            raise ValueError(f"Box size — {e}") from e
        if all(end is None for end in ends):
            return None
        return (ends[0], ends[1]), (ends[2], ends[3]), self.size_unit.currentText()

    @staticmethod
    def _made(row: str, make, *args):
        """A condition, or ValueError naming the row it came from."""
        try:
            return make(*args)
        except ValueError as e:
            raise ValueError(f"{row} — {e}") from e
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
        return QFileDialog.getExistingDirectory(self.parent, title) or None

    def edit_queue(self, dataset: Dataset, current: ImageFilter) -> ImageFilter | None:
        dialog = QueueEditor(dataset, current, self.parent)
        try:
            return dialog.filter() if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()                    # a child of the window until deleted
```

with:

```python
        return QFileDialog.getExistingDirectory(self.parent, title) or None

    def edit_queue(self, dataset: Dataset, current: ImageFilter, conf: float = 0.25) -> ImageFilter | None:
        dialog = QueueEditor(dataset, current, self.parent, conf=conf)
        try:
            return dialog.chosen if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()                    # a child of the window until deleted
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_editor.py tests/ui/test_filter_view.py tests/ui/test_prompter.py tests/ui/test_main_window.py`
Expected: 49 passed.

- [ ] **Step 5: Look at it**

Seed a `QueueEditor` with `Boxes(("car",), w=(10, 30), unit="px")`, `Overlap("same", 0.99, 1.0)` and `ModelDisagrees("unlabelled")`. Type `40` into the width's lower end, press OK, save `dialog.grab()` and open the PNG. Expected: every row is readable, and `Box size — width: 40 is above 30: put the lower end first` shows in red above OK, with the 40 still typed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 774 passed.

```bash
git add src/deeplabeling/ui/queue_editor.py src/deeplabeling/ui/prompter.py src/deeplabeling/ui/main_window.py tests/fixtures.py tests/ui/test_queue_editor.py tests/ui/test_filter_view.py
git commit -m "ui: the queue editor's size, overlap and model rows, refusing what it cannot use by name" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The window's measurements, and the docs

**Files:**
- Modify:
  - `tools/measure_assist.py`;
  - `docs/design/2026-10-06-filters.md` (the status, inferring a model queue, the chip's examples, the measured rows);
  - `CLAUDE.md` (the status).

**Interfaces:**
- Consumes: everything above.
- Produces: three more lines from `tools/measure_assist.py` for each of two queues built in the window: first items, complete, and the event loop's longest wait.

- [ ] **Step 1: Measure the window's builds**

In `tools/measure_assist.py`, replace:

```python
#!/usr/bin/env python3
"""Measure slice 2's performance targets with a real model on a real dataset, read-only
(docs/design/2026-10-05-model-assist.md#performance-targets).

App state -- the prediction store included -- goes to a temporary folder, deleted at the
```

with:

```python
#!/usr/bin/env python3
"""Measure slice 2's performance targets with a real model on a real dataset, read-only
(docs/design/2026-10-05-model-assist.md#performance-targets), and slice 3's model and size
conditions as the window builds them (docs/design/2026-10-06-filters.md#performance-targets).

App state -- the prediction store included -- goes to a temporary folder, deleted at the
```

In `tools/measure_assist.py`, replace:

```python
    settings_before = md5(SETTINGS)

    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch

    app = QApplication.instance() or QApplication(sys.argv[:1])
```

with:

```python
    settings_before = md5(SETTINGS)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch
    from deeplabeling.core.queue import Boxes, ImageFilter, ModelDisagrees

    app = QApplication.instance() or QApplication(sys.argv[:1])
```

In `tools/measure_assist.py`, replace:

```python
    store.inferred(model.key)
    rows.append((f"the store's rows read when a model loads ({len(rows_now):,} rows)", time.perf_counter() - t, "(none)"))
    files = [store.path, store.path.with_name(store.path.name + "-wal")]
    size = sum(f.stat().st_size for f in files if f.exists())
```

with:

```python
    store.inferred(model.key)
    rows.append((f"the store's rows read when a model loads ({len(rows_now):,} rows)", time.perf_counter() - t, "(none)"))

    def build(name, condition) -> None:
        """A queue built in the window: its first items, its end, and the longest the
        event loop went without a turn meanwhile, which is what paging would wait."""
        gaps, last = [], [time.perf_counter()]

        def tick():
            now = time.perf_counter()
            gaps.append(now - last[0])
            last[0] = now

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(5)
        t = time.perf_counter()
        s.set_queue(ImageFilter(conditions=(condition,)))
        first = wait(app, lambda: len(s.queue) > 0 or s.queue.complete)
        total = first + wait(app, lambda: s.queue.complete)
        timer.stop()
        rows.append((f"{name}: first items", first, "≤ 1 s"))
        rows.append((f"{name}: complete, {len(s.queue):,} images{s.progress_text()}", total, "≤ 30 s cold"))
        rows.append((f"{name}: the event loop's longest wait", max(gaps), "≤ 100 ms"))

    build("labels the model does not see", ModelDisagrees("unseen"))
    build("a size in px, cold", Boxes((), w=(None, 10), unit="px"))
    files = [store.path, store.path.with_name(store.path.name + "-wal")]
    size = sum(f.stat().st_size for f in files if f.exists())
```

- [ ] **Step 2: Run it once, from the repository root, read-only**

Run: `/home/sonnn/miniconda3/bin/python3 tools/measure_assist.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml /home/sonnn/Documents/ultralytics/runs/detect/backup/yolo26n_vehicle/weights/best.pt --pass-seconds 30`
Expected:
- every target met (2026-10-06: the model condition 231 ms / 709 ms; a size in px, cold, 8.62 s; the event loop's longest wait 48 ms and 24 ms);
- `ultralytics settings unchanged: True`;
- `git status` shows nothing new in the dataset.

A missed target is a finding: run it twice more, then record what was measured.

- [ ] **Step 3: Record the measurements, and update the status**

The table below holds the 2026-10-06 figures. Where your run's figures differ, write yours, with your date.

In `CLAUDE.md`, replace:

````markdown
**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. Slice 3 (filters) has its core built; its UI (plan 3b) is next. The
design and the plans are in [docs/design/](docs/design/).

```sh
````

with:

````markdown
**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. The design and the plans are in [docs/design/](docs/design/).

```sh
````

In `docs/design/2026-10-06-filters.md`, replace:

```markdown
# DeepLabeling — slice 3: filters

**Status:** approved 2026-10-06 · plan 3a (the core) implemented; 3b (the UI) next
**Scope:** slice 3 of [the app foundation](2026-10-04-app-foundation.md#slices): box size,
overlap between labels and Label/Prediction IoU become conditions of the one queue source,
```

with:

```markdown
# DeepLabeling — slice 3: filters

**Status:** approved 2026-10-06 · implemented: plans 3a (the core) and 3b (the UI)
**Scope:** slice 3 of [the app foundation](2026-10-04-app-foundation.md#slices): box size,
overlap between labels and Label/Prediction IoU become conditions of the one queue source,
```

In `docs/design/2026-10-06-filters.md`, replace:

```markdown
  and says so; it builds when the model is ready. With no model loaded, the queue is empty
  and a notice says the queue needs a model.
- **Saved** with the queue for each opening, as every condition is, and restored on every
  launch path ([landmine 7](../../CLAUDE.md#landmines)).
```

with:

```markdown
  and says so; it builds when the model is ready. With no model loaded, the queue is empty
  and a notice says the queue needs a model.
- **Inferring a model queue:** *Infer this queue* also infers the images it left out as not
  inferred, and each joins the queue, in dataset order, as its predictions arrive. Without
  that, a model queue on a fresh store would be empty and nothing would fill it.
- **Saved** with the queue for each opening, as every condition is, and restored on every
  launch path ([landmine 7](../../CLAUDE.md#landmines)).
```

In `docs/design/2026-10-06-filters.md`, replace:

```markdown
### The queue chip

It describes every condition in words, then what the build could not settle:
`has car 10–30 px wide · labels overlapping, same class, IoU 0.99–1.00`,
`labels the model does not see (IoU 0.50, conf ≥ 0.25) · 1,204 not inferred`,
`· waiting for the model`, `· 3 images could not be sized`.

### The canvas
```

with:

```markdown
### The queue chip

It describes every condition in words, joined by "and", then what the build could not
settle: `has a car 10–30 px wide and labels overlapping, same class, IoU 0.99–1.00`,
`labels the model does not see (IoU 0.50, conf ≥ 0.25) · 1,204 not inferred`,
`· waiting for the model`, `· needs a model`, `· 3 images could not be sized`.

### The canvas
```

In `docs/design/2026-10-06-filters.md`, replace:

```markdown
| a size, overlap or model condition over 45k images: first items | ≤ 1 s | 73–724 ms warm, 172–200 ms cold; **missed once:** 1.33 s cold for overlap, same class, IoU 0.9–1.0, whose only match in 45k images lies that far in |
| the same, complete: cold / warm caches | ≤ 30 s / ≤ 5 s, streaming | a size in px 6.15 s / 0.93 s; in % 2.67 s / 0.61 s; overlap 3.65–5.34 s / 1.77–3.37 s |
| the image on screen while such a queue builds | as without one: [slice 1's targets](2026-10-04-app-foundation.md#performance-targets) | plan 3b |

- "Cold" is a fresh label store and size cache, as the first build after opening: every
```

with:

```markdown
| a size, overlap or model condition over 45k images: first items | ≤ 1 s | 73–724 ms warm, 172–200 ms cold; **missed once:** 1.33 s cold for overlap, same class, IoU 0.9–1.0, whose only match in 45k images lies that far in |
| the same, complete: cold / warm caches | ≤ 30 s / ≤ 5 s, streaming | a size in px 6.15 s / 0.93 s; in % 2.67 s / 0.61 s; overlap 3.65–5.34 s / 1.77–3.37 s |
| the model condition, in the window, with 3,843 of 45,252 images inferred: first items / complete | ≤ 1 s / ≤ 30 s | 231 ms / 709 ms (2026-10-06) |
| the image on screen while such a queue builds | as without one: [slice 1's targets](2026-10-04-app-foundation.md#performance-targets) | the event loop's longest wait: 48 ms building the model condition, 24 ms a size in px, cold (2026-10-06) |

- "Cold" is a fresh label store and size cache, as the first build after opening: every
```

In `docs/design/2026-10-06-filters.md`, replace:

```markdown
  measured in plan 3b, with the model's rows.
- A condition with few matches cannot show its first item before it reaches the first one.
- Reproduce the core's figures, read-only (no app state is written):

```

with:

```markdown
  measured in plan 3b, with the model's rows.
- A condition with few matches cannot show its first item before it reaches the first one.
- The window's figures come from `tools/measure_assist.py`, read-only, after its pass; the
  image on screen is held to slice 1's paging target through the event loop's longest wait.
- Reproduce the core's figures, read-only (no app state is written):

```

- [ ] **Step 4: Check the docs, and run the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 774 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/measure_assist.py docs/design/2026-10-06-filters.md CLAUDE.md
git commit -m "docs: slice 3 is built; its window builds measured with the real model" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
