# Blurry boxes — the core: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score every label box's sharpness, cache the scores per image, and build a `Blurry`
queue source whose items are the blurriest share of each class-and-size group.

**Architecture:** `core/sharpness.py` holds the two measures and the per-image scoring;
`core/sqlitefile.py` is the prediction store's connection handling, shared by a new
`SharpnessStore`; `core/blurry.py` holds the settings, the ranking and the source. The source
plugs into the queue system as `Findings` does; its items are `Finding`s of kind `blurry`.
The UI wiring is plan 6b ([the UI plan](2026-10-27-blurry-ui-plan.md)).

**Tech Stack:** Python 3.10, numpy, OpenCV 5 (`cv2`), SQLite, pytest.

**Spec:** [2026-10-27-blurry.md](2026-10-27-blurry.md)

## Global Constraints

- No new dependency: numpy and OpenCV only. scikit-image appears only in a test that skips
  without it.
- Measures: Gaussian σ 0.7 before the Laplacian; tile `t = max(8, short // 3)`, step
  `max(1, t // 2)`; skip tiles with grey variance < 25 (std 5); 80th percentile; `log10`;
  whole-crop fallback divides by grey variance + 1. Crété-Roffet h_size 11, max over axes.
- A flat crop: grey std < 2 over the whole box. Scored boxes: rectangle short side ≥ 8 px.
- Groups: (class, octave) with octaves 8–15, 16–31, 32–63, 64–127, 128+; a group under 20
  boxes is not ranked. z = (v − median) / max(1.4826 · MAD, 1e-6); score = mean of the two z
  (Crété-Roffet negated first); listed = first `ceil(share · n)` of a group by (score,
  dataset order, line), then dismissed ones dropped; rank = index / n.
- Settings defaults: share 0.05 (above 0, at most 1), minimum side 16 (8 to 4096).
- The cache: `sharpness.sqlite`, `PRAGMA user_version` 1, one row per image:
  `img TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER, boxes TEXT` (JSON
  `[[x0, y0, x1, y1, lap, cr], …]`, `lap`/`cr` null for a flat crop).
- Jobs never write files: the build emits `Scored` batches; it never calls `put_many`.
- Counts on the chip, by box: `too small`, `flat`, `too few peers`; by image:
  `cannot decode`, `labels unreadable`.
- Cite code by file and symbol, never by line (CLAUDE.md rule 3); tests write only to
  temporary folders.

## Review Focus

- An EXIF-rotated image: boxes are measured on the image as shown (`cv2.imread` applies the
  orientation), so its rectangles match the crop grid's — pinned in Task 2.
- A box that runs off the frame or is degenerate after clipping: not scored, never an
  exception — pinned in Task 2.
- A cache row whose stamp no longer matches (the image re-encoded in place): the image is
  rescored, not served stale — pinned in Task 4.
- A label file with a polygon line: polygons are not boxes and are not scored — pinned in
  Task 4 (the `seg/mixed` image of the edge-case dataset).
- A group whose boxes are all equal (a synthetic or duplicated set): every z is 0 and the
  share still lists `ceil(share · n)` — pinned in Task 3.

---

### Task 1: The shared SQLite file and the score store

**Files:**
- Create: `src/deeplabeling/core/sqlitefile.py`
- Modify: `src/deeplabeling/core/predstore.py` (subclass the base; behaviour unchanged)
- Create: `src/deeplabeling/core/sharpstore.py`
- Test: `tests/core/test_sharpstore.py` (new); `tests/core/test_predstore.py` must stay green

**Interfaces:**
- Produces: `SqliteFile(path)` with class attributes `SCHEMA: str`, `VERSION: int`, and
  `warning: str`, `_connection() -> sqlite3.Connection`, `close()`, `_closed: bool` — the
  connection, set-aside, read-only and close logic now in
  `src/deeplabeling/core/predstore.py::PredictionStore`, moved verbatim, with `SCHEMA` and
  `VERSION` read from the class.
- Produces: `SHARP_NAME = "sharpness.sqlite"`; `BoxScore = tuple[int, int, int, int, float | None, float | None]`
  (x0, y0, x1, y1, lap, cr); `SharpnessStore(SqliteFile)` with
  `get(img: str, stamp: Stamp) -> list[BoxScore] | None` (None when absent or the stamp
  differs) and `put_many(rows: Iterable[tuple[str, Stamp, list[BoxScore]]]) -> None` (one
  transaction; a no-op after `close()`).

- [ ] **Step 1: Write the failing tests** in `tests/core/test_sharpstore.py`:

```python
def test_a_row_comes_back_while_its_stamp_matches(tmp_path):
    s = SharpnessStore(tmp_path / SHARP_NAME)
    s.put_many([("a/1.jpg", (10, 20), [(0, 0, 16, 16, 1.25, 0.31), (4, 4, 30, 30, None, None)])])
    assert s.get("a/1.jpg", (10, 20)) == [(0, 0, 16, 16, 1.25, 0.31), (4, 4, 30, 30, None, None)]
    assert s.get("a/1.jpg", (10, 21)) is None and s.get("b.jpg", (10, 20)) is None

def test_a_corrupt_file_is_set_aside_and_started_again(tmp_path):
    (tmp_path / SHARP_NAME).write_bytes(b"not a database")
    s = SharpnessStore(tmp_path / SHARP_NAME)
    assert "unreadable" in s.warning and s.get("x", (1, 1)) is None

def test_another_version_is_set_aside(tmp_path):      # make a file with PRAGMA user_version = 7
    ...  # assert the warning names the version and a fresh store answers None

def test_after_close_it_answers_nothing_and_writes_nothing(tmp_path): ...
```

- [ ] **Step 2: Run** `python3 -m pytest tests/core/test_sharpstore.py -q` — Expected: FAIL (no module).
- [ ] **Step 3: Move the connection handling into `SqliteFile`; make `PredictionStore` a
  subclass; write `SharpnessStore`.** JSON with `separators=(",", ":")`; rows decoded to
  tuples.
- [ ] **Step 4: Run** `python3 -m pytest tests/core/test_sharpstore.py tests/core/test_predstore.py -q` — Expected: all pass.
- [ ] **Step 5: Commit** `core: the score cache, sharing the prediction store's SQLite handling`.

### Task 2: The measures

**Files:**
- Create: `src/deeplabeling/core/sharpness.py`
- Test: `tests/core/test_sharpness.py`

**Interfaces:**
- Consumes: `src/deeplabeling/core/geometry.py::corners`, `Box`.
- Produces:
  - `box_rect(box: Box, w: int, h: int) -> tuple[int, int, int, int] | None` — corners ×
    size, `round`ed, clipped to the frame; None when empty. It equals
    `crop_rect(box, None, w, h)` before the padding; make `crop_rect` call it for its first
    line so the two cannot drift.
  - `is_flat(grey: np.ndarray) -> bool` — std < 2.
  - `tiled_ratio(grey: np.ndarray) -> float` and `crete_roffet(grey: np.ndarray, h_size: int = 11) -> float`
    (scikit-image's value: 0 sharp … 1 blurry). Vectorised: local means by `cv2.blur` with
    `BORDER_REFLECT`, no Python loop over tiles. The port: per axis, a uniform filter of
    `h_size` along that axis (`cv2.blur`, `BORDER_REFLECT`), `|Sobel|` along that axis of the
    image and of the filtered image (floored at `np.spacing(1)`), sums over
    `[2:-1, 2:-1]`, `|M1 − M2| / M1`; the max of the two axes.
  - `MIN_SCORED = 8`; `score_image(grey: np.ndarray, boxes: Iterable[Box]) -> list[BoxScore]`
    — one score per distinct rectangle of short side ≥ 8; `lap`/`cr` None when flat.

- [ ] **Step 1: Write the failing tests:**

```python
def textured(seed=0, n=64):                 # a crop with detail at every scale
    return np.random.default_rng(seed).integers(0, 256, (n, n)).astype(np.uint8)

def test_blur_lowers_both_measures():
    sharp = cv2.GaussianBlur(textured(), (0, 0), 1.0)           # natural-ish detail
    blurred = cv2.GaussianBlur(sharp, (0, 0), 2.0)
    assert tiled_ratio(blurred) < tiled_ratio(sharp)
    assert crete_roffet(blurred) > crete_roffet(sharp)

def test_flat_tiles_are_skipped():
    # a sharp 24 px textured square in the corner of a flat 96 px crop scores as the square
    # alone does (within 0.05), not as the mostly flat whole
    ...

def test_a_flat_crop_is_flat():
    assert is_flat(np.full((40, 40), 17, np.uint8)) and not is_flat(textured())

def test_the_port_equals_scikit_image():
    blur_effect = pytest.importorskip("skimage.measure").blur_effect
    for seed, n in ((0, 16), (1, 40), (2, 97)):
        g = cv2.GaussianBlur(textured(seed, n), (0, 0), 0.8)
        assert crete_roffet(g) == pytest.approx(blur_effect(g, h_size=11), abs=1e-6)

def test_box_rect_is_the_crop_grids_rule_and_clips():
    assert box_rect((0.5, 0.5, 0.2, 0.2), 64, 48) == (26, 19, 38, 29)
    assert box_rect((0.98, 0.5, 0.2, 0.2), 64, 48)[2] == 64          # clipped at the right
    assert box_rect((1.5, 0.5, 0.2, 0.2), 64, 48) is None             # wholly off the frame

def test_score_image_scores_each_rectangle_once_and_skips_small_ones(): ...
def test_an_exif_rotated_image_is_scored_as_shown(tmp_path):
    # tests/fixtures.py::make_exif_rotated_image: cv2.imread gives h x w as displayed (48 x 64 → 64 x 48 swapped)
    ...
```

- [ ] **Step 2: Run** `python3 -m pytest tests/core/test_sharpness.py -q` — Expected: FAIL (no module).
- [ ] **Step 3: Implement** as the Interfaces say; change `crop_rect`'s first line to use `box_rect`'s unclipped corners (keep `crop_rect`'s tests green).
- [ ] **Step 4: Run** `python3 -m pytest tests/core/test_sharpness.py tests/core/test_crops.py -q` — Expected: pass (the skimage test passes here; it is installed in base).
- [ ] **Step 5: Commit** `core: the two sharpness measures, and the box rectangle the crop grid uses`.

### Task 3: Settings and ranking

**Files:**
- Create: `src/deeplabeling/core/blurry.py`
- Test: `tests/core/test_blurry_rank.py`

**Interfaces:**
- Produces:
  - `BlurSettings(share: float = 0.05, min_side: int = 16)`, frozen; refuses
    `share` outside (0, 1] with `"share: must be above 0% and at most 100%"` and `min_side`
    outside 8–4096 or not an int with `"minimum side: must be from 8 to 4096 px"`;
    `to_json() -> {"share": …, "min_side": …}`; `from_json(data)` raising
    `ValueError("not Blurry settings: …")`.
  - `OCTAVES = ((8, 15), (16, 31), (32, 63), (64, 127), (128, None))`;
    `octave(side: int) -> int`; `octave_name(i) -> "16–31 px"` / `"128+ px"`.
  - `MIN_PEERS = 20`.
  - `Candidate` (frozen dataclass): `key: str, entry_order: int, line: int, cls: int,
    side: int, lap: float, cr: float`.
  - `rank(candidates: list[Candidate], share: float) -> tuple[dict[str, tuple[float, float]], set[str]]`
    — `{key: (z, rank)}` for the listed (the first `ceil(share · n)` of each group), and
    the keys of groups under `MIN_PEERS`. Dismissals are dropped by the caller, after.

- [ ] **Step 1: Write the failing tests:**

```python
def test_settings_refuse_by_name():
    with pytest.raises(ValueError, match="share: must be above 0% and at most 100%"):
        BlurSettings(share=0)
    with pytest.raises(ValueError, match="minimum side: must be from 8 to 4096 px"):
        BlurSettings(min_side=7)
    assert BlurSettings.from_json(BlurSettings(0.1, 24).to_json()) == BlurSettings(0.1, 24)

def test_octaves():
    assert [octave(s) for s in (8, 15, 16, 31, 32, 127, 128, 900)] == [0, 0, 1, 1, 2, 3, 4, 4]
    assert octave_name(1) == "16–31 px" and octave_name(4) == "128+ px"

def test_the_blurriest_share_of_each_group_is_listed_rounded_up():
    # 40 heads 16–31 px with lap = cr-negated rising with i; 25 cars 32–63 px likewise
    listed, _ = rank(cands, 0.05)
    assert sorted(k for k in listed if k.startswith("head")) == ["head0", "head1"]   # ceil(0.05 * 40)
    assert sorted(k for k in listed if k.startswith("car")) == ["car0", "car1"]      # ceil(1.25)
    assert listed["head0"][1] == 0 and listed["head1"][1] == 1 / 40

def test_a_small_group_is_not_ranked_and_said(): ...      # 19 boxes: none listed, all 19 keys returned
def test_a_group_of_equal_values_lists_its_share_with_z_zero(): ...
def test_the_score_averages_both_z(): ...                 # a box low on one measure only is outranked by a box low on both
```

- [ ] **Step 2: Run** `python3 -m pytest tests/core/test_blurry_rank.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.** z per measure with numpy median and MAD; Crété-Roffet's z is of
  `-cr`; ties by `(score, entry_order, line)`.
- [ ] **Step 4: Run** it — Expected: pass.
- [ ] **Step 5: Commit** `core: Blurry's settings, groups and ranking`.

### Task 4: The Blurry source

**Files:**
- Modify: `src/deeplabeling/core/blurry.py` (the source)
- Modify: `src/deeplabeling/core/findings.py` (`BlurFinding`)
- Modify: `src/deeplabeling/core/queue.py` (`BuildContext.sharpness`, `BuildContext.count_box`, `Scored`, `source_from_json`)
- Modify: `src/deeplabeling/core/workspace.py` (`Workspace.sharpness`: opened beside the predictions, its warning listed, closed on close)
- Modify: `tests/fixtures.py` (`build_blur_dataset`)
- Test: `tests/core/test_blurry_source.py`

**Interfaces:**
- Consumes: Tasks 1–3; `src/deeplabeling/core/predstore.py::image_stamp`.
- Produces:
  - `BlurFinding(Finding)`: adds `z: float = 0.0`, `group: str = ""` (the octave's name);
    `kind="blurry"`, `score` = the rank, no model fields.
  - `Scored(rows: list[tuple[str, Stamp, list[BoxScore]]])` in `core/queue.py`, emitted
    among a build's batches as `Scanned` is.
  - `BuildContext.sharpness: SharpnessStore | None = None`;
    `BuildContext.count_box(what: str, entry: ImageEntry, line: int)` — `unsettled[what] += 1`
    and `left_out[what].add(f"{entry.rel}#{line}")`, so the chip counts boxes.
  - `Blurry(scope: ImageFilter = ImageFilter(), settings: BlurSettings = BlurSettings())`,
    frozen; `needs_model = False`;
    `build(ctx, emit, cancelled=lambda: False, *, batch=500, interval=0.2, progress=None) -> bool`;
    `still(entry, items, ctx) -> set[str]` (an item holds while its line text is in the
    file); `holds(item, ctx)`; `highlight(...)`/`highlight_predictions(...)` → `frozenset()`;
    `describe(dataset) -> "blurry: 5% of each class and size, ≥ 16 px"` plus
    `" of <scope>"` when the scope is not the default; `to_json()` →
    `{"source": "blurry", "scope": …, "settings": …}`; `from_json` raising
    `ValueError("not a blurry queue: …")`. `source_from_json` dispatches `"blurry"`.
  - Item keys `f"{rel}#{line}#blurry"`, focus `LineRef(line, cls, box)`, rank tuple
    `(rank, score, entry.order, line)`.
  - `build_blur_dataset(root: Path, *, n: int = 30, blurred: tuple[int, ...] = (3, 17)) -> DatasetFixture`:
    `n` 160 × 120 JPEGs under `cam/images`, each with one class-0 box of 40 × 40 px over
    seeded noise texture (and class-1 boxes of 20 px, so two groups); the images in
    `blurred` Gaussian-blurred σ 3 before saving; `names: [head, human]`.

- [ ] **Step 1: Write the failing tests** in `tests/core/test_blurry_source.py`:

```python
def built(ds_root, source, store, dismissed=frozenset()):
    """Run a build; return (items, scored rows, ctx). Writes the Scored rows to `store`
    as the session will, so a second build is warm."""

def test_the_blurred_images_come_first(tmp_path):
    ds = build_blur_dataset(tmp_path / "b")
    items, rows, ctx = built(ds.root, Blurry(settings=BlurSettings(share=0.1)), SharpnessStore(tmp_path / SHARP_NAME))
    heads = [i for i in items if i.focus.cls_id == 0]
    assert {i.entry.rel for i in heads[:2]} == {"cam/images/0003.jpg", "cam/images/0017.jpg"}     # the blurred two
    assert all(i.finding.kind == "blurry" and i.key.endswith("#blurry") for i in items)

def test_a_warm_build_decodes_nothing(tmp_path, monkeypatch):
    # second build with the rows written: patch cv2.imread to raise; same items
def test_a_class_change_needs_no_rescore_and_a_moved_box_rescores_its_image(tmp_path, monkeypatch): ...
def test_a_changed_image_is_rescored(tmp_path): ...         # rewrite one JPEG: its stamp differs
def test_dismissed_boxes_are_peers_but_not_listed(tmp_path): ...
def test_counts_too_small_flat_too_few_and_cannot_decode(tmp_path): ...   # the edge-case dataset: corrupt.jpg, tiny and flat boxes, a polygon not scored
def test_a_cancelled_build_has_emitted_its_scores(tmp_path): ...
def test_an_item_holds_while_its_line_text_is_there(tmp_path): ...
def test_json_round_trip_and_source_from_json(): ...
def test_the_workspace_opens_and_closes_the_score_store(tmp_path, ds): ...
```

- [ ] **Step 2: Run** `python3 -m pytest tests/core/test_blurry_source.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement the build.** For each image (in dataset order, cancel checked per
  image, `progress` as `Findings.build` does, `time.sleep(0.0005)` every 64 images for the
  GUI thread's turn at the GIL): skip if the scope does not match; labels (`ERROR` →
  `ctx.count("labels unreadable", entry)`); its box lines (`labels.boxes`, parsed boxes
  only); stamp; the needed rectangles, from the image's size as shown, `ctx.size(entry)`
  (its header, EXIF applied — the size a decode gives); the cached row if its stamp matches
  and it holds every needed rectangle; else (or when the header cannot be read)
  `cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)` (None → `ctx.count("cannot decode",
  entry)`), rectangles from the decoded size, `score_image`, and
  the new row queued for the next `Scored` emit (every `batch` images, and at the end).
  Then per box: short side < `min_side` → `count_box("too small")`; flat →
  `count_box("flat")`; else a `Candidate`. `rank`; the small groups → `count_box("too few
  peers")`; drop dismissed `(rel, text, "blurry")`; items sorted; emitted in `batch`es.
- [ ] **Step 4: Run** `python3 -m pytest tests/core -q` — Expected: all pass.
- [ ] **Step 5: Commit** `core: the Blurry queue source`.

## After the plan

Run the full suite and `python3 tools/check_docs.py`. The docs (caches.md, the measured
targets) are the UI plan's last task.
