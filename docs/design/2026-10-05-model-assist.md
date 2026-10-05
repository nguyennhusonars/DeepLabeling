# DeepLabeling — slice 2: model assist

**Status:** approved 2026-10-05 · plan 2a (the core) implemented; 2b (the UI) next
**Scope:** slice 2 of [the app foundation](2026-10-04-app-foundation.md#slices): load a
model, see its predictions beside the labels, accept them (one box, one image, or a whole
queue), infer a whole queue ahead of time, and map the model's classes onto the dataset's.
It replaces the legacy app for pre-labeling. Everything slice 1 built stays as it is,
except where this spec says so.

## Why

Pre-labeling is the fourth of the [daily workflows](2026-10-04-app-foundation.md#why): run
the model, accept its predictions, correct them. The user does all four of these:

- **looks** at predictions beside the labels while fixing them;
- **accepts one box**: a missed object on an image already labelled;
- **accepts per image**: on an unlabelled frame, takes the model's boxes, then fixes them;
- **accepts a whole queue**: every unlabelled image at once, reviewed afterwards.

The legacy app inferred the whole dataset at startup with no way to stop it, froze its GUI
on the model lock, compared raw model ids with dataset ids, re-inferred on every threshold
change, and shared one class map between every `best.pt`
([legacy-defects.md](../knowledge/legacy-defects.md)). Each of those is a rule below.

## Decisions

| Question | Decision |
|---|---|
| Where the model runs | **One inference thread in the app**, owning the model. A separate process was the alternative; the [responsiveness target](#performance-targets) is the test that would move it there |
| What accepting does to an image that has labels | **Adds only what is missing**: predictions that no existing label overlaps at IoU ≥ 0.5, of any class. Existing labels are never touched, and accepting twice adds nothing twice |
| The legacy prediction cache | **Clean break**: not read, not imported. Every model is inferred afresh into the new store |
| Which `ultralytics` | **The standard one** this checkout resolves to ([environment.md](../knowledge/environment.md#which-ultralytics-gets-imported)). Models that need the `ultralytics_sonnn` fork are out of scope |
| Accepting one box | **Double-click** the prediction |
| Review marks | Accepting on the image on screen (one box, or the image's missing boxes) marks it reviewed like any edit. **Accepting across a queue marks nothing**: those images were not looked at |

## Architecture

New modules follow slice 1's split: a Qt-free core, tested headless, and a thin Qt shell.

```
src/deeplabeling/core/
  inference.py   Predictor (the interface); UltralyticsPredictor, which imports ultralytics
                 only when a model is loaded
  predstore.py   the prediction store (SQLite)
  classmap.py    model class names → dataset class names
  assist.py      which predictions are missing from the labels; accept intents
src/deeplabeling/ui/
  model.py       the inference thread, the loaded model and its state, for the session
  model_chip.py  the state bar's model chip and its menu
  class_map_editor.py
```

`canvas.py` gains the predictions layer; `editing.py` gains accepting; `core/editor.py`
gains an edit across many images.

### The inference thread

- **One `QThread` owns the model** from loading to unloading. An ultralytics model is not
  safe to share across threads, and its CUDA context stays on the thread that made it.
  The GUI thread never calls the model and never waits on the thread
  ([landmine 3](../../CLAUDE.md#landmines)).
- **Requests go through one priority queue:** the image on screen first, then its
  neighbours (the next two and the previous one, as the image cache keeps them), then a
  dataset pass. A request for an image already in the store is answered from the store
  without the model.
- **A pass infers in batches of 8.** It runs on CUDA when there is one, otherwise on the
  CPU; the device is a setting. Measured 2026-10-05 on this machine: a GTX 1660 SUPER with
  6 GB, 1 GB of it in use (`nvidia-smi`).
- **Results reach the GUI by queued signal**, delivered through method slots, never
  lambdas ([environment.md](../knowledge/environment.md#pyside6-and-numpy)).
- **Loading a model takes seconds** and happens on the thread; the model chip says
  "loading…" meanwhile. A file that does not load is a notice naming the file and the
  reason, and no model is loaded.
- **A failed prediction** (CUDA out of memory, an undecodable image) fails that request
  alone, with a notice for the image on screen and a count for a pass. The model stays
  loaded.
- **Closing the dataset or the window** cancels the queue and waits at most 2 s for the
  request in flight, as slice 1's jobs do.

### The prediction store

The store follows [caches.md](../knowledge/caches.md): it infers at the floor and filters
by threshold on read ([why](../knowledge/caches.md#store-at-a-floor-and-filter-on-read)),
keeps raw model ids and translates on read
([why](../knowledge/caches.md#store-raw-model-ids)), and a dataset pass streams from it
([why](../knowledge/caches.md#reading-during-a-dataset-pass)). What is new:

- **One file per root**, `.deeplabeling/datasets/<root>/predictions.sqlite`, beside
  `dataset.json` ([state](2026-10-04-app-foundation.md#state-and-settings)). WAL mode; a
  pass commits each batch, so a cancel or a crash keeps what was done.
- **Keyed by `(model, image)`.** `model` is the weights file's `name:size:mtime`, as the
  [legacy store](../knowledge/caches.md#the-durable-store) keyed it, so a file retrained
  in place never serves the old checkpoint's rows. `image` is the dataset-relative path.
- **A row holds the image's stamp** `(size, mtime_ns)`; a row whose stamp no longer
  matches is a miss.
- **Boxes are normalised** `(cls, cx, cy, w, h, conf)`, with the model's own class id,
  against the image the model saw. `cv2.imread` honours EXIF orientation as Qt's decode
  does ([image sizes](../knowledge/caches.md#image-sizes)), so they need no conversion to
  be drawn.
- **"Never inferred" and "inferred, nothing found" stay apart** (`None` and `[]`).
- **Reads on the GUI thread** are the image on screen only. Each thread has its own
  connection.

### The class map

- **A map takes the model's class names to the dataset's class names**, or to nothing. It
  is stored in the root's `dataset.json`, keyed by the model's list of class names. Two
  models with different classes therefore never share a map: the legacy app's
  [`best.pt` defect](../knowledge/legacy-defects.md#not-fixed-in-the-legacy-app). A model
  retrained with the same classes keeps its map. The yamls of one root share it, as they
  share colours and hotkeys.
- **A new map is seeded by name**, ignoring case, spaces, dashes and underscores
  ([how](../knowledge/datasets.md#prediction-maps-and-class-groups)).
- **Translating happens on read, in every consumer.** A prediction whose class is
  unmapped is still drawn, in grey, captioned with the model's name for it and a `?`
  (`truck?`). It is never accepted ([why](../knowledge/matching.md#unmapped-classes-are-inconclusive)).
- **The editor** is a dialog: one row per model class, each with a dataset class picker
  or "not mapped", and a button that seeds by name again. A change redraws the
  predictions at once; nothing is re-inferred.
- Class groups are slice 4's.

### Accepting

- **Missing** means a prediction above the threshold, with a mapped class, that no
  existing label overlaps at IoU ≥ 0.5, of any class, and that speaks for its place: of
  predictions overlapping each other at IoU ≥ 0.5, only the most confident does, covered
  by a label or not ([why](../knowledge/matching.md#candidates-and-the-deciding-prediction)).
  A box at the frame's edge is clipped into the image, so the write path takes it.
- **Double-click a prediction** to accept it as a label of its mapped class, even one an
  existing label overlaps: the user chose that box.
- **`A`** accepts every missing prediction on the image on screen, as one edit.
- **Accept missing boxes in this queue…** (the model chip's menu) first shows what it will
  do: *N boxes on M images; K images are not inferred yet and are skipped*. It skips
  negative samples too, an empty label file being someone's decision that the image has
  no objects, and read-only label files, and counts both. It is then
  **one edit across every image it touches**, undone as one, and it marks nothing
  reviewed.
- **It is written in chunks on the GUI thread's write path**, as every edit is, so the
  label store keeps its one owner ([landmine 2](../../CLAUDE.md#landmines)); the event
  loop runs between chunks. Written at once it would freeze the window: slice 1 measured
  about 2 ms per written edit, so 45k images would take some 90 s. A modal progress dialog
  shows it and can cancel it; nothing else edits meanwhile. A cancel keeps the chunks
  already written, as one edit.
- **The core gains `Editor.apply_many`**, which applies a list of intents as one edit,
  marking nothing. Every file is written atomically. If a write fails partway, the files
  already written get their before-bytes back and nothing is recorded, so a failed accept
  leaves no half. A file that cannot be put back either (the disk still full) stays
  recorded as an edit, so undo puts it back once the cause is gone; it is never dropped.
  Undo is slice 1's: refused as a whole if any file changed since
  ([History](2026-10-04-app-foundation.md#history)).
- **Undo and redo of a queue accept are written in chunks too**, behind the same dialog:
  45k files undone at once would freeze the window as long as writing them at once.
  `LabelStore.restore` and `History` gain a chunked form in plan 2b.
- An accept that skips unmapped predictions says how many it skipped.

### A dataset pass

- **Infer this queue** (the model chip's menu) infers the queue's images, in queue order,
  that the store has no row for. Running it again resumes where it stopped.
- **It is cancelled** from the same menu, and the image on screen always goes first.
- **Progress shows in the model chip** (`inferring 1,234 / 45,252`). The end says how
  many were inferred and how many failed.
- Nothing is inferred unasked except the image on screen and its neighbours
  ([legacy defect](../knowledge/legacy-defects.md)).

## Window

### The predictions layer

- **Toggled by `P`**, and listed under Layers, persisted like the other layers.
- **Each prediction is drawn dashed** in its mapped class's colour (grey when unmapped),
  with its caption, the class and the confidence (`car 0.82`), on a plate **above** the
  box. Labels keep theirs inside the top edge, so the two never collide
  ([the legacy defect](../knowledge/legacy-defects.md)).
- **A prediction that is not missing is drawn faint.** What is drawn solid is exactly
  what `A` would add.
- **One confidence threshold per root**, default 0.25, never below the floor. It is set
  in the model chip, and a change redraws from the store without re-inferring.
- With the labels layer off, predictions are still shown, but none is accepted: hidden
  boxes are never acted on, and that includes what an accept compares against.

### The model chip

- **Joins the state bar:** `Model: best.pt · 7 classes · conf 0.25 · 12,430 / 45,252
  inferred`, the count being the queue's images that have a row. Without a model:
  `Model: none · load one`.
- **Its menu:** load a model…, recent models, the threshold, the class map…, infer this
  queue or cancel the pass, and accept missing boxes in this queue….
- **The last model used** is remembered for each opening and loaded again when the
  dataset opens.

### Inspector

A **Predictions** line: `5 (2 missing)`, `not inferred yet`, `loading`, or `no model`.

### Keys

| Key | Action |
|---|---|
| `P` | the predictions layer |
| `A` | accept the missing predictions on this image |
| double-click a prediction | accept it |

## Errors

| Situation | What happens | Where it shows |
|---|---|---|
| A weights file does not load | no model is loaded; the reason is named | notice strip |
| A prediction fails (CUDA out of memory, an undecodable image) | that request alone fails; the model stays loaded | notice strip (on screen), the pass's count |
| Accepting a prediction of an unmapped class | skipped, and counted | status bar |
| An accept across a queue meets a write error | every file already written is restored; nothing is recorded | notice strip |
| An accept across a queue is cancelled | the chunks already written stay, as one edit that undoes them | status bar |
| A queue accept meets images not inferred yet | they are skipped, and the confirmation says how many | dialog |

## Performance targets

Measured on `data_13class.yaml`, on this machine. A missed target is recorded with its
measured value, not quietly dropped.

| Action | Target |
|---|---|
| predictions for the image on screen, already in the store | ≤ 50 ms |
| predictions for the image on screen, not in the store | ≤ 500 ms after it is shown |
| paging while a pass runs | ≤ 100 ms, as without one: the test of the in-app thread |
| a dataset pass | ≥ 20 images/s |
| the store | ≤ 2 KB per image (the legacy store: 209 MB for 201,301 rows, about 1 KB) |

## Testing

- **Tests never import ultralytics.** A fake predictor, from the test fixtures, returns
  chosen boxes per image, counts its calls, and can be told to fail or to wait.
- **The store:** stamps make a changed image a miss; `None` and `[]` stay apart; the floor
  and the threshold; a pass commits each batch, so a cancelled one keeps its rows.
- **The class map:** seeding by name, two models with different classes never sharing a
  map, translating on read, and unmapped predictions drawn but never accepted.
- **Missing:** a prediction overlapping a label of any class is not missing; the
  threshold and the class map apply first.
- **Accepting:** double-click, `A` and the queue accept, each read back from the label
  files' bytes; the queue accept undoes to byte-identical files and marks nothing
  reviewed; a write failure partway restores every file; a cancel keeps the chunks done as
  one edit; the window keeps painting between chunks.
- **The thread:** the image on screen goes ahead of a pass; a cancel stops a pass; closing
  waits at most 2 s; the GUI never waits on a request.
- **What is visible** ([landmine 4](../../CLAUDE.md#landmines)): predictions are read back
  from `grab()`, dashed and solid or faint; their captions sit above their boxes.
- **One measurement script** runs a real model on pvn-vehicle, read-only, with app state
  in a temporary folder, for the [targets](#performance-targets).

## Out of scope

- Predictions on grid tiles.
- Find Bad and the IoU filter: slices 4 and 3. They read this slice's store.
- Class groups: slice 4.
- Models that need the `ultralytics_sonnn` fork.
- Reading or importing the legacy prediction cache.
- Removing a model's rows from the store.
