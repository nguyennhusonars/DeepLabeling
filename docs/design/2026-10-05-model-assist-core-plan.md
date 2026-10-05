# Slice 2a: the model-assist core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Qt-free core of model assist. It covers:
- a predictor that runs an ultralytics detection model and turns its results into predictions;
- a SQLite prediction store per dataset root;
- the class map, by name;
- the rules for what an accept adds;
- an edit across many images, written in chunks.

**Architecture:** Five pure-Python modules under `src/deeplabeling/core/`, tested headless. `inference.py` imports ultralytics only when a model is loaded; tests never import it. `Editor` gains `batch()` and `apply_many()`, built on the existing `LabelStore.apply` and `LabelStore.restore`, so writing and undoing go through slice 1's one write path. Plan 2b builds the UI on these.

**Tech Stack:** Python 3.10 (conda base), sqlite3, ultralytics (the editable install this checkout resolves to), pytest.

**Spec:** [2026-10-05-model-assist.md](2026-10-05-model-assist.md). This plan implements its Architecture section's core: the inference interface, the prediction store, the class map and accepting. The inference thread, the window and the measurements are plan 2b's.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)).
- **`src/deeplabeling/core/` imports no Qt** (`tests/core/test_core_imports_no_qt.py` checks it), and **importing it imports neither ultralytics nor torch** (Task 1 adds the check). Which ultralytics loads depends on the launch directory ([landmine 8](../../CLAUDE.md#landmines)).
- **Tests never import ultralytics** and never load a model. They stand in for `ultralytics.YOLO` through `sys.modules`. The one real-model run is Task 6's script, which is read-only.
- **One write path** ([landmine 1](../../CLAUDE.md#landmines)): an accept is `AddBox` intents applied through `Editor`, and a batch writes through `LabelStore.apply`. On failure it puts files back through `LabelStore.restore`.
- **The disk is nearly full** ([landmine 9](../../CLAUDE.md#landmines)): nothing copies a dataset. The real-model script reads pvn-vehicle in place.
- **Tests write only to temporary folders** (landmine 10).
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice2-model-assist` (it holds the spec already). One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone once plan 2b puts this core behind the window. Each has a named test:

1. **A weights file that is not a detection model:** a classifier from the same `runs/` tree, or not a model at all. It must be refused with the file's name and why, never loaded half-way. *(Task 1 `test_a_model_that_does_not_detect_is_refused`, `test_a_file_that_is_no_model_is_refused_with_its_name`.)*
2. **One bad image in a batch:** an undecodable frame, or CUDA out of memory on a batch. It fails alone, and the rest of the batch is still answered. *(Task 1 `test_an_image_that_cannot_be_read_fails_alone`, `test_a_batch_the_model_fails_on_is_retried_image_by_image`.)*
3. **An image edited or replaced on disk after it was inferred.** Its old predictions must never be served. *(Task 2 `test_a_row_is_served_while_the_image_is_unchanged`.)*
4. **One object the model sees twice:** ultralytics' NMS is per class, so a car comes with a weaker truck. An accept must add one box at that place, and an unmapped strongest prediction keeps the weaker mapped one out. *(Task 4 `test_of_overlapping_predictions_the_most_confident_speaks_for_the_place`, `test_a_stronger_unmapped_prediction_keeps_a_weaker_mapped_one_out`.)*
5. **The disk filling up partway through a queue accept.** Every file already written goes back, and nothing is recorded. *(Task 5 `test_a_write_failing_partway_puts_back_every_file_already_written`.)*

## Found while building this plan

The plan's code was built and run in a scratch copy first: 589 tests pass. The predictor was then run on pvn-vehicle with `runs/detect/backup/yolo26n_vehicle/weights/best.pt` on the GTX 1660 SUPER.

- **Decoding, not the model, limited a pass.** pvn-vehicle's frames are 2592×1944, and decoding one takes 22 ms, so passing paths to ultralytics capped a pass at about 20 images/s at any batch size. Decoding each batch on 4 threads gave 42–70 images/s, against the spec's ≥ 20.
- **Loading takes 1.7 s, and the first prediction 3.6 s more** while the model warms up. Plan 2b's chip must show that, not treat it as a hang.
- **An undecodable image** used to fail its whole batch inside ultralytics. Read separately, it fails alone without a retry.
- **The `runs/` tree holds classifiers beside detectors.** Loading one is refused, by its `task`.
- **Importing ultralytics from this checkout left `~/.config/Ultralytics/settings.json` unchanged:** its md5 was the same before and after.
- **NMS per class** made "accept everything missing" add two boxes for one car. The rule above, the most confident speaks for the place, follows [matching.md](../knowledge/matching.md#candidates-and-the-deciding-prediction).

## Decisions this plan makes

- **The many-image edit is `EditBatch`.** `Editor.batch(description)` returns a batch that applies chunks, then `finish()` records one edit that marks nothing. `Editor.apply_many(intents, description)`, the spec's name, is the one-chunk case. Chunks are what keep plan 2b's window painting.
- **A batch merges by file.** An image written twice keeps its first before-bytes, so undo restores what it was.
- **A store that cannot be read is set aside and started again**, as `dataset.json` is. One that cannot even be moved aside makes the open fail with that reason, as an `OSError`.
- **A queue accept skips read-only images** (a label file two images share, an unreadable one) and counts them.
- **The store keeps a `floor` column**, so a row inferred at a higher floor never answers a lower threshold.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/inference.py` | `Prediction`, `Failure`, `ModelError`, `Predictor`, `model_key`, `predictions_from`, `UltralyticsPredictor` | 1 |
| `src/deeplabeling/core/predstore.py`, `workspace.py` | the SQLite store; the workspace opens and closes it | 2 |
| `src/deeplabeling/core/classmap.py` | `ClassMap`, `CLASS_MAPS`, seeding and loading by name | 3 |
| `src/deeplabeling/core/assist.py` | what is missing; accept intents; a queue accept's plan | 4 |
| `src/deeplabeling/core/editor.py` | `EditBatch`, `Editor.batch`, `Editor.apply_many` | 5 |
| `docs/knowledge/caches.md`, `environment.md`, `CLAUDE.md`, the spec | the store's facts, the GPU, the status | 6 |

---

### Task 1: Predictions and the predictor

**Files:**
- Create: `src/deeplabeling/core/inference.py`
- Test: `tests/core/test_inference.py`

**Interfaces:**
- Consumes: `deeplabeling.core.geometry.Box`.
- Produces in `deeplabeling.core.inference`:
  - `FLOOR = 0.10`, `MAX_BOXES = 100`, `DECODE_THREADS = 4`;
  - `Prediction(cls: int, box: Box, conf: float)`, frozen; `box` is normalised `(cx, cy, w, h)`;
  - `Failure(why: str)`, frozen;
  - `ModelError(Exception)`;
  - `Predictor`, a Protocol with `key: str`, `names: tuple[str, ...]` and `predict(paths) -> list[list[Prediction] | Failure]`;
  - `model_key(weights) -> str`, which is `name:size:mtime`;
  - `predictions_from(result) -> list[Prediction]`, strongest first, at the floor, capped;
  - `UltralyticsPredictor(weights, device=None)`, which raises `ModelError` and has `.key`, `.names` and `.predict(paths)`.

- [ ] **Step 1: Commit this plan**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout slice2-model-assist
git add docs/design/2026-10-05-model-assist-core-plan.md
git commit -m "docs: the slice 2a model-assist core plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/core/test_inference.py`:

```python
"""The model's side: predictions, the model key, and the real predictor's edges.

The real predictor is exercised by the measurement script, never here: tests never
import ultralytics (docs/design/2026-10-05-model-assist.md#testing)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from deeplabeling.core import inference
from deeplabeling.core.inference import (FLOOR, MAX_BOXES, Failure, ModelError, Prediction,
                                         UltralyticsPredictor, model_key, predictions_from)

SRC = Path(__file__).resolve().parents[2] / "src"


class Tensor(list):
    def tolist(self):
        return list(self)


class Boxes:
    def __init__(self, xywhn, cls, conf):
        self.xywhn, self.cls, self.conf = Tensor(xywhn), Tensor(cls), Tensor(conf)


class Result:
    def __init__(self, *rows):
        self.boxes = Boxes([r[1] for r in rows], [r[0] for r in rows], [r[2] for r in rows])


def test_the_model_key_names_the_file_its_size_and_its_time(tmp_path):
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"x" * 10)
    first = model_key(weights)
    assert first.startswith("best.pt:10:")
    weights.write_bytes(b"y" * 11)                          # retrained in place
    assert model_key(weights) != first


def test_a_result_becomes_normalised_predictions_strongest_first():
    result = Result((2.0, [0.5, 0.5, 0.2, 0.3], 0.40004), (0.0, [0.25, 0.25, 0.1, 0.1], 0.87654))
    assert predictions_from(result) == [Prediction(0, (0.25, 0.25, 0.1, 0.1), 0.877),
                                        Prediction(2, (0.5, 0.5, 0.2, 0.3), 0.4)]


def test_a_result_is_cut_at_the_floor_and_capped():
    rows = [(0.0, [0.5, 0.5, 0.1, 0.1], 0.5)] * (MAX_BOXES + 5) + [(1.0, [0.5, 0.5, 0.1, 0.1], FLOOR / 2)]
    kept = predictions_from(Result(*rows))
    assert len(kept) == MAX_BOXES and all(p.conf >= FLOOR for p in kept)


def test_an_empty_result_is_an_empty_list_not_nothing():
    assert predictions_from(Result()) == []


def test_importing_the_core_does_not_import_ultralytics():
    code = ("import sys\nimport deeplabeling.core.inference\n"
            "print('ultralytics' in sys.modules, 'torch' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(SRC)})
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["False", "False"]


def test_a_file_that_is_no_model_is_refused_with_its_name(tmp_path, monkeypatch):
    class Loader:
        def __init__(self, path):
            raise RuntimeError("invalid load key, 'x'")

    monkeypatch.setitem(sys.modules, "ultralytics", type("M", (), {"YOLO": Loader}))
    weights = tmp_path / "broken.pt"
    weights.write_bytes(b"x")
    with pytest.raises(ModelError, match="broken.pt could not be loaded: invalid load key"):
        UltralyticsPredictor(weights)


def test_a_model_that_does_not_detect_is_refused(tmp_path, monkeypatch):
    class Classifier:
        task, names = "classify", {0: "helmet"}

        def __init__(self, path):
            pass

    monkeypatch.setitem(sys.modules, "ultralytics", type("M", (), {"YOLO": Classifier}))
    weights = tmp_path / "helmet.pt"
    weights.write_bytes(b"x")
    with pytest.raises(ModelError, match="helmet.pt is a classify model, not a detection model"):
        UltralyticsPredictor(weights)


class Detector:
    """A stand-in for ultralytics' YOLO: fails any batch of more than one image when told
    to, and the image "poison" alone."""

    task, names, fail_batches = "detect", {0: "car", 1: "bus"}, False

    def __init__(self, path):
        pass

    def predict(self, images, **kw):
        if (self.fail_batches and len(images) > 1) or "poison" in images:
            raise RuntimeError("CUDA out of memory")
        return [Result((1.0, [0.5, 0.5, 0.2, 0.2], 0.9)) for _ in images]


@pytest.fixture
def predictor(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "ultralytics", type("M", (), {"YOLO": Detector}))
    monkeypatch.setattr(inference, "_read", lambda path: None if "bad" in path.name else path.stem)
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"x")
    return UltralyticsPredictor(weights)


CAR = [Prediction(1, (0.5, 0.5, 0.2, 0.2), 0.9)]


def test_the_predictor_names_its_model_and_its_classes(predictor, tmp_path):
    assert predictor.names == ("car", "bus") and predictor.key == model_key(tmp_path / "best.pt")


def test_an_image_that_cannot_be_read_fails_alone(predictor, tmp_path):
    out = predictor.predict([tmp_path / "a.jpg", tmp_path / "bad.jpg", tmp_path / "b.jpg"])
    assert out[0] == CAR and out[2] == CAR
    assert out[1] == Failure("bad.jpg could not be read as an image")


def test_a_batch_the_model_fails_on_is_retried_image_by_image(predictor, tmp_path, monkeypatch):
    monkeypatch.setattr(Detector, "fail_batches", True)
    out = predictor.predict([tmp_path / "a.jpg", tmp_path / "poison.jpg", tmp_path / "b.jpg"])
    assert out[0] == CAR and out[2] == CAR
    assert out[1] == Failure("RuntimeError: CUDA out of memory")
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_inference.py`
Expected: `ImportError: cannot import name 'inference' from 'deeplabeling.core'`.

- [ ] **Step 4: Write the module**

Create `src/deeplabeling/core/inference.py`:

```python
"""The model's side of model assist (docs/design/2026-10-05-model-assist.md#the-inference-thread).

A Predictor turns image files into Predictions: the model's own class ids, normalised
boxes, at the floor (docs/knowledge/caches.md#store-at-a-floor-and-filter-on-read).
UltralyticsPredictor imports ultralytics only when a model is loaded, never on import:
which ultralytics loads depends on the launch directory (CLAUDE.md landmine 8), and
importing it costs seconds.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .geometry import Box

FLOOR = 0.10        #: every prediction is inferred, and stored, at this confidence
MAX_BOXES = 100     #: the strongest this many are kept per image
#: Decoding a 2592x1944 JPEG takes 22 ms and capped a pass at 20 images/s; decoded on 4
#: threads (cv2 releases the GIL) a batch of 8 ran at 70/s on a GTX 1660 SUPER (2026-10-05).
DECODE_THREADS = 4


@dataclass(frozen=True)
class Prediction:
    cls: int        #: the model's class id; the class map gives the dataset's
    box: Box        #: normalised (cx, cy, w, h), against the image as the model read it
    conf: float


@dataclass(frozen=True)
class Failure:
    """An image the model could not predict on, and why."""

    why: str


class ModelError(Exception):
    """A weights file that cannot be used: it does not load, or it does not detect."""


class Predictor(Protocol):
    key: str                        #: model_key of the weights
    names: tuple[str, ...]          #: the model's class names, by id

    def predict(self, paths: Sequence[Path]) -> list[list[Prediction] | Failure]: ...


def model_key(weights) -> str:
    """`name:size:mtime`: a file retrained in place gets a new key, so its old rows are
    never served for it (docs/knowledge/caches.md#the-durable-store)."""
    path = Path(weights)
    stat = path.stat()
    return f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}"


def predictions_from(result) -> list[Prediction]:
    """One ultralytics result as Predictions, strongest first, at the floor and capped."""
    boxes = result.boxes
    found = [Prediction(int(cls), tuple(round(float(v), 6) for v in box), round(float(conf), 3))
             for box, cls, conf in zip(boxes.xywhn.tolist(), boxes.cls.tolist(), boxes.conf.tolist())
             if conf >= FLOOR]
    found.sort(key=lambda p: -p.conf)
    return found[:MAX_BOXES]


def _read(path: Path):
    """The image as the model reads it: cv2 applies EXIF orientation as Qt's decode does
    (docs/knowledge/caches.md#image-sizes). None when it is not an image."""
    import cv2

    return cv2.imread(str(path))


class UltralyticsPredictor:
    """A detection model from an ultralytics weights file. Not thread-safe: one thread
    loads it and asks it everything."""

    def __init__(self, weights, device: str | None = None):
        path = Path(weights)
        try:
            from ultralytics import YOLO

            model = YOLO(str(path))
        except Exception as e:                      # whatever the file or the library raises
            raise ModelError(f"{path.name} could not be loaded: {e}") from e
        if model.task != "detect":
            raise ModelError(f"{path.name} is a {model.task} model, not a detection model")
        self.key = model_key(path)
        self.names = tuple(str(model.names[i]) for i in sorted(model.names))
        self._model, self._device = model, device
        self._decoder = ThreadPoolExecutor(DECODE_THREADS)

    def predict(self, paths: Sequence[Path]) -> list[list[Prediction] | Failure]:
        """One answer per path. An image that cannot be read fails alone; a batch the
        model fails on is retried image by image, so one bad image never fails the rest."""
        images = list(self._decoder.map(_read, paths))
        answers: list[list[Prediction] | Failure] = [
            Failure(f"{Path(p).name} could not be read as an image") if image is None else []
            for p, image in zip(paths, images)]
        readable = [i for i, image in enumerate(images) if image is not None]
        for i, found in zip(readable, self._run([images[i] for i in readable])):
            answers[i] = found
        return answers

    def _run(self, images: list) -> list[list[Prediction] | Failure]:
        if not images:
            return []
        try:
            results = self._model.predict(images, conf=FLOOR, max_det=MAX_BOXES, batch=len(images),
                                          device=self._device, verbose=False)
            if len(results) != len(images):
                raise ValueError(f"{len(results)} results for {len(images)} images")
            return [predictions_from(r) for r in results]
        except Exception as e:                      # CUDA out of memory, a library error
            if len(images) == 1:
                return [Failure(f"{type(e).__name__}: {e}")]
            return [self._run([image])[0] for image in images]
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_inference.py tests/core/test_core_imports_no_qt.py`
Expected: 11 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 560 passed.

```bash
git add src/deeplabeling/core/inference.py tests/core/test_inference.py
git commit -m "core: predictions, the model key, and a predictor that imports ultralytics only to load" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The prediction store

**Files:**
- Create: `src/deeplabeling/core/predstore.py`
- Modify: `src/deeplabeling/core/workspace.py`
- Test: `tests/core/test_predstore.py`

**Interfaces:**
- Consumes: `FLOOR` and `Prediction` (Task 1); `set_aside` (`deeplabeling.core.state`).
- Produces in `deeplabeling.core.predstore`:
  - `STORE_NAME = "predictions.sqlite"`;
  - `Stamp`, which is `tuple[int, int]`;
  - `image_stamp(path) -> Stamp`, the file's `(size, mtime_ns)`;
  - `PredictionStore(path)`, with `.path` and `.warning`, and these methods:
    - `.get(model, img, stamp, conf=FLOOR) -> list[Prediction] | None`;
    - `.put(model, img, stamp, preds)`;
    - `.put_many(model, rows)`, all rows in one transaction;
    - `.inferred(model) -> dict[str, Stamp]`;
    - `.close()`.
  - Each thread uses its own connection.
- Produces in `Workspace`: `.predictions`, opened on open and closed on close. Its warning joins `Workspace.warnings`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_predstore.py`:

```python
"""The prediction store: what it serves, what counts as a miss, and what it survives
(docs/design/2026-10-05-model-assist.md#the-prediction-store)."""

import threading

import pytest

from deeplabeling.core.inference import FLOOR, Prediction
from deeplabeling.core.predstore import STORE_NAME, PredictionStore, image_stamp
from deeplabeling.core.workspace import Workspace

MODEL, OTHER = "best.pt:5396421:1787353306", "best.pt:5396421:1787353999"
CAR = Prediction(3, (0.25, 0.25, 0.1, 0.15), 0.96)
FAINT = Prediction(2, (0.5, 0.5, 0.2, 0.2), 0.15)


@pytest.fixture
def store(tmp_path):
    s = PredictionStore(tmp_path / STORE_NAME)
    yield s
    s.close()


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "a.jpg"
    path.write_bytes(b"pixels")
    return path


def test_a_row_is_served_while_the_image_is_unchanged(store, image):
    store.put(MODEL, "a.jpg", image_stamp(image), [CAR, FAINT])
    assert store.get(MODEL, "a.jpg", image_stamp(image)) == [CAR, FAINT]
    image.write_bytes(b"other pixels")                      # edited, or replaced, on disk
    assert store.get(MODEL, "a.jpg", image_stamp(image)) is None


def test_never_inferred_and_nothing_found_are_different_answers(store, image):
    stamp = image_stamp(image)
    assert store.get(MODEL, "a.jpg", stamp) is None
    store.put(MODEL, "a.jpg", stamp, [])
    assert store.get(MODEL, "a.jpg", stamp) == []


def test_another_model_is_a_miss(store, image):
    store.put(MODEL, "a.jpg", image_stamp(image), [CAR])
    assert store.get(OTHER, "a.jpg", image_stamp(image)) is None


def test_the_threshold_filters_on_read_and_nothing_below_the_floor_is_answered(store, image):
    stamp = image_stamp(image)
    store.put(MODEL, "a.jpg", stamp, [CAR, FAINT])
    assert store.get(MODEL, "a.jpg", stamp, conf=0.5) == [CAR]
    assert store.get(MODEL, "a.jpg", stamp, conf=FLOOR / 2) is None


def test_rows_survive_closing_and_a_batch_is_written_at_once(tmp_path, image):
    stamp = image_stamp(image)
    first = PredictionStore(tmp_path / STORE_NAME)
    first.put_many(MODEL, [("a.jpg", stamp, [CAR]), ("b.jpg", (1, 2), [])])
    first.close()
    again = PredictionStore(tmp_path / STORE_NAME)
    assert again.get(MODEL, "a.jpg", stamp) == [CAR]
    assert again.inferred(MODEL) == {"a.jpg": stamp, "b.jpg": (1, 2)}
    again.close()


def test_every_thread_reads_through_its_own_connection(store, image):
    stamp = image_stamp(image)
    store.put(MODEL, "a.jpg", stamp, [CAR])
    seen = []
    worker = threading.Thread(target=lambda: seen.append(store.get(MODEL, "a.jpg", stamp)))
    worker.start()
    worker.join()
    assert seen == [[CAR]]


def test_a_store_that_cannot_be_read_is_set_aside_and_started_again(tmp_path, image):
    (tmp_path / STORE_NAME).write_bytes(b"not a database, " * 200)
    store = PredictionStore(tmp_path / STORE_NAME)
    assert "predictions.sqlite could not be read" in store.warning
    assert list(tmp_path.glob(f"{STORE_NAME}.unreadable-*"))
    store.put(MODEL, "a.jpg", image_stamp(image), [CAR])
    assert store.get(MODEL, "a.jpg", image_stamp(image)) == [CAR]
    store.close()


def test_the_workspace_keeps_one_store_per_root(ds):
    ws = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    try:
        assert ws.predictions.path == ws.directory / STORE_NAME
        ws.predictions.put(MODEL, "camA/images/0001.jpg", (1, 2), [CAR])
    finally:
        ws.close()
    again = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    try:
        assert again.predictions.get(MODEL, "camA/images/0001.jpg", (1, 2)) == [CAR]
    finally:
        again.close()


def test_a_store_that_can_neither_be_read_nor_moved_aside_refuses_as_an_os_error(tmp_path, monkeypatch):
    from deeplabeling.core import predstore

    (tmp_path / STORE_NAME).write_bytes(b"not a database, " * 200)
    monkeypatch.setattr(predstore, "set_aside", lambda path, e: ("predictions.sqlite could not be moved", False))
    with pytest.raises(OSError, match="predictions.sqlite could not be moved"):
        PredictionStore(tmp_path / STORE_NAME)
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_predstore.py`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.core.predstore'`.

- [ ] **Step 3: Write the store, and open it with the workspace**

Create `src/deeplabeling/core/predstore.py`:

```python
"""The prediction store (docs/design/2026-10-05-model-assist.md#the-prediction-store).

One SQLite file per dataset root, keyed by (model, image). It holds what the model found
at the floor, in the model's own class ids; thresholds and the class map apply on read
(docs/knowledge/caches.md). A row is served only while the image's stamp still matches.
Each thread talks to it through its own connection.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from .inference import FLOOR, Prediction
from .state import set_aside

STORE_NAME = "predictions.sqlite"
Stamp = tuple[int, int]             #: (size, mtime_ns) of an image file

SCHEMA = """
CREATE TABLE IF NOT EXISTS preds (
    model TEXT NOT NULL,            -- the weights' name:size:mtime
    img TEXT NOT NULL,              -- the image's dataset-relative path
    size INTEGER NOT NULL,          -- the image's stamp when it was inferred
    mtime_ns INTEGER NOT NULL,
    floor REAL NOT NULL,            -- the confidence it was inferred at
    boxes TEXT NOT NULL,            -- JSON [[cls, cx, cy, w, h, conf], ...]
    PRIMARY KEY (model, img)
)
"""


def image_stamp(path) -> Stamp:
    stat = os.stat(path)
    return stat.st_size, stat.st_mtime_ns


def _encode(preds: Iterable[Prediction]) -> str:
    return json.dumps([[p.cls, *p.box, p.conf] for p in preds], separators=(",", ":"))


def _decode(text: str) -> list[Prediction]:
    return [Prediction(int(row[0]), tuple(row[1:5]), row[5]) for row in json.loads(text)]


class PredictionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.warning = ""                           # for the notice strip
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        try:
            self._connection()
        except sqlite3.DatabaseError as e:
            self._close_all()
            self.warning, writable = set_aside(self.path, e)
            if not writable:                        # the open says why, as for any OSError
                raise OSError(self.warning) from e
            self._connection()

    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute(SCHEMA)
                conn.commit()
            except sqlite3.DatabaseError:
                conn.close()
                raise
            self._local.conn = conn
            with self._lock:
                self._all.append(conn)
        return conn

    def get(self, model: str, img: str, stamp: Stamp, conf: float = FLOOR) -> list[Prediction] | None:
        """What `model` found on `img`, at or above `conf`: None when it never looked at
        this image as it is now, or not down to `conf`; [] when it found nothing."""
        row = self._connection().execute(
            "SELECT size, mtime_ns, floor, boxes FROM preds WHERE model = ? AND img = ?",
            (model, img)).fetchone()
        if row is None or (row[0], row[1]) != tuple(stamp) or conf < row[2]:
            return None
        return [p for p in _decode(row[3]) if p.conf >= conf]

    def put(self, model: str, img: str, stamp: Stamp, preds: Iterable[Prediction]) -> None:
        self.put_many(model, [(img, stamp, preds)])

    def put_many(self, model: str, rows: Iterable[tuple[str, Stamp, Iterable[Prediction]]]) -> None:
        """Write rows in one transaction: a cancelled or crashed pass keeps every batch
        it committed."""
        conn = self._connection()
        with conn:
            conn.executemany(
                "INSERT OR REPLACE INTO preds VALUES (?, ?, ?, ?, ?, ?)",
                [(model, img, stamp[0], stamp[1], FLOOR, _encode(preds)) for img, stamp, preds in rows])

    def inferred(self, model: str) -> dict[str, Stamp]:
        """Every image `model` has a row for, with the stamp it was inferred at: what a
        pass reads to know what is left, without reading the boxes."""
        rows = self._connection().execute(
            "SELECT img, size, mtime_ns FROM preds WHERE model = ?", (model,))
        return {img: (size, mtime_ns) for img, size, mtime_ns in rows}

    def _close_all(self) -> None:
        with self._lock:
            for conn in self._all:
                conn.close()
            self._all.clear()
        self._local = threading.local()

    def close(self) -> None:
        self._close_all()
```

In `src/deeplabeling/core/workspace.py`, replace:

```python
from .history import History
```

with:

```python
from .history import History
from .predstore import STORE_NAME, PredictionStore
```

In `src/deeplabeling/core/workspace.py`, replace:

```python
    history: History
    editor: Editor
```

with:

```python
    history: History
    editor: Editor
    predictions: PredictionStore
```

In `src/deeplabeling/core/workspace.py`, replace:

```python
            editor = Editor(store, history, review, on_labels_changed=on_labels_changed,
                            on_history_changed=on_history_changed)
```

with:

```python
            editor = Editor(store, history, review, on_labels_changed=on_labels_changed,
                            on_history_changed=on_history_changed)
            predictions = PredictionStore(directory / STORE_NAME)
```

In `src/deeplabeling/core/workspace.py`, replace:

```python
                   review, store, history, editor)
```

with:

```python
                   review, store, history, editor, predictions)
```

In `src/deeplabeling/core/workspace.py`, replace:

```python
        return tuple(w for w in (self.file.warning, self.review.warning) if w)
```

with:

```python
        return tuple(w for w in (self.file.warning, self.review.warning, self.predictions.warning) if w)
```

In `src/deeplabeling/core/workspace.py`, replace:

```python
    def close(self) -> None:
        try:
            self.save()
        finally:
            self.lock.release()
```

with:

```python
    def close(self) -> None:
        try:
            self.save()
        finally:
            self.predictions.close()
            self.lock.release()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_predstore.py tests/core/test_workspace.py`
Expected: 21 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 569 passed.

```bash
git add src/deeplabeling/core tests/core/test_predstore.py
git commit -m "core: the prediction store, one per root, opened with the workspace" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The class map

**Files:**
- Create: `src/deeplabeling/core/classmap.py`
- Test: `tests/core/test_classmap.py`

**Interfaces:**
- Consumes: `Dataset.id_of` and `Settings`, with `define` (`deeplabeling.core.settings`).
- Produces in `deeplabeling.core.classmap`:
  - `CLASS_MAPS`, a root setting shaped `{model class list as JSON: {model class name: dataset class name | None}}`;
  - `normalize(name) -> str`;
  - `ClassMap(model_names, targets)`, frozen, with these members:
    - `.key`;
    - `.seeded(model_names, dataset_names)`, a classmethod;
    - `.translate(model_cls, dataset) -> int | None`;
    - `.with_target(model_cls, name | None) -> ClassMap`;
    - `.to_json()`;
  - `load_class_map(settings, model_names, dataset_names) -> ClassMap`;
  - `save_class_map(settings, cmap)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_classmap.py`:

```python
"""The class map: model class names onto dataset class names, kept per model class list
(docs/design/2026-10-05-model-assist.md#the-class-map)."""

import pytest
import yaml

from deeplabeling.core.classmap import CLASS_MAPS, ClassMap, load_class_map, normalize, save_class_map
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.settings import JsonFile, Settings

MODEL = ("BSD", "Bus-M", "car", "human")                     # a model's classes, by id


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)                            # person, car, bus_m, bus_l


@pytest.fixture
def settings(tmp_path):
    return Settings(JsonFile(tmp_path / "dataset.json"), "root", ("root",))


def test_names_match_ignoring_case_spaces_dashes_and_underscores():
    assert normalize("Bus_M") == normalize("bus m") == normalize("busm") == normalize("BUS-M")


def test_a_new_map_is_seeded_by_name(dataset):
    cmap = ClassMap.seeded(MODEL, dataset.names)
    assert cmap.targets == (None, "bus_m", "car", None)
    assert [cmap.translate(i, dataset) for i in range(4)] == [None, 2, 1, None]


def test_a_class_past_the_model_list_translates_to_nothing(dataset):
    assert ClassMap.seeded(MODEL, dataset.names).translate(9, dataset) is None


def test_a_map_is_kept_by_the_model_class_list(dataset, settings):
    cmap = load_class_map(settings, MODEL, dataset.names).with_target(3, "person")
    save_class_map(settings, cmap)
    assert load_class_map(settings, MODEL, dataset.names) == cmap        # retrained, same classes
    other = load_class_map(settings, ("car", "truck"), dataset.names)     # another best.pt
    assert other.targets == ("car", None)


def test_a_yaml_without_the_mapped_name_translates_it_to_nothing(dataset, ds):
    cmap = ClassMap.seeded(MODEL, dataset.names)
    assert cmap.translate(1, dataset) == 2
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data["names"] = ["person", "car"]                       # another yaml of the root, no bus_m
    (ds.root / "two.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    seven = Dataset.open(ds.root / "two.yaml")
    assert cmap.translate(1, seven) is None and cmap.translate(2, seven) == 1


def test_a_stored_map_missing_a_class_seeds_that_one_and_drops_strangers(dataset, settings):
    key = ClassMap.seeded(MODEL, dataset.names).key
    settings.set(CLASS_MAPS, {key: {"car": None, "human": "person", "ghost": "bus_l"}})
    cmap = load_class_map(settings, MODEL, dataset.names)
    assert cmap.targets == (None, "bus_m", None, "person")   # car stays unmapped: the user chose
    assert cmap.to_json() == {"BSD": None, "Bus-M": "bus_m", "car": None, "human": "person"}


def test_the_settings_refuse_what_is_not_a_map_of_maps(settings):
    with pytest.raises(ValueError):
        settings.set(CLASS_MAPS, {"k": ["car"]})
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_classmap.py`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.core.classmap'`.

- [ ] **Step 3: Write the module**

Create `src/deeplabeling/core/classmap.py`:

```python
"""The class map: the model's class names onto the dataset's
(docs/design/2026-10-05-model-assist.md#the-class-map).

Kept by name on both sides, so the yamls of one root share it, and stored per model
class list, so two models with different classes never share one (the legacy app gave
every best.pt one map: docs/knowledge/legacy-defects.md). Predictions keep the model's
own ids; this map translates them on read (docs/knowledge/caches.md#store-raw-model-ids).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .dataset import Dataset
from .settings import Settings, define


def _is_map_of_maps(v) -> bool:
    return isinstance(v, dict) and all(
        isinstance(k, str) and isinstance(m, dict)
        and all(isinstance(a, str) and (b is None or isinstance(b, str)) for a, b in m.items())
        for k, m in v.items())


#: {model class list, as JSON: {model class name: dataset class name or None}}
CLASS_MAPS = define("models.class_maps", "root", {}, _is_map_of_maps)


def normalize(name: str) -> str:
    """Names compare ignoring case, spaces, dashes and underscores: `Bus_M`, `bus m` and
    `busm` are one name (docs/knowledge/datasets.md#prediction-maps-and-class-groups)."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def _seed(name: str, dataset_names: Sequence[str]) -> str | None:
    key = normalize(name)
    return next((d for d in dataset_names if normalize(d) == key), None)  # the first wins


@dataclass(frozen=True)
class ClassMap:
    model_names: tuple[str, ...]            #: the model's classes, by id
    targets: tuple[str | None, ...]         #: the dataset class name each one maps to

    @property
    def key(self) -> str:
        return json.dumps(list(self.model_names))

    @classmethod
    def seeded(cls, model_names: Sequence[str], dataset_names: Sequence[str]) -> ClassMap:
        names = tuple(model_names)
        return cls(names, tuple(_seed(n, dataset_names) for n in names))

    def translate(self, model_cls: int, dataset: Dataset) -> int | None:
        """The dataset class id a model class id stands for, or None: unmapped, or mapped
        to a name this yaml does not have."""
        if not 0 <= model_cls < len(self.targets) or self.targets[model_cls] is None:
            return None
        return dataset.id_of(self.targets[model_cls])

    def with_target(self, model_cls: int, name: str | None) -> ClassMap:
        targets = list(self.targets)
        targets[model_cls] = name
        return replace(self, targets=tuple(targets))

    def to_json(self) -> dict[str, str | None]:
        return dict(zip(self.model_names, self.targets))


def load_class_map(settings: Settings, model_names: Sequence[str],
                   dataset_names: Sequence[str]) -> ClassMap:
    """The stored map for this model class list; a class it does not cover is seeded by
    name, and an entry for a class the model lacks is dropped."""
    seeded = ClassMap.seeded(model_names, dataset_names)
    stored = settings.get(CLASS_MAPS).get(seeded.key)
    if stored is None:
        return seeded
    return replace(seeded, targets=tuple(stored[n] if n in stored else t
                                         for n, t in zip(seeded.model_names, seeded.targets)))


def save_class_map(settings: Settings, cmap: ClassMap) -> None:
    settings.set(CLASS_MAPS, {**settings.get(CLASS_MAPS), cmap.key: cmap.to_json()})
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_classmap.py`
Expected: 7 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 576 passed.

```bash
git add src/deeplabeling/core/classmap.py tests/core/test_classmap.py
git commit -m "core: the class map, by name, kept per model class list" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: What an accept adds

**Files:**
- Create: `src/deeplabeling/core/assist.py`
- Test: `tests/core/test_assist.py`

**Interfaces:**
- Consumes:
  - `ClassMap.translate` (Task 3) and `Prediction` (Task 1);
  - `iou` (geometry), `AddBox` and `Intent` (edits);
  - `ImageLabels`, with `.boxes` and `.editable` (store);
  - `Dataset.entry`, `ImageEntry.path` and `ImageEntry.rel`.
- Produces in `deeplabeling.core.assist`:
  - `MATCH_IOU = 0.5`;
  - `Shown(pred, cls: int | None, missing: bool)`;
  - `shown_predictions(preds, labels, cmap, dataset, conf) -> list[Shown]`, strongest first;
  - `accept_image(image, shown) -> tuple[Intent | None, int]`, the intent and how many unmapped were skipped;
  - `accept_one(image, shown) -> Intent | None`;
  - `QueueAccept(intents, boxes, uninferred, unmapped, read_only)`;
  - `plan_queue_accept(entries, labels_of, preds_of, cmap, dataset, conf, cancelled=...) -> QueueAccept | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_assist.py`:

```python
"""What an accept adds (docs/design/2026-10-05-model-assist.md#accepting)."""

import pytest

from deeplabeling.core.assist import Shown, accept_image, accept_one, plan_queue_accept, shown_predictions
from deeplabeling.core.classmap import ClassMap
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, materialize
from deeplabeling.core.inference import Prediction
from deeplabeling.core.store import LabelStore
from fixtures import CAMA_0001

MODEL = ("car", "truck", "human")                           # car → car, human: unmapped here
PERSON_BOX = (0.5, 0.5, 0.2, 0.3)                           # camA/0001 line 0 (person)


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)                            # person, car, bus_m, bus_l


@pytest.fixture
def store(dataset):
    return LabelStore(dataset)


@pytest.fixture
def cmap(dataset):
    return ClassMap.seeded(MODEL, dataset.names)            # car → car; truck, human unmapped


def p(cls, box, conf):
    return Prediction(cls, box, conf)


def test_a_prediction_a_label_overlaps_is_not_missing_whatever_its_class(store, cmap, dataset, ds):
    labels = store.get(ds.img("camA/0001.jpg"))
    shown = shown_predictions([p(0, (0.51, 0.5, 0.2, 0.3), 0.9), p(0, (0.8, 0.8, 0.1, 0.1), 0.8)],
                              labels, cmap, dataset, conf=0.25)
    assert [(s.cls, s.missing) for s in shown] == [(1, False), (1, True)]


def test_the_threshold_applies_before_anything_else(store, cmap, dataset, ds):
    labels = store.get(ds.img("camA/0003.jpg"))
    assert shown_predictions([p(0, (0.8, 0.8, 0.1, 0.1), 0.2)], labels, cmap, dataset, conf=0.25) == []


def test_of_overlapping_predictions_the_most_confident_speaks_for_the_place(store, cmap, dataset, ds):
    labels = store.get(ds.img("camA/0003.jpg"))
    car, truck = p(0, (0.5, 0.5, 0.2, 0.2), 0.8), p(1, (0.505, 0.5, 0.2, 0.2), 0.35)
    shown = shown_predictions([truck, car], labels, cmap, dataset, conf=0.25)
    assert [(s.pred, s.missing) for s in shown] == [(car, True), (truck, False)]


def test_a_stronger_unmapped_prediction_keeps_a_weaker_mapped_one_out(store, cmap, dataset, ds):
    labels = store.get(ds.img("camA/0003.jpg"))
    human, car = p(2, (0.5, 0.5, 0.2, 0.2), 0.9), p(0, (0.5, 0.5, 0.2, 0.2), 0.5)
    intent, unmapped = accept_image(ds.img("camA/0003.jpg"),
                                    shown_predictions([human, car], labels, cmap, dataset, conf=0.25))
    assert intent is None and unmapped == 1


def test_accepting_an_image_adds_its_missing_mapped_predictions_as_one_edit(store, cmap, dataset, ds):
    image = ds.img("camA/0001.jpg")
    labels = store.get(image)
    shown = shown_predictions([p(0, PERSON_BOX, 0.9), p(0, (0.8, 0.8, 0.1, 0.1), 0.8),
                               p(2, (0.1, 0.9, 0.1, 0.1), 0.7)], labels, cmap, dataset, conf=0.25)
    intent, unmapped = accept_image(image, shown)
    assert intent.ops == (AddBox(1, (0.8, 0.8, 0.1, 0.1)),) and unmapped == 1
    assert intent.description == "accept 1 prediction"
    after = materialize(labels.raw, intent.ops, class_ok=dataset.known).decode()
    assert after == CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"


def test_accepting_one_takes_even_a_covered_prediction_but_never_an_unmapped_one(store, cmap, dataset, ds):
    image = ds.img("camA/0001.jpg")
    covered = Shown(p(0, PERSON_BOX, 0.9), 1, False)
    assert accept_one(image, covered).ops == (AddBox(1, PERSON_BOX),)
    assert accept_one(image, Shown(p(2, PERSON_BOX, 0.9), None, True)) is None


def test_a_queue_accept_is_planned_from_what_is_inferred(store, cmap, dataset, ds):
    entries = [dataset.entry(ds.img(rel)) for rel in ("camA/0001.jpg", "camA/0003.jpg", "camA/0004.JPG",
                                                      "camB/twin.jpg")]
    found = {"camA/images/0001.jpg": [p(0, PERSON_BOX, 0.9)],              # covered: nothing to add
             "camA/images/0003.jpg": [p(0, (0.5, 0.5, 0.2, 0.2), 0.8), p(2, (0.1, 0.1, 0.1, 0.1), 0.9)],
             "camB/images/twin.jpg": [p(0, (0.5, 0.5, 0.3, 0.3), 0.8)]}     # its label file is shared
    plan = plan_queue_accept(entries, store.get, lambda e: found.get(e.rel), cmap, dataset, conf=0.25)
    assert [i.image for i in plan.intents] == [ds.img("camA/0003.jpg")]
    assert (plan.boxes, plan.uninferred, plan.unmapped, plan.read_only) == (1, 1, 1, 1)


def test_a_queue_accept_plan_stops_when_cancelled(store, cmap, dataset, ds):
    entries = list(dataset.images)
    plan = plan_queue_accept(entries, store.get, lambda e: [], cmap, dataset, conf=0.25,
                             cancelled=lambda: True)
    assert plan is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_assist.py`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.core.assist'`.

- [ ] **Step 3: Write the module**

Create `src/deeplabeling/core/assist.py`:

```python
"""What accepting predictions adds (docs/design/2026-10-05-model-assist.md#accepting).

A prediction is shown with its dataset class (or None, unmapped) and whether it is
missing: above the threshold, overlapped by no label of any class, and the most confident
prediction at its place. Of overlapping predictions the most confident speaks for the
place (docs/knowledge/matching.md#candidates-and-the-deciding-prediction): ultralytics
keeps one box per class, so one car often comes with a weaker truck. An unmapped one
speaking for a place keeps every weaker one out (matching.md#unmapped-classes-are-inconclusive).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .classmap import ClassMap
from .dataset import Dataset, ImageEntry
from .edits import AddBox, Intent
from .geometry import iou
from .inference import Prediction
from .store import ImageLabels

MATCH_IOU = 0.5     #: a label or a stronger prediction this close covers a prediction


@dataclass(frozen=True)
class Shown:
    pred: Prediction
    cls: int | None     #: the dataset class id, or None when the class map leaves it out
    missing: bool       #: what an accept of the whole image would add (or skip, if unmapped)


def shown_predictions(preds: Iterable[Prediction], labels: ImageLabels, cmap: ClassMap,
                      dataset: Dataset, conf: float) -> list[Shown]:
    """The predictions at or above `conf`, strongest first, each translated and marked."""
    boxes = [line.bbox for _, line in labels.boxes]
    places: list[Prediction] = []           # the strongest prediction at each place
    out = []
    for pred in sorted((p for p in preds if p.conf >= conf), key=lambda p: -p.conf):
        covered = any(iou(pred.box, box) >= MATCH_IOU for box in boxes)
        shadowed = not covered and any(iou(pred.box, q.box) >= MATCH_IOU for q in places)
        if not covered and not shadowed:
            places.append(pred)
        out.append(Shown(pred, cmap.translate(pred.cls, dataset), not covered and not shadowed))
    return out


def _plural(n: int) -> str:
    return "1 prediction" if n == 1 else f"{n} predictions"


def accept_image(image, shown: Iterable[Shown]) -> tuple[Intent | None, int]:
    """The image's missing predictions as one intent, and how many of them it skipped for
    being unmapped."""
    missing = [s for s in shown if s.missing]
    ops = tuple(AddBox(s.cls, s.pred.box) for s in missing if s.cls is not None)
    unmapped = len(missing) - len(ops)
    return (Intent(Path(image), ops, f"accept {_plural(len(ops))}") if ops else None), unmapped


def accept_one(image, shown: Shown) -> Intent | None:
    """One prediction the user chose, covered or not; never an unmapped one."""
    if shown.cls is None:
        return None
    return Intent(Path(image), (AddBox(shown.cls, shown.pred.box),), "accept a prediction")


@dataclass(frozen=True)
class QueueAccept:
    intents: tuple[Intent, ...]
    boxes: int          #: predictions the intents add
    uninferred: int     #: images with no row: skipped
    unmapped: int       #: missing predictions skipped for an unmapped class
    read_only: int      #: images whose label file cannot be edited: skipped


def plan_queue_accept(entries: Iterable[ImageEntry], labels_of: Callable[[Path], ImageLabels],
                      preds_of: Callable[[ImageEntry], list[Prediction] | None], cmap: ClassMap,
                      dataset: Dataset, conf: float,
                      cancelled: Callable[[], bool] = lambda: False) -> QueueAccept | None:
    """What accepting the missing predictions across these images would do. Reads only, so
    it runs on a worker; None when cancelled part-way."""
    intents, boxes, uninferred, unmapped, read_only = [], 0, 0, 0, 0
    for entry in entries:
        if cancelled():
            return None
        preds = preds_of(entry)
        if preds is None:
            uninferred += 1
            continue
        labels = labels_of(entry.path)
        if not labels.editable:
            read_only += 1
            continue
        intent, skipped = accept_image(entry.path, shown_predictions(preds, labels, cmap, dataset, conf))
        unmapped += skipped
        if intent is not None:
            intents.append(intent)
            boxes += len(intent.ops)
    return QueueAccept(tuple(intents), boxes, uninferred, unmapped, read_only)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_assist.py`
Expected: 8 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 584 passed.

```bash
git add src/deeplabeling/core/assist.py tests/core/test_assist.py
git commit -m "core: what an accept adds: missing predictions, the strongest speaking for each place" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: One edit across many images

**Files:**
- Modify: `src/deeplabeling/core/editor.py` (replaced whole)
- Test: `tests/core/test_batch.py`

**Interfaces:**
- Consumes: `LabelStore.apply` and `LabelStore.restore(edit, undo=True)`; `Edit`, `FileChange`, `Intent` and `Refused`; `History.push`.
- Produces in `deeplabeling.core.editor`:
  - `EditBatch`, with `.apply(intents)` and `.finish() -> Edit | None`:
    - `.apply` writes one chunk and reports that chunk's images. On a failed write it puts back every file the batch wrote, re-raises `Refused`, and the batch is spent.
    - `.finish` pushes one edit that marks nothing.
  - `Editor.batch(description) -> EditBatch`;
  - `Editor.apply_many(intents, description) -> Edit | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_batch.py`:

```python
"""One edit across many images, written a chunk at a time
(docs/design/2026-10-05-model-assist.md#accepting)."""

import pytest

from deeplabeling.core import store as store_module
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, Intent, Refused
from deeplabeling.core.editor import Editor
from deeplabeling.core.history import History
from deeplabeling.core.review import ReviewMarks
from deeplabeling.core.store import LabelStore
from fixtures import CAMA_0001, assert_only_changed, read_exact

BOX = (0.5, 0.5, 0.2, 0.2)
IMAGES = ("camA/0001.jpg", "camA/0003.jpg", "camA/0004.JPG", "camB/0001.jpg")


class Recorder:
    def __init__(self):
        self.labels, self.history = [], 0

    def labels_changed(self, images):
        self.labels.append(images)

    def history_changed(self):
        self.history += 1


@pytest.fixture
def rec():
    return Recorder()


@pytest.fixture
def editor(ds, tmp_path, rec):
    dataset = Dataset.open(ds.yaml)
    store = LabelStore(dataset)
    return Editor(store, History(store), ReviewMarks(tmp_path / "review.json", dataset.root),
                  on_labels_changed=rec.labels_changed, on_history_changed=rec.history_changed)


def adds(ds, names=IMAGES):
    return [Intent(ds.img(n), (AddBox(1, BOX),), "accept") for n in names]


def test_many_intents_are_one_edit_that_marks_nothing_and_undoes_as_one(editor, ds):
    before = ds.snapshot()
    edit = editor.apply_many(adds(ds), "accept 4 predictions on 4 images")
    assert len(edit.changes) == 4 and edit.description == "accept 4 predictions on 4 images"
    assert editor.history.depth == 1 and editor.review.count() == 0
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.500000 0.500000 0.200000 0.200000\n"
    editor.undo()
    assert_only_changed(before, ds.snapshot(), set())       # 0003 and 0004 had no file: gone again


def test_chunks_written_one_after_another_are_still_one_edit(editor, ds, rec):
    batch = editor.batch("accept")
    batch.apply(adds(ds, IMAGES[:2]))
    batch.apply(adds(ds, IMAGES[2:]))
    assert rec.history == 0 and len(rec.labels) == 2        # each chunk is shown as it lands
    edit = batch.finish()
    assert len(edit.changes) == 4 and editor.history.depth == 1 and rec.history == 1


def test_a_write_failing_partway_puts_back_every_file_already_written(editor, ds, rec, monkeypatch):
    before = ds.snapshot()
    batch = editor.batch("accept")
    batch.apply(adds(ds, IMAGES[:2]))
    real, calls = store_module.write_atomic, []

    def failing(path, data):
        calls.append(path)
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", failing)
    with pytest.raises(Refused, match="No space left on device"):
        batch.apply(adds(ds, IMAGES[2:]))
    monkeypatch.setattr(store_module, "write_atomic", real)
    assert_only_changed(before, ds.snapshot(), set())
    assert editor.history.depth == 0 and set(rec.labels[-1]) >= {ds.img(n) for n in IMAGES[:3]}
    with pytest.raises(RuntimeError):
        batch.apply(adds(ds, IMAGES[:1]))                   # a failed batch is spent


def test_an_image_written_twice_undoes_to_what_it_was_first(editor, ds):
    batch = editor.batch("accept")
    batch.apply(adds(ds, IMAGES[:1]))
    batch.apply([Intent(ds.img(IMAGES[0]), (AddBox(2, (0.2, 0.2, 0.1, 0.1)),), "accept")])
    edit = batch.finish()
    assert len(edit.changes) == 1
    editor.undo()
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_a_batch_that_changed_nothing_records_nothing(editor, ds, rec):
    batch = editor.batch("accept")
    batch.apply([])
    assert batch.finish() is None and editor.history.depth == 0 and rec.history == 0
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_batch.py`
Expected: 5 failed. They fail on `AttributeError: 'Editor' object has no attribute 'batch'` (and `apply_many`).

- [ ] **Step 3: Write the batch**

Replace `src/deeplabeling/core/editor.py` with:

```python
"""The GUI thread's one way to change labels (docs/design/2026-10-04-app-foundation.md#edits).

An applied edit is written by the store, recorded in the history and marks its
image reviewed; the listeners hear which images changed. An edit across many images
(accepting predictions over a queue) is written in chunks by an EditBatch and recorded
as one edit that marks nothing (docs/design/2026-10-05-model-assist.md#accepting).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from .edits import Edit, FileChange, Intent, Refused
from .history import History
from .review import ReviewMarks
from .store import LabelStore


class Editor:
    def __init__(self, store: LabelStore, history: History, review: ReviewMarks, *,
                 on_labels_changed: Callable[[tuple[Path, ...]], None] | None = None,
                 on_history_changed: Callable[[], None] | None = None):
        self.store = store
        self.history = history
        self.review = review
        self._labels_changed = on_labels_changed or (lambda images: None)
        self._history_changed = on_history_changed or (lambda: None)

    def apply(self, intent: Intent) -> Edit | None:
        """Write, record and mark. On Refused nothing has changed."""
        edit = self.store.apply(intent)
        if edit is None:
            return None
        self.history.push(edit)
        self.review.mark(self.store.dataset.entry(intent.image).rel)
        self._labels_changed(edit.images)
        self._history_changed()
        return edit

    def batch(self, description: str) -> EditBatch:
        """An edit across many images, written a chunk at a time, recorded at finish()."""
        return EditBatch(self, description)

    def apply_many(self, intents: Iterable[Intent], description: str) -> Edit | None:
        """Apply intents across many images as one edit that marks nothing."""
        batch = self.batch(description)
        batch.apply(intents)
        return batch.finish()

    def undo(self) -> Edit | None:
        try:
            edit = self.history.undo()
        finally:
            self._history_changed()     # a refused undo still dropped an edit
        if edit is not None:
            self._labels_changed(edit.images)
        return edit

    def redo(self) -> Edit | None:
        try:
            edit = self.history.redo()
        finally:
            self._history_changed()
        if edit is not None:
            self._labels_changed(edit.images)
        return edit


class EditBatch:
    """One edit across many images. Each chunk is written at once, on the owner thread,
    and its images reported; finish() records the whole as one edit and marks nothing.

    If a write fails, every file the batch has written gets its before-bytes back, the
    batch is spent, and nothing is recorded: a failed batch leaves no half.
    """

    def __init__(self, editor: Editor, description: str):
        self._editor, self._description = editor, description
        self._changes: dict[Path, FileChange] = {}      # by label file: first before, last after
        self._images: dict[Path, None] = {}
        self._spent = False

    def apply(self, intents: Iterable[Intent]) -> None:
        if self._spent:
            raise RuntimeError("this batch is finished or failed")
        store, touched = self._editor.store, []
        try:
            for intent in intents:
                edit = store.apply(intent)
                if edit is None:
                    continue
                for change in edit.changes:
                    first = self._changes.get(change.path)
                    self._changes[change.path] = FileChange(
                        change.path, change.before if first is None else first.before, change.after)
                for image in edit.images:
                    self._images[image] = None
                    touched.append(image)
        except Refused as e:
            self._spent = True
            self._roll_back(e)
        if touched:
            self._editor._labels_changed(tuple(touched))

    def _roll_back(self, cause: Refused) -> None:
        written = self._edit()
        if written is not None:
            try:
                self._editor.store.restore(written, undo=True)
            except Refused as e:
                raise Refused(f"{cause}; putting back what was written failed too: {e}") from cause
            finally:
                self._editor._labels_changed(written.images)
        raise cause

    def _edit(self) -> Edit | None:
        if not self._changes:
            return None
        return Edit(tuple(self._changes.values()), tuple(self._images), self._description)

    def finish(self) -> Edit | None:
        """Record what was written as one edit; None when nothing changed."""
        if self._spent:
            raise RuntimeError("this batch is finished or failed")
        self._spent = True
        edit = self._edit()
        if edit is not None:
            self._editor.history.push(edit)
            self._editor._history_changed()
        return edit
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_batch.py tests/core/test_history.py`
Expected: 19 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 589 passed.

```bash
git add src/deeplabeling/core/editor.py tests/core/test_batch.py
git commit -m "core: one edit across many images, written in chunks, put back whole on failure" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The real model, and the docs

**Files:**
- Modify:
  - `docs/knowledge/caches.md` (the new store);
  - `docs/knowledge/environment.md` (the GPU and the model);
  - `CLAUDE.md` (the status);
  - `docs/design/2026-10-05-model-assist.md` (the status).

**Interfaces:**
- Consumes: `UltralyticsPredictor` (Task 1).
- Produces: the docs.

- [ ] **Step 1: Run the real model once, read-only**

Run, from the repository root (so `ultralytics` resolves to the editable install):

```bash
md5sum ~/.config/Ultralytics/settings.json
PYTHONPATH=src /home/sonnn/miniconda3/bin/python3 - <<'EOF'
import time
from pathlib import Path
from deeplabeling.core.inference import ModelError, UltralyticsPredictor
runs = Path("/home/sonnn/Documents/ultralytics/runs")
images = sorted(Path("/home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle").rglob("*.jpg"))[:64]
t = time.perf_counter()
p = UltralyticsPredictor(runs / "detect/backup/yolo26n_vehicle/weights/best.pt")
print(f"loaded in {time.perf_counter() - t:.1f} s: {p.key} {p.names}")
t = time.perf_counter(); p.predict(images[:1]); print(f"first prediction {time.perf_counter() - t:.1f} s")
t = time.perf_counter()
for i in range(0, 64, 8):
    p.predict(images[i:i + 8])
print(f"a pass: {64 / (time.perf_counter() - t):.0f} images/s")
try:
    UltralyticsPredictor(runs / "classify/helmet_binary/weights/best.pt")
except ModelError as e:
    print("refused:", e)
EOF
md5sum ~/.config/Ultralytics/settings.json
```

Expected:
- the model loads in about 2 s with 7 classes, and the first prediction takes a few seconds;
- a pass runs at ≥ 20 images/s (42 on 2026-10-05);
- the classifier is refused with `best.pt is a classify model, not a detection model`;
- the two md5 sums are equal.

A pass under 20 images/s is a finding: profile it, and record the measured value in `environment.md`.

- [ ] **Step 2: Update the knowledge and the status**

In `docs/knowledge/caches.md`, replace:

```markdown
  ([environment.md](environment.md#disk)). Which models it holds:
  [datasets.md](datasets.md#models-in-the-legacy-prediction-cache).

## Reading during a dataset pass
```

with:

```markdown
  ([environment.md](environment.md#disk)). Which models it holds:
  [datasets.md](datasets.md#models-in-the-legacy-prediction-cache).

### DeepLabeling's store

`src/deeplabeling/core/predstore.py::PredictionStore` keeps the legacy store's rules — a
row per `(model, image)`, the model key, the floor, raw model ids — with three changes
([the slice 2 spec](../design/2026-10-05-model-assist.md#the-prediction-store)):

- one file per dataset root, `predictions.sqlite` beside `dataset.json`, and the image is
  its dataset-relative path;
- the stamp is `(size, mtime_ns)`, not the integer mtime;
- boxes are normalised `(cls, cx, cy, w, h, conf)`, not pixels, so a read needs no image
  size.

A file that cannot be read is set aside, as `dataset.json` is, and the store starts empty.

## Reading during a dataset pass
```

In `docs/knowledge/environment.md`, replace:

```markdown
Owns: the Python environment, which `ultralytics` gets imported, the OpenCV and setuptools
installs, and disk space.
```

with:

```markdown
Owns: the Python environment, which `ultralytics` gets imported, the GPU, the OpenCV and
setuptools installs, and disk space.
```

The new section takes **today's measured values** from Step 1, in place of the 2026-10-05 ones shown.

In `docs/knowledge/environment.md`, replace:

```markdown
## OpenCV
```

with:

```markdown
## The GPU and the model

- A GTX 1660 SUPER with 6 GB; torch 2.5.1+cu121 sees it (2026-10-05; check with
  `nvidia-smi` and `python3 -c "import torch; print(torch.cuda.is_available())"`).
- Measured 2026-10-05 with `runs/detect/backup/yolo26n_vehicle/weights/best.pt` on
  pvn-vehicle's 2592×1944 frames:
  - loading the model takes 1.7 s, and its first prediction 3.6 s more while it warms up;
  - decoding a frame takes 22 ms, which capped a pass at about 20 images/s whatever the
    batch size;
  - decoding each batch of 8 on 4 threads (`cv2` releases the GIL) gave 42–70 images/s.
- Importing ultralytics from this checkout leaves `~/.config/Ultralytics/settings.json`
  unchanged (its md5 was the same before and after; 2026-10-05).

**Rule:** a pass decodes in parallel and expects the first prediction to take seconds.

## OpenCV
```

In `CLAUDE.md`, replace:

```markdown
**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 (model assist) is next. The design and the plans are in
[docs/design/](docs/design/).
```

with:

```markdown
**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 (model assist) has its core built; its UI (plan 2b) is next. The design and
the plans are in [docs/design/](docs/design/).
```

In `docs/design/2026-10-05-model-assist.md`, replace:

```markdown
**Status:** design approved 2026-10-05; this written spec awaits review; not yet planned
```

with:

```markdown
**Status:** approved 2026-10-05 · plan 2a (the core) implemented; 2b (the UI) next
```

- [ ] **Step 3: Check the docs and run everything**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 589 passed.

- [ ] **Step 4: Commit**

```bash
git add docs CLAUDE.md
git commit -m "docs: the prediction store and the GPU, measured; slice 2's core is built" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short
```

Expected: `git status --short` prints nothing.
