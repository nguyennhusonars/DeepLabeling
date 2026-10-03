# Matching predictions to labels

Owns: how predictions are matched to labelled boxes, and what each finding of Find Bad
Annotations, the Label/Prediction IoU filter and the overlap filter means.

The evidence is `legacy/yolo_labeling/core/badscan.py`, which Find Bad Annotations and the
IoU filter share so they cannot disagree. Predictions reach it already narrowed to the
shared confidence floor and translated to dataset ids, with `None` for a model class that
has no mapping ([caches.md](caches.md#store-raw-model-ids)).

## Candidates and the deciding prediction

- **Candidates** are the predictions that overlap the label at IoU ≥ the matching
  threshold (`iou_match`, default 0.5), of any class, mapped or not:
  `legacy/yolo_labeling/core/badscan.py::candidates`.
- The **deciding** prediction is the most confident candidate (ties go to the better
  overlap), not the best-overlapping one: `legacy/yolo_labeling/core/badscan.py::deciding`.
- Why: Ultralytics runs NMS per class by default (`agnostic_nms: False`), so one car
  routinely yields `car 0.80` plus a slightly better aligned `truck 0.35`. Deciding on
  overlap flipped the verdict between runs on a 0.02 IoU difference.

**Rule:** the most confident candidate speaks for the model.

## Unmapped classes are inconclusive

- When the deciding prediction's class has no dataset mapping, there is no finding. It
  proves an object is there but says nothing about which, and a weaker mapped candidate
  must not overrule it.
- An unmapped prediction still counts as a candidate, so its label is never "not an
  object" either.

**Rule:** an unmapped class is inconclusive — never a disagreement, never "missing".

## Finding kinds

`legacy/yolo_labeling/core/badscan.py::classify_gt`, configured by
`legacy/yolo_labeling/core/badscan.py::ScanConfig` (dialog defaults in
`legacy/yolo_labeling/ui/classes.py::FIND_BAD_DEFAULTS`).

| Kind | When | Reported only if | Review order score |
|---|---|---|---|
| wrong class | the deciding prediction disagrees with the label (through class groups) | its confidence ≤ the wrong-class ceiling | confidence |
| not an object | no candidate at all | the nearest prediction's IoU is inside the band (default 0 up to `iou_match`) and the label's class is [checkable](#the-checkable-class-guard) | 1 − nearest IoU |
| weakly seen | the deciding prediction agrees | its confidence < the cutoff (default 0.6; kind off by default) | 1 − confidence |

- "Agrees" goes through class groups ([datasets.md](datasets.md#prediction-maps-and-class-groups)).
- "Not an object" is banded on the **nearest** box's IoU: near 0 is a stray box (nothing
  there), higher is a badly drawn one (the model sees the object; the outline disagrees).
- Measured 2026-10-02 on 45,252 pvn-vehicle images with the newest 13-class model, at
  conf ≥ 0.25 and IoU ≥ 0.5: 29,863 labels had no match. By nearest-box IoU, 62% were
  < 0.05, 7% 0.05–0.10 and 31% 0.10–0.50. The legacy scan told the user to delete all of
  them, though a third are boxes to redraw. The same run found 1,127 predictions at conf
  0.80–1.00, in 1,070 images, that no label covers. Reproduce with the `dataset-analysis`
  skill's `unmatched.py`.
- Find Bad examines only boxes that exist. Objects nobody labelled are found by
  [the IoU filter](#the-iou-filter).
- Confusion pair ("every A the model calls B"): naming a predicted class turns "not an
  object" and "weakly seen" off, since neither has a prediction of that class to show.
  Naming both sides also makes agreement raw id equality, ignoring groups.
- Results are ordered with kind as the primary axis: the scores of different kinds are
  different quantities (model confidence versus how little the model saw), so one ranking
  mixing them by score would be meaningless.

**Rule:** each kind answers a different question with a different fix — reassign, delete
or redraw, inspect — and is reported and ranked as its own kind.

## One floor and per-kind ceilings

- One shared confidence floor ("seen when confidence ≥") decides what the model sees, for
  every kind. Per-kind upper bounds only limit which findings are reported.
- An upper bound never removes a prediction from matching. The naive reading of a
  confidence range — filter predictions to [lo, hi], then match — reports a box the model
  sees at 0.95 as "not an object" as soon as hi drops to 0.6.
- A kind's results never depend on which other kinds are on. That is why the floor is
  shared: separate floors would let one box be both "not an object" and "weakly seen".
- The floor cannot go below the cache floor ([caches.md](caches.md#store-at-a-floor-and-filter-on-read)).

**Rule:** one floor for existence; ceilings filter the report, never the predictions.

## The checkable-class guard

- A label whose class the model cannot emit — directly, or by emitting another class in
  the same group — is never reported as "not an object": the model's silence proves
  nothing there, and the finding tells the user to delete a good box.
- Evidence: `legacy/yolo_labeling/ui/classes.py::ClassManagementMixin._checkable_classes`,
  built on `legacy/yolo_labeling/core/classmap.py::PredictionClassMap.emittable`, which is
  defined through `translate` so it cannot drift from what predictions actually become.
  An unknown model vocabulary skips nothing. The legacy status line counts the skipped
  labels.
- The IoU filter's "labels the model does not see" applies the same guard.
- The case that forced it: `data_UK` ([datasets.md](datasets.md#data_uk)).

**Rule:** before calling a label unseen, check that the model could have seen it.

## The nearest box and the review crop

- A "not an object" finding records the nearest prediction only when its IoU is ≥
  `legacy/yolo_labeling/core/badscan.py::NEAREST_MIN_IOU` (0.10); below that the crop
  shows the label alone.
- The review crop is the union of the label and the model's box plus a margin
  (`legacy/yolo_labeling/core/crops.py::render_review_crop`). IoU ≥ 0.1 bounds the
  **area** ratio to 10×, not the side ratio: a 400×40 prediction over a 40×40 label is
  IoU 0.1 and squeezed the label to about 10% of the crop width. Capping the reach at
  `legacy/yolo_labeling/core/crops.py::MAX_REACH` (2× the label's larger side) keeps it at
  about 19%; beyond the reach the model's box is drawn clipped at the edge.

**Rule:** the label is the subject of its crop; a prediction widens the view only so far.

## Geometry

- IoU is invariant under independent x/y scaling — intersection and both areas scale by
  the same sx·sy — so it can be computed on normalised coordinates with no image size
  (`legacy/yolo_labeling/core/geometry.py::iou_xyxy`).
- Pixel conversion rounds, never truncates: `int()` floors both edges and shrank every box
  by up to a pixel per load/save cycle
  (`legacy/yolo_labeling/core/geometry.py::yolo_to_pixel`, `rounding="round"`).
- Measured 2026-10-02 on every pvn-vehicle label file a recursive walk finds
  ([datasets.md](datasets.md#counting)): rounding versus the legacy truncation changed zero
  overlap verdicts — a latent disagreement, not an observed one.

**Rule:** match in normalised coordinates where possible; where pixels are needed, one
conversion function that rounds.

## Overlap between labels

- Scope: **different** classes (one object labelled as two things), **same** class (one
  object labelled twice — the duplicate-box error) or **any**:
  `legacy/yolo_labeling/ui/filters.py::FiltersMixin.overlap_pair_counts`. The filter and
  the highlighter share it, so what the filter selects is what the view highlights.
- The IoU range is inclusive at both ends — two identical boxes are exactly 1.0, so
  0.99–1.00 isolates exact duplicates (safe to clean in bulk) while 0.5–0.9 finds partial
  overlaps (often legitimate occlusion): `legacy/yolo_labeling/ui/filters.py::FiltersMixin.overlap_iou_in_range`.
- A reversed range is refused by name when applied, never swapped while typed (people edit
  one end at a time), and a typed value is never clamped:
  `legacy/yolo_labeling/core/ranges.py::range_error`,
  `legacy/yolo_labeling/core/ranges.py::parse_unit`.
- Identical boxes draw as one rectangle, so each box shows how many boxes are stacked on
  it, itself included (`L bus x2`). The count is per box, not per group: in a chain A–B–C
  where A and C do not touch, A reads x2 and B reads x3
  (`legacy/yolo_labeling/app.py::YOLOLabelingTool.detect_current_overlaps`).
- Measured 2026-10-02 on the same files: different @ IoU ≥ 0.5 → 123 images;
  same @ 0.5 → 455; any @ 0.5 → 570; same @ 0.9 → 8, of which 7 were byte-identical
  duplicate lines. The default (different @ 0.5) and the query most sessions end on
  (same @ 0.9) differ fifteen-fold. Reproduce with the `dataset-analysis` skill's
  `overlaps.py`.

**Rule:** a filter and the view that shows its result use one predicate; a duplicate must
be visible, not just countable.

## The IoU filter

The Label/Prediction IoU filter has three directions: labels the model does not see,
predictions with no label, or either
(`legacy/yolo_labeling/ui/filters.py::FiltersMixin._iou_filter_passes`).

- **Unmatched label:** no prediction at or above the floor — of any class, mapped or not —
  overlaps it at the matching IoU. This is geometry, so unmapped boxes count. The upper
  confidence bound plays no part, and the
  [checkable-class guard](#the-checkable-class-guard) applies. It uses `candidates`, so at
  the same floor and matching IoU it selects an image exactly when a not-an-object scan
  would flag one of its labels.
- **Unmatched prediction:** a **mapped** prediction within the confidence range that
  overlaps no label at the matching IoU — an object nobody labelled, including on frames
  with no label file at all. Unmapped boxes are excluded, or every class the dataset does
  not care about would be flagged.
- Images never inferred are handled as in [caches.md](caches.md#reading-during-a-dataset-pass).

**Rule:** "the model does not see this label" is geometry against every prediction;
"nobody labelled this" counts only classes the dataset has.
