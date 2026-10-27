# Blurry boxes — the UI: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the `Blurry` source in the window: built with its scores written on the GUI
thread, shown as crop tiles and rows, keyed like Find Bad, chosen in the queue editor, and
measured.

**Architecture:** The session routes a build's `Scored` batches to the workspace's score
store before it checks which queue a batch belongs to; Find Bad's views learn the `blurry`
kind; the queue editor gains a third source. Builds on
[the core plan](2026-10-27-blurry-core-plan.md).

**Tech Stack:** PySide6 6.6, pytest-qt (offscreen), the core of plan 6a.

**Spec:** [2026-10-27-blurry.md](2026-10-27-blurry.md)

## Global Constraints

- Texts, exactly: row `blurry: head, 0.4% of 16–31 px`; inspector
  `blurry · 0.4% of head 16–31 px · z −3.4` (a typographic minus); tile caption
  `head 0.4%`; `M`/`B` refusal `not for blurry boxes`; chip progress
  `scoring 1,200 / 19,499`; chip counts `· 412 blurry`, then `· N too small`, `· N flat`,
  `· N too few peers`, `· N cannot decode`.
- Percent: `f"{rank * 100:.1f}%"`.
- The editor: *Source* items `Images`, `Find Bad`, `Blurry`; group title
  `Blurry — the blurriest of each class and size`; fields *share* (%) default `5` and
  *minimum side* (px) default `16`; a line under them:
  `A deleted label leaves its object as background.`; refusals `Blurry — share: …`,
  `Blurry — minimum side: …`.
- A score write that fails says so once per build, as an error notice:
  `scores not saved: <why>`; the build goes on.
- UI changes are verified by what is visible (CLAUDE.md landmine 4): pixels or geometry, and
  a screenshot looked at.

## Review Focus

- A queue switched mid-build: the old build's `Scored` batches are still written, its item
  batches dropped — pinned in Task 1.
- The dataset closed mid-build: a late `Scored` batch for the closed workspace is dropped,
  never written to the next dataset's store — pinned in Task 1.
- A Blurry queue restored on relaunch (its JSON in the opening settings), cursor on a
  `rel#line#blurry` key — pinned in Task 1.
- A multi-tile `M` over blurry boxes: nothing changes and the skip reason is said — pinned
  in Task 3.
- The editor seeded from a Blurry queue returns the same source unchanged — pinned in
  Task 4.

---

### Task 1: Session wiring

**Files:**
- Modify: `src/deeplabeling/ui/session.py` (`context`, `set_queue`, `_grew`, `progress_text`, `UNSETTLED`)
- Test: `tests/ui/test_blurry_session.py`

**Interfaces:**
- Consumes: `Blurry`, `BlurSettings`, `Scored`, `BuildContext.sharpness`,
  `Workspace.sharpness`, `build_blur_dataset` (plan 6a).
- Produces: `Session.context()` passes `sharpness=ws.sharpness`; `_grew(queue, ws, items)`
  writes a `Scored` batch to `ws.sharpness.put_many` when `ws is self.workspace`, whatever
  the queue; `progress_text()` says `scoring` for a Blurry queue and counts its items by
  kind; `UNSETTLED` gains `too small`, `flat`, `too few peers`, `cannot decode`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_a_blurry_queue_builds_and_its_scores_are_kept(qtbot, tmp_path):
    ds = build_blur_dataset(tmp_path / "b")
    s = open_session(qtbot, ds.yaml)
    s.set_queue(Blurry(settings=BlurSettings(share=0.1)))
    qtbot.waitUntil(lambda: s.queue.complete, timeout=10000)
    assert s.progress_text().startswith(" · ") and "blurry" in s.progress_text()
    assert s.workspace.sharpness.get("cam/images/0003.jpg", image_stamp(ds.root / "cam/images/0003.jpg"))

def test_the_chip_says_scoring_while_it_builds(qtbot, tmp_path): ...       # a gate in build: " · scoring 0 / 30"
def test_a_replaced_build_still_writes_its_scores(qtbot, tmp_path): ...     # set_queue(ImageFilter()) mid-build
def test_a_closed_datasets_late_scores_are_dropped(qtbot, tmp_path): ...
def test_a_failed_write_is_said_once(qtbot, tmp_path, monkeypatch): ...     # put_many raises sqlite3.OperationalError twice
def test_a_blurry_queue_and_its_cursor_survive_a_relaunch(qtbot, tmp_path): ...
```

- [ ] **Step 2: Run** `python3 -m pytest tests/ui/test_blurry_session.py -q -o addopts= -p no:warnings` — Expected: FAIL.
- [ ] **Step 3: Implement.** In `set_queue`, capture `ws` in the batch callback; `_grew`
  handles `Scored` first. A failure flag lives on the `Queue` object the build belongs to.
- [ ] **Step 4: Run** the file — Expected: pass.
- [ ] **Step 5: Commit** `ui: a Blurry queue builds, and its scores are written on the GUI thread`.

### Task 2: What a blurry box shows

**Files:**
- Modify: `src/deeplabeling/ui/findview.py` (`finding_text`, `finding_caption`, `finding_detail`)
- Modify: `src/deeplabeling/ui/queue_panel.py` (`QueuePanel._on_crops`: Findings or Blurry)
- Test: `tests/ui/test_findview.py` (extend), `tests/ui/test_blurry_window.py` (new)

**Interfaces:**
- Consumes: `BlurFinding` (`z`, `group`, `score` = rank).

- [ ] **Step 1: Write the failing tests:**

```python
def test_a_blurry_findings_texts(dataset):
    f = BlurFinding(line=0, text="0 0.5 0.5 0.2 0.2", kind="blurry", score=0.004, label_cls=0,
                    label_box=(0.5, 0.5, 0.2, 0.2), z=-3.42, group="16–31 px")
    assert finding_text(f, dataset) == "blurry: person, 0.4% of 16–31 px"
    assert finding_caption(f, dataset) == "person 0.4%"
    assert finding_detail(f, dataset, ()) == "blurry · 0.4% of person 16–31 px · z −3.4"

def test_a_blurry_queue_shows_crop_tiles_read_from_pixels(qtbot, tmp_path): ...
    # the grid on: a tile's pixmap is the box's crop (not the whole frame): its size ratio
    # follows the crop's, and a pixel inside the box matches the source image's texture region
def test_the_spotlight_dims_outside_a_blurry_box(qtbot, tmp_path): ...     # read from canvas pixels
```

- [ ] **Step 2: Run** them — Expected: FAIL.
- [ ] **Step 3: Implement**; the dash-free spotlight needs no change (no model box).
- [ ] **Step 4: Run** them — Expected: pass. Screenshot the grid and the full frame on the
  blur dataset (`widget.grab().save(...)` into the scratchpad) and look at them.
- [ ] **Step 5: Commit** `ui: a blurry box's row, caption, inspector line and crop tile`.

### Task 3: Keys on a blurry box

**Files:**
- Modify: `src/deeplabeling/ui/editing.py` (`Editing.take_model_class`, `Editing.take_model_box`)
- Modify: `src/deeplabeling/ui/grid_actions.py` (`take_model_class`, `take_model_box`)
- Test: `tests/ui/test_blurry_window.py`

- [ ] **Step 1: Write the failing tests:** `M` and `B` in the full frame emit
  `not for blurry boxes` and leave the file byte-identical; a multi-tile `M` says
  `nothing changed; skipped 2 (not for blurry boxes)`; `D` dismisses and moves on;
  a multi-tile `Delete` is one edit, undone whole; after a `Delete` in the full frame the
  item shows *fixed* on its row.
- [ ] **Step 2: Run** — Expected: the `M`/`B` tests FAIL (today's texts differ); the others may
  already pass (they are Find Bad's code): keep them as the proof.
- [ ] **Step 3: Implement**: test `finding.kind == "blurry"` first in each.
- [ ] **Step 4: Run** — Expected: pass.
- [ ] **Step 5: Commit** `ui: M and B say they are not for blurry boxes`.

### Task 4: The queue editor

**Files:**
- Modify: `src/deeplabeling/ui/queue_editor.py`, `src/deeplabeling/ui/prompter.py` (types)
- Test: `tests/ui/test_queue_editor.py` (extend)

**Interfaces:**
- Produces: `SOURCES = ("Images", "Find Bad", "Blurry")`; `QueueEditor.blur_rows: QGroupBox`,
  `blur_share: QLineEdit`, `blur_min_side: QLineEdit`; `QueueEditor.source()` returns
  `Blurry(self.filter(), BlurSettings(share / 100, min_side))`.

- [ ] **Step 1: Write the failing tests:** seeded from `Blurry(ImageFilter(("val",), ()),
  BlurSettings(0.1, 24))` the dialog shows `Blurry`, `10`, `24` and `source()` returns it;
  the group shows only for Blurry and its title and warning line are the constraints';
  `0`, `101`, `x` in share and `7` in minimum side are refused by name and the dialog stays
  open; every Blurry field is visible inside the dialog and none overlaps (geometry).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement**: share typed in percent (`_text(share * 100)`), minimum side an
  integer (`int(text)`, refused as not a number otherwise).
- [ ] **Step 4: Run** — Expected: pass; screenshot the dialog in Blurry mode and look at it.
- [ ] **Step 5: Commit** `ui: the queue editor's Blurry source`.

### Task 5: Measure, and the docs

**Files:**
- Create: `tools/measure_blurry.py` (read-only; app state in a temporary folder, as
  `tools/measure_find_bad.py` does)
- Modify: `docs/design/2026-10-27-blurry.md` (the measured column), `docs/knowledge/caches.md`

- [ ] **Step 1: Write the script**: open the yaml in a `Session` window offscreen, set a
  `Blurry()` queue, time the cold build to complete, then a warm rebuild; record the event
  loop's longest wait while building (a 10 ms `QTimer` timing its own gaps); then switch the
  grid on and time the first page of crop tiles. Print the four numbers.
- [ ] **Step 2: Run** it on `/home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-person/data_human_040226/data_040226.yaml`
  — Expected: within the spec's targets; a miss is recorded with its value, not dropped.
- [ ] **Step 3: Fill the spec's Performance table** with the measured values and the date;
  add the `sharpness.sqlite` section to `docs/knowledge/caches.md`.
- [ ] **Step 4: Run** the full suite and `python3 tools/check_docs.py` — Expected: green, 0 failures.
- [ ] **Step 5: Commit** `tools: measure the Blurry queue; the docs`.
