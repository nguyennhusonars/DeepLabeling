# Caches

Owns: the prediction cache (what is stored, how it is keyed and read), the score cache,
label-cache freshness, how image sizes are read, and where app state lives.

The evidence is `legacy/yolo_labeling/core/predcache.py` and the read paths in
`legacy/yolo_labeling/app.py` and `legacy/yolo_labeling/ui/filters.py`.

## Store at a floor and filter on read

- Inference always runs at `legacy/yolo_labeling/core/predcache.py::CONF_FLOOR` (0.10),
  and that is what is cached, capped at the strongest
  `legacy/yolo_labeling/core/predcache.py::MAX_BOXES` (100) per image.
- Each consumer narrows the cached boxes to its own threshold on read
  (`legacy/yolo_labeling/core/predcache.py::filter_conf`). A scan at 0.40 and the canvas
  at 0.25 share one row; moving a slider re-filters instead of re-inferring.
- Below the floor nothing exists: no threshold under 0.10 can be answered from the cache.
  The legacy scan dialog (`legacy/yolo_labeling/ui/dialogs.py::DialogsMixin.show_find_bad_dialog`)
  and IoU filter (`legacy/yolo_labeling/ui/filters.py::FiltersMixin._filter_range_error`)
  refuse such a value, and restored settings are clamped up to the floor. (SPEC §5 still
  says such a threshold re-runs the model; SPEC §9 and the code say it never did.)

**Rule:** infer once at the floor; every threshold is a read-side filter; nothing below the
floor is offered.

## Store raw model ids

- Rows hold the model's own class ids. Translation through the prediction map
  ([datasets.md](datasets.md#prediction-maps-and-class-groups)) happens on read, like the
  threshold. Editing the map then re-derives from the cache instead of re-inferring, and an
  unmapped prediction stays distinguishable from no prediction at all
  ([matching.md](matching.md#unmapped-classes-are-inconclusive)).
- `legacy/yolo_labeling/core/classmap.py::PredictionClassMap.apply` **drops** unmapped
  boxes. The legacy display path uses it
  (`legacy/yolo_labeling/app.py::YOLOLabelingTool._display_predictions`); the scan and the
  IoU filter call `translate` themselves and keep unmapped boxes as `None`.

**Rule:** translate on read, in every consumer. Display and accept may drop unmapped boxes;
matching must keep them.

## The durable store

`legacy/yolo_labeling/core/predcache.py::PredictionCache` — SQLite in WAL mode, committed
incrementally so a cancel or a crash keeps the work already done.

```
preds(model TEXT, img TEXT, size INTEGER, mtime INTEGER, floor REAL, boxes TEXT)
PRIMARY KEY (model, img)
```

| Column | Holds |
|---|---|
| `model` | the weights file's `name:size:mtime` (`legacy/yolo_labeling/core/predcache.py::model_key`). Retraining in place keeps the name, so the name alone would serve the old checkpoint's predictions. |
| `img` | the image's absolute path |
| `size`, `mtime` | the image's byte size and integer mtime when inferred; a row is valid only while both still match |
| `floor` | the confidence the row was inferred at |
| `boxes` | JSON `[[cls, x1, y1, x2, y2, conf], …]` in pixels and raw model ids; coordinates rounded to 0.1 px, confidence to 3 decimals |

- A miss (`get` returns `None`) covers all of: never inferred, another model, the image
  changed on disk, or a threshold below the row's floor.
- Measured on pvn-vehicle frames: a lookup costs about 0.018 ms per image.
- The legacy store is
  `/home/sonnn/Documents/PGit/yolo_labeling/.yolo_labeling_cache/predictions.sqlite`
  (measured 2026-10-02: 209 MB, 201,301 rows). Read it in place and read-only — open it as
  `sqlite3.connect("file:<path>?mode=ro", uri=True)` — and never copy it
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

### The score cache

`src/deeplabeling/core/sharpstore.py::SharpnessStore` keeps the Blurry queue's sharpness
measures ([the Blurry spec](../design/2026-10-27-blurry.md#the-score-cache)):

- one file per dataset root, `sharpness.sqlite` beside `predictions.sqlite`; a row per image,
  served only while its `(size, mtime_ns)` stamp matches;
- a box is found by its pixel rectangle, not its label line: a class change needs no rescore,
  a moved box rescores its image;
- it holds raw measures, never ranks: ranks depend on the scope, and are made at each build;
- written on the GUI thread only, from the build's `Scored` batches — a job never writes a
  file — so a cancelled build's scores are kept.

Its connection handling, setting aside and closing are the prediction store's, shared:
`src/deeplabeling/core/sqlitefile.py::SqliteFile`. Deleting it costs one cold build.

## Reading during a dataset pass

- A pass over the dataset reads the durable store without promoting each row into the
  in-memory cache: `legacy/yolo_labeling/app.py::YOLOLabelingTool._peek_cached_predictions`
  with `promote=False`. Promoting holds about 250 B/box × 20–100 boxes × 46k images ≈
  0.2–1.1 GB.
- "Never inferred" (`None`) and "inferred, nothing found" (`[]`) are different answers. The
  legacy IoU filter counts never-inferred images as "not inferred" in its result line
  rather than passing them as clean, and evaluates inferred-but-empty ones.

**Rule:** a dataset pass streams from the durable store; memory holds only what is on
screen. An unknown answer is reported as unknown.

## Label-cache freshness

- A cached parse of a label file is trusted only while the file's `(mtime_ns, size)`
  matches the stamp taken when it was cached; an entry with no stamp is stale:
  `legacy/yolo_labeling/ui/filters.py::FiltersMixin._labels_cache_fresh`,
  `legacy/yolo_labeling/ui/filters.py::FiltersMixin._label_stamp`.
- Size alone is not enough: reassigning a class rewrites one byte and keeps the length.
- DeepLabeling stamps `(inode, mtime_ns, size, writable)`
  (`src/deeplabeling/core/store.py::LabelStore.get`): an atomic replace makes a new
  inode, so a same-size rewrite within one mtime tick is still noticed, and a chmod,
  which changes no mtime, is noticed by its writability.
- Every writer of the cache stamps its entry
  (`legacy/yolo_labeling/ui/filters.py::FiltersMixin._stamp_labels_cache`). A forgotten
  stamp is merely slow, never wrong.
- This is what notices an import or an external edit underneath the running app.

**Rule:** every read of a cached parse checks the stamp.

## Image sizes

- Read the size from the file header, honouring EXIF orientation: tag 274 values 5–8 are
  quarter turns, so for dimensions a width/height swap is the whole transform
  (`legacy/yolo_labeling/ui/filters.py::FiltersMixin._image_size`). `cv2.imread` applies
  EXIF rotation and PIL's raw `.size` does not, so without the swap the two disagree by a
  transpose on rotated phone photos.
- Measured on pvn-vehicle frames: a header read is about 0.03 ms; `cv2.imread` 3.42 ms;
  `ImageOps.exif_transpose()` decodes and rotates the whole frame, 4.51 ms — slower than
  decoding. Decoding 46k frames only to learn their sizes cost about 6 minutes per scan,
  indistinguishable from re-running the model.

- Which formats are turned depends on the decoder. Measured 2026-10-06 with orientation 6
  written into a 64×48 image: Qt's decode (the canvas's) turns a JPEG and a TIFF, and shows
  a PNG and a WebP as stored. Pillow already reports the TIFF's size as shown, so only a
  JPEG's swap is the size function's to make. Reproduce:
  `tests/ui/test_images.py::test_the_header_size_is_the_decoded_size_in_every_format`.
- Pillow's `getexif()` decodes a PNG to look for EXIF after its pixels: about 21× a header
  read on small crops, 300× on a 4000×3000 frame (2026-10-06). The EXIF a header holds is
  in `info["exif"]` once the file is opened.
- DeepLabeling's one size function is `src/deeplabeling/core/imagesize.py::image_size`;
  `src/deeplabeling/core/imagesize.py::ImageSizes` caches it for the open dataset, stamped
  like the label cache.

**Rule:** never decode an image to learn its size; one size function, header-only and
EXIF-aware, for every caller.

## Where app state lives

- In one fixed directory, never relative to the launch directory:
  `legacy/yolo_labeling/app.py::STATE_DIR` (the legacy package directory). With relative
  paths, launching from another folder silently started with no classes, hotkeys,
  prediction maps or cache, and wrote a fresh default config there.
- DeepLabeling's is `<repository>/.deeplabeling/`, or `DEEPLABELING_STATE_DIR` when set:
  `src/deeplabeling/core/state.py::state_dir`. Its layout is in the
  [app design](../design/2026-10-04-app-foundation.md#state-and-settings); the tests
  guard it with `tests/conftest.py::_real_state_untouched`.
- The legacy tests redirect it to a temporary directory for every test and fail the
  session if the real files changed:
  `legacy/yolo_labeling/tests/conftest.py::state_dir`,
  `legacy/yolo_labeling/tests/conftest.py::_real_state_untouched`.

**Rule:** state lives at one fixed path; tests point it at a temporary directory and assert
the real one is untouched.
