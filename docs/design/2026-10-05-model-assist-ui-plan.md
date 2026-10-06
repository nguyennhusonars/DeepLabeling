# Slice 2b: model assist on screen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put plan 2a's core on screen. It covers:
- a thread that owns the model and predicts the image on screen and its neighbours;
- the predictions layer on the canvas;
- accepting on screen: `A` for the image, a double-click for one box;
- the model chip, with the class-map editor;
- the inspector's Predictions line.

**Architecture:** `ui/model.py` holds `ModelSession`, the session's view of the model. It owns one `QThread` that loads the predictor, asks it for the images on screen, and writes the answers into the prediction store. The GUI reads only the store and never waits on the thread. The window draws predictions from the store through `Canvas.set_boxes`, so an edit still redraws once. `Editing` accepts from the snapshot the canvas drew, through slice 1's one write path.

**Tech Stack:** Python 3.10 (conda base), PySide6, pytest-qt; the core from plan 2a.

**Spec:** [2026-10-05-model-assist.md](2026-10-05-model-assist.md). This plan implements:
- *The inference thread*, except the dataset pass;
- *Window*: the predictions layer, the model chip without the pass's entries, the inspector and the keys;
- *Accepting*: double-click and `A`;
- the *Errors* rows for loading, predicting and unmapped classes.

Plan 2c builds the rest:
- the dataset pass;
- the queue accept, with its chunked dialog;
- chunked undo and redo;
- the chip's inferred count;
- the performance measurements.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)).
- **The GUI thread never waits on the model; the thread never touches a widget** ([landmine 3](../../CLAUDE.md#landmines)). The thread talks to the GUI only through queued signals and the prediction store.
- **One owner for each image's labels** ([landmine 2](../../CLAUDE.md#landmines)) and **one write path** ([landmine 1](../../CLAUDE.md#landmines)): an accept is an `Intent` applied through `Session.apply`.
- **A UI change is verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines)): predictions are read back from `grab()` pixels and from the canvas's own items, and dialogs by their geometry.
- **Unmapped is never accepted** ([landmine 5](../../CLAUDE.md#landmines)): it is drawn grey with a `?`, and an accept skips it and says so.
- **Every setting survives every launch path** ([landmine 7](../../CLAUDE.md#landmines)): the layer, the last model, the threshold and the class map are each tested across a relaunch.
- **Tests never load a real model.** Task 2 makes `import ultralytics` fail in every test; the fake is `FakePredictor`, which Task 2 adds to `tests/fixtures.py` ([landmine 8](../../CLAUDE.md#landmines)).
- **Tests write only to temporary folders** ([landmine 10](../../CLAUDE.md#landmines)).
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice2-model-assist-ui`, from `main`. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone using this window. Each has a named test:

1. **Paging fast through a long queue while the model works.** The window must keep up, and the model must predict where the cursor stops, not every image passed on the way. *(Task 2 `test_fast_paging_predicts_where_the_cursor_stops`, `test_the_image_on_screen_goes_before_its_neighbours`.)*
2. **Closing the dataset or quitting while a prediction is in hand.** Closing waits at most 2 s and never crashes: Qt aborts the process when a running thread is destroyed. *(Task 2 `test_shutdown_waits_at_most_two_seconds`, `test_closing_lets_the_model_go_and_reopening_loads_it_again`.)*
3. **An image that fails** (CUDA out of memory, an undecodable frame). It is said once and not asked for again, and the model stays loaded. *(Task 2 `test_a_failed_prediction_is_said_once_and_not_retried`; Task 6 `test_the_inspector_says_when_the_model_could_not_predict`.)*
4. **A prediction of a class the map leaves out.** It is drawn grey with a `?`. `A` skips it and says how many it skipped; a double-click names the class and points to the class map. *(Task 4 `test_a_accepts_the_missing_mapped_predictions_and_says_what_it_skipped`, `test_double_clicking_an_unmapped_prediction_says_so_and_adds_nothing`.)*
5. **A remembered model whose file is gone, or one that does not load.** Neither must block opening the dataset. *(Task 5 `test_a_remembered_model_that_is_gone_is_not_loaded`, `test_a_model_that_does_not_load_says_why`.)*

## Found while building this plan

The plan's code was built in a scratch copy first, and its suite ran green there (641 passed). The scratch window was then run once with the real `yolo26n_vehicle/weights/best.pt` on three pvn-vehicle frames, offscreen, with app state in a temporary folder:
- the model loaded in 0.9 s, and the first image's predictions were drawn 1.3 s after the load began;
- the next image's predictions were on screen at once, inferred as a neighbour;
- closing took no measurable time;
- `~/.config/Ultralytics/settings.json` kept its md5;
- the store was written under the app state folder, never into the dataset.

- **A `QThread` destroyed while running aborts the whole process.** Closing a dataset mid-prediction did exactly that. The thread now has no Qt parent and is stopped with a bounded wait. A thread that is still finishing is kept in `_FINISHING` until it ends.
- **The store has a row before the GUI hears of it.** The thread writes the row and then emits `ready`, and the screen updates on `ready`. A check that polls the store can see the row while the screen does not show it yet, so tests wait for what is on screen.
- **A faint prediction's caption collided with its label's.** A covered prediction sits on its label, so the two plates overlapped. Faint predictions are drawn without a caption.
- **The predictions layer is on by default**, so the Layers chip lists it. Four slice 1 assertions on that chip's text change in Task 4.

## Decisions this plan makes

- **Predictions go into the same `Canvas.set_boxes` call as the labels**, so an edit still redraws once. A prediction that arrives later redraws through `Canvas.set_predictions`.
- **An accept uses the predictions the canvas drew** (`Editing.show_predictions`). This is the same snapshot pattern as slice 1's stale-index fix.
- **The inspector's "missing" counts what `A` would add:** missing predictions of a mapped class.
- **The chip's menu has no "unload".** The spec lists none; closing the dataset lets the model go.
- **The chip's `N / M inferred` count comes with plan 2c's pass**, which keeps it current. Plan 2b's chip shows the name, the classes and the threshold.
- **Chunked undo and redo of a queue accept move to plan 2c**, with the queue accept itself. The spec says so after Task 7.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/inference.py`, `predstore.py` | `Predictor.close`; a closed store answers nothing | 1 |
| `src/deeplabeling/ui/model.py`, `session.py` | `ModelSession`: the thread, loading, the screen's requests, failures | 2 |
| `src/deeplabeling/ui/boxes.py`, `canvas.py` | `PredictionView`; the dashed layer, captions above, faint, double-click | 3 |
| `src/deeplabeling/ui/editing.py`, `keymap.py`, `settings_ui.py`, `main_window.py` | `A`, double-click, `P`; the window draws predictions | 4 |
| `src/deeplabeling/ui/class_map_dialog.py`, `prompter.py`, `state_bar.py`, `main_window.py` | the model chip and its menu; the class-map editor | 5 |
| `src/deeplabeling/ui/inspector.py` | the Predictions line | 6 |
| `CLAUDE.md`, the spec, the run-and-verify-ui skill | the status; what testing a model in the UI takes | 7 |

---

### Task 1: Letting go of a model

**Files:**
- Modify: `src/deeplabeling/core/inference.py`, `src/deeplabeling/core/predstore.py`
- Test: `tests/core/test_inference.py`, `tests/core/test_predstore.py`

**Interfaces:**
- Consumes: plan 2a's `UltralyticsPredictor` and `PredictionStore`.
- Produces:
  - `Predictor.close()` in the protocol. `UltralyticsPredictor.close()` lets go of the model, its decode threads and the CUDA cache; `predict` afterwards raises `ModelError("this model is closed")`.
  - `PredictionStore.close()` marks the store closed. Afterwards `get` returns `None`, `put` and `put_many` are dropped, and `inferred` returns `{}`. A thread still finishing a prediction when the dataset closes therefore writes nothing.

- [ ] **Step 1: Commit this plan, on its branch**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout -b slice2-model-assist-ui main
git add docs/design/2026-10-05-model-assist-ui-plan.md
git commit -m "docs: the slice 2b model-assist UI plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/core/test_inference.py`:

```python
def test_a_closed_predictor_lets_go_of_its_model_and_its_decoders(predictor, tmp_path):
    predictor.close()
    assert predictor._model is None and predictor._decoder._shutdown
    with pytest.raises(ModelError, match="closed"):
        predictor.predict([tmp_path / "a.jpg"])
    predictor.close()                                       # twice is harmless
```

Append to `tests/core/test_predstore.py`:

```python
def test_a_closed_store_answers_nothing_and_drops_late_writes(tmp_path, image):
    store = PredictionStore(tmp_path / STORE_NAME)
    store.put(MODEL, "a.jpg", image_stamp(image), [CAR])
    store.close()
    store.put(MODEL, "b.jpg", (1, 2), [CAR])                # an inference thread, after the close
    assert store.get(MODEL, "a.jpg", image_stamp(image)) is None and store.inferred(MODEL) == {}
    assert store._all == []                                  # no connection was opened again
    again = PredictionStore(tmp_path / STORE_NAME)
    assert again.inferred(MODEL) == {"a.jpg": image_stamp(image)}
    again.close()
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_inference.py tests/core/test_predstore.py`
Expected: 2 failed, 21 passed: the two new tests fail, on `close`.

- [ ] **Step 4: Close the predictor and the store**

In `src/deeplabeling/core/inference.py`, replace:

```python

    def predict(self, paths: Sequence[Path]) -> list[list[Prediction] | Failure]: ...


```

with:

```python

    def predict(self, paths: Sequence[Path]) -> list[list[Prediction] | Failure]: ...

    def close(self) -> None: ...


```

In `src/deeplabeling/core/inference.py`, replace:

```python
        self._decoder = ThreadPoolExecutor(DECODE_THREADS)

    def predict(self, paths: Sequence[Path]) -> list[list[Prediction] | Failure]:
        """One answer per path. An image that cannot be read fails alone; a batch the
        model fails on is retried image by image, so one bad image never fails the rest."""
        images = list(self._decoder.map(_read, paths))
        answers: list[list[Prediction] | Failure] = [
```

with:

```python
        self._decoder = ThreadPoolExecutor(DECODE_THREADS)

    def close(self) -> None:
        """Let go of the model, and its GPU memory, and of the decode threads."""
        if self._model is None:
            return
        self._model = None
        self._decoder.shutdown(wait=False, cancel_futures=True)
        import sys

        torch = sys.modules.get("torch")            # loaded with the model, if at all
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def predict(self, paths: Sequence[Path]) -> list[list[Prediction] | Failure]:
        """One answer per path. An image that cannot be read fails alone; a batch the
        model fails on is retried image by image, so one bad image never fails the rest."""
        if self._model is None:
            raise ModelError("this model is closed")
        images = list(self._decoder.map(_read, paths))
        answers: list[list[Prediction] | Failure] = [
```

In `src/deeplabeling/core/predstore.py`, replace:

```python
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        try:
            try:
```

with:

```python
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._closed = False
        try:
            try:
```

In `src/deeplabeling/core/predstore.py`, replace:

```python
        """What `model` found on `img`, at or above `conf`: None when it never looked at
        this image as it is now, or not down to `conf`; [] when it found nothing."""
        row = self._connection().execute(
            "SELECT size, mtime_ns, floor, boxes FROM preds WHERE model = ? AND img = ?",
```

with:

```python
        """What `model` found on `img`, at or above `conf`: None when it never looked at
        this image as it is now, or not down to `conf`; [] when it found nothing."""
        if self._closed:
            return None
        row = self._connection().execute(
            "SELECT size, mtime_ns, floor, boxes FROM preds WHERE model = ? AND img = ?",
```

In `src/deeplabeling/core/predstore.py`, replace:

```python
    def put_many(self, model: str, rows: Iterable[tuple[str, Stamp, Iterable[Prediction]]]) -> None:
        """Write rows in one transaction: a cancelled or crashed pass keeps every batch
        it committed."""
        conn = self._connection()
        with conn:
```

with:

```python
    def put_many(self, model: str, rows: Iterable[tuple[str, Stamp, Iterable[Prediction]]]) -> None:
        """Write rows in one transaction: a cancelled or crashed pass keeps every batch
        it committed. After close() they are dropped: the dataset they were for is shut."""
        if self._closed:
            return
        conn = self._connection()
        with conn:
```

In `src/deeplabeling/core/predstore.py`, replace:

```python
        """Every image `model` has a row for, with the stamp it was inferred at: what a
        pass reads to know what is left, without reading the boxes."""
        rows = self._connection().execute(
            "SELECT img, size, mtime_ns FROM preds WHERE model = ?", (model,))
```

with:

```python
        """Every image `model` has a row for, with the stamp it was inferred at: what a
        pass reads to know what is left, without reading the boxes."""
        if self._closed:
            return {}
        rows = self._connection().execute(
            "SELECT img, size, mtime_ns FROM preds WHERE model = ?", (model,))
```

In `src/deeplabeling/core/predstore.py`, replace:

```python

    def close(self) -> None:
        self._close_all()
```

with:

```python

    def close(self) -> None:
        """Close every connection; afterwards the store answers nothing and writes nothing,
        rather than opening a connection again for a thread that comes late."""
        self._closed = True
        self._close_all()
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_inference.py tests/core/test_predstore.py`
Expected: 23 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 598 passed.

```bash
git add src/deeplabeling/core/inference.py src/deeplabeling/core/predstore.py tests/core/test_inference.py tests/core/test_predstore.py
git commit -m "core: a closed predictor lets its model go; a closed store answers nothing" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The inference thread

**Files:**
- Create: `src/deeplabeling/ui/model.py`, `tests/ui/test_model.py`
- Modify: `src/deeplabeling/ui/session.py`, `tests/fixtures.py`, `tests/conftest.py`

**Interfaces:**
- Consumes:
  - from Task 1: `Predictor.close`, `PredictionStore.close`;
  - from plan 2a: `UltralyticsPredictor`, `FLOOR`, `Failure`, `ModelError`, `image_stamp`, `load_class_map`, `save_class_map`, `shown_predictions`;
  - from slice 1: the session's `cursorChanged`, `opened` and `notice` signals, `Session.saver`, and `Workspace.predictions`.
- Produces in `deeplabeling.ui.model`:
  - settings:
    - `MODEL_PATH`, for each opening, `str | None`;
    - `RECENT_MODELS`, global, newest first, at most `RECENT_MAX = 8`;
    - `PRED_CONF`, for each root, default 0.25, `FLOOR ≤ v ≤ 1`;
  - `SHUTDOWN_MS = 2000`, and `NEIGHBOURS = (1, 2, -1)`, the queue offsets predicted after the image on screen;
  - `ModelSession(session)`, as `Session.model`:
    - signals: `changed()`, `ready(path)` and `failed(path, why)`;
    - `factory`, a callable taking a weights path; the default is `UltralyticsPredictor`;
    - `state`: `"none"`, `"loading"`, `"ready"` or `"failed"`;
    - `path`, `key`, `names`, `error` and `class_map`;
    - `load(path)`, `unload()`, `release()` and `shutdown()`;
    - `conf`, a property, and `set_conf(value)`, which raises `ValueError` below the floor;
    - `set_class_map(cmap)`;
    - `predictions(entry)`, `shown(entry) -> list[Shown] | None`, `failure(entry) -> str | None` and `want_screen()`.
  - `Session.close()` calls `model.release()` before the store closes.
- Produces in `tests/fixtures.py`: `FakePredictor(path, *, names=("car", "truck", "human"), found=None, fail=(), gate=None)`:
  - its key is `fake:<file name>`;
  - a file whose name contains `broken` raises `ModelError`;
  - `found` maps an image's file name to its predictions;
  - `fail` lists file names that fail with `CUDA out of memory`;
  - `gate` is an event that `predict` waits on;
  - it records `asked` and `closed`.
- Produces in `tests/conftest.py`: `_no_real_model`, autouse, which makes `import ultralytics` fail.

- [ ] **Step 1: Write the failing tests and the fake**

In `tests/fixtures.py`, replace:

```python


def open_session(qtbot, source, prompter=None, **kw):
    """A Session with `source` open and its first queue fully built."""
```

with:

```python



def open_session(qtbot, source, prompter=None, **kw):
    """A Session with `source` open and its first queue fully built."""
```

In `tests/fixtures.py`, replace:

```python
    def to_json(self):
        return {"kind": self.kind}
```

with:

```python
    def to_json(self):
        return {"kind": self.kind}


class FakePredictor:
    """Stands in for UltralyticsPredictor: finds what it is told per file name, fails the
    names it is told to, records what it was asked, and can be held at a gate."""

    def __init__(self, path, *, names=("car", "truck", "human"), found=None, fail=(), gate=None):
        from deeplabeling.core.inference import ModelError

        if "broken" in Path(path).name:
            raise ModelError(f"{Path(path).name} could not be loaded: not a model")
        self.key, self.names = f"fake:{Path(path).name}", tuple(names)
        self.found, self.fail, self.gate = dict(found or {}), set(fail), gate
        self.asked: list[str] = []
        self.closed = False

    def predict(self, paths):
        from deeplabeling.core.inference import Failure

        if self.gate is not None:
            self.gate.wait(10)
        out = []
        for path in paths:
            self.asked.append(Path(path).name)
            out.append(Failure(f"{Path(path).name}: CUDA out of memory") if Path(path).name in self.fail
                       else list(self.found.get(Path(path).name, [])))
        return out

    def close(self):
        self.closed = True
```

In `tests/conftest.py`, replace:

```python

import os
from pathlib import Path

```

with:

```python

import os
import sys
from pathlib import Path

```

In `tests/conftest.py`, replace:

```python


@pytest.fixture
def ds(tmp_path):
```

with:

```python


@pytest.fixture(autouse=True)
def _no_real_model(monkeypatch):
    """No test loads a real model: `import ultralytics` fails, so a weights file opened
    without a fake predictor is a model that does not load (CLAUDE.md landmine 8)."""
    monkeypatch.setitem(sys.modules, "ultralytics", None)


@pytest.fixture
def ds(tmp_path):
```

Create `tests/ui/test_model.py`:

```python
"""The model for the session: loading, the image on screen first, the store first, and a
GUI that never waits (docs/design/2026-10-05-model-assist.md#the-inference-thread)."""

import threading
import time

import pytest

from deeplabeling.core.inference import Prediction
from deeplabeling.ui.model import MODEL_PATH, PRED_CONF, RECENT_MODELS
from fixtures import FakePredictor, open_session

CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9)
HUMAN = Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)


@pytest.fixture
def made():
    return []


@pytest.fixture
def factory(made):
    """The fake predictor every load makes; made[-1] is the latest."""
    def make(path, **kw):
        predictor = FakePredictor(path, found={"0001.jpg": [CAR, HUMAN]}, **kw)
        made.append(predictor)
        return predictor
    return make


@pytest.fixture
def weights(tmp_path):
    path = tmp_path / "best.pt"
    path.write_bytes(b"weights")
    return path


def load(qtbot, session, weights, factory):
    session.model.factory = factory
    with qtbot.waitSignal(session.model.changed, timeout=5000,
                          check_params_cb=lambda: session.model.state == "ready"):
        session.model.load(weights)


def test_loading_a_model_names_it_and_remembers_it(qtbot, session, weights, factory):
    load(qtbot, session, weights, factory)
    model = session.model
    assert (model.state, model.key, model.names) == ("ready", "fake:best.pt", ("car", "truck", "human"))
    assert session.workspace.opening_settings.get(MODEL_PATH) == str(weights)
    assert session.settings.get(RECENT_MODELS)[0] == str(weights)


def test_a_file_that_does_not_load_says_why_and_leaves_no_model(qtbot, session, tmp_path, factory):
    session.model.factory = factory
    broken = tmp_path / "broken.pt"
    broken.write_bytes(b"x")
    with qtbot.waitSignal(session.notice, timeout=5000) as said:
        session.model.load(broken)
    assert said.args[1] == "broken.pt could not be loaded: not a model"
    assert session.model.state == "failed" and session.model.key is None


def test_the_image_on_screen_is_predicted_and_then_served_from_the_store(qtbot, session, weights, factory, made):
    load(qtbot, session, weights, factory)
    entry = session.current().entry                          # camA/0001
    qtbot.waitUntil(lambda: session.model.predictions(entry) is not None)
    assert session.model.predictions(entry) == [CAR, HUMAN]
    asked = made[-1].asked.count("0001.jpg")
    session.move(1)
    session.move(-1)
    qtbot.wait(100)
    assert made[-1].asked.count("0001.jpg") == asked == 1


def test_the_image_on_screen_goes_before_its_neighbours(qtbot, session, weights, factory, made):
    load(qtbot, session, weights, factory)
    qtbot.waitUntil(lambda: len(made[-1].asked) >= 3)
    assert made[-1].asked[0] == "0001.jpg"


def test_paging_fast_predicts_where_the_cursor_stops_first(qtbot, session, weights, factory, made):
    gate = threading.Event()
    load(qtbot, session, weights, lambda path: factory(path, gate=gate))
    for _ in range(6):
        session.move(1)                                      # the GUI never waits on the model
    stop = session.current().entry.path.name
    gate.set()
    qtbot.waitUntil(lambda: stop in made[-1].asked)
    assert made[-1].asked.index(stop) <= 1                   # at most the one already in hand first


def test_a_failed_prediction_is_said_once_and_not_retried(qtbot, session, weights, factory, made):
    load(qtbot, session, weights, lambda path: factory(path, fail={"0002.jpg"}))
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda *a: "0002.jpg" in a[1]):
        session.move(1)
    entry = session.current().entry
    assert "CUDA out of memory" in session.model.failure(entry)
    session.move(1)
    session.move(-1)
    qtbot.wait(100)
    assert made[-1].asked.count("0002.jpg") == 1


def test_shown_predictions_follow_the_threshold_and_the_class_map(qtbot, session, weights, factory):
    load(qtbot, session, weights, factory)
    entry = session.current().entry
    qtbot.waitUntil(lambda: session.model.shown(entry) is not None)
    assert [(s.pred, s.cls) for s in session.model.shown(entry)] == [(CAR, 1), (HUMAN, None)]
    session.model.set_conf(0.8)
    assert session.workspace.root_settings.get(PRED_CONF) == 0.8
    assert [s.pred for s in session.model.shown(entry)] == [CAR]
    with pytest.raises(ValueError):
        session.model.set_conf(0.05)                         # nothing below the floor is offered
    session.model.set_class_map(session.model.class_map.with_target(2, "person"))
    session.model.set_conf(0.25)
    assert [s.cls for s in session.model.shown(entry)] == [1, 0]


def test_closing_the_dataset_lets_the_model_go_and_reopening_loads_it_again(qtbot, session, weights,
                                                                             factory, made, ds):
    load(qtbot, session, weights, factory)
    first = made[-1]
    session.close()
    qtbot.waitUntil(lambda: first.closed)
    assert session.model.state == "none"
    with qtbot.waitSignal(session.model.changed, timeout=5000,
                          check_params_cb=lambda: session.model.state == "ready"):
        assert session.open(ds.yaml)
    assert made[-1] is not first and session.model.key == "fake:best.pt"


def test_shutting_down_waits_at_most_two_seconds_for_a_prediction_in_hand(qtbot, ds, weights, factory):
    gate = threading.Event()
    session = open_session(qtbot, ds.yaml)
    load(qtbot, session, weights, lambda path: factory(path, gate=gate))
    qtbot.wait(50)                                           # the image on screen is in hand
    started = time.monotonic()
    session.close()
    session.model.shutdown()
    assert time.monotonic() - started < 3
    gate.set()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_model.py`
Expected: `No module named 'deeplabeling.ui.model'`.

- [ ] **Step 3: Write the model session, and give the session one**

Create `src/deeplabeling/ui/model.py`:

```python
"""The model, for the session (docs/design/2026-10-05-model-assist.md#the-inference-thread).

One QThread owns the predictor from loading to closing: an ultralytics model is not safe to
share across threads, and its CUDA context stays on the thread that made it. The GUI thread
never calls it and never waits on it (CLAUDE.md landmine 3). It asks for the image on screen
and its neighbours; each new cursor position replaces the list, so a fast page through the
queue leaves no backlog. Answers go into the prediction store, which the GUI reads.
"""

from __future__ import annotations

import collections
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from ..core.assist import Shown, shown_predictions
from ..core.classmap import ClassMap, load_class_map, save_class_map
from ..core.dataset import ImageEntry
from ..core.inference import FLOOR, Failure, ModelError, Prediction, UltralyticsPredictor
from ..core.predstore import PredictionStore, Stamp, image_stamp
from ..core.settings import define, is_str_list, is_str_or_none

#: The weights last used, for each opening (yaml or folder): loaded again when it opens.
MODEL_PATH = define("model.path", "opening", None, is_str_or_none)
#: Weights files used lately, newest first.
RECENT_MODELS = define("models.recent", "global", [], is_str_list)
#: The confidence a prediction needs to be shown or accepted, for each root.
PRED_CONF = define("model.conf", "root", 0.25,
                   lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and FLOOR <= v <= 1)

RECENT_MAX = 8
SHUTDOWN_MS = 2000      #: the longest closing waits for a prediction in hand
NEIGHBOURS = (1, 2, -1)  #: queue offsets predicted after the image on screen, as images are kept

Wanted = tuple[str, Path, Stamp]   #: (dataset-relative path, file, stamp)

#: Threads let go of while a prediction was still in hand: kept until they finish, since Qt
#: aborts the process when a running QThread is destroyed.
_FINISHING: set = set()


class _Worker(QThread):
    """The thread that owns the predictor. Control jobs (load, unload, stop) go first, then
    the images wanted on screen, in order."""

    loaded = Signal(object, object, object)   # path, key, names
    loadFailed = Signal(object, str)          # path, why
    ready = Signal(object)                    # image path: its row is in the store
    failed = Signal(object, str)              # image path, why

    def __init__(self):
        super().__init__()                            # no parent: it may outlive its session
        self._cond = threading.Condition()
        self._control: collections.deque = collections.deque()
        self._screen: list[Wanted] = []
        self._store: PredictionStore | None = None
        self._predictor = None

    # -- asked from the GUI thread ----------------------------------------------------

    def load(self, factory: Callable, path: Path) -> None:
        self._put(("load", factory, path))

    def unload(self) -> None:
        self.want(None, [])
        self._put(("unload",))

    def stop(self) -> None:
        self.want(None, [])
        self._put(("stop",))

    def want(self, store: PredictionStore | None, items: list[Wanted]) -> None:
        """Replace the images wanted on screen: the first is the one shown."""
        with self._cond:
            self._store, self._screen = store, list(items)
            self._cond.notify()

    def _put(self, job) -> None:
        with self._cond:
            self._control.append(job)
            self._cond.notify()

    # -- on the thread ---------------------------------------------------------------------

    def run(self) -> None:
        while True:
            with self._cond:
                while not self._control and not (self._screen and self._predictor is not None):
                    self._cond.wait()
                if self._control:
                    job, item, store = self._control.popleft(), None, None
                else:
                    job, item, store = None, self._screen.pop(0), self._store
            if job is not None:
                if job[0] == "stop":
                    self._close()
                    return
                if job[0] == "unload":
                    self._close()
                else:
                    self._load(*job[1:])
            elif store is not None:
                self._predict(store, *item)

    def _close(self) -> None:
        if self._predictor is not None:
            self._predictor.close()
            self._predictor = None

    def _load(self, factory, path: Path) -> None:
        self._close()
        try:
            predictor = factory(path)
        except ModelError as e:
            self.loadFailed.emit(path, str(e))
            return
        except Exception as e:                        # whatever a factory raises: say it
            self.loadFailed.emit(path, f"{Path(path).name} could not be loaded: {e}")
            return
        self._predictor = predictor
        self.loaded.emit(path, predictor.key, predictor.names)

    def _predict(self, store: PredictionStore, rel: str, path: Path, stamp: Stamp) -> None:
        key = self._predictor.key
        if store.get(key, rel, stamp) is not None:
            return                                    # asked again while it was in hand
        [found] = self._predictor.predict([path])
        if isinstance(found, Failure):
            self.failed.emit(path, found.why)
            return
        store.put(key, rel, stamp, found)
        self.ready.emit(path)


class ModelSession(QObject):
    """The loaded model as the GUI sees it: its state, its class map and threshold for the
    open root, and the predictions for an image, read from the store."""

    changed = Signal()                  # the state, the model, the threshold or the map
    ready = Signal(object)              # image path: predictions for it are in the store
    failed = Signal(object, str)        # image path, why

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.factory: Callable = UltralyticsPredictor
        self.state = "none"             # none, loading, ready or failed
        self.path: Path | None = None
        self.key: str | None = None
        self.names: tuple[str, ...] = ()
        self.error = ""
        self.class_map: ClassMap | None = None
        self._failures: dict[Path, str] = {}
        self._worker: _Worker | None = None        # runs while a model is loaded or loading
        session.cursorChanged.connect(self.want_screen)
        session.opened.connect(self._opened)

    # -- the model ----------------------------------------------------------------------

    def load(self, path) -> None:
        """Load a weights file on the thread; `changed` says when it is ready or failed."""
        self.state, self.path, self.key, self.names, self.error = "loading", Path(path), None, (), ""
        self.class_map, self._failures = None, {}
        if self._worker is None:
            self._worker = self._start_worker()
        self._worker.want(None, [])
        self._worker.load(self.factory, Path(path))
        self.changed.emit()

    def unload(self) -> None:
        """Let the model go: its thread stops, waiting at most SHUTDOWN_MS."""
        self._stop_worker()
        self._forget()

    def _start_worker(self) -> _Worker:
        worker = _Worker()
        worker.loaded.connect(self._loaded)
        worker.loadFailed.connect(self._load_failed)
        worker.ready.connect(self._ready)
        worker.failed.connect(self._failed)
        worker.start()
        return worker

    def _stop_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is None:
            return
        for signal, slot in ((worker.loaded, self._loaded), (worker.loadFailed, self._load_failed),
                             (worker.ready, self._ready), (worker.failed, self._failed)):
            signal.disconnect(slot)                   # a late answer is for a dataset now gone
        worker.stop()
        if not worker.wait(SHUTDOWN_MS):
            _FINISHING.add(worker)
        for done in [w for w in _FINISHING if w.isFinished()]:
            _FINISHING.discard(done)

    def _forget(self) -> None:
        self.state, self.path, self.key, self.names, self.error = "none", None, None, (), ""
        self.class_map, self._failures = None, {}
        self.changed.emit()

    def _loaded(self, path, key, names) -> None:
        if path != self.path or self.state != "loading":
            return                                    # superseded by another load or unload
        self.state, self.key, self.names = "ready", key, tuple(names)
        ws = self.session.workspace
        if ws is not None:
            self.class_map = load_class_map(ws.root_settings, self.names, ws.dataset.names)
            ws.opening_settings.set(MODEL_PATH, str(path))
        settings = self.session.settings
        recent = [str(path)] + [p for p in settings.get(RECENT_MODELS) if p != str(path)]
        settings.set(RECENT_MODELS, recent[:RECENT_MAX])
        self.session.saver.schedule()
        self.changed.emit()
        self.want_screen()

    def _load_failed(self, path, why: str) -> None:
        if path != self.path:
            return
        self.state, self.error = "failed", why
        self.session.notice.emit("error", why, None)
        self.changed.emit()

    # -- for the open dataset ---------------------------------------------------------

    def _opened(self) -> None:
        stored = self.session.workspace.opening_settings.get(MODEL_PATH)
        if stored and Path(stored).is_file():
            self.load(stored)
        elif self.key is not None:
            self.class_map = load_class_map(self.session.workspace.root_settings, self.names,
                                            self.session.workspace.dataset.names)
            self.changed.emit()

    def release(self) -> None:
        """The dataset closes: nothing more is asked of its store, and the model goes, so
        that the next dataset loads its own."""
        if self._worker is not None or self.state != "none":
            self.unload()

    def shutdown(self) -> None:
        """The app quits: as release, the thread waited for at most SHUTDOWN_MS."""
        self.release()

    @property
    def conf(self) -> float:
        ws = self.session.workspace
        return ws.root_settings.get(PRED_CONF) if ws is not None else PRED_CONF.default

    def set_conf(self, value: float) -> None:
        """The threshold for this root; nothing below the floor is offered (ValueError)."""
        self.session.workspace.root_settings.set(PRED_CONF, float(value))
        self.session.saver.schedule()
        self.changed.emit()

    def set_class_map(self, cmap: ClassMap) -> None:
        self.class_map = cmap
        save_class_map(self.session.workspace.root_settings, cmap)
        self.session.saver.schedule()
        self.changed.emit()

    # -- predictions --------------------------------------------------------------------------

    def predictions(self, entry: ImageEntry) -> list[Prediction] | None:
        """What the model found on this image at the floor; None when it has not looked
        (or no model is loaded)."""
        ws = self.session.workspace
        if self.state != "ready" or ws is None:
            return None
        try:
            stamp = image_stamp(entry.path)
        except OSError:
            return None
        return ws.predictions.get(self.key, entry.rel, stamp)

    def shown(self, entry: ImageEntry) -> list[Shown] | None:
        """The predictions as shown: above the threshold, translated, missing or not."""
        preds = self.predictions(entry)
        if preds is None:
            return None
        ws = self.session.workspace
        return shown_predictions(preds, self.session.labels(entry), self.class_map, ws.dataset, self.conf)

    def failure(self, entry: ImageEntry) -> str | None:
        return self._failures.get(entry.path)

    def want_screen(self) -> None:
        """Ask for the image on screen, then its neighbours, of those not yet in the store."""
        session, ws = self.session, self.session.workspace
        queue = session.queue
        if (self.state != "ready" or self._worker is None or ws is None or queue is None
                or queue.position() is None):
            return
        i, items = queue.position(), queue.items
        wanted = []
        for j in (i, *(i + d for d in NEIGHBOURS)):
            if not 0 <= j < len(items):
                continue
            entry = items[j].entry
            if entry.path in self._failures:
                continue
            try:
                stamp = image_stamp(entry.path)
            except OSError:
                continue
            if ws.predictions.get(self.key, entry.rel, stamp) is None:
                wanted.append((entry.rel, entry.path, stamp))
        self._worker.want(ws.predictions, wanted)

    def _ready(self, path) -> None:
        self.ready.emit(path)

    def _failed(self, path, why: str) -> None:
        self._failures[path] = why
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self.session.notice.emit("error", f"{item.key}: the model could not predict ({why})", path)
        self.failed.emit(path, why)
```

In `src/deeplabeling/ui/session.py`, replace:

```python
from .classes import assign_classes
from .images import THUMB_BYTES, ImageCache, decode_thumb
from .settings_ui import Saver, global_settings, remember_source
from .workers import Jobs
```

with:

```python
from .classes import assign_classes
from .images import THUMB_BYTES, ImageCache, decode_thumb
from .model import ModelSession
from .settings_ui import Saver, global_settings, remember_source
from .workers import Jobs
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self._watch.timeout.connect(self.check_current)
        self._watch.start()

    # -- opening and closing -----------------------------------------------
```

with:

```python
        self._watch.timeout.connect(self.check_current)
        self._watch.start()
        self.model = ModelSession(self, self)

    # -- opening and closing -----------------------------------------------
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            return
        self.io.cancel_all()
        self.images.clear()
        self.thumbs.clear()
```

with:

```python
            return
        self.io.cancel_all()
        self.model.release()                        # before the store it writes to closes
        self.images.clear()
        self.thumbs.clear()
```

- [ ] **Step 4: Run the tests to see them pass, three times**

The thread's tests depend on timing; three green runs in a row is the bar.

Run: `for i in 1 2 3; do /home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_model.py tests/ui/test_session.py | tail -1; done`
Expected: three lines, each `43 passed`.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 607 passed.

```bash
git add src/deeplabeling/ui/model.py src/deeplabeling/ui/session.py tests/ui/test_model.py tests/fixtures.py tests/conftest.py
git commit -m "ui: one thread owns the model; the image on screen first, the store first" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The predictions layer

**Files:**
- Modify: `src/deeplabeling/ui/boxes.py`, `src/deeplabeling/ui/canvas.py`
- Test: `tests/ui/test_boxes.py`, `tests/ui/test_canvas.py`

**Interfaces:**
- Consumes: `Shown` (plan 2a); `class_color` and `UNKNOWN` (slice 1).
- Produces in `deeplabeling.ui.boxes`:
  - `PredictionView(index, rect, color, caption, faint)`, frozen. `index` is the prediction's place in the shown list, `rect` is in image pixels, and `faint` means not missing;
  - `prediction_views(shown, dataset, size, colors, model_names) -> list[PredictionView]`. Captions read `car 0.88`, or `human? 0.50` in grey when unmapped.
- Produces in `deeplabeling.ui.canvas`:
  - `FAINT_ALPHA = 90`;
  - `CaptionItem(text, color, above=False)`, where `above` puts the plate above its box;
  - `Canvas.predictionPicked(int)`, emitted by a double-click on a prediction, the smallest under the cursor;
  - `Canvas.set_predictions(views)` and `Canvas.prediction_caption_items()`;
  - `Canvas.set_layers(*, labels, captions, predictions=None)`, and `Canvas.show_predictions`.
- How predictions are drawn: dashed, 2 px, under the labels. A faint one is drawn at `FAINT_ALPHA` and without a caption. They are drawn with the labels layer off too. `set_image` clears them.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_boxes.py`:

```python
def test_prediction_views_are_in_pixels_with_their_class_colour_and_confidence(dataset):
    from deeplabeling.core.assist import Shown
    from deeplabeling.core.inference import Prediction
    from deeplabeling.ui.boxes import prediction_views

    shown = [Shown(Prediction(0, (0.5, 0.5, 0.2, 0.2), 0.876), 1, True),
             Shown(Prediction(2, (0.25, 0.25, 0.1, 0.1), 0.5), None, False)]
    car, unmapped = prediction_views(shown, dataset, SIZE, {"car": "#123456"}, ("car", "truck", "human"))
    assert car.rect == pytest.approx((40, 20, 60, 30)) and car.color == "#123456"
    assert (car.caption, car.faint, car.index) == ("car 0.88", False, 0)
    assert (unmapped.caption, unmapped.color, unmapped.faint) == ("human? 0.50", UNKNOWN, True)
```

In `tests/ui/test_canvas.py`, replace:

```python
from PySide6.QtWidgets import QApplication

from deeplabeling.ui.boxes import BoxView
from deeplabeling.ui.canvas import Canvas
from drive import click, drag, mouse, vp
```

with:

```python
from PySide6.QtWidgets import QApplication

from deeplabeling.ui.boxes import BoxView, PredictionView
from deeplabeling.ui.canvas import Canvas
from drive import click, drag, mouse, vp
```

In `tests/ui/test_canvas.py`, replace:

```python
    [(kind, delta)] = seen
    assert kind == "moved" and delta == pytest.approx((20, 0), abs=1)
```

with:

```python
    [(kind, delta)] = seen
    assert kind == "moved" and delta == pytest.approx((20, 0), abs=1)


# -- predictions (plan 2b) ----------------------------------------------------------------


GREEN_PRED = PredictionView(0, (50, 25, 150, 75), "#00ff00", "car 0.90", False)
FAINT_PRED = PredictionView(1, (20, 10, 40, 30), "#00ff00", "car 0.40", True)


def is_green(c):
    return c.green() > 200 and c.red() < 80 and c.blue() < 80


def test_a_prediction_is_drawn_dashed_in_its_colour_and_a_faint_one_fainter(canvas):
    canvas.set_image(grey_image())
    canvas.set_predictions([GREEN_PRED, FAINT_PRED])
    image = shot(canvas)
    x = canvas.mapFromScene(QPointF(150, 50)).x()
    top, bottom = canvas.mapFromScene(QPointF(150, 30)).y(), canvas.mapFromScene(QPointF(150, 70)).y()
    edge = [any(is_green(QColor(image.pixel(x + dx, y))) for dx in range(-2, 3)) for y in range(top, bottom)]
    assert any(edge) and not all(edge)                      # dashes, with gaps
    faint = [QColor(c) for c in near(canvas, 40, 20, image)]
    assert not any(map(is_green, faint)) and any(c.green() > c.red() + 20 for c in faint)
    # a label already names what a faint one shows: its caption would only cover the label's
    assert [c.text for c in canvas.prediction_caption_items()] == ["car 0.90"]


def test_a_predictions_caption_sits_above_its_box(canvas):
    canvas.set_image(grey_image())
    canvas.set_predictions([GREEN_PRED])
    [caption] = canvas.prediction_caption_items()
    top = canvas.mapFromScene(QPointF(50, 25))
    plate = caption.sceneBoundingRect()
    assert caption.text == "car 0.90"
    assert canvas.mapFromScene(plate.bottomLeft()).y() <= top.y() + 1


def test_double_clicking_a_prediction_picks_it_and_a_click_still_selects_labels(qtbot, canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([SMALL])
    canvas.set_predictions([GREEN_PRED])
    seen = record(canvas)
    accepted = []
    canvas.predictionPicked.connect(accepted.append)
    click(canvas, (80, 50))
    qtbot.mouseDClick(canvas.viewport(), Qt.LeftButton, pos=vp(canvas, 120, 60))
    assert seen[0] == ("picked", [1]) and accepted == [0]


def test_the_predictions_layer_can_be_hidden(canvas):
    canvas.set_image(grey_image())
    canvas.set_predictions([GREEN_PRED])
    canvas.set_layers(labels=True, captions=True, predictions=False)
    assert not any(map(is_green, near(canvas, 100, 25))) and canvas.prediction_caption_items() == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_boxes.py tests/ui/test_canvas.py`
Expected: `cannot import name 'PredictionView'`.

- [ ] **Step 3: Draw the predictions**

In `src/deeplabeling/ui/boxes.py`, replace:

```python
from dataclasses import dataclass

from ..core.dataset import Dataset
from ..core.geometry import norm_to_px
```

with:

```python
from dataclasses import dataclass

from ..core.assist import Shown
from ..core.dataset import Dataset
from ..core.geometry import norm_to_px
```

In `src/deeplabeling/ui/boxes.py`, replace:

```python
                             known, index in highlight))
    return views
```

with:

```python
                             known, index in highlight))
    return views


@dataclass(frozen=True)
class PredictionView:
    index: int                                  #: its place in the shown list
    rect: tuple[float, float, float, float]     #: (x1, y1, x2, y2) in image pixels
    color: str                                  #: its class's colour, grey when unmapped
    caption: str                                #: "car 0.82", or "truck? 0.40" when unmapped
    faint: bool                                 #: not missing: an accept would not add it


def prediction_views(shown: list[Shown], dataset: Dataset, size: tuple[int, int],
                     colors: dict[str, str], model_names: tuple[str, ...]) -> list[PredictionView]:
    """What the predictions layer draws (docs/design/2026-10-05-model-assist.md#the-predictions-layer)."""
    w, h = size
    views = []
    for index, s in enumerate(shown):
        if s.cls is None:
            name = model_names[s.pred.cls] if 0 <= s.pred.cls < len(model_names) else str(s.pred.cls)
            color, caption = UNKNOWN, f"{name}? {s.pred.conf:.2f}"
        else:
            name = dataset.names[s.cls] if s.cls < len(dataset.names) else str(s.cls)
            color, caption = class_color(s.cls, name, colors), f"{name} {s.pred.conf:.2f}"
        views.append(PredictionView(index, norm_to_px(s.pred.box, w, h), color, caption, not s.missing))
    return views
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
)

from .boxes import BoxView
from .classes import text_color

```

with:

```python
)

from .boxes import BoxView, PredictionView
from .classes import text_color

```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
GRAB_PX = 6             #: how near a handle's centre a press takes the handle
SELECTED_ALPHA = 70     #: a selected box is filled with its colour at this opacity
CROSSHAIR = "#ffffff"
#: the eight handles of a box, as fractions of its width and height
```

with:

```python
GRAB_PX = 6             #: how near a handle's centre a press takes the handle
SELECTED_ALPHA = 70     #: a selected box is filled with its colour at this opacity
FAINT_ALPHA = 90        #: a prediction an accept would not add is drawn at this opacity
CROSSHAIR = "#ffffff"
#: the eight handles of a box, as fractions of its width and height
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
    zoom, so it stays readable; the plate keeps it legible on any image."""

    def __init__(self, text: str, color: str):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
```

with:

```python
    zoom, so it stays readable; the plate keeps it legible on any image."""

    def __init__(self, text: str, color: str, above: bool = False):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
        self._font.setPointSize(9)
        metrics = QFontMetricsF(self._font)
        self._rect = QRectF(0, 0, metrics.horizontalAdvance(text) + 6, metrics.height() + 2)

    def boundingRect(self) -> QRectF:
```

with:

```python
        self._font.setPointSize(9)
        metrics = QFontMetricsF(self._font)
        height = metrics.height() + 2
        # A label's plate hangs inside its box's top edge, a prediction's sits above its
        # box: the two never cover each other (docs/knowledge/legacy-defects.md).
        self._rect = QRectF(0, -height if above else 0, metrics.horizontalAdvance(text) + 6, height)

    def boundingRect(self) -> QRectF:
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
    moved = Signal(float, float)        #: the selected boxes' shift, in image pixels
    resized = Signal(int, object)       #: a line index and its new (x1, y1, x2, y2)

    def __init__(self, parent=None):
```

with:

```python
    moved = Signal(float, float)        #: the selected boxes' shift, in image pixels
    resized = Signal(int, object)       #: a line index and its new (x1, y1, x2, y2)
    predictionPicked = Signal(int)      #: a prediction was double-clicked: its index

    def __init__(self, parent=None):
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
        self._items: list[QGraphicsItem] = []
        self._views: list[BoxView] = []
        self._size: tuple[int, int] | None = None
        self.show_labels = True
```

with:

```python
        self._items: list[QGraphicsItem] = []
        self._views: list[BoxView] = []
        self._predictions: list[PredictionView] = []
        self._pred_items: list[QGraphicsItem] = []
        self.show_predictions = True
        self._size: tuple[int, int] | None = None
        self.show_labels = True
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
    def set_image(self, image: QImage | None, message: str = "") -> None:
        """Show an image, fitted to the view; or no image and a message saying why."""
        self._views, self._selected = [], frozenset()
        self._clear()
        if image is None:
```

with:

```python
    def set_image(self, image: QImage | None, message: str = "") -> None:
        """Show an image, fitted to the view; or no image and a message saying why."""
        self._views, self._selected, self._predictions = [], frozenset(), []
        self._clear()
        if image is None:
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
        self._redraw()

    def set_layers(self, *, labels: bool, captions: bool) -> None:
        self.show_labels, self.show_captions = labels, captions
        self._redraw()

    def set_draw_color(self, color: str) -> None:
```

with:

```python
        self._redraw()

    def set_layers(self, *, labels: bool, captions: bool, predictions: bool | None = None) -> None:
        self.show_labels, self.show_captions = labels, captions
        if predictions is not None:
            self.show_predictions = predictions
        self._redraw()

    def set_predictions(self, views: list[PredictionView]) -> None:
        self._predictions = list(views)
        self._redraw()

    def prediction_caption_items(self) -> list[CaptionItem]:
        return [it for it in self._pred_items if isinstance(it, CaptionItem)]

    def set_draw_color(self, color: str) -> None:
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
    def _clear(self) -> None:
        self._drag = None                           # whatever it previewed is gone
        for item in self._items + ([self._preview] if self._preview else []):
            self.scene().removeItem(item)
        self._items, self._box_items, self._handles, self._preview = [], {}, [], None

    def _redraw(self) -> None:
        self._clear()
        if not self.show_labels or self._size is None:
            return
        for view in self._views:
            self._draw(view)

    def _draw(self, view: BoxView) -> None:
```

with:

```python
    def _clear(self) -> None:
        self._drag = None                           # whatever it previewed is gone
        for item in self._items + self._pred_items + ([self._preview] if self._preview else []):
            self.scene().removeItem(item)
        self._items, self._box_items, self._handles, self._preview = [], {}, [], None
        self._pred_items = []

    def _redraw(self) -> None:
        self._clear()
        if self._size is None:
            return
        if self.show_predictions:                   # shown with the labels hidden, too
            for view in self._predictions:
                self._draw_prediction(view)
        if not self.show_labels:
            return
        for view in self._views:
            self._draw(view)

    def _draw_prediction(self, view: PredictionView) -> None:
        color = QColor(view.color)
        if view.faint:
            color.setAlpha(FAINT_ALPHA)
        pen = QPen(color)
        pen.setCosmetic(True)
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        x1, y1, x2, y2 = view.rect
        shape = self.scene().addRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)), pen)
        shape.setZValue(0.5)                        # under the labels
        self._pred_items.append(shape)
        if self.show_captions and not view.faint:   # a faint one's label names it already
            caption = CaptionItem(view.caption, view.color, above=True)
            caption.setPos(x1, y1)
            caption.setZValue(0.6)
            self.scene().addItem(caption)
            self._pred_items.append(caption)

    def _draw(self, view: BoxView) -> None:
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
            self.fit()

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
```

with:

```python
            self.fit()

    def mouseDoubleClickEvent(self, event) -> None:
        """A double-click on a prediction accepts it: the smallest under the cursor."""
        if (event.button() == Qt.LeftButton and self._size is not None and self.show_predictions
                and self._predictions):
            point = self.mapToScene(event.position().toPoint())
            under = [v for v in self._predictions
                     if v.rect[0] <= point.x() <= v.rect[2] and v.rect[1] <= point.y() <= v.rect[3]]
            if under:
                smallest = min(under, key=lambda v: (v.rect[2] - v.rect[0]) * (v.rect[3] - v.rect[1]))
                self.predictionPicked.emit(smallest.index)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_boxes.py tests/ui/test_canvas.py`
Expected: 51 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 612 passed.

```bash
git add src/deeplabeling/ui/boxes.py src/deeplabeling/ui/canvas.py tests/ui/test_boxes.py tests/ui/test_canvas.py
git commit -m "ui: predictions drawn dashed, captioned above, faint when an accept would not add them" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Accepting on screen

**Files:**
- Create: `tests/ui/test_accepting.py`
- Modify: `src/deeplabeling/ui/canvas.py`, `editing.py`, `keymap.py`, `settings_ui.py`, `main_window.py`; `tests/ui/test_main_window.py`, `tests/ui/test_editing.py`

**Interfaces:**
- Consumes:
  - from Task 2: `Session.model` (`state`, `names`, `shown`, `changed`, `ready`);
  - from Task 3: `prediction_views`, `Canvas.set_predictions`, `Canvas.predictionPicked`, and `set_layers(predictions=)`;
  - from plan 2a: `accept_image` and `accept_one`.
- Produces:
  - `Canvas.set_boxes(views, selected=(), predictions=None)`, which draws the labels and, when given, the predictions in one redraw. `None` keeps the current predictions.
  - In `Editing`:
    - `show_predictions(image, shown)`, the snapshot drawn;
    - `accept_missing()`, which the `A` key calls;
    - `accept_prediction(index)`, which a double-click calls.

    With the labels hidden, neither accepts anything. Their status messages are:
    - `accepted N predictions`, with `; M of a class the map leaves out was skipped` when it skipped some;
    - `no missing predictions to accept`;
    - `no model is loaded`;
    - `the model is still loading`;
    - `the model has not looked at this image yet`;
    - `“human” is not mapped to a class of this dataset: map it in the class map`.
  - Actions:
    - `toggle_predictions` (`P`), checkable;
    - `accept_missing` (`A`).
  - `SHOW_PREDICTIONS` (`view.predictions`, global, default `True`), bound to `P` and listed under Layers after Captions.

- [ ] **Step 1: Write the failing tests, and the Layers chip's new text**

Create `tests/ui/test_accepting.py`:

```python
"""Predictions in the window, and accepting them on screen
(docs/design/2026-10-05-model-assist.md#accepting)."""

import threading

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor

from deeplabeling.core.inference import Prediction
from deeplabeling.ui.settings_ui import SHOW_PREDICTIONS
from drive import start, vp
from fixtures import CAMA_0001, FakePredictor, read_exact

# camA/0001 holds a person (0.5, 0.5, 0.2, 0.3) and a car. The model's classes are car,
# truck, human: car maps to car; truck and human map to nothing here.
MISSING_CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9)
ON_THE_PERSON = Prediction(0, (0.5, 0.5, 0.2, 0.3), 0.85)      # a label covers it: faint
HUMAN = Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)                # unmapped
CAR_LINE = "1 0.800000 0.800000 0.100000 0.100000\n"


@pytest.fixture
def window(qtbot, ds, tmp_path):
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    w.session.model.factory = lambda path: FakePredictor(
        path, found={"0001.jpg": [MISSING_CAR, ON_THE_PERSON, HUMAN]})
    w.session.model.load(weights)
    qtbot.waitUntil(lambda: len(w.canvas._predictions) == 3, timeout=5000)
    yield w
    w.close()


def colours_at(window, x, y):
    image = window.canvas.viewport().grab().toImage()
    at = window.canvas.mapFromScene(QPointF(x, y))
    return [QColor(image.pixel(at.x() + dx, at.y() + dy)) for dx in range(-2, 3) for dy in range(-2, 3)]


def is_car_green(c):                                            # #3cb44b
    return c.green() > 150 and c.red() < 100 and c.blue() < 120


def test_predictions_appear_on_the_image_on_screen(window):
    # the missing car's left edge, x = 0.75 of 64 px, half way down it
    assert any(map(is_car_green, colours_at(window, 48, 38.4)))
    captions = [c.text for c in window.canvas.prediction_caption_items()]
    assert captions == ["car 0.90", "human? 0.70"]              # the faint one has none


def test_a_accepts_the_missing_mapped_predictions_and_says_what_it_skipped(qtbot, window, ds):
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_A)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + CAR_LINE
    assert said.args == ["accepted 1 prediction; 1 of a class the map leaves out was skipped"]
    assert window.session.workspace.review.is_marked("camA/images/0001.jpg")
    qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_double_clicking_a_prediction_accepts_that_one_even_when_covered(qtbot, window, ds):
    qtbot.mouseDClick(window.canvas.viewport(), Qt.LeftButton, pos=vp(window.canvas, 32, 24))
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.500000 0.500000 0.200000 0.300000\n"


def test_double_clicking_an_unmapped_prediction_says_so_and_adds_nothing(qtbot, window, ds):
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.mouseDClick(window.canvas.viewport(), Qt.LeftButton, pos=vp(window.canvas, 6.4, 43.2))
    assert said.args == ["“human” is not mapped to a class of this dataset: map it in the class map"]
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_p_hides_the_predictions_and_the_choice_persists(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_P)
    assert not any(map(is_car_green, colours_at(window, 48, 38.4)))
    assert window.session.settings.get(SHOW_PREDICTIONS) is False
    assert window.state_bar.layers.full_text == "Layers: labels, captions"


def test_with_the_labels_hidden_predictions_show_but_none_is_accepted(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_L)
    assert any(map(is_car_green, colours_at(window, 48, 38.4)))
    qtbot.keyClick(window, Qt.Key_A)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_predictions_arriving_later_are_drawn_when_they_come(qtbot, window):
    window.session.move(1)                                      # camA/0002: nothing found
    qtbot.waitUntil(lambda: window.session.model.shown(window.session.current().entry) == [])
    window.session.move(-1)
    qtbot.waitUntil(lambda: len(window.canvas._predictions) == 3)


def test_an_accept_redraws_once_and_what_it_added_turns_faint(qtbot, window, monkeypatch):
    redraws, redraw = [], window.canvas._redraw
    monkeypatch.setattr(window.canvas, "_redraw", lambda: (redraws.append(1), redraw()))
    qtbot.keyClick(window, Qt.Key_A)
    assert len(redraws) == 1
    assert [c.text for c in window.canvas.prediction_caption_items()] == ["human? 0.70"]
    assert [p.faint for p in window.canvas._predictions] == [True, True, False]


def test_without_a_model_a_says_so(qtbot, window):
    window.session.model.unload()
    assert window.canvas._predictions == []
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_A)
    assert said.args == ["no model is loaded"]


def test_before_the_model_has_looked_a_says_so(qtbot, window, tmp_path):
    gate = threading.Event()
    other = tmp_path / "other.pt"
    other.write_bytes(b"other weights")
    window.session.model.factory = lambda path: FakePredictor(path, gate=gate)
    window.session.model.load(other)
    qtbot.waitUntil(lambda: window.session.model.state == "ready")
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_A)
    gate.set()
    assert said.args == ["the model has not looked at this image yet"]
```

In `tests/ui/test_main_window.py`, replace:

```python
    assert not window.canvas.show_labels and window.canvas.caption_items() == []
    assert window.session.settings.get(SHOW_LABELS) is False
    assert window.state_bar.layers.full_text == "Layers: captions"
    qtbot.keyClick(window, Qt.Key_T)
    assert window.state_bar.layers.full_text == "Layers: none"
    window.close()
    again = start(qtbot, [str(ds.yaml)])
```

with:

```python
    assert not window.canvas.show_labels and window.canvas.caption_items() == []
    assert window.session.settings.get(SHOW_LABELS) is False
    assert window.state_bar.layers.full_text == "Layers: captions, predictions"
    qtbot.keyClick(window, Qt.Key_T)
    assert window.state_bar.layers.full_text == "Layers: predictions"
    window.close()
    again = start(qtbot, [str(ds.yaml)])
```

In `tests/ui/test_main_window.py`, replace:

```python
    action.trigger()
    qtbot.waitUntil(window.queue_dock.isVisible)
    assert window.state_bar.layers.full_text == "Layers: labels, captions"
```

with:

```python
    action.trigger()
    qtbot.waitUntil(window.queue_dock.isVisible)
    assert window.state_bar.layers.full_text == "Layers: labels, captions, predictions"
```

In `tests/ui/test_editing.py`, replace:

```python
    window.actions["toggle_crosshair"].trigger()
    assert window.canvas.show_crosshair and window.session.settings.get(SHOW_CROSSHAIR) is True
    assert window.state_bar.layers.full_text == "Layers: labels, captions, crosshair"
    window.close()
    again = start(qtbot, [str(ds.yaml)])
```

with:

```python
    window.actions["toggle_crosshair"].trigger()
    assert window.canvas.show_crosshair and window.session.settings.get(SHOW_CROSSHAIR) is True
    assert window.state_bar.layers.full_text == "Layers: labels, captions, predictions, crosshair"
    window.close()
    again = start(qtbot, [str(ds.yaml)])
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_accepting.py`
Expected: `cannot import name 'SHOW_PREDICTIONS'`.

- [ ] **Step 3: Accept from what the canvas drew, and wire the window**

In `src/deeplabeling/ui/canvas.py`, replace:

```python
        self.fit()

    def set_boxes(self, views: list[BoxView], selected=()) -> None:
        self._views, self._selected = list(views), frozenset(selected)
        self._redraw()

```

with:

```python
        self.fit()

    def set_boxes(self, views: list[BoxView], selected=(), predictions: list[PredictionView] | None = None) -> None:
        """The labels, and the predictions when given (None keeps them): drawn once."""
        self._views, self._selected = list(views), frozenset(selected)
        if predictions is not None:
            self._predictions = list(predictions)
        self._redraw()

```

In `src/deeplabeling/ui/settings_ui.py`, replace:

```python
SHOW_LABELS = define("view.labels", "global", True, lambda v: isinstance(v, bool))
SHOW_CAPTIONS = define("view.captions", "global", True, lambda v: isinstance(v, bool))
SHOW_CROSSHAIR = define("view.crosshair", "global", False, lambda v: isinstance(v, bool))
SHOW_GRID = define("view.queue_grid", "global", False, lambda v: isinstance(v, bool))
```

with:

```python
SHOW_LABELS = define("view.labels", "global", True, lambda v: isinstance(v, bool))
SHOW_CAPTIONS = define("view.captions", "global", True, lambda v: isinstance(v, bool))
SHOW_PREDICTIONS = define("view.predictions", "global", True, lambda v: isinstance(v, bool))
SHOW_CROSSHAIR = define("view.crosshair", "global", False, lambda v: isinstance(v, bool))
SHOW_GRID = define("view.queue_grid", "global", False, lambda v: isinstance(v, bool))
```

In `src/deeplabeling/ui/keymap.py`, replace:

```python
    ActionSpec("go_to", "Go to an item by number or name", ("Ctrl+G",)),
    ActionSpec("help", "Shortcut help", ("?",)),
)

```

with:

```python
    ActionSpec("go_to", "Go to an item by number or name", ("Ctrl+G",)),
    ActionSpec("help", "Shortcut help", ("?",)),
    ActionSpec("toggle_predictions", "Predictions", ("P",), checkable=True),
    ActionSpec("accept_missing", "Accept the missing predictions on this image", ("A",)),
)

```

In `src/deeplabeling/ui/editing.py`, replace:

```python
from PySide6.QtGui import QGuiApplication

from ..core.edits import Intent
from ..core.geometry import px_to_norm
```

with:

```python
from PySide6.QtGui import QGuiApplication

from ..core.assist import Shown, accept_image, accept_one
from ..core.edits import Intent
from ..core.geometry import px_to_norm
```

In `src/deeplabeling/ui/editing.py`, replace:

```python
        self.selection = Selection(self)
        self._shown: ImageLabels | None = None      # what the canvas draws; its indices mean these
        self._applying: tuple | None = None         # (image, what to select) while an edit applies
        self._copied: tuple[str, tuple[str, ...]] | None = None    # (text, the class names it used)
```

with:

```python
        self.selection = Selection(self)
        self._shown: ImageLabels | None = None      # what the canvas draws; its indices mean these
        self._predicted: tuple[Path, list[Shown] | None] | None = None    # the predictions it draws
        self._applying: tuple | None = None         # (image, what to select) while an edit applies
        self._copied: tuple[str, tuple[str, ...]] | None = None    # (text, the class names it used)
```

In `src/deeplabeling/ui/editing.py`, replace:

```python
        turned into a box identity here, and the core locates that box in the file."""
        self._shown = labels

    def _current(self) -> tuple[Path, ImageLabels] | None:
```

with:

```python
        turned into a box identity here, and the core locates that box in the file."""
        self._shown = labels

    def show_predictions(self, image: Path, shown: list[Shown] | None) -> None:
        """The predictions the canvas now draws for `image`, None when the model has not
        looked at it: a double-clicked index means one of these, and `A` adds what of
        these is drawn solid."""
        self._predicted = (image, shown)

    def _current(self) -> tuple[Path, ImageLabels] | None:
```

In `src/deeplabeling/ui/editing.py`, replace:

```python
                        select=self.selection.indices(labels))      # the one box with handles

    # -- the editing keys -----------------------------------------------------------------

```

with:

```python
                        select=self.selection.indices(labels))      # the one box with handles

    # -- accepting predictions --------------------------------------------------------------

    def _drawn_predictions(self) -> tuple[Path, list[Shown]] | None:
        """The predictions drawn for the image being edited, or None, said why."""
        current, model = self._current(), self.session.model
        if not current:
            return None
        if model.state != "ready":
            self.session.status.emit("the model is still loading" if model.state == "loading"
                                     else "no model is loaded")
            return None
        if self._predicted is None or self._predicted[0] != current[0] or self._predicted[1] is None:
            self.session.status.emit("the model has not looked at this image yet")
            return None
        return self._predicted

    def accept_missing(self) -> None:
        """A: every missing prediction drawn on this image, as one edit."""
        drawn = self._drawn_predictions()
        if drawn is None:
            return
        intent, unmapped = accept_image(*drawn)
        n = len(intent.ops) if intent is not None else 0
        if intent is not None and not self._apply(intent, select=_last(n)):
            return
        said = (f"accepted {n} prediction" if n == 1 else f"accepted {n} predictions") if n else \
            "no missing predictions to accept"
        if unmapped:
            said += (f"; 1 of a class the map leaves out was skipped" if unmapped == 1 else
                     f"; {unmapped} of classes the map leaves out were skipped")
        self.session.status.emit(said)

    def accept_prediction(self, index: int) -> None:
        """A double-clicked prediction, covered by a label or not."""
        drawn = self._drawn_predictions()
        if drawn is None or not 0 <= index < len(drawn[1]):
            return
        image, shown = drawn
        chosen = shown[index]
        intent = accept_one(image, chosen)
        if intent is None:
            names = self.session.model.names
            name = names[chosen.pred.cls] if 0 <= chosen.pred.cls < len(names) else str(chosen.pred.cls)
            self.session.status.emit(f"“{name}” is not mapped to a class of this dataset: "
                                     "map it in the class map")
            return
        self._apply(intent, select=_last(1))

    # -- the editing keys -----------------------------------------------------------------

```

In `src/deeplabeling/ui/main_window.py`, replace:

```python

from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .canvas import Canvas
from .classes import DEFAULT_HOTKEYS
```

with:

```python

from ..core.workspace import CLASS_COLORS
from .boxes import box_views, prediction_views
from .canvas import Canvas
from .classes import DEFAULT_HOTKEYS
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
from .session import Session
from .settings_ui import (QUEUE_GRID_WIDTH, QUEUE_LIST_WIDTH, RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_GRID,
                          SHOW_LABELS, WINDOW_GEOMETRY, WINDOW_STATE, bind_toggle)
from .state_bar import StateBar
```

with:

```python
from .session import Session
from .settings_ui import (QUEUE_GRID_WIDTH, QUEUE_LIST_WIDTH, RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_GRID,
                          SHOW_PREDICTIONS,
                          SHOW_LABELS, WINDOW_GEOMETRY, WINDOW_STATE, bind_toggle)
from .state_bar import StateBar
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
            "copy": self.editing.copy,
            "paste": self.editing.paste,
        })
        layers = self.state_bar.layers.menu()
        for key, setting in (("toggle_labels", SHOW_LABELS), ("toggle_captions", SHOW_CAPTIONS),
                             ("toggle_crosshair", SHOW_CROSSHAIR)):
            bind_toggle(self.actions[key], session.settings, setting, self._layers_changed)
            layers.addAction(self.actions[key])
```

with:

```python
            "copy": self.editing.copy,
            "paste": self.editing.paste,
            "accept_missing": self.editing.accept_missing,
        })
        layers = self.state_bar.layers.menu()
        for key, setting in (("toggle_labels", SHOW_LABELS), ("toggle_captions", SHOW_CAPTIONS),
                             ("toggle_predictions", SHOW_PREDICTIONS), ("toggle_crosshair", SHOW_CROSSHAIR)):
            bind_toggle(self.actions[key], session.settings, setting, self._layers_changed)
            layers.addAction(self.actions[key])
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        session.standing.connect(lambda key, text: self.notices.add("warning", text, key=key))
        session.status.connect(lambda text: self.statusBar().showMessage(text, 4000))
        self._restore_layout()
        self._show_grid(self.actions["toggle_grid"].isChecked())
```

with:

```python
        session.standing.connect(lambda key, text: self.notices.add("warning", text, key=key))
        session.status.connect(lambda text: self.statusBar().showMessage(text, 4000))
        session.model.changed.connect(self._predictions_changed)
        session.model.ready.connect(self._image_predicted)
        self.canvas.predictionPicked.connect(self.editing.accept_prediction)
        self._restore_layout()
        self._show_grid(self.actions["toggle_grid"].isChecked())
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
                                        ws.root_settings.get(CLASS_COLORS), highlight),
                              selected=self.editing.selection.indices(labels))

    def _image_event(self, path) -> None:
```

with:

```python
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
                                        ws.root_settings.get(CLASS_COLORS), highlight),
                              selected=self.editing.selection.indices(labels),
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
        """The model, its threshold or its class map changed: redraw the predictions alone."""
        item = self.session.current()
        if item is not None and self.canvas.image_size is not None and self._shown == item.entry.path:
            self.canvas.set_predictions(self._prediction_views(item))
        self._update_status()

    def _image_predicted(self, path) -> None:
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self._predictions_changed()

    def _image_event(self, path) -> None:
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        if not labels:
            self.editing.selection.clear()          # hidden boxes are not acted on
        self.canvas.set_layers(labels=labels, captions=self.actions["toggle_captions"].isChecked())
        self.canvas.set_crosshair(self.actions["toggle_crosshair"].isChecked())
        self.session.saver.schedule()
```

with:

```python
        if not labels:
            self.editing.selection.clear()          # hidden boxes are not acted on
        self.canvas.set_layers(labels=labels, captions=self.actions["toggle_captions"].isChecked(),
                               predictions=self.actions["toggle_predictions"].isChecked())
        self.canvas.set_crosshair(self.actions["toggle_crosshair"].isChecked())
        self.session.saver.schedule()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_accepting.py tests/ui/test_main_window.py tests/ui/test_editing.py tests/ui/test_keymap.py`
Expected: 64 passed.

- [ ] **Step 5: Look at it**

Save `window.canvas.viewport().grab()` from the `window` fixture of `tests/ui/test_accepting.py`, and open the PNG. Expected:
- the missing car is a dashed green box, with `car 0.90` on a plate above it;
- the unmapped one is a dashed grey `human? 0.70`;
- the person label covers the faint prediction under it, and no second caption collides with `person`.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 622 passed.

```bash
git add src/deeplabeling/ui/canvas.py src/deeplabeling/ui/editing.py src/deeplabeling/ui/keymap.py src/deeplabeling/ui/settings_ui.py src/deeplabeling/ui/main_window.py tests/ui/test_accepting.py tests/ui/test_main_window.py tests/ui/test_editing.py
git commit -m "ui: predictions on screen; A and a double-click accept them" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The model chip and the class-map editor

**Files:**
- Create: `src/deeplabeling/ui/class_map_dialog.py`, `tests/ui/test_class_map_dialog.py`, `tests/ui/test_model_chip.py`
- Modify: `src/deeplabeling/ui/prompter.py`, `state_bar.py`, `main_window.py`; `tests/fixtures.py`, `tests/ui/test_prompter.py`, `tests/ui/test_state_bar.py`

**Interfaces:**
- Consumes:
  - from Task 2: `ModelSession` (`load`, `conf`, `set_conf`, `class_map`, `set_class_map`, `changed`), and `RECENT_MODELS`;
  - from plan 2a: `ClassMap.seeded` and `ClassMap.with_target`.
- Produces in `deeplabeling.ui.class_map_dialog`:
  - `NOT_MAPPED = "not mapped"`;
  - `ClassMapDialog(cmap, dataset_names, parent=None)`, with these members:
    - `rows() -> [(model name, shown target)]` and `row_widgets()`;
    - `choose(model_name, target)`;
    - `seed_button`;
    - `class_map() -> ClassMap`, in which only the rows that were changed become choices.

    It scrolls inside a dialog at most 640 px tall.
- Produces in `QtPrompter`, and in `FakePrompter`, which takes `weights=`, `threshold=` and `class_map=` (a dict of model name to target):
  - `choose_weights() -> str | None`;
  - `ask_threshold(current) -> float | None`;
  - `edit_class_map(cmap, dataset_names) -> ClassMap | None`.
- Produces in `deeplabeling.ui.state_bar`:
  - `model_text(model)`, which gives one of:
    - `Model: none · load one`;
    - `Model: best.pt · loading…`;
    - `Model: broken.pt · not loaded`;
    - `Model: best.pt · 3 classes · conf 0.25`;
  - `StateBar.model`, a chip with a menu, between Queue and Layers.
- Produces in `MainWindow`:
  - the model menu:
    - Load a model…;
    - the recent models, as `best.pt — <folder>`;
    - Threshold…, which needs a dataset;
    - Class map…, which needs a dataset and a loaded model;
  - `load_model()`, `ask_threshold()` and `edit_class_map()`.

- [ ] **Step 1: Write the failing tests**

In `tests/fixtures.py`, replace:

```python
    """Answers the UI's dialogs from preset values and records what was asked."""

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

with:

```python
    """Answers the UI's dialogs from preset values and records what was asked."""

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
        self.weights, self.threshold = weights, threshold
        self.class_map = class_map          #: {model class name: dataset class name or None}
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

In `tests/fixtures.py`, replace:

```python
        return next((info for info in infos if info.name == self.class_name), None)



```

with:

```python
        return next((info for info in infos if info.name == self.class_name), None)

    def choose_weights(self):
        self.asked.append(("weights",))
        return None if self.weights is None else str(self.weights)

    def ask_threshold(self, current):
        self.asked.append(("threshold", current))
        return self.threshold

    def edit_class_map(self, cmap, dataset_names):
        self.asked.append(("class map", cmap.model_names, tuple(dataset_names)))
        if self.class_map is None:
            return None
        for name, target in self.class_map.items():
            cmap = cmap.with_target(cmap.model_names.index(name), target)
        return cmap


```

Create `tests/ui/test_class_map_dialog.py`:

```python
"""The class-map editor (docs/design/2026-10-05-model-assist.md#the-class-map)."""

from PySide6.QtCore import QPoint, QRect

from deeplabeling.core.classmap import ClassMap
from deeplabeling.ui.class_map_dialog import NOT_MAPPED, ClassMapDialog

NAMES = ("person", "car", "bus_m", "bus_l")
MODEL = ("car", "truck", "human")


def dialog(qtbot, cmap=None):
    d = ClassMapDialog(cmap or ClassMap.seeded(MODEL, NAMES), NAMES)
    qtbot.addWidget(d)
    return d


def test_one_row_per_model_class_showing_what_it_maps_to(qtbot):
    assert dialog(qtbot).rows() == [("car", "car"), ("truck", NOT_MAPPED), ("human", NOT_MAPPED)]


def test_a_choice_becomes_the_map_and_is_marked_as_chosen(qtbot):
    d = dialog(qtbot)
    d.choose("human", "person")
    d.choose("car", NOT_MAPPED)
    cmap = d.class_map()
    assert cmap.targets == (None, None, "person") and cmap.chosen == (True, False, True)


def test_a_row_left_alone_stays_as_it_was(qtbot):
    d = dialog(qtbot)
    d.choose("human", "person")
    d.choose("human", NOT_MAPPED)                   # back to where it was
    assert d.class_map() == ClassMap.seeded(MODEL, NAMES)


def test_seeding_again_forgets_the_choices(qtbot):
    d = dialog(qtbot, ClassMap.seeded(MODEL, NAMES).with_target(0, None).with_target(2, "person"))
    assert d.rows()[0] == ("car", NOT_MAPPED)
    d.seed_button.click()
    assert d.rows() == [("car", "car"), ("truck", NOT_MAPPED), ("human", NOT_MAPPED)]
    assert d.class_map() == ClassMap.seeded(MODEL, NAMES)


def test_every_row_is_visible_and_none_overlaps(qtbot):
    d = dialog(qtbot)
    d.show()
    qtbot.waitUntil(d.isVisible)
    rects = []
    for label, combo in d.row_widgets():
        for w in (label, combo):
            rect = QRect(w.mapTo(d, QPoint(0, 0)), w.size())
            assert w.isVisible() and w.width() >= w.sizeHint().width() and d.rect().contains(rect)
            assert not any(rect.intersects(r) for r in rects)
            rects.append(rect)


def test_eighty_classes_scroll_inside_a_dialog_that_fits_the_screen(qtbot):
    names = tuple(f"class {i}" for i in range(80))
    d = ClassMapDialog(ClassMap.seeded(names, NAMES), NAMES)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(d.isVisible)
    assert d.height() <= 700 and len(d.rows()) == 80
```

Append to `tests/ui/test_prompter.py`:

```python
def test_the_class_map_and_threshold_dialogs_answer_none_when_cancelled(qtbot):
    from deeplabeling.core.classmap import ClassMap
    from deeplabeling.ui.class_map_dialog import ClassMapDialog

    parent = QWidget()
    qtbot.addWidget(parent)
    prompter = QtPrompter(parent)
    answer_with_cancel()
    assert prompter.edit_class_map(ClassMap.seeded(("car",), ("car",)), ("car",)) is None
    answer_with_cancel()
    assert prompter.ask_threshold(0.25) is None
    qtbot.waitUntil(lambda: not parent.findChildren(ClassMapDialog))
```

In `tests/ui/test_state_bar.py`, replace:

```python

def chips(bar):
    return (bar.dataset, bar.queue, bar.layers, bar.reviewed)


```

with:

```python

def chips(bar):
    return (bar.dataset, bar.queue, bar.model, bar.layers, bar.reviewed)


```

In `tests/ui/test_state_bar.py`, replace:

```python
    assert bar.reviewed.full_text == "Reviewed 0 / 15"
    assert bar.layers.full_text == "Layers: none"
    session.done_and_next()
    assert bar.reviewed.full_text == "Reviewed 1 / 15"
```

with:

```python
    assert bar.reviewed.full_text == "Reviewed 0 / 15"
    assert bar.layers.full_text == "Layers: none"
    assert bar.model.full_text == "Model: none · load one"
    session.done_and_next()
    assert bar.reviewed.full_text == "Reviewed 1 / 15"
```

Create `tests/ui/test_model_chip.py`:

```python
"""The model chip and its menu (docs/design/2026-10-05-model-assist.md#the-model-chip)."""

import threading

import pytest
from PySide6.QtCore import Qt

import deeplabeling.ui.model as model_module
from deeplabeling.core.inference import Prediction
from drive import start
from fixtures import CAMA_0001, FakePredictor, FakePrompter, read_exact

MISSING_CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9)
ON_THE_PERSON = Prediction(0, (0.5, 0.5, 0.2, 0.3), 0.85)
HUMAN = Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)


def fake(path):
    return FakePredictor(path, found={"0001.jpg": [MISSING_CAR, ON_THE_PERSON, HUMAN]})


@pytest.fixture
def weights(tmp_path):
    path = tmp_path / "models" / "best.pt"
    path.parent.mkdir()
    path.write_bytes(b"weights")
    return path


@pytest.fixture
def prompter(weights):
    return FakePrompter(weights=weights)


@pytest.fixture
def window(qtbot, ds, prompter, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", fake)   # every launch path
    w = start(qtbot, [str(ds.yaml)], prompter)
    yield w
    w.close()


def menu(window) -> dict:
    m = window.state_bar.model.menu()
    m.aboutToShow.emit()
    return {a.text(): a for a in m.actions() if not a.isSeparator()}


def load(qtbot, window):
    menu(window)["Load a model…"].trigger()
    qtbot.waitUntil(lambda: len(window.canvas._predictions) == 3, timeout=5000)


def captions(window):
    return [c.text for c in window.canvas.prediction_caption_items()]


def test_without_a_model_the_chip_invites_one(window):
    assert window.state_bar.model.full_text == "Model: none · load one"
    assert not menu(window)["Class map…"].isEnabled()


def test_loading_from_the_chip_names_the_model_and_draws_its_predictions(qtbot, window):
    load(qtbot, window)
    assert window.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.25"
    assert captions(window) == ["car 0.90", "human? 0.70"]


def test_while_it_loads_the_chip_says_so(qtbot, window, weights):
    gate = threading.Event()
    window.session.model.factory = lambda path: (gate.wait(5), fake(path))[1]
    menu(window)["Load a model…"].trigger()
    assert window.state_bar.model.full_text == "Model: best.pt · loading…"
    gate.set()
    qtbot.waitUntil(lambda: window.session.model.state == "ready")


def test_a_model_that_does_not_load_says_why(qtbot, window, prompter, tmp_path):
    prompter.weights = tmp_path / "broken.pt"
    prompter.weights.write_bytes(b"not a model")
    window.session.model.factory = FakePredictor
    menu(window)["Load a model…"].trigger()
    qtbot.waitUntil(lambda: window.state_bar.model.full_text == "Model: broken.pt · not loaded")
    assert "broken.pt could not be loaded: not a model" in window.notices.texts()


def test_recent_models_are_listed_newest_first_and_load_again(qtbot, window, prompter, weights, tmp_path):
    load(qtbot, window)
    other = tmp_path / "other.pt"
    other.write_bytes(b"other")
    prompter.weights = other
    menu(window)["Load a model…"].trigger()
    qtbot.waitUntil(lambda: window.session.model.state == "ready" and window.session.model.path == other)
    texts = list(menu(window))
    first, second = texts.index(f"other.pt — {tmp_path}"), texts.index(f"best.pt — {weights.parent}")
    assert first < second
    menu(window)[f"best.pt — {weights.parent}"].trigger()
    qtbot.waitUntil(lambda: window.session.model.state == "ready" and window.session.model.path == weights)


def test_the_threshold_hides_weaker_predictions(qtbot, window, prompter):
    load(qtbot, window)
    prompter.threshold = 0.8
    menu(window)["Threshold…"].trigger()
    assert ("threshold", 0.25) in prompter.asked
    assert window.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.80"
    assert captions(window) == ["car 0.90"]         # the person's is faint: no caption


def test_the_class_map_redraws_at_once_and_a_accepts_what_it_maps(qtbot, window, prompter, ds):
    load(qtbot, window)
    prompter.class_map = {"human": "person"}
    menu(window)["Class map…"].trigger()
    assert ("class map", ("car", "truck", "human"), ("person", "car", "bus_m", "bus_l")) in prompter.asked
    assert captions(window) == ["car 0.90", "person 0.70"]
    qtbot.keyClick(window, Qt.Key_A)
    assert read_exact(ds.lbl("camA/0001")) == (CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"
                                              "0 0.100000 0.900000 0.100000 0.100000\n")


def test_the_model_its_threshold_and_its_map_survive_a_relaunch(qtbot, window, prompter, ds):
    load(qtbot, window)
    prompter.threshold, prompter.class_map = 0.5, {"human": "person"}
    menu(window)["Threshold…"].trigger()
    menu(window)["Class map…"].trigger()
    window.close()
    again = start(qtbot, [str(ds.yaml)], FakePrompter())
    qtbot.waitUntil(lambda: len(again.canvas._predictions) == 3, timeout=5000)
    assert again.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.50"
    assert captions(again) == ["car 0.90", "person 0.70"]
    again.close()


def test_without_a_dataset_only_loading_is_offered(qtbot, monkeypatch, prompter):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", fake)
    w = start(qtbot, [], prompter)
    actions = menu(w)
    assert actions["Load a model…"].isEnabled()
    assert not actions["Threshold…"].isEnabled() and not actions["Class map…"].isEnabled()
    w.close()


def test_a_remembered_model_that_is_gone_is_not_loaded(qtbot, window, weights, ds):
    load(qtbot, window)
    window.close()
    weights.unlink()
    again = start(qtbot, [str(ds.yaml)], FakePrompter())
    assert again.session.model.state == "none"
    assert again.state_bar.model.full_text == "Model: none · load one"
    again.close()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_class_map_dialog.py`
Expected: `No module named 'deeplabeling.ui.class_map_dialog'`.

- [ ] **Step 3: Write the editor, the prompts and the chip**

In `src/deeplabeling/ui/main_window.py`, replace:

```python
from .inspector import Inspector
from .keymap import HelpDialog, build_actions
from .notices import NoticeStrip
from .queue_panel import QueuePanel
```

with:

```python
from .inspector import Inspector
from .keymap import HelpDialog, build_actions
from .model import RECENT_MODELS
from .notices import NoticeStrip
from .queue_panel import QueuePanel
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        self._layers_changed()
        self.state_bar.dataset.menu().aboutToShow.connect(self._fill_dataset_menu)
        self.state_bar.queue.clicked.connect(self.edit_queue)
        session.cursorChanged.connect(self.show_current)
```

with:

```python
        self._layers_changed()
        self.state_bar.dataset.menu().aboutToShow.connect(self._fill_dataset_menu)
        self.state_bar.model.menu().aboutToShow.connect(self._fill_model_menu)
        self.state_bar.queue.clicked.connect(self.edit_queue)
        session.cursorChanged.connect(self.show_current)
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
                           lambda e=entry: self.session.open(e["source"], e["labels"]))

    def open_yaml(self) -> None:
        path = self.prompter.choose_yaml()
```

with:

```python
                           lambda e=entry: self.session.open(e["source"], e["labels"]))

    def _fill_model_menu(self) -> None:
        menu, model, ws = self.state_bar.model.menu(), self.session.model, self.session.workspace
        menu.clear()
        menu.addAction("Load a model…", self.load_model)
        recent = self.session.settings.get(RECENT_MODELS)
        if recent:
            menu.addSeparator()
        for path in map(Path, recent):
            menu.addAction(f"{path.name} — {path.parent}", lambda p=path: model.load(p))
        menu.addSeparator()
        menu.addAction("Threshold…", self.ask_threshold).setEnabled(ws is not None)
        menu.addAction("Class map…", self.edit_class_map).setEnabled(ws is not None and model.state == "ready")

    def load_model(self) -> None:
        path = self.prompter.choose_weights()
        if path:
            self.session.model.load(path)

    def ask_threshold(self) -> None:
        value = self.prompter.ask_threshold(self.session.model.conf)
        if value is not None:
            self.session.model.set_conf(value)

    def edit_class_map(self) -> None:
        model = self.session.model
        cmap = self.prompter.edit_class_map(model.class_map, self.session.workspace.dataset.names)
        if cmap is not None:
            model.set_class_map(cmap)

    def open_yaml(self) -> None:
        path = self.prompter.choose_yaml()
```

Create `src/deeplabeling/ui/class_map_dialog.py`:

```python
"""The class-map editor (docs/design/2026-10-05-model-assist.md#the-class-map): one row per
model class, each mapped to a dataset class or to nothing, and a button that seeds by name
again. Only a row the user changes becomes their choice; the rest stay seeded."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..core.classmap import ClassMap

NOT_MAPPED = "not mapped"
MAX_HEIGHT = 640


class ClassMapDialog(QDialog):
    def __init__(self, cmap: ClassMap, dataset_names: Sequence[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Class map")
        self._base, self._names = cmap, tuple(dataset_names)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        self._rows: list[tuple[QLabel, QComboBox]] = []
        for name in cmap.model_names:
            label, combo = QLabel(name), QComboBox()
            combo.addItems([NOT_MAPPED, *self._names])
            form.addRow(label, combo)
            self._rows.append((label, combo))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        self.seed_button = QPushButton("Seed by name again")
        self.seed_button.clicked.connect(self._seed)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Each model class is accepted as the dataset class chosen here."))
        layout.addWidget(scroll)
        layout.addWidget(self.seed_button)
        layout.addWidget(buttons)
        self._show(cmap)
        hint = form_widget.sizeHint()
        self.resize(max(hint.width() + 60, 360), min(hint.height() + 140, MAX_HEIGHT))

    def _show(self, cmap: ClassMap) -> None:
        for (_, combo), target in zip(self._rows, cmap.targets):
            combo.setCurrentText(target if target in self._names else NOT_MAPPED)

    def _seed(self) -> None:
        self._base = ClassMap.seeded(self._base.model_names, self._names)
        self._show(self._base)

    def rows(self) -> list[tuple[str, str]]:
        return [(label.text(), combo.currentText()) for label, combo in self._rows]

    def row_widgets(self) -> list[tuple[QLabel, QComboBox]]:
        return list(self._rows)

    def choose(self, model_name: str, target: str) -> None:
        self._rows[self._base.model_names.index(model_name)][1].setCurrentText(target)

    def class_map(self) -> ClassMap:
        """The map as shown: the rows that differ from where they started are choices."""
        cmap = self._base
        for i, (_, combo) in enumerate(self._rows):
            target = None if combo.currentText() == NOT_MAPPED else combo.currentText()
            if target != cmap.targets[i]:
                cmap = cmap.with_target(i, target)
        return cmap
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from ..core.dataset import Dataset
from ..core.queue import ImageFilter
from .class_picker import ClassPicker
from .classes import ClassInfo
```

with:

```python
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from ..core.classmap import ClassMap
from ..core.dataset import Dataset
from ..core.inference import FLOOR
from ..core.queue import ImageFilter
from .class_map_dialog import ClassMapDialog
from .class_picker import ClassPicker
from .classes import ClassInfo
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
        finally:
            dialog.deleteLater()
```

with:

```python
        finally:
            dialog.deleteLater()

    def choose_weights(self) -> str | None:
        path, _ = QFileDialog.getOpenFileName(self.parent, "Load a model", "",
                                              "Model weights (*.pt);;All files (*)")
        return path or None

    def ask_threshold(self, current: float) -> float | None:
        value, ok = QInputDialog.getDouble(self.parent, "Confidence threshold",
                                           "Show and accept predictions at or above:",
                                           current, FLOOR, 1.0, 2)
        return value if ok else None

    def edit_class_map(self, cmap: ClassMap, dataset_names) -> ClassMap | None:
        dialog = ClassMapDialog(cmap, dataset_names, self.parent)
        try:
            return dialog.class_map() if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()
```

In `src/deeplabeling/ui/state_bar.py`, replace:

```python


class StateBar(QWidget):
    def __init__(self, session: Session, parent=None):
```

with:

```python


def model_text(model) -> str:
    if model.state == "none":
        return "Model: none · load one"
    name = model.path.name
    if model.state == "loading":
        return f"Model: {name} · loading…"
    if model.state == "failed":
        return f"Model: {name} · not loaded"
    return f"Model: {name} · {len(model.names)} classes · conf {model.conf:.2f}"


class StateBar(QWidget):
    def __init__(self, session: Session, parent=None):
```

In `src/deeplabeling/ui/state_bar.py`, replace:

```python
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
```

with:

```python
        self._session = session
        self.dataset, self.queue, self.layers, self.reviewed = Chip(), Chip(), Chip(), Chip()
        self.model = Chip()
        for chip in (self.dataset, self.model, self.layers):
            chip.setPopupMode(QToolButton.InstantPopup)
            chip.setMenu(QMenu(chip))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        for chip, stretch in ((self.dataset, 3), (self.queue, 4), (self.model, 3), (self.layers, 1),
                              (self.reviewed, 1)):
            layout.addWidget(chip, stretch)
        for signal in (session.opened, session.closed, session.queueReset,
                       session.queueDone, session.reviewChanged):
            signal.connect(self.refresh)
        session.model.changed.connect(self.refresh)
        # A building queue grows every 0.2 s, and each refresh counts what is left across
        # the whole queue; while it builds, refresh at most every REFRESH_MS.
```

In `src/deeplabeling/ui/state_bar.py`, replace:

```python
            marked, total = session.reviewed_counts()
            self.reviewed.set_full_text(f"Reviewed {marked:,} / {total:,}")
        shown = [a.text().lower() for a in self.layers.menu().actions() if a.isChecked()]
        self.layers.set_full_text("Layers: " + (", ".join(shown) if shown else "none"))
```

with:

```python
            marked, total = session.reviewed_counts()
            self.reviewed.set_full_text(f"Reviewed {marked:,} / {total:,}")
        self.model.set_full_text(model_text(session.model))
        shown = [a.text().lower() for a in self.layers.menu().actions() if a.isChecked()]
        self.layers.set_full_text("Layers: " + (", ".join(shown) if shown else "none"))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_model_chip.py tests/ui/test_class_map_dialog.py tests/ui/test_prompter.py tests/ui/test_state_bar.py`
Expected: 24 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 639 passed.

```bash
git add src/deeplabeling/ui/class_map_dialog.py src/deeplabeling/ui/prompter.py src/deeplabeling/ui/state_bar.py src/deeplabeling/ui/main_window.py tests/fixtures.py tests/ui/test_class_map_dialog.py tests/ui/test_model_chip.py tests/ui/test_prompter.py tests/ui/test_state_bar.py
git commit -m "ui: the model chip: load, recent, threshold, and the class-map editor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The inspector's Predictions line

**Files:**
- Modify: `src/deeplabeling/ui/inspector.py`
- Test: `tests/ui/test_panels.py`

**Interfaces:**
- Consumes: from Task 2, `ModelSession` (`state`, `failure`, `shown`, `changed`, `ready`, `failed`).
- Produces: `Inspector.predictions_label`, which reads one of:
  - `no model`;
  - `loading`;
  - `not inferred yet`;
  - `none found`;
  - `3 (1 missing)`;
  - `failed: <why>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_panels.py`:

```python
def test_the_inspector_says_what_the_model_found(qtbot, inspector, session, tmp_path):
    import threading

    from deeplabeling.core.inference import Prediction
    from fixtures import FakePredictor

    assert inspector.predictions_label.text() == "no model"
    loading, predicting = threading.Event(), threading.Event()
    found = {"0001.jpg": [Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9),           # car, missing
                          Prediction(0, (0.5, 0.5, 0.2, 0.3), 0.85),          # on the person
                          Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)]}          # human: unmapped
    session.model.factory = lambda p: (loading.wait(5), FakePredictor(p, found=found, gate=predicting))[1]
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    session.model.load(weights)
    assert inspector.predictions_label.text() == "loading"
    loading.set()
    qtbot.waitUntil(lambda: inspector.predictions_label.text() == "not inferred yet")
    predicting.set()
    qtbot.waitUntil(lambda: inspector.predictions_label.text() == "3 (1 missing)")
    session.go_to("camA/images/0002.jpg")
    qtbot.waitUntil(lambda: inspector.predictions_label.text() == "none found")


def test_the_inspector_says_when_the_model_could_not_predict(qtbot, inspector, session, tmp_path):
    from fixtures import FakePredictor

    session.model.factory = lambda p: FakePredictor(p, fail={"0001.jpg"})
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    session.model.load(weights)
    qtbot.waitUntil(lambda: inspector.predictions_label.text() == "failed: 0001.jpg: CUDA out of memory")
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_panels.py`
Expected: 2 failed, 12 passed: the two new tests fail, on `predictions_label`.

- [ ] **Step 3: Add the line**

In `src/deeplabeling/ui/inspector.py`, replace:

```python
        self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label = (
            QLabel() for _ in range(5))
        for label in self._fields():
            label.setWordWrap(True)
```

with:

```python
        self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label = (
            QLabel() for _ in range(5))
        self.predictions_label = QLabel()
        for label in self._fields():
            label.setWordWrap(True)
```

In `src/deeplabeling/ui/inspector.py`, replace:

```python
        form.addRow("Unparsable lines", self.unparsed_label)
        form.addRow("Reviewed", self.reviewed_label)
        self.classes = QListWidget()
        self.boxes = QListWidget()
```

with:

```python
        form.addRow("Unparsable lines", self.unparsed_label)
        form.addRow("Reviewed", self.reviewed_label)
        form.addRow("Predictions", self.predictions_label)
        self.classes = QListWidget()
        self.boxes = QListWidget()
```

In `src/deeplabeling/ui/inspector.py`, replace:

```python
        editing.selection.changed.connect(self._show_selection)
        editing.activeChanged.connect(self.refresh)
        self.refresh()

    def _fields(self) -> tuple[QLabel, ...]:
        # *_label names: a field called `size` would shadow QWidget.size()
        return (self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label)

    def _labels_event(self, images) -> None:
```

with:

```python
        editing.selection.changed.connect(self._show_selection)
        editing.activeChanged.connect(self.refresh)
        session.model.changed.connect(self.refresh)
        session.model.ready.connect(self._image_event)
        session.model.failed.connect(lambda path, why: self._image_event(path))
        self.refresh()

    def _fields(self) -> tuple[QLabel, ...]:
        # *_label names: a field called `size` would shadow QWidget.size()
        return (self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label,
                self.predictions_label)

    def _labels_event(self, images) -> None:
```

In `src/deeplabeling/ui/inspector.py`, replace:

```python
        marked = ws.review.marked_at(entry.rel)
        self.reviewed_label.setText(time.strftime("%Y-%m-%d %H:%M", time.localtime(marked)) if marked else "not yet")
        colors = ws.root_settings.get(CLASS_COLORS)
        counts = Counter(line.cls_id for _, line in labels.boxes)
```

with:

```python
        marked = ws.review.marked_at(entry.rel)
        self.reviewed_label.setText(time.strftime("%Y-%m-%d %H:%M", time.localtime(marked)) if marked else "not yet")
        self.predictions_label.setText(self._predictions_text(session.model, entry))
        colors = ws.root_settings.get(CLASS_COLORS)
        counts = Counter(line.cls_id for _, line in labels.boxes)
```

In `src/deeplabeling/ui/inspector.py`, replace:

```python

    @staticmethod
    def _state_text(labels) -> str:
        if labels.state is LabelState.ERROR:
```

with:

```python

    @staticmethod
    def _predictions_text(model, entry) -> str:
        if model.state == "loading":
            return "loading"
        if model.state != "ready":
            return "no model"
        why = model.failure(entry)
        if why is not None:
            return f"failed: {why}"
        shown = model.shown(entry)
        if shown is None:
            return "not inferred yet"
        if not shown:
            return "none found"
        missing = sum(1 for s in shown if s.missing and s.cls is not None)     # what A would add
        return f"{len(shown)} ({missing} missing)"

    @staticmethod
    def _state_text(labels) -> str:
        if labels.state is LabelState.ERROR:
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_panels.py`
Expected: 14 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 641 passed.

```bash
git add src/deeplabeling/ui/inspector.py tests/ui/test_panels.py
git commit -m "ui: the inspector says what the model found on the image" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The docs

**Files:**
- Modify:
  - `CLAUDE.md` (the status);
  - `docs/design/2026-10-05-model-assist.md` (the status, and chunked undo in plan 2c);
  - `.claude/skills/run-and-verify-ui/SKILL.md` (models in tests, and threads that must outlive their owner).

**Interfaces:**
- Consumes: the code of Tasks 2 and 5, which the skill cites.
- Produces: the docs.

- [ ] **Step 1: Update the status and the skill**

In `CLAUDE.md`, replace:

````markdown

**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 (model assist) has its core built; its UI (plan 2b) is next. The design and
the plans are in [docs/design/](docs/design/).

```sh
````

with:

````markdown

**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 (model assist) has its core and its on-screen UI built; the dataset pass and
the queue accept (plan 2c) are next. The design and the plans are in [docs/design/](docs/design/).

```sh
````

In `docs/design/2026-10-05-model-assist.md`, replace:

```markdown
# DeepLabeling — slice 2: model assist

**Status:** approved 2026-10-05 · plan 2a (the core) implemented; 2b (the UI) next
**Scope:** slice 2 of [the app foundation](2026-10-04-app-foundation.md#slices): load a
model, see its predictions beside the labels, accept them (one box, one image, or a whole
```

with:

```markdown
# DeepLabeling — slice 2: model assist

**Status:** approved 2026-10-05 · plans 2a (the core) and 2b (the UI on screen) implemented;
2c (the dataset pass and the queue accept) next
**Scope:** slice 2 of [the app foundation](2026-10-04-app-foundation.md#slices): load a
model, see its predictions beside the labels, accept them (one box, one image, or a whole
```

In `docs/design/2026-10-05-model-assist.md`, replace:

```markdown
- **Undo and redo of a queue accept are written in chunks too**, behind the same dialog:
  45k files undone at once would freeze the window as long as writing them at once.
  `LabelStore.restore` and `History` gain a chunked form in plan 2b.
- An accept that skips unmapped predictions says how many it skipped.

```

with:

```markdown
- **Undo and redo of a queue accept are written in chunks too**, behind the same dialog:
  45k files undone at once would freeze the window as long as writing them at once.
  `LabelStore.restore` and `History` gain a chunked form in plan 2c.
- An accept that skips unmapped predictions says how many it skipped.

```

In `.claude/skills/run-and-verify-ui/SKILL.md`, replace:

```markdown
- **A painter clip outlives the drawing it was for.** Wrap a clipped part of a delegate's
  paint in `save()`/`restore()`, or everything painted after it is clipped too.
```

with:

```markdown
- **A painter clip outlives the drawing it was for.** Wrap a clipped part of a delegate's
  paint in `save()`/`restore()`, or everything painted after it is clipped too.
- **A model in a test is a fake.** Load `tests/fixtures.py::FakePredictor` through
  `session.model.factory`; a test that relaunches patches the name `UltralyticsPredictor`
  in `deeplabeling.ui.model`, where `src/deeplabeling/ui/model.py::ModelSession` takes its
  default. `import ultralytics` fails in every test
  (`tests/conftest.py::_no_real_model`), so a real weights file is never loaded.
- **A running QThread must outlive its owner.** Qt aborts the process when one is
  destroyed while it runs: give the thread no parent, stop it with a bounded wait, and
  keep a reference while it finishes (`src/deeplabeling/ui/model.py::ModelSession`).
```

- [ ] **Step 2: Check the docs, and run the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 641 passed.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/design/2026-10-05-model-assist.md .claude/skills/run-and-verify-ui/SKILL.md
git commit -m "docs: slice 2's UI on screen is built; how a test loads a model" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
