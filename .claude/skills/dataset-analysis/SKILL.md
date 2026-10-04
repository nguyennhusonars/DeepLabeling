---
name: dataset-analysis
description: Analyse the pvn YOLO datasets and the legacy prediction cache — label quality, duplicate or overlapping boxes, objects the model sees that nobody labelled, labels the model does not see, class maps and groups, and what a training-time size filter (min_rel_wh / MinBoxFilter) really keeps. Use it for any question about these datasets or their labels, even an informal one, before reasoning from memory.
---

Read [CLAUDE.md](../../../CLAUDE.md) first — the landmines are there and are not repeated here.

The datasets themselves — where they are, their yamls, class groups, prediction maps and
the training fork's size filter — are documented in
[datasets.md](../../../docs/knowledge/datasets.md); this skill does not repeat any of it.

All three scripts are read-only: `unmatched.py` opens the prediction cache with
`mode=ro`; none of the three ever writes a label file, a dataset or the cache.
`overlaps.py` imports its label parsing and overlap predicate from `deeplabeling.core`,
so it agrees with the app. `unmatched.py` and `size_cut_sim.py` still parse labels
themselves; they move onto the core with slice 4's port of the matching code.

- **`scripts/overlaps.py`** — images whose labels overlap each other, from the label
  files alone (IoU on normalised coordinates is exact, so no image sizes are needed).
  Scope picks same-class pairs (duplicate boxes), different-class pairs (one object
  labelled twice as different things) or any. What each scope and IoU range means, and
  what it found on pvn-vehicle, is in
  [Overlap between labels](../../../docs/knowledge/matching.md#overlap-between-labels).

  ```sh
  python3 .claude/skills/dataset-analysis/scripts/overlaps.py /path/to/dataset --min 0.99 --max 1 --scope same
  ```

- **`scripts/unmatched.py`** — reads the legacy prediction cache and reports predictions
  with no covering label, and labels the model does not see; matching is geometry only
  (any class — there is no checkable-class guard here, so restrict the predictions
  direction with `--classes`). What a "no match" or "unseen" result means, and what it
  found on pvn-vehicle, is in
  [Finding kinds](../../../docs/knowledge/matching.md#finding-kinds).

  ```sh
  python3 .claude/skills/dataset-analysis/scripts/unmatched.py --cache .../predictions.sqlite --conf-lo 0.8
  ```

- **`scripts/size_cut_sim.py`** — simulates the training fork's `MinBoxFilter`
  (`min_rel_wh`) per image, for train (the square mosaic canvas, under scale jitter) and
  val (rect batches) separately, since the two use different canvases and so keep
  different boxes at the same threshold. Why they differ, and what it found, is in
  [The training fork and its size filter](../../../docs/knowledge/datasets.md#the-training-fork-and-its-size-filter).

  ```sh
  python3 .claude/skills/dataset-analysis/scripts/size_cut_sim.py --yaml .../data_13class.yaml --val-thr 0.01 --train-thr 0.005
  ```
