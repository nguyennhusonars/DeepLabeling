# Legacy defects

Owns: every known defect of the legacy app (`legacy/yolo_labeling/`) — symptom, root
cause, fix — and the rule it implies for DeepLabeling. This is the do-not-repeat list.

When porting a legacy behaviour, find it here first and port the fix, not the code it
replaced. Each rule links to the file that owns the detail; "landmine" means a
[CLAUDE.md landmine](../../CLAUDE.md#landmines).

## Fixed in the 2026-08 refactor

The legacy SPEC's §8 (`legacy/yolo_labeling/SPEC.md`). Its heading says fourteen defects,
but its table has thirteen rows, numbered 1–15 without 9 and 11, and nothing in the
snapshot mentions those two numbers. `#` is the SPEC's number; most rows are pinned by
`legacy/yolo_labeling/tests/test_bugs.py`.

| # | Symptom | Root cause | Fix | Rule for DeepLabeling |
|---|---|---|---|---|
| 1 | One image's boxes written into another image's label file | `user_boxes` was cleared on only 3 of the 12 navigation paths; the next autosave wrote the previous image's boxes at their old coordinates | cleared in the one navigation funnel, `legacy/yolo_labeling/app.py::YOLOLabelingTool.load_image` | per-image state belongs to that image's one owner and never crosses an image boundary (landmine) |
| 2 | A valid label file deleted | an unreadable image produced an empty box list, and saving then deleted the file | loading bails out on an unreadable image and saving refuses without geometry: `legacy/yolo_labeling/app.py::YOLOLabelingTool.load_labels`, `legacy/yolo_labeling/app.py::YOLOLabelingTool.save_labels` | "could not read" is never "no boxes": refuse to save, and say why |
| 3 | A 0-byte label file after a crash mid-write | every label write truncated in place | `legacy/yolo_labeling/core/labelio.py::write_label_file` | [atomic writes](label-files.md#writing) |
| 4 | Opening a segmentation dataset and pressing `s` destroyed every polygon | a 5-field parse/write pair | lines keep their raw text (`legacy/yolo_labeling/core/labelio.py::LabelLine`), and a save with no change writes nothing | [byte-preserving round trips](label-files.md#byte-preserving-round-trips) — incomplete in the legacy app, see [not fixed](#not-fixed-in-the-legacy-app) |
| 5 | Load and save disagreed and silently forked the dataset | six divergent label-path resolvers | `legacy/yolo_labeling/core/paths.py::LabelPathResolver` | [one resolver](label-files.md#one-path-resolver) — still bypassed by some legacy producers, see [not fixed](#not-fixed-in-the-legacy-app) |
| 6 | A mapping for /ds/set1 captured /ds/set10/a.jpg | `str.startswith` prefix matching | `legacy/yolo_labeling/core/paths.py::is_within` | match paths on path boundaries |
| 7 | Exported crops of same-stem images in different folders overwrote each other | crop file names built from the image stem | listed as fixed, but the snapshot's `legacy/yolo_labeling/ui/dialogs.py::DialogsMixin.show_export_crops_dialog` still names a crop `<stem>__line<NNNN>.jpg` inside its class folder, so the same line of two folders' `0001.jpg`, when it has the same class, still collides; no legacy test covers it (found by reading the code, not run) | a file name derived from an image includes what makes the image unique in the dataset (its dataset-relative path), not only its stem |
| 8 | A review action rewrote a different object than intended | a stale `line_idx` | `legacy/yolo_labeling/core/labelio.py::locate_line` | [locate before writing](label-files.md#locate-before-writing) |
| 10 | Deleting every box removed the file | delete instead of empty | `legacy/yolo_labeling/app.py::YOLOLabelingTool.save_labels` writes zero bytes | [an empty file is a negative sample](label-files.md#empty-file-is-a-negative-sample) |
| 12 | Appending silently corrupted the last line | saved files had no trailing newline | `legacy/yolo_labeling/core/labelio.py::LabelLine.render` ends every re-serialised line with `\n` | [trailing newline](label-files.md#writing) |
| 13 | The next save truncated everything after one bad line | one non-numeric class id aborted the parse mid-file | `legacy/yolo_labeling/core/labelio.py::parse_label_text` keeps such a line verbatim | [the parser never raises](label-files.md#line-format) |
| 14 | Every box shrank by up to a pixel per save cycle | `int()` truncation converting to pixels | `legacy/yolo_labeling/core/geometry.py::yolo_to_pixel` rounds | [round, never truncate](matching.md#geometry) — one legacy path still truncates, see [not fixed](#not-fixed-in-the-legacy-app) |
| 15 | Values like `2.73` written to a label file | no clamping to [0, 1] when pasting across image sizes | `legacy/yolo_labeling/core/geometry.py::pixel_to_yolo` clamps | [clamp on write](label-files.md#writing) |

## Performance fixes in the 2026-08 refactor

Also from SPEC §8, and the code comments at each fix.

| Symptom | Root cause | Fix | Rule for DeepLabeling |
|---|---|---|---|
| A dead, uncancellable window of 14 min – 3.5 h at startup | the whole dataset was inferred in the constructor, before the event loop started | inference per image, when it is shown: `legacy/yolo_labeling/app.py::YOLOLabelingTool.load_model_predictions` | never infer the dataset unasked; a dataset pass is explicit, cancellable and resumable |
| Every Apply Filters re-parsed every label file (30–90 s per click on 50k images) | `get_label_boxes` read the label cache but never wrote it | it fills the cache: `legacy/yolo_labeling/ui/filters.py::FiltersMixin.get_label_boxes` | cache parses — [stamped](caches.md#label-cache-freshness) |
| A periodic slowdown | a periodic `gc.collect(2)` caused the slowdown its comment claimed to fix | removed | measure before and after a performance change |
| Overlap detection slow on crowded frames (about 1M operations per load with 100 mutually overlapping boxes) | a list-membership test inside the inner loop: O(b³) | a dict: O(b²), `legacy/yolo_labeling/app.py::YOLOLabelingTool.detect_current_overlaps` | per-frame pairwise work stays O(b²); membership tests use sets or dicts |
| Zoom redraw storms | redraws were not coalesced | coalesced | coalesce repaints |
| Slow batch grid | every tile decoded at full resolution | reduced-resolution decode, cached: `legacy/yolo_labeling/app.py::YOLOLabelingTool._read_reduced` | decode at display size |

## Fixed in the 2026-09 and 2026-10 sessions

| Symptom | Root cause | Fix | Rule for DeepLabeling |
|---|---|---|---|
| Find Bad flagged almost every box | raw model class ids compared with dataset ids | the scan translates on read: `legacy/yolo_labeling/ui/crop_review.py::CropReviewMixin._bad_scan_worker` | [translate on read](caches.md#store-raw-model-ids); unmapped = [inconclusive](matching.md#unmapped-classes-are-inconclusive) |
| Captions overlapped, unreadable | three layers (predictions, labels, user boxes) drew same-colour bare text at one anchor | a filled plate behind every caption, and one anchor per layer — predictions above the box, labels inside its top edge, user boxes inside its bottom edge: `legacy/yolo_labeling/core/draw.py::draw_tag` | per-layer caption anchors on solid plates |
| The GUI froze during scans | the GUI thread waited on the model lock the scan worker held; `threading.Lock` is unfair, so the GUI lost the race repeatedly (measured: a 124 ms wait on a 50 ms dwell) | inference on the GUI thread is non-blocking and retries later: `legacy/yolo_labeling/app.py::YOLOLabelingTool._predict_image` (`blocking=False`), `legacy/yolo_labeling/app.py::YOLOLabelingTool._schedule_prediction_retry` | the GUI never blocks on the model: non-blocking predict plus retry (landmine) |
| The status bar and toolbar were invisible | the status line was packed after an expanding sibling and got zero height; the action row needed 1422 px in an 1100 px window; the tests asserted widget state (`StringVar`, progress value), so they passed and the user had to send a screenshot | status line packed before the grid; the unbounded selection text moved to its own row: `legacy/yolo_labeling/ui/crop_review.py::CropReviewMixin._open_crop_review_window` | assert visibility and geometry, not state (landmine; the `run-and-verify-ui` skill) |
| "Infer all" did not speed up scans | the scan decoded every image to learn its size, which cost as much as inference ([caches.md](caches.md#image-sizes)) | header-only size reads (`legacy/yolo_labeling/ui/filters.py::FiltersMixin._image_size`); the cache is asked before anything is decoded | [header-only size reads](caches.md#image-sizes) |
| The review window edited the wrong box | selection was an integer index into a list re-sorted every 150 ms during a streaming scan, so one new entry shifted every index and the next keystroke acted on a neighbour; the stored line index was trusted | selection carried by identity (`legacy/yolo_labeling/ui/crop_review.py::CropReviewMixin._crop_review_sort_entries`); lines located by class and box (`legacy/yolo_labeling/core/labelio.py::locate_line`) | select by identity; [locate by class and box, refuse if ambiguous](label-files.md#locate-before-writing) |
| Review edits flattened polygons and lost CRLF | hand-rolled non-atomic writers; text-mode reads; the main window's `_loaded_boxes` mirror was not updated, so its no-op guard failed and the next `s` re-serialised the whole file; class changes reformatted coordinates | review writers go through `labelio` (`legacy/yolo_labeling/app.py::YOLOLabelingTool._rewrite_label_line`); the main window's copies are updated (`legacy/yolo_labeling/ui/crop_review.py::CropReviewMixin._crop_review_apply_change_to_main`); class changes splice (`legacy/yolo_labeling/core/labelio.py::LabelLine.with_class`) | [one write path](label-files.md#writing); one owner of each image's labels ([design spec](../design/2026-10-02-project-init.md#sync-2--label-edits-stay-consistent)) |
| A file emptied by a review deletion vanished | two crop-review writers called `os.remove`, while their docstring claimed to match the main save | it writes zero bytes: `legacy/yolo_labeling/app.py::YOLOLabelingTool._delete_label_line` | [write zero bytes](label-files.md#empty-file-is-a-negative-sample) |
| Duplicate boxes were impossible to see | identical rectangles draw as one; the warning caption's `⚠` came out as `?` — cv2's Hershey fonts draw any non-ASCII codepoint as `?` — so it read "L bus ?" | a stack count on each box's caption: `legacy/yolo_labeling/app.py::YOLOLabelingTool.detect_current_overlaps`, `legacy/yolo_labeling/app.py::YOLOLabelingTool.display_image` | [show stack counts](matching.md#overlap-between-labels); text drawn with cv2 is ASCII only (`×` happens to render in the installed build, but Latin-1 coverage varies by build) |
| Filter results differed after a restart | settings were not persisted, and a YAML launch never called the config loader, so the next save — which a yaml `groups:` block always triggers — wrote defaults over them; the test missed it because it rebuilt the app without a yaml. The defaults are a far broader query than the usual one ([matching.md](matching.md#overlap-between-labels)) | settings persisted and restored on the YAML path too: `legacy/yolo_labeling/ui/classes.py::ClassManagementMixin._restore_saved_prefs`, `legacy/yolo_labeling/ui/classes.py::ClassManagementMixin._adopt_filter_prefs` | persist every setting; restore it on every launch path; test every launch path (landmine) |
| The panel showed 0.9 while the filter used 0.5 | a widget seeded from a literal while the logic read the restored attribute | widgets seeded from the restored attributes (`legacy/yolo_labeling/app.py::YOLOLabelingTool.setup_gui`); an entry not showing the value in force is rewritten (`legacy/yolo_labeling/ui/filters.py::FiltersMixin._read_unit_var`) | seed every widget from the value the logic reads (landmine) |
| Filters reported stale boxes after an import (export, edit elsewhere, import back) until a restart | the label cache was keyed on the path alone and never checked file freshness | entries stamped with `(mtime_ns, size)`: `legacy/yolo_labeling/ui/filters.py::FiltersMixin._labels_cache_fresh` | [stamp cache entries](caches.md#label-cache-freshness) |
| The IoU filter was blind after a restart | it read only in-memory predictions, empty after a restart; it dropped unmapped classes before matching, fabricating unmatched labels; and its threshold entry was disabled for good by a setup-time `if not model: entry.disable()` that ran before any model loaded | reads the durable store without promoting and matches geometry against every class (`legacy/yolo_labeling/ui/filters.py::FiltersMixin._iou_filter_passes`); a missing model is refused, with a message, when the filter is applied (`legacy/yolo_labeling/ui/filters.py::FiltersMixin._filter_range_error`) | [read the durable store](caches.md#reading-during-a-dataset-pass); [geometry-only matching](matching.md#the-iou-filter); never disable a control at setup on a condition that changes later |
| "Wrong class" flipped between runs | the verdict followed the best-overlapping prediction ([why that flips](matching.md#candidates-and-the-deciding-prediction)) | `legacy/yolo_labeling/core/badscan.py::deciding` | [decide on the most confident](matching.md#candidates-and-the-deciding-prediction) |
| Valid labels marked for deletion | the model cannot emit their class | `legacy/yolo_labeling/ui/classes.py::ClassManagementMixin._checkable_classes` | [the checkable-class guard](matching.md#the-checkable-class-guard) |
| Config written to random folders | app state lived relative to the launch directory | `legacy/yolo_labeling/app.py::STATE_DIR` | [one fixed state directory](caches.md#where-app-state-lives) |
| Plain `pytest` could not collect the tests | the tests imported `core.*` as a top-level package | the tests import `yolo_labeling.core.*`, and `pytest.ini` puts the parent directory on the path — which works only while the folder is named `yolo_labeling` | import the package by its real name; DeepLabeling's `src/` layout drops the folder-name rule ([design spec](../design/2026-10-02-project-init.md#layout)) |
| Find Bad's Start button disappeared on short screens | it was packed last in a vertically resizable dialog, which clips from the bottom | the button row is packed first, at the bottom: `legacy/yolo_labeling/ui/dialogs.py::DialogsMixin.show_find_bad_dialog` | primary actions stay visible at the smallest window size; assert their geometry |
| An overlap-only filter reported "Showing all N images" | the result line's label-based branch covered only some of the filters | every label-based filter reports "Found: N/M": `legacy/yolo_labeling/ui/filters.py::FiltersMixin.apply_filters` | status text comes from the same condition that selected the images |
| (no symptom recorded) | the scan worker could read class info the user was editing mid-scan | class state is snapshotted on the GUI thread before the worker starts: `legacy/yolo_labeling/app.py::YOLOLabelingTool.open_bad_label_review` | snapshot user-editable state before a worker starts; workers never read it live |

## Also fixed, recorded only in code comments

Fixed at some point before the snapshot; the comment at each fix is the only record.

| Symptom | Root cause | Fix | Rule for DeepLabeling |
|---|---|---|---|
| "Infer all" animated a progress bar on a window that accepted no input, for hours | it looped on the GUI thread calling `update_idletasks()` | a worker thread: `legacy/yolo_labeling/app.py::YOLOLabelingTool.run_dataset_inference` | long work runs on a worker; the GUI thread only renders its progress |
| Moving the confidence slider made the threshold untunable on 46k images | every change emptied the prediction cache and re-inferred | a re-filter of the cached floor: `legacy/yolo_labeling/app.py::YOLOLabelingTool._on_prediction_conf_change` | [store at a floor, filter on read](caches.md#store-at-a-floor-and-filter-on-read) |
| Changing the overlap max was silently not saved | the save-on-change check compared only the scope and the floor | one tuple of every persisted filter setting, read by both sides: `legacy/yolo_labeling/ui/filters.py::FiltersMixin._persisted_filter_state` | one list of persisted settings, shared by the save and its change check |
| The overlap filter selected images the highlighter drew nothing on | each hard-coded its own class test | one predicate for both: `legacy/yolo_labeling/ui/filters.py::FiltersMixin.overlap_pair_counts` | a filter and the view of its result share one predicate |
| Transposed pixel boxes on EXIF-rotated photos in filters and statistics | the header size reader ignored EXIF orientation, which the editor's decode applies | the size reader swaps on quarter turns: `legacy/yolo_labeling/ui/filters.py::FiltersMixin._image_size` | [one EXIF-aware size function](caches.md#image-sizes) |
| Review actions edited a shadow copy on non-standard layouts | the review writers resolved label paths with `startswith` | they resolve through `LabelPathResolver`: `legacy/yolo_labeling/app.py::YOLOLabelingTool._review_label_lines` | [one resolver](label-files.md#one-path-resolver) |

## Not fixed in the legacy app

Latent in the snapshot. Sources: SPEC §9, the session notes, and — where marked — reading
the code.

| Defect | Where | Rule for DeepLabeling |
|---|---|---|
| Editing any box in the main editor rewrites the whole file from pixel boxes: polygons become boxes, extra columns and unparsable lines are dropped, CRLF and the original precision are lost. SPEC §9 records only the polygon case (found by reading the code) | `legacy/yolo_labeling/app.py::YOLOLabelingTool.save_labels` builds every line anew | [only changed lines are re-serialised](label-files.md#byte-preserving-round-trips), on every save |
| Crop-export name collisions | #7 above | unique output names |
| A YAML-launch save overwrites the config's `prediction_maps`, `hotkeys` and `class_groups` with the session's state | `legacy/yolo_labeling/ui/classes.py::ClassManagementMixin.save_class_config` | a save writes only what this session loaded or changed |
| Every `best.pt` shares one prediction map ([datasets.md](datasets.md#models-in-the-legacy-prediction-cache)) | `legacy/yolo_labeling/ui/classes.py::ClassManagementMixin._model_key` is the bare filename | key per-model settings so that two different models never share them |
| Boxes cached by Build Label Cache can be a pixel smaller on each edge | `legacy/yolo_labeling/app.py::YOLOLabelingTool.build_label_cache` converts with `int()` | [one rounding conversion](matching.md#geometry) |
| The reassign dialog's counts lag an external import until a restart | `legacy/yolo_labeling/ui/classes.py::ClassManagementMixin._count_class_labels` reads the label cache without the freshness check | [every cache read checks freshness](caches.md#label-cache-freshness) |
| Statistics and Build Label Cache read header sizes without EXIF orientation | `legacy/yolo_labeling/ui/stats.py::StatisticsMixin._collect_statistics`, `legacy/yolo_labeling/app.py::YOLOLabelingTool.build_label_cache` | [one size function](caches.md#image-sizes) |
| Producers still resolve label paths with `startswith`; the review's write guard turns a disagreement into a refusal rather than a wrong write | `legacy/yolo_labeling/app.py::YOLOLabelingTool._find_label_file_for` (used by the scan and the crop export), `legacy/yolo_labeling/ui/stats.py::StatisticsMixin._collect_statistics`, `legacy/yolo_labeling/ui/filters.py::FiltersMixin.apply_filters`, `legacy/yolo_labeling/app.py::YOLOLabelingTool.build_label_cache` | [one resolver](label-files.md#one-path-resolver) |
| The scan reads `parts[1:5]` with no arity check, so a polygon's first two points become its box; the write guard then refuses the entry | `legacy/yolo_labeling/ui/crop_review.py::CropReviewMixin._bad_scan_worker` | parse every label through the one parser ([label-files.md](label-files.md#line-format)) |
| Find Bad scans and Infer all keep every result in an unbounded in-memory dict (found by reading the code; not measured) | the scan calls `legacy/yolo_labeling/app.py::YOLOLabelingTool._peek_cached_predictions` with the default `promote=True`, and `legacy/yolo_labeling/app.py::YOLOLabelingTool._cached_predictions` keeps every new inference in memory | [a dataset pass streams from the durable store](caches.md#reading-during-a-dataset-pass) |
| Batch accept and crop-review actions cannot be undone; `a` in single view asks no confirmation. (SPEC §9 says `d`, delete image, asks none either; the snapshot's `legacy/yolo_labeling/app.py::YOLOLabelingTool.delete_current_image` does ask.) | SPEC §9 | every edit is a command through the label owner, which is what makes undo possible ([design spec](../design/2026-10-02-project-init.md#sync-2--label-edits-stay-consistent)) |
| "Mark reviewed" in the crop review lasts one session, so re-running the scan resurfaces everything dismissed that way | SPEC §9 | a review decision is either persisted or visibly temporary |
| Two instances on one dataset overwrite each other's review marks (and `class_config.json`); the last writer wins | SPEC §9 | shared state files are merged on save, or a second writer is detected |
| Review marks belong to the yaml that defined the dataset root: two yamls at different depths give two mark files with incompatible keys | SPEC §9 | key per-dataset state on one canonical root |
| Marking is immediate: paging through the grid marks every page passed, and re-applying a filter marks the image it lands on | SPEC §9 | only an edit, done & next or mark page marks an image ([app design](../design/2026-10-04-app-foundation.md#review-marks)) |
| Crop-review prefetch memory is bounded by frame count, not bytes | SPEC §9 | bound caches in bytes |
| Inference coverage counts the loaded model's rows, which may exceed the filtered set | SPEC §9 | a coverage readout states its denominator |
| Every label file the legacy app edited became private (mode `0600`): `mkstemp` creates `0600`, and `os.replace` keeps it. Found by reading the code; counted 2026-10-04 with the command below — 1,987 pvn-vehicle label files are `0600`, the rest `0664` | `legacy/yolo_labeling/core/labelio.py::write_label_file` | an atomic write keeps the target's permission bits: `src/deeplabeling/core/atomic.py::write_atomic` |

```sh
find /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle -name '*.txt' -path '*labels*' -perm 600 | wc -l
```

Scope limits SPEC §9 lists that are choices rather than defects, as the
[app design](../design/2026-10-04-app-foundation.md) decided them: a polygon cannot be
moved or resized, only reclassified or deleted; images are found the way training finds
them, recursively; viewing an image never marks it reviewed; a second DeepLabeling on the
same dataset root is refused; per-dataset state is keyed on the canonical root.
EXIF-rotated images still need labels in the rotation-applied geometry, semantic
segmentation stays out of scope, and Find Bad can only check distinctions the model can
make ([datasets.md](datasets.md#prediction-maps-and-class-groups)).
