# Datasets

Owns: the pvn datasets and their yamls, prediction maps and class groups, the models in the
legacy prediction cache, the label-transfer tools, and the training fork's box-size filter.

## Where they are

- Root: `/home/sonnn/Videos/tmp_dataset/pvn-dataset/` — `pvn-vehicle`, `pvn-person`,
  `pvn-helmet-violation`, `pvn-face-attribute` and others (`ls` the root).
- Read them in place; never copy one ([environment.md](environment.md#disk)).

## pvn-vehicle

The yamls are in `/home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/`.

| yaml | Classes | `groups:` |
|---|---|---|
| `data_13class.yaml` | 13 | 7 |
| `data_7class.yaml` | 7 — the merged dataset | none |
| `data_UK_new.yaml` | 15: the 13 plus `LP_UK`, `pickup` | 8: adds `LPUK`, and `car` absorbs `pickup` |

- The 13 classes, in id order: BSD, BSV, bus_m, bus_l, bus_xl, car, human,
  twowheels_standalone, bike_with_driver, motorbike_with_driver, truck_m, truck_l,
  truck_xl.
- The 7 groups of `data_13class.yaml`, in insertion order: BSD, BSV, bus (bus_m, bus_l,
  bus_xl), car, human, motorbike (motorbike_with_driver, bike_with_driver,
  twowheels_standalone), truck (truck_m, truck_l, truck_xl).
- **Group order defines the merged model's class ids**: model class *i* is the *i*-th group
  (BSD=0 … truck=6). In `data_UK_new.yaml`, `LPUK` is the third group, so a merged UK
  model's ids differ from the 7-class model's from `bus` on.

```sh
python3 -c "import sys, yaml; d = yaml.safe_load(open(sys.argv[1])); print(d['names']); print(list(d.get('groups') or {}))" \
    /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml
```

### data_UK

- `data_UK/` uses the 15-class taxonomy (13 = `LP_UK`, 14 = `pickup`) and is deliberately
  absent from `data_13class.yaml`; a blind filesystem walk mis-maps its boxes.
- Measured 2026-10-02: 11,476 `LP_UK`/`pickup` labels in 9,525 files — classes a 13-class
  model can never predict, which is why Find Bad needs the
  [checkable-class guard](matching.md#the-checkable-class-guard).

### Counting

- Many top-level folders are copies (`check_run*`, `backup`, …). Count a split from a
  yaml's `train`/`val` lists, never with a recursive walk.
- Measured 2026-10-02 via `data_13class.yaml`: train 36,725 frames / 320,549 boxes; val
  8,527 frames / 80,800 boxes. A recursive walk finds 54,821 label files.
- Frame sizes vary; the most common measured 2026-10-02 were 1920×1080, 472×303,
  4096×2336, 2048×1365 and 3840×2160.
- Measured 2026-10-02 on every pvn-vehicle label file a recursive walk finds (54,821 files,
  including copies): all 447,027 label lines are plain 5-token boxes — pvn-vehicle alone
  never exercises the polygon and extra-column rules of
  [label-files.md](label-files.md#line-format).
- Label archives made by `dataset_transfer.sh` (see below):

```sh
find /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle -maxdepth 2 -name 'labels_*.zip'
```

## Prediction maps and class groups

Two different things, both needed with a coarse model:

| | Prediction map | Class groups |
|---|---|---|
| Is | model class id → dataset class id | sets of dataset classes that count as the same class when comparing |
| Used for | translating every prediction before it is shown, accepted or matched | whether the model "agrees" with a label in Find Bad, and which classes are checkable |
| Legacy | `legacy/yolo_labeling/core/classmap.py::PredictionClassMap`, saved per model | `class_groups`, adopted automatically from a yaml's `groups:` block |

- A new map is seeded by name: names are compared ignoring case, spaces, dashes and
  underscores (`Bus_M`, `bus m` and `busm` all match); a model class whose name matches
  nothing stays unmapped (`legacy/yolo_labeling/core/classmap.py::auto_map_by_name`).
- The 7-class model's map onto the 13 classes was {0:0, 1:1, 2:2, 3:5, 4:6, 5:9, 6:10}:
  each group onto one of its members. Without groups, a bus_l or bus_xl that the model
  calls "bus" (→ bus_m) counts as a wrong class.
- With a coarse model, every distinction inside a group is invisible to Find Bad — for the
  pvn-vehicle taxonomy that is 9 of the 13 classes.

## Models in the legacy prediction cache

Measured 2026-10-02: seven models, every one named `best.pt`, told apart only by their
`name:size:mtime` key ([caches.md](caches.md#the-durable-store)). List them, read-only:

```sh
python3 -c "
import sqlite3
db = sqlite3.connect('file:/home/sonnn/Documents/PGit/yolo_labeling/.yolo_labeling_cache/predictions.sqlite?mode=ro', uri=True)
for model, n in db.execute('SELECT model, COUNT(*) FROM preds GROUP BY model'):
    print(model, n)
"
```

What that does to their prediction maps: `_model_key` in
[legacy-defects.md](legacy-defects.md#not-fixed-in-the-legacy-app).

## Label-transfer tools

In `/home/sonnn/Documents/ultralytics_sonnn/tools/data_transfer/`:

| Tool | Does |
|---|---|
| `dataset_transfer.sh` | exports, imports and inspects label zips, with the yamls and metadata |
| `merge_label_groups.py` | 13 → 7: rewrites each class id to its group index, everything else on the line byte-identical; touches only directories the yaml names |
| `backport_merged_edits.py` | carries edits made on the 7-class labels back onto the 13-class originals |

- The backport takes three inputs — the fine originals, the merged copy exactly as the
  merge produced it, and that copy after review. A matched, unmoved box is copied
  byte-for-byte from the fine original; only added boxes and boxes moved into another
  group need a fine class (for pvn-vehicle, 641 edits became 55 decisions).
- Its matcher
  (`/home/sonnn/Documents/ultralytics_sonnn/tools/data_transfer/backport_merged_edits.py`)
  is scale-aware and tests once, pairing strongest overlap first: two boxes are the same
  box at IoU ≥ 0.5 **or** when every normalised coordinate moved ≤ the move tolerance
  (`--move-tolerance`, default 0.01). A matched pair counts as moved when that shift
  exceeds the tolerance. The script also defines a 0.95 IoU constant (`MATCH_IOU`), but
  only its unit tests use it; it is not on the pipeline's path. A fixed
  IoU 0.95 tore an 8 px box nudged 0.3 px (IoU 0.88) into delete + add, and sub-type
  defaulting then re-typed real `truck_xl` boxes.

**Rule:** a "same box" test on coordinates that went through integer pixels needs a
tolerance that does not shrink with the box.

## The training fork and its size filter

- `/home/sonnn/Documents/ultralytics_sonnn` adds `groups:` (merge classes when the dataset
  loads) and `MinBoxFilter` (`min_rel_wh`, `min_rel_area`; a scalar, or a per-class dict by
  name) in `/home/sonnn/Documents/ultralytics_sonnn/ultralytics/data/augment.py`.
  `/home/sonnn/Documents/ultralytics_sonnn/ultralytics/data/dataset.py` appends it to the
  train **and** the val transforms whenever either key is set, in the train args or the
  data yaml.
- It runs after all augmentation and normalises by the augmented output image: a box is
  kept only if its relative width and height are both ≥ the threshold (and its relative
  area ≥ `min_rel_area`). Label files are untouched.

Consequences:

1. **The cut differs between train and val.** Training uses the square mosaic canvas with
   scale jitter s ∈ [0.5, 1.5]. Validation uses rect batches whose sides are
   ceil(shape · imgsz/stride + 0.5) · stride (`BaseDataset.set_rectangle`, pad 0.5 for
   val), so at imgsz 640 a landscape 1080p frame becomes 640×360 padded to 672×384. At
   t = 0.01 on 1080p, training cuts at a height of 1.78%/s of the frame (1.19%–3.56% across
   s); validation at about 1.07% of the height and 1.05% of the width.
2. **Dropped boxes become background**, not ignored: training is told those objects are not
   there.
3. **The validator does not filter predictions.** Val drops ground truth below the cut but
   keeps every prediction, so correct detections of dropped boxes score as false positives.

Measured 2026-10-02 with `size_cut_sim.py`: with the same 1% in train and val, 3.8% of the
boxes val scores are trained as background in more than half their samples (22.1% for BSD,
20.9% for BSV), and val drops 4,700 of its boxes ([counted above](#counting)). Training at
0.5% with val at 1% drops 1.9% of training boxes and starves 0% of the scored ones. The
`dataset-analysis` skill's `size_cut_sim.py` computes this.

**Rule:** a box-size question about training is answered by simulating the fork's pipeline,
not by measuring boxes against the original frame.
