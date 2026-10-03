# YOLO Labeling Tool — Specification

A desktop GUI for creating, auditing and mass-correcting YOLO-format object-detection
annotations. Beyond drawing boxes, most of it is dedicated to **label quality assurance
at dataset scale**: filtering tens of thousands of images, reviewing hundreds of crops
of one class at a time, bulk-reclassifying, and scanning for suspicious ground truth
with a model.

---

## 1. Invocation

```bash
cd tools
python -m yolo_labeling                                   # pick folders in the Setup tab
python -m yolo_labeling -i IMAGES -l LABELS               # flat folder pair
python -m yolo_labeling -y data.yaml                      # multi-folder dataset
python -m yolo_labeling -y data.yaml -m yolo11n.pt        # with an assist model
```

| Flag | Meaning |
|---|---|
| `-i, --image-folder` | Directory of images (non-recursive) |
| `-l, --label-folder` | Directory of `.txt` labels; inferred if omitted |
| `-y, --yaml-path` | `data.yaml` — supplies class names and multiple image roots |
| `-m, --model-path` | `.pt` weights for assistive predictions |

Class names come from `data.yaml` when given, otherwise from `class_config.json`.

---

## 2. Package layout

```
yolo_labeling/
├── pyproject.toml       makes this directory installable as `yolo_labeling`
├── __main__.py          argparse + Tk root + mainloop
├── app.py               YOLOLabelingTool: lifecycle, canvas, drawing, navigation, label I/O
├── core/                no tkinter, no global state — unit-tested in isolation
│   ├── geometry.py      IoU, YOLO<->pixel conversion, box normalisation
│   ├── labelio.py       LabelLine, parsing, byte-preserving rendering, ATOMIC writes
│   ├── paths.py         LabelPathResolver — the single image->label mapping
│   ├── classmap.py      model class id -> dataset class id translation
│   ├── draw.py          plated captions + per-layer anchoring
│   ├── predcache.py     durable SQLite prediction cache
│   ├── crops.py         review-crop compositor (context + both boxes)
│   ├── badscan.py       what predictions say about one label (scan + IoU filter)
│   ├── ranges.py        validating the numeric ranges typed into panels
│   ├── imagetype.py     image-format sniffing (replaces imghdr, gone in 3.13)
│   └── reviewmarks.py   which images have been gone through
├── ui/                  GUI mixins; `self.*` resolves through the MRO
│   ├── crop_review.py   crop-review window + background bad-annotation scan
│   ├── classes.py       class registry, hotkeys, colours, groups
│   ├── filters.py       working-set filtering, label/prediction lookup
│   ├── dialogs.py       crop export, Qwen import, bad scan, bulk reassign
│   ├── session.py       per-session labeling telemetry
│   ├── stats.py         dataset statistics + matplotlib charts
│   └── batch.py         grid/batch browsing
└── tests/               702 tests (508 headless + 194 GUI)
```

`ultralytics` and `matplotlib` are imported lazily, at the point of use. Importing the
package costs ~0.1 s rather than ~1.6 s.

---

## 3. Keyboard and mouse

### Canvas
| Input | Action |
|---|---|
| Left drag | Draw a new box |
| Right click | Select a box or prediction |
| Double click | Re-draw the selected box |
| Drag an edge/corner | Resize |
| Wheel / `Button-4`/`5` | Zoom, anchored on the cursor |
| Motion | Crosshair + edge-hover cursor |

### Global
| Key | Action |
|---|---|
| `s` | Save labels |
| `←` / `→` | Previous / next image |
| `Delete` | Delete selected box |
| `Return` | Accept selected prediction |
| `a` | Accept predictions — whole page in batch view (confirmed), current image otherwise |
| `d` | Delete current image **and its label file** (no confirmation) |
| `Ctrl+V` | Paste boxes from the clipboard |
| `Ctrl+Z` / `Ctrl+Y` / `Ctrl+Shift+Z` | Undo / redo |
| `f` | Fit image to window |
| `+` `=` `KP_Add` / `-` `KP_Subtract` | Zoom in / out |
| `P` / `L` / `U` | Toggle predictions / labels / user-box layers |
| `T` | Toggle box captions (they can cover a small object) |
| `k` | Toggle reviewed — whole page in grid view, current image otherwise |
| `Escape` | Clear selections |
| `0`–`9`, `KP_0`–`KP_9` | Assign class by hotkey |
| `?` or `h` | Shortcut help |

All hotkeys are suppressed while a text entry has focus, so typing in a filter box
cannot trigger `d` or `s`.

---

## 4. Data formats

### `.yolo_labeling_cache/predictions.sqlite` — durable prediction cache
```
preds(model TEXT, img TEXT, size INT, mtime INT, floor REAL, boxes TEXT)
PRIMARY KEY (model, img)
```
`boxes` is JSON: `[[cls, x1, y1, x2, y2, conf], ...]` in **model** class ids, at
`predcache.CONF_FLOOR` (0.10), capped at the strongest 100 per image.

Two deliberate choices make one row serve every consumer:

* **Store at a floor, filter at read.** The scan at 0.40 and the canvas at 0.25
  share a row; moving the threshold re-filters instead of re-inferring.
* **Store raw, translate at read.** Class mapping is a view, so editing the map
  re-derives from cache. It also preserves the distinction between an *unmapped*
  prediction (inconclusive) and *no* prediction, which `PredictionClassMap.apply`
  erases by dropping unmapped boxes.

`model` is `name:size:mtime`, so retraining in place invalidates the rows. A row
is valid only while the image's own size and mtime still match.

The directory is regenerable and git-ignored.

### `review_state.json` — which images have been gone through
Written beside the dataset's `data.yaml`.
```json
{ "version": 1, "marks": { "camA/images/0001.jpg": 1757400000 } }
```
Keys are **dataset-relative POSIX paths**, unlike every other store here, which
keys on the absolute path. Review progress represents days of work, so it has to
survive the dataset being copied or opened from a different working directory —
an absolute key would not. Images outside the root fall back to an absolute key
and correctly do not survive a move, because neither do they.

An image counts as reviewed as soon as it is opened, on `k`, or on a successful
save. Grid pages mark every visible tile the same way. `k` is therefore mostly
used to take something back *off* the reviewed list. Writes are debounced and
atomic, and honour `--dry-run`.

### Label `.txt` — one object per line
```
<class_id> <cx> <cy> <w> <h>              # bounding box, normalized 0..1
<class_id> <x1> <y1> <x2> <y2> ...        # segmentation polygon (>= 3 points)
<class_id> <cx> <cy> <w> <h> <conf>       # auto-labeled, with confidence
```
Unparseable lines are preserved verbatim. Polygons and extra columns survive editing —
only lines the user actually changed are re-serialized. An empty file is a valid
**negative sample** and is never deleted implicitly.

### `class_config.json`
```json
{ "0": {"name": "person", "color": [0, 255, 0], "hotkey": "1"} }
```

### `data.yaml`
```yaml
path: /datasets/vehicle
train: [camA/images, camB/images]
val:   [val/images]
nc: 4
names: [person, car, bus_m, bus_l]
```

### Label-path resolution
1. an explicit `--label-folder`;
2. the **longest** matching per-folder mapping from `data.yaml`;
3. convention — `…/images/x.jpg` pairs with `…/labels/x.txt`, otherwise a `labels`
   directory beside or above the image, preferring one that exists.

Reading and writing always resolve identically.

---

## 5. Features

**Annotation** — draw, resize by edge or corner, delete, reassign class by hotkey,
copy/paste, per-image undo/redo (history never crosses an image boundary).

**Navigation** — sequential, jump-to-index, filtered subsets, batch grid (up to 5×5).

**Filtering** — by class presence/absence, box area, **relative box width/height (% of
image)**, filename substring, **review state**, label↔prediction IoU, and intra-image
overlapping boxes. Overlap has a scope: **different classes** (one object labelled as two
things), **same class** (one object labelled twice -- the duplicate-box error) or **any**.
The red highlighter follows the same scope, so what the filter selects is always what the
highlighter draws. A highlighted box's caption carries **how many boxes are stacked on it**
(`L bus x2`), and the corner overlay gains `!N` for the whole frame: two identical label
lines draw two identical rectangles, so without a count the editor cannot show the very
error the filter selected the image for. The count is per box, not per group — in a chain
A-B-C where A and C do not touch, A reads `x2` and B reads `x3`. Scope and threshold are
**persisted**; their defaults are a far broader query than the one most sessions end on
(measured on a 55k-image dataset: 123 images flagged at different-class @ 0.5 against 8 at
same-class @ 0.9), and silently reverting made repeat runs look unreliable. Overlap IoU
is a **range**: `0.99–1.00` isolates exact duplicates (safe to clean in bulk), `0.5–0.9`
partial overlaps (often legitimate occlusion); a max below 1 hides exact duplicates from the
highlight too, deliberately.

The **Label/Prediction IoU** filter has a direction — *labels the model does not see*,
*predictions with no label*, or *either* — a matching IoU, and its own confidence range,
independent of the display slider. *Predictions with no label* finds objects nobody
labelled, including frames with **no label file at all**. It reads the durable prediction
cache without promoting it into memory; a never-inferred image is counted as "not
inferred" in the result line rather than passed, while an inferred-but-empty one is
evaluated. Unmatched labels match against predictions of **any** class, mapped or not —
it is geometry; unmatched predictions count **mapped** classes only. It shares its
matching with Find Bad Annotations (`core/badscan.py`), so "labels the model does not see"
selects an image exactly when a not-an-object scan would flag its label.

Every range is inclusive, and a reversed range is **refused by name at Apply** rather than
swapped while being typed. The result line reads "Found: N/M" for every label-based
filter. Scope, both overlap bounds and every IoU-filter setting persist. Relative size
is what separates a full-frame box from a thin wide
sliver; area alone cannot, and those are different annotation mistakes. Every enabled
per-box condition must hold on the *same* box.

**Review tracking** — an image is marked reviewed as soon as it is opened, by `k`, or by
saving it. Grid pages mark every visible tile. The Filters tab shows
coverage (`12,430 of 46,049 reviewed`) and can show only reviewed or only not-yet-reviewed
images. Unlike every other filter, this one does **not** require label files — an image
with no `.txt` at all is exactly what "not yet reviewed" should surface.

**Model assist** — predictions are computed lazily for the image being viewed and cached
durably (§4). Accept one, one class, every visible class, or a whole batch page. The
model's class ids are translated to dataset ids via a per-model map (`core/classmap.py`),
seeded by name matching and editable from the Setup tab.

**Dataset inference** — Setup → *Dataset inference* shows how much of the working set has
been inferred and runs a cancellable background pass over the rest. Already-cached images
are skipped, so it is safe to stop and resume. *Clear* discards the cache for the loaded
model.

Inference never blocks the GUI thread: a lazy prediction that would have to wait on a
running scan defers and retries instead, because Tk's event loop — and therefore every
progress readout — lives on that thread.

**Crop review** — page through crops of a single class and reclassify or delete with one
keystroke. A bad-annotation crop shows the labelled box **and the model's box** inside a
margin of context: a class disagreement you used to have to take on trust is now two
rectangles you can compare, and a wrong *geometry* is distinguishable from a wrong *class*.

Every action here writes straight to disk, so each one is verified first: the line is
matched on class **and** box geometry, relocated if it moved (sibling deletes and
main-window saves both renumber lines), and **refused** if the box is gone or if two lines
match ambiguously. A refusal flags the crop rather than writing — and says so on the
selection line, because the status bar is overwritten every 150ms while a scan streams.
Closing with findings still pending asks first; they are not persisted anywhere. Fed either by a class filter or by a background scan that flags ground truth a
model disagrees with.

**Find bad annotations** — scans a chosen scope and reports labelled boxes the model
contradicts, in three kinds: **wrong class** (the model sees a different class there — fix
by reassigning), **probably not an object** (no prediction matches) and **weakly seen**
(the model agrees, but only below a cutoff — often occluded, truncated or tiny). It
examines only boxes that already exist; unlabelled objects are found by the IoU filter.

Confidence is a shared **floor** plus a per-kind **ceiling**, never one band applied to
predictions: an upper bound that removed strong predictions before matching would report
a box the model sees at 0.95 as "not an object". The floor ("seen when confidence ≥")
defines what the model sees for every kind, which is also why a kind's findings never
depend on which other kinds are on. Wrong class is reported while the model's confidence
is at most its ceiling; *not an object* has a band on the **nearest** box's IoU — near 0
is a stray box, higher is a badly drawn one, and the crop then draws the model's box.

The deciding prediction for a label is its most **confident** match, not its best
overlapping one: per-class NMS routinely yields `car 0.80` plus a slightly better aligned
`truck 0.35` on one car, and deciding on overlap flipped the verdict on a 0.02 IoU
difference. If the most confident match has an unmapped class the label is inconclusive.
A label whose class the model cannot emit (directly or through its group) is never
reported as not an object — its silence proves nothing — and the status line counts how
many were skipped. Every dialog setting persists, including through a yaml launch.

Results are ordered by a **Sort** picker in the review window, defaulting to *Worst image
first*: images are ranked by their single worst entry and each image's crops are kept
adjacent, so a frame with three problems is fixed in one visit rather than three. *Worst
box first* ranks every crop independently, and *File order* walks the dataset by path.

Within any order, kind stays the primary severity axis: the two scores are not the same
quantity — one is model confidence, the other is how little the model saw — so a single
mixed ranking by score would be meaningless.

Scope is the filtered set or all loaded images, and the dialog states how many images are
already cached before you commit. A confidence below the cache floor cannot be served from
the store and silently re-runs the model over everything, so that asks for confirmation.
Class comparison goes through the
prediction map, and `class_groups` (adopted automatically from `data.yaml`'s `groups:`
block) relaxes it so a coarse model is not asked to distinguish sub-types it cannot see.
An optional GT-class/predicted-class pair filter answers "show me every A the model calls
B"; naming both sides overrides the group relaxation. Results stream in with a progress
bar, rate and ETA.

**Bulk reassign** — rewrite one class to another across the current image, the filtered
set, or the whole dataset.

**Qwen workflow** — export every box as a crop plus `manifest.json`, verify externally
with `qwen3_class_verify.py`, re-import the verdicts as a review queue.

**Statistics** — class balance, box-size distributions, per-folder counts, six charts.

---

## 6. State

Persisted: `class_config.json` (classes, colours, hotkeys, groups), `review_state.json`
(which images have been gone through) and the label files.
In-memory only: undo history, caches, filters, zoom, session telemetry.

---

## 7. Testing

The app has no dependency on the ultralytics repository it lives in. Its only
link is a lazy `from ultralytics import YOLO` when a model is loaded, which uses
whichever ultralytics is installed -- so models trained with a fork's custom
modules need that fork installed. To run it outside this repository:

```bash
pip install -e .[test]          # from this directory; add [model] for predictions
yolo-labeling -y path/to/data.yaml -m path/to/best.pt
```

`class_config.json` and `.yolo_labeling_cache/` live in the package directory,
next to `app.py` (`app.STATE_DIR`), wherever the app is launched from. Install
with `-e` so that directory is this checkout -- a plain `pip install .` would
put them in site-packages, where an upgrade wipes them. Review marks live with
the dataset.

```bash
cd tools/yolo_labeling
pytest                          # 508 headless tests, ~4 s
xvfb-run -a pytest -m gui       # 194 GUI tests
```

`tests/fixtures.py` generates a dataset covering multi-folder layouts, same-stem
collisions across folders, `startswith` prefix collisions, polygons, extra columns,
malformed lines, unreadable images, uppercase extensions, EXIF rotation, unicode names
and a label with no image.

The load-bearing assertion is `assert_only_changed(before, after, expected)`, which
sha256s every label file and fails if anything changed that shouldn't have. Almost every
data-loss bug in this tool's history was "a file changed that nobody asked to change".

---

## 8. Fixed in the 2026-08 refactor

Fourteen catalogued defects, each with a regression test:

| # | Defect |
|---|---|
| 1 | `user_boxes` leaked across 9 of 12 navigation paths, writing one image's boxes into another's label file |
| 2 | An unreadable image produced an empty box list, and saving then **deleted** a valid label file |
| 3 | All label writes were truncate-in-place; a crash mid-write left a 0-byte file |
| 4 | Opening a segmentation dataset and pressing `s` destroyed every polygon |
| 5 | Six divergent label-path resolvers; load and save could disagree and silently fork the dataset |
| 6 | `startswith` matching let `/ds/set1` capture `/ds/set10/a.jpg` |
| 7 | Crop-export filename collisions across folders |
| 8 | Stale `line_idx` rewrote a different object than intended |
| 10 | Deleting every box removed the file instead of emptying it |
| 12 | Saved files had no trailing newline, so appends silently corrupted the last line |
| 13 | One non-numeric class id aborted parsing mid-file; the next save truncated everything after it |
| 14 | `int()` truncation shrank every box by up to a pixel per save cycle |
| 15 | No `[0,1]` clamping, so a paste across image sizes wrote values like `2.73` |

Performance: startup inference (14 min – 3.5 h dead window) is now lazy per image;
`get_label_boxes` populates its cache instead of re-parsing every file on each filter;
a periodic `gc.collect(2)` that *caused* the slowdown its comment claimed to fix was
removed; overlap detection went O(b³) → O(b²); zoom redraws coalesce; batch tiles decode
at reduced resolution and are cached.

---

## 9. Known limitations

- **Editing** a polygon re-serializes it as a bounding box. Merely opening and saving
  preserves polygons exactly; only a deliberate edit converts.
- EXIF-rotated images are handled consistently, but the on-disk labels must already match
  the rotation-applied geometry.
- Image discovery is non-recursive: one directory per configured path.
- `a` in single view and `d` (delete image) have no confirmation. Batch accept does.
- Crop-review prefetch memory is bounded by frame count, not bytes.
- Semantic-segmentation datasets are out of scope.
- Batch accept writes many files at once and is **not undoable** — the undo stack is
  per-image. The confirmation dialog is the only guard.
- Crop-review actions are not undoable either. The write guard refuses a wrong target, but
  a correct-and-unwanted reassign or delete has to be fixed by hand.
- "Mark reviewed" in the crop review is per-session and is not persisted; re-running the
  scan resurfaces everything dismissed that way.
- Nothing below `CONF_FLOOR` (0.10) exists: inference always runs at the floor, so no
  threshold below it can be answered. Both the scan dialog and the IoU filter refuse or
  clamp to it. (This line previously claimed such a threshold re-infers; it never did.)
- Deciding on the most confident match changed Wrong-class counts from earlier scans:
  fewer NMS-duplicate false hits, and a few new true ones where the confident box
  disagrees with the label.
- A yaml-launch save still overwrites the config's `prediction_maps`, `hotkeys` and
  `class_groups` with the session's state, and `_model_key` is the bare filename, so every
  `best.pt` shares one prediction map. Threshold settings are now restored on that path;
  these are not.
- Review marks belong to the yaml that defined the dataset root. Opening the same tree via
  two yamls at different depths yields two mark files with incompatible keys.
- Two instances open on one dataset overwrite each other's review marks; last writer wins.
  The same weakness `class_config.json` already has.
- Marking is immediate, so paging through the grid marks every page you pass, and
  re-applying a filter marks the first image it lands on. The working set is a snapshot;
  re-apply to refresh it, and use `k` to take a page back off the list.
- Inference coverage counts rows for the loaded model, which may exceed the current
  filtered set. Verifying each row's mtime would cost more than the readout is worth.
- Find-bad-annotations can only check distinctions the model can make. With a coarse
  model, everything inside a `class_groups` entry is invisible to it — for the pvn-vehicle
  taxonomy that is 9 of 13 classes.
- `_collect_statistics` and the scan's entry *producers* still resolve label paths with
  `startswith` rather than `LabelPathResolver`. The review window's **writers** no longer
  do, and the write guard turns any producer/consumer disagreement into a refusal rather
  than a wrong write.
- The scan reads `parts[1:5]` with no arity check, so a segmentation polygon's first two
  points are misread as its box. The crop is then wrong — but the write guard compares
  against `LabelLine.bbox`, which computes a polygon's true extent, so such an entry is
  refused rather than written.
- `labels_cache` is checked against each label file's `(mtime_ns, size)` before it is
  trusted, so an import underneath a running app is noticed. `_count_class_labels` reads
  the same cache without that check, so the reassign dialog's counts can lag an external
  import until the next restart. It is a displayed count, not a write path.
- `build_label_cache` still converts with `int()` truncation where every other path uses
  `round()`, so boxes it caches can be a pixel smaller on each edge. Measured across 54,821
  pvn-vehicle label files, this flips no overlap verdict at any threshold; it remains a
  latent disagreement rather than an observed one.
