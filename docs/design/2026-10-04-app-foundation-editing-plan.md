# Slice 1c: editing on the canvas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make slice 1 an editor. The user draws boxes of the active class; selects by click, cycle, Shift+click, Tab or Ctrl+A; moves and resizes with handles; reclassifies with `1`–`0`, the `C` picker or the inspector's palette; deletes; and copies and pastes, all undoable. The inspector's box list and the canvas show one selection.

**Architecture:** Three new pieces. `ui/actions.py` (no Qt) turns "these boxes, this change" into an `Intent`. `ui/selection.py` holds the one selection by box identity (`LineRef`), not by index. `ui/editing.py` turns the canvas's gestures and the editing keys into intents for `Session.apply`. The canvas edits nothing: a finished drag or click becomes a signal in image pixels (`drawn`, `picked`, `moved`, `resized`). While the mouse moves, it only previews. Class colours and hotkeys are assigned by name when a dataset opens, and an edit waits until its image is decoded.

**Tech Stack:** PySide6 6.6 (conda base), pytest-qt (offscreen), the core from plan 1a and the viewer from plan 1b.

**Spec:** [2026-10-04-app-foundation.md](2026-10-04-app-foundation.md). This plan implements the editing parts of its Window section: the canvas's **Mouse** bullet, the inspector's **Classes** and **Boxes**, the editing rows of the **Keys** table, and the crosshair layer. It also implements the class colours and hotkeys by name from its Dataset section, and the polygon-move refusal from its Errors table. It does not cover the grid, which is plan 1d. The earlier plans are [the core](2026-10-04-app-foundation-core-plan.md) and [the viewer](2026-10-04-app-foundation-ui-plan.md).

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base, PySide6 6.6.0). Bare `python3` can be another conda env ([environment.md](../knowledge/environment.md#python)). Install nothing.
- **One write path** ([landmine 1](../../CLAUDE.md#landmines)): every label change goes through `Session.apply`, which goes through `Editor.apply`. The canvas, the inspector and `Editing` never write a file. Deleting every box leaves an empty file, which is a negative sample, never a deletion.
- **One owner** ([landmine 2](../../CLAUDE.md#landmines)): no widget keeps labels. The canvas gets `BoxView`s to draw. The selection holds `LineRef`s (index hint, class and box), and `Selection.indices(labels)` locates them again in the current labels. A box that changed drops out of the selection; it is never acted on under a stale index.
- **Threads** ([landmine 3](../../CLAUDE.md#landmines)): nothing in this plan runs on a worker.
- **Verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines); the `run-and-verify-ui` skill): canvas tests read pixels back from `grab()`. Window tests drive real mouse events and real keys, then read the label file's bytes and what is on screen.
- **`src/deeplabeling/core/` is not changed.** Every edit is built from the core's existing ops (`AddBox`, `SetBox`, `SetClass`, `DeleteLine`).
- **PySide6 keeps every lambda connected to a signal** ([environment.md](../knowledge/environment.md#pyside6-and-numpy)). A connection made per event or per object connects a bound method of a `QObject`. Lambdas are only for connections made once per window.
- **Tests write only to temporary folders** (landmine 10); the autouse `state_dir` fixture guards the real `.deeplabeling/`.
- **Doc rules:** one fact, one home; a command over a restatement; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice1-editing` from `main`. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit. The `-o addopts=` is there because the project's `-q` plus another `-q` hides the summary line.
- **pytest-qt habits:** `qtbot.waitUntil` takes a callback returning a bool. Window shortcuts need `with qtbot.waitActive(w): w.show(); w.activateWindow()`; `start` in `tests/ui/drive.py` does it. A script run outside `tests/` must set `QT_QPA_PLATFORM=offscreen` itself.

## Review Focus

These are the inputs the spec implies that are most likely to hurt someone editing. Each has a named test in the task that owns the code:

1. **The label file changes outside the app while a box is selected or being dragged.** The drag is dropped, and the selection follows its boxes by identity or lets them go. An edit built from the old view is refused, never applied to the wrong line. *(Task 2 `test_a_selection_finds_its_boxes_after_lines_move`, `test_a_selected_box_that_is_gone_drops_out`; Task 3 `test_labels_redrawn_during_a_drag_cancel_it`.)*
2. **Editing an image that is still decoding.** Until it decodes, "could not read" must not become "no boxes": the edit is refused with a notice, and nothing is written. *(Task 1 `test_an_image_still_loading_is_not_edited`.)*
3. **Moving or resizing a polygon.** The move is refused where it can be seen, and the file is untouched; a polygon never silently becomes a box. *(Task 4 `test_moving_a_polygon_is_refused_where_it_can_be_seen`.)*
4. **Geometry past the image's edge:** a drag outside the frame, a box moved against an edge, a pasted box from a larger crop. Every box is clamped inside the image, and a box with nothing left inside is skipped. *(Task 2 `test_move_keeps_the_size_and_stays_inside_the_image`, `test_paste_clamps_and_skips_what_is_not_a_box_of_a_known_class`; Task 3 `test_a_drawn_box_is_clamped_to_the_image`.)*
5. **Keys acting on boxes the user cannot see.** With the labels layer off, the selection is cleared and the mouse does not edit, so `Del` deletes nothing hidden. *(Task 3 `test_nothing_is_edited_without_an_image_or_with_the_labels_hidden`; Task 4 `test_hiding_the_labels_clears_the_selection`.)*

## Found while building this plan

The plan's code was built and run in a scratch copy of `main` before it was written down, and the plan was then dry-run task by task on a fresh copy: 497 tests pass. Along the way:

- **Two 1b tests passed only because decoding was fast.** Once edits wait for the decoded image, `N` pressed straight after `go_to` was refused. The tests now wait for the image, with `wait_decoded` in `tests/fixtures.py`.
- **A spike outside `tests/` found no shortcut firing.** It ran on the real display `:0`, where synthetic keys never reach the window. Offscreen, `Tab`, `Shift+Tab` (which arrives as `Backtab`), `Esc`, `Delete`, `Backspace`, the digits and `Ctrl+A` all fire as window shortcuts, and the clipboard works. This is now a lesson in the `run-and-verify-ui` skill.
- **A selected box's handles are drawn white over its edge,** so a pixel test sampling an edge must sample between handles.

## Decisions this plan makes

The spec leaves these open; each is pinned by a test, and Task 6 writes the design-level ones into the spec.

- **Colours and hotkeys are assigned by name when a dataset opens, and stored.** The keys are digits only, unique within one class list. A class past the tenth has no key and is reached with `C`.
- **A dataset without names** (a folder with no `classes.txt`) offers ids 0–9 on the digit keys.
- **An edit waits until its image is decoded.**
- **What the selection is after an edit.** A drawn or pasted box is selected. A reclassify, move or resize keeps the same boxes selected. A delete clears the selection.
- **A press inside a selected box moves it,** with or without Shift. A press anywhere else draws, even over an unselected box, because boxes inside boxes (a person in a bus) are normal.
- **A click on empty space clears the selection; a Shift+click there changes nothing.**
- **With the labels layer off,** the mouse only zooms and pans, and the selection is cleared.
- **The crosshair** is a global layer setting, off by default, with no key, and spans the image.
- **The palette marks the active class with ✎.** It has no selection highlight of its own, so that mark is the only one.
- **The grid** (`G`, thumbnails, mark page, `↑` `↓` by row) **moves to plan 1d.**

## Left for plan 1d

- **The grid:** `G`, thumbnails decoded at display size into a 64 MB cache, mark page, and `↑` `↓` moving by row.
- **Two minor findings deferred from plan 1b:** `Ctrl+Z` with no dataset open raises instead of saying "nothing to undo", and a queue build that fails leaves the chip saying "building…".

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/ui/classes.py`, `src/deeplabeling/ui/session.py` | colours and hotkeys by name; edits wait for the decoded image | 1 |
| `src/deeplabeling/ui/actions.py`, `src/deeplabeling/ui/selection.py` | every edit as an intent, without Qt; the one selection, by identity | 2 |
| `src/deeplabeling/ui/canvas.py`, `tests/ui/drive.py` | drawing, picking, moving and resizing gestures; handles; the crosshair; the test mouse | 3 |
| `src/deeplabeling/ui/editing.py`, `class_picker.py`, `keymap.py`, `settings_ui.py`, `prompter.py`, `main_window.py` | gestures and keys to intents; the `C` picker; the editing keys; the crosshair setting | 4 |
| `src/deeplabeling/ui/inspector.py` | the palette and the box list act on the selection | 5 |
| the spec, `CLAUDE.md`, the `run-and-verify-ui` skill | the end-to-end test and the docs | 6 |

UI tests live in `tests/ui/`. Their basenames are unique across `tests/`, and they import shared helpers as `from fixtures import …` and `from drive import …`.

---

### Task 1: Classes by name, and edits wait for the decoded image

**Files:**
- Modify: `src/deeplabeling/ui/classes.py` (replaced whole), `src/deeplabeling/ui/session.py`
- Test: `tests/ui/test_boxes.py` (replaced whole), `tests/ui/test_session.py`, `tests/ui/test_main_window.py`, `tests/fixtures.py`

**Interfaces:**
- Consumes: `CLASS_COLORS` and `CLASS_HOTKEYS` (root-scope settings in `deeplabeling.core.workspace`); `Workspace.root_settings`; `ImageCache.get` (plan 1b).
- Produces in `deeplabeling.ui.classes`:
  - `assign_classes(names, colors, hotkeys) -> (colors, hotkeys)`, which returns new maps and keeps what is stored by name;
  - `class_infos(dataset, colors, hotkeys) -> list[ClassInfo]`, which reads only stored values and, for a dataset without names, gives ids 0–9 named `"0"`–`"9"` on keys `1`–`0`;
  - `class_with_hotkey(infos, key) -> ClassInfo | None`.
- Produces in `Session`:
  - on open, every class name has a stored colour, and the first ten have a digit key;
  - `Session.apply` refuses an intent while its image is not decoded, with the notice "the image is still loading".
- Produces in `tests/fixtures.py`: `wait_decoded(qtbot, session, image)`.

- [ ] **Step 1: Branch, and commit this plan**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout main && git pull --ff-only && git checkout -b slice1-editing
git add docs/design/2026-10-04-app-foundation-editing-plan.md
git commit -m "docs: the slice 1c editing plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Replace `tests/ui/test_boxes.py` with:

```python
import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.store import LabelStore
from deeplabeling.ui.boxes import box_views
from deeplabeling.ui.classes import PALETTE, UNKNOWN, assign_classes, class_infos, class_with_hotkey, text_color

SIZE = (100, 50)


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


def views(dataset, ds, name, **kw):
    labels = LabelStore(dataset).get(ds.img(name))
    return {v.index: v for v in box_views(labels, dataset, SIZE, kw.pop("colors", {}), **kw)}


def test_captions_name_the_class_and_count_stacked_boxes(dataset, ds):
    v = views(dataset, ds, "bad/ok.jpg")
    assert {i: v[i].caption for i in v} == {
        0: "car x4", 1: "#99? x2", 2: "#-1? x2", 3: "person",
        5: "person x4", 6: "person x4", 10: "person x4"}


def test_an_id_outside_the_names_is_grey_and_unknown(dataset, ds):
    v = views(dataset, ds, "bad/ok.jpg")
    assert not v[1].known and v[1].color == UNKNOWN
    assert v[0].known and v[0].color == PALETTE[1]


def test_boxes_are_in_image_pixels(dataset, ds):
    assert views(dataset, ds, "bad/ok.jpg")[0].rect == pytest.approx((40, 20, 60, 30))


def test_a_polygon_keeps_its_points(dataset, ds):
    v = views(dataset, ds, "seg/poly1.jpg")
    points = [c for point in v[0].polygon for c in point]
    assert points == pytest.approx([10, 5, 20, 5, 20, 10, 10, 10])
    assert v[0].rect == pytest.approx((10, 5, 20, 10))


def test_colour_overrides_and_highlight(dataset, ds):
    v = views(dataset, ds, "bad/ok.jpg", colors={"car": "#123456"}, highlight=frozenset({3}))
    assert v[0].color == "#123456"
    assert v[3].highlighted and not v[0].highlighted


def test_without_names_captions_are_ids(ds):
    folder = Dataset.open(ds.root / "camA/images")
    labels = LabelStore(folder).get(ds.img("camA/0001.jpg"))
    assert [v.caption for v in box_views(labels, folder, SIZE, {})] == ["0", "1"]


def test_class_infos_read_the_colour_and_key_stored_for_each_name(dataset):
    infos = class_infos(dataset, {"bus_l": "#000000"}, {"car": "7"})
    assert [(i.name, i.hotkey) for i in infos] == [("person", ""), ("car", "7"), ("bus_m", ""), ("bus_l", "")]
    assert infos[3].color == "#000000" and infos[0].color == PALETTE[0]


def test_a_first_class_list_takes_colours_and_digits_in_order():
    colors, keys = assign_classes([f"c{i}" for i in range(12)], {}, {})
    assert [colors[f"c{i}"] for i in range(12)] == list(PALETTE[:12])
    assert [keys[f"c{i}"] for i in range(12)] == list("1234567890") + ["", ""]


def test_a_second_class_list_keeps_shared_names_and_fills_in_new_ones():
    colors, keys = assign_classes(["person", "car", "bus_m", "bus_l"], {}, {})
    colors, keys = assign_classes(["car", "truck", "person"], colors, keys)
    assert (keys["car"], keys["person"], keys["truck"]) == ("2", "1", "3")
    assert colors["truck"] == PALETTE[2]               # first colour unused by THIS list
    assert colors["car"] == PALETTE[1] and colors["person"] == PALETTE[0]


def test_two_names_sharing_a_stored_key_in_one_list_do_not_collide():
    _, keys = assign_classes(["a", "b"], {}, {"a": "5", "b": "5"})
    assert keys == {"a": "5", "b": "1"}


def test_assignment_does_not_change_its_arguments():
    colors, keys = {"a": "#123456"}, {"a": "9"}
    assign_classes(["a", "b"], colors, keys)
    assert colors == {"a": "#123456"} and keys == {"a": "9"}


def test_the_class_with_a_hotkey(dataset):
    infos = class_infos(dataset, {}, {"car": "2", "bus_l": "4"})
    assert class_with_hotkey(infos, "4").name == "bus_l" and class_with_hotkey(infos, "9") is None


def test_text_colour_contrasts():
    assert text_color("#000075") == "#ffffff" and text_color("#fffac8") == "#000000"


def test_a_dataset_without_names_offers_the_bare_ids_0_to_9(ds):
    folder = Dataset.open(ds.root / "camA" / "images")         # no classes.txt beside it
    infos = class_infos(folder, {}, {})
    assert [(i.cls_id, i.name, i.hotkey) for i in infos[:2]] == [(0, "0", "1"), (1, "1", "2")]
    assert len(infos) == 10 and infos[9].hotkey == "0" and infos[3].color == PALETTE[3]
```

Append to `tests/fixtures.py`:

```python
def wait_decoded(qtbot, session, image):
    """Edits wait for the image to be decoded; so do tests that edit."""
    qtbot.waitUntil(lambda: session.images.get(image) is not None, timeout=5000)
```

In `tests/ui/test_session.py`, replace:

```python
from deeplabeling.core.queue import HasClass, ImageFilter
from deeplabeling.ui.session import OUT_OF_RANGE, Session
from fixtures import FakePrompter, assert_only_changed, open_session
```

with:

```python
from deeplabeling.core.queue import HasClass, ImageFilter
from deeplabeling.core.workspace import CLASS_COLORS, CLASS_HOTKEYS
from deeplabeling.ui.classes import PALETTE
from deeplabeling.ui.session import OUT_OF_RANGE, Session
from fixtures import FakePrompter, assert_only_changed, open_session, wait_decoded
```

In `tests/ui/test_session.py`, replace:

```python
def test_mark_negative_creates_an_empty_file_and_undo_removes_it(session, ds):
    session.go_to("camA/images/0003.jpg")
```

with:

```python
def test_mark_negative_creates_an_empty_file_and_undo_removes_it(qtbot, session, ds):
    session.go_to("camA/images/0003.jpg")
    wait_decoded(qtbot, session, ds.img("camA/0003.jpg"))
```

In `tests/ui/test_session.py`, replace:

```python
def test_mark_negative_on_a_labelled_image_is_refused_visibly(session, ds):
```

with:

```python
def test_mark_negative_on_a_labelled_image_is_refused_visibly(qtbot, session, ds):
    wait_decoded(qtbot, session, ds.img("camA/0001.jpg"))
```

In `tests/ui/test_session.py`, replace:

```python
def test_undo_goes_to_the_image_it_changes(session, ds):
    session.go_to("camA/images/0003.jpg")
```

with:

```python
def test_undo_goes_to_the_image_it_changes(qtbot, session, ds):
    session.go_to("camA/images/0003.jpg")
    wait_decoded(qtbot, session, ds.img("camA/0003.jpg"))
```

Append to `tests/ui/test_session.py`:

```python
def test_an_image_still_loading_is_not_edited(qtbot, session, ds):
    notices, before = record(session.notice), ds.snapshot()
    session.apply(Intent(ds.img("seg/poly1.jpg"), (AddBox(0, BOX),), "draw"))   # never shown
    assert_only_changed(before, ds.snapshot(), set())
    assert "still loading" in notices[-1][1]


def test_class_colours_and_hotkeys_follow_the_name_across_yamls(qtbot, ds):
    s = open_session(qtbot, ds.yaml)
    assert s.workspace.root_settings.get(CLASS_HOTKEYS) == {"person": "1", "car": "2", "bus_m": "3", "bus_l": "4"}
    s.close()
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data["names"] = ["car", "truck", "person"]
    other = ds.root / "other.yaml"
    other.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    again = open_session(qtbot, other)
    keys, colors = again.workspace.root_settings.get(CLASS_HOTKEYS), again.workspace.root_settings.get(CLASS_COLORS)
    assert (keys["car"], keys["person"], keys["truck"]) == ("2", "1", "3")
    assert (colors["car"], colors["truck"]) == (PALETTE[1], PALETTE[2])
    again.close()
```

In `tests/ui/test_main_window.py`, replace:

```python
    window.session.go_to("camA/images/0003.jpg")
    qtbot.keyClick(window, Qt.Key_N)
```

with:

```python
    window.session.go_to("camA/images/0003.jpg")
    qtbot.waitUntil(lambda: window._shown == ds.img("camA/0003.jpg"))     # edits wait for the image
    qtbot.keyClick(window, Qt.Key_N)
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_boxes.py`
Expected: `ImportError: cannot import name 'assign_classes' from 'deeplabeling.ui.classes'`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_session.py -k "still_loading or follow_the_name"`
Expected: 2 failed, 29 deselected. The edit is written although the image never decoded, and no hotkeys are stored.

- [ ] **Step 4: Assign classes by name, and gate edits on the decoded image**

Replace `src/deeplabeling/ui/classes.py` with:

```python
"""Class colours and hotkeys, keyed by class name so every yaml of a root shares them
(docs/design/2026-10-04-app-foundation.md#dataset)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..core.dataset import Dataset

#: Distinct colours, handed out in order; no greys, which mean "unknown class".
PALETTE = (
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6",
    "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324", "#fffac8", "#800000",
    "#aaffc3", "#808000", "#ffd8b1", "#000075", "#ffe119", "#a9a9f5",
)
#: A class id the dataset's names do not cover.
UNKNOWN = "#9e9e9e"
#: The hotkeys there are; a class past the tenth is chosen with the class picker.
DEFAULT_HOTKEYS = "1234567890"


@dataclass(frozen=True)
class ClassInfo:
    cls_id: int
    name: str
    color: str
    hotkey: str     #: "" when the class has none


def assign_classes(names: Sequence[str], colors: dict[str, str],
                   hotkeys: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """A colour and a hotkey for every class name, keeping what is stored by name.

    The yamls of one root differ in class ids but share names (car is id 3 in one and 5
    in another), so a class keeps its colour and key by name. A name seen for the first
    time takes the first colour and the first digit no other class of THIS list uses;
    when two names of one list hold the same stored key, the first keeps it and the
    other is given a free one. Returns new maps; the arguments are not changed.
    """
    colors, hotkeys = dict(colors), dict(hotkeys)
    used = {colors[n] for n in names if n in colors}
    free_colors = [c for c in PALETTE if c not in used]
    for i, name in enumerate(names):
        if name not in colors:
            colors[name] = free_colors.pop(0) if free_colors else PALETTE[i % len(PALETTE)]
    taken: set[str] = set()
    waiting = []
    for name in names:
        key = hotkeys.get(name, "")
        if key and key not in taken:
            taken.add(key)
        else:
            waiting.append(name)
    free_keys = [k for k in DEFAULT_HOTKEYS if k not in taken]
    for name in waiting:
        hotkeys[name] = free_keys.pop(0) if free_keys else ""
    return colors, hotkeys


def class_color(cls_id: int, name: str, overrides: dict[str, str]) -> str:
    """The colour of a class: the one stored for its name, else the palette's for its id."""
    return overrides.get(name) or PALETTE[cls_id % len(PALETTE)]


def class_infos(dataset: Dataset, colors: dict[str, str], hotkeys: dict[str, str]) -> list[ClassInfo]:
    """Every class of the dataset, with the colour and hotkey stored for its name. A
    dataset without names (a folder with no classes.txt) shows bare ids, so it offers
    the ids 0-9 on the digit keys."""
    if not dataset.names:
        return [ClassInfo(i, str(i), class_color(i, str(i), colors), key)
                for i, key in enumerate(DEFAULT_HOTKEYS)]
    return [ClassInfo(cls_id, name, class_color(cls_id, name, colors), hotkeys.get(name, ""))
            for cls_id, name in enumerate(dataset.names)]


def class_with_hotkey(infos: Sequence[ClassInfo], key: str) -> ClassInfo | None:
    return next((info for info in infos if info.hotkey == key), None)


def text_color(background: str) -> str:
    """Black or white, whichever reads better on `background` (#rrggbb)."""
    r, g, b = (int(background[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#ffffff"
```

In `src/deeplabeling/ui/session.py`, replace:

```python
from ..core.workspace import QUEUE_CURSOR, QUEUE_SOURCE, OpenCancelled, Workspace
```

with:

```python
from ..core.workspace import CLASS_COLORS, CLASS_HOTKEYS, QUEUE_CURSOR, QUEUE_SOURCE, OpenCancelled, Workspace
from .classes import assign_classes
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self._by_rel = {e.rel: e for e in ws.dataset.images}
        self._follow = self._seen = self._keys = None
        remember_source(self.settings, *self.current_source())
```

with:

```python
        self._by_rel = {e.rel: e for e in ws.dataset.images}
        self._follow = self._seen = self._keys = None
        root = ws.root_settings
        colors, hotkeys = assign_classes(ws.dataset.names, root.get(CLASS_COLORS), root.get(CLASS_HOTKEYS))
        root.set(CLASS_COLORS, colors)
        root.set(CLASS_HOTKEYS, hotkeys)
        remember_source(self.settings, *self.current_source())
```

In `src/deeplabeling/ui/session.py`, replace:

```python
                             "so its labels are not edited", intent.image)
            return None
        try:
```

with:

```python
                             "so its labels are not edited", intent.image)
            return None
        if self.images.get(intent.image) is None:
            # Until it is decoded, whether it CAN be decoded is unknown -- and "could not
            # read" must never become "no boxes" (legacy defect #2).
            self.notice.emit("error", f"{rel}: the image is still loading, so its labels "
                             "are not edited yet", intent.image)
            return None
        try:
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_boxes.py tests/ui/test_session.py tests/ui/test_main_window.py`
Expected: 66 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 443 passed.

```bash
git add src/deeplabeling/ui tests
git commit -m "ui: class colours and keys by name; edits wait for the decoded image" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Every edit as an intent, and the selection

**Files:**
- Create: `src/deeplabeling/ui/actions.py`, `src/deeplabeling/ui/selection.py`
- Test: `tests/ui/test_actions.py`

**Interfaces:**
- Consumes from the core:
  - `AddBox`, `SetBox`, `SetClass`, `DeleteLine`, `Intent`, `LineRef` and `materialize` (edits);
  - `locate_line` and `parse_label_text` (labelio);
  - `corners` and `px_to_norm` (geometry);
  - `ImageLabels`, with `.image`, `.lines`, `.boxes` and `.ref(i)` (store).
- Produces in `deeplabeling.ui.actions`. Boxes are normalised `(cx, cy, w, h)`, and every function returns `None` when there is nothing to do:
  - `add_box(image, cls_id, bbox) -> Intent`;
  - `reclassify(image, labels, indices, cls_id) -> Intent | None`, which skips boxes already of that class;
  - `delete(image, labels, indices) -> Intent | None`;
  - `move(image, labels, indices, dx, dy) -> Intent | None`, where `dx` and `dy` are normalised, and each box keeps its size and stays inside the image;
  - `resize(image, labels, index, bbox) -> Intent | None`;
  - `copy_text(labels, indices) -> str`, in label-file form, with a polygon copied as its extent;
  - `clamp_box(bbox) -> Box | None`;
  - `paste(image, text, class_ok) -> Intent | None`.
  - Indices that are not boxes (unparsed lines) are ignored.
- Produces in `deeplabeling.ui.selection`:
  - `Selection(QObject)`, with the signal `changed()` and the attributes `.image` and `.refs` (a tuple of `LineRef`);
  - `.set(image, refs)`, which emits only on a change;
  - `.select(labels, indices)`, which keeps boxes only;
  - `.clear()`;
  - `.indices(labels) -> list[int]`, sorted, which returns `[]` for another image and drops a box that is gone;
  - `len(selection)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_actions.py`:

```python
import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, SetBox, SetClass, materialize
from deeplabeling.core.store import LabelStore
from deeplabeling.ui import actions
from deeplabeling.ui.selection import Selection
from fixtures import CAMA_0001

BOX = (0.5, 0.5, 0.2, 0.2)


@pytest.fixture
def store(ds):
    return LabelStore(Dataset.open(ds.yaml))


def written(store, intent) -> str:
    """The file an intent would leave, computed without writing it."""
    labels = store.get(intent.image)
    return materialize(labels.raw, intent.ops, class_ok=store.dataset.known).decode()


def test_add_box(ds):
    intent = actions.add_box(ds.img("camA/0003.jpg"), 2, BOX)
    assert intent.ops == (AddBox(2, BOX),) and intent.description == "draw a box"


def test_reclassify_skips_boxes_already_of_that_class(store, ds):
    img = ds.img("camA/0001.jpg")
    labels = store.get(img)
    intent = actions.reclassify(img, labels, [0, 1], 1)
    assert [type(op) for op in intent.ops] == [SetClass] and intent.description == "reclassify 1 box"
    assert written(store, intent) == "1" + CAMA_0001[1:]
    assert actions.reclassify(img, labels, [1], 1) is None


def test_delete(store, ds):
    img = ds.img("camA/0001.jpg")
    labels = store.get(img)
    intent = actions.delete(img, labels, [1, 0])
    assert written(store, intent) == "" and intent.description == "delete 2 boxes"
    assert actions.delete(img, labels, []) is None


def test_lines_that_are_not_boxes_are_ignored(store, ds):
    img = ds.img("bad/ok.jpg")
    labels = store.get(img)                       # GAUNTLET: line 4 is not a box
    assert actions.delete(img, labels, [4]) is None
    assert len(actions.delete(img, labels, [4, 0]).ops) == 1


def test_move_keeps_the_size_and_stays_inside_the_image(store, ds):
    img = ds.img("camA/0001.jpg")
    labels = store.get(img)
    intent = actions.move(img, labels, [0], 0.6, 0.0)
    assert intent.ops[0].bbox == pytest.approx((0.9, 0.5, 0.2, 0.3))
    assert isinstance(intent.ops[0], SetBox) and intent.description == "move 1 box"
    assert actions.move(img, labels, [0], 0, 0) is None


def test_resize(store, ds):
    img = ds.img("bad/ok.jpg")
    labels = store.get(img)
    intent = actions.resize(img, labels, 0, (0.4, 0.4, 0.2, 0.2))
    assert written(store, intent).startswith("1 0.400000 0.400000 0.200000 0.200000\n")
    assert actions.resize(img, labels, 4, BOX) is None


def test_copy_writes_label_lines_and_a_polygon_as_its_extent(store, ds):
    poly = store.get(ds.img("seg/poly1.jpg"))
    assert actions.copy_text(poly, [0]) == "0 0.150000 0.150000 0.100000 0.100000\n"


def test_a_copy_pastes_back_as_the_same_lines(store, ds):
    text = actions.copy_text(store.get(ds.img("camA/0001.jpg")), [0, 1])
    intent = actions.paste(ds.img("camA/0003.jpg"), text, store.dataset.known)
    assert written(store, intent) == CAMA_0001 and intent.description == "paste 2 boxes"


def test_paste_clamps_and_skips_what_is_not_a_box_of_a_known_class(store, ds):
    text = "0 0.95 0.5 0.2 0.2\n9 0.5 0.5 0.1 0.1\n-1 0.5 0.5 0.1 0.1\nhello\n1 2.0 2.0 0.1 0.1\n"
    intent = actions.paste(ds.img("camA/0003.jpg"), text, store.dataset.known)
    assert len(intent.ops) == 1 and intent.ops[0].bbox == pytest.approx((0.925, 0.5, 0.15, 0.2))
    assert actions.paste(ds.img("camA/0003.jpg"), "nothing here", store.dataset.known) is None


def test_a_selection_finds_its_boxes_after_lines_move(qtbot, store, ds):
    img = ds.img("camA/0001.jpg")
    selection = Selection()
    selection.select(store.get(img), [1])
    ds.lbl("camA/0001").write_bytes(b"2 0.1 0.1 0.05 0.05\n" + CAMA_0001.encode())   # a line above
    assert selection.indices(store.get(img)) == [2]


def test_a_selected_box_that_is_gone_drops_out(qtbot, store, ds):
    img = ds.img("camA/0001.jpg")
    selection = Selection()
    selection.select(store.get(img), [0, 1])
    ds.lbl("camA/0001").write_bytes(CAMA_0001.splitlines(keepends=True)[1].encode())
    assert selection.indices(store.get(img)) == [0]


def test_another_image_has_nothing_selected(qtbot, store, ds):
    selection = Selection()
    selection.select(store.get(ds.img("camA/0001.jpg")), [0])
    assert selection.indices(store.get(ds.img("camB/0001.jpg"))) == []


def test_only_lines_that_are_boxes_can_be_selected(qtbot, store, ds):
    selection = Selection()
    selection.select(store.get(ds.img("bad/ok.jpg")), [4, 7])
    assert len(selection) == 0


def test_changed_fires_only_when_the_selection_changes(qtbot, store, ds):
    labels = store.get(ds.img("camA/0001.jpg"))
    selection, seen = Selection(), []
    selection.changed.connect(lambda: seen.append(1))
    selection.select(labels, [0])
    selection.select(labels, [0])
    selection.clear()
    selection.clear()
    assert seen == [1, 1]
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_actions.py`
Expected: `ImportError: cannot import name 'actions' from 'deeplabeling.ui'`.

- [ ] **Step 3: Write the two modules**

Create `src/deeplabeling/ui/actions.py`:

```python
"""The editing actions as intents, built from what is on screen. No Qt: tested headless.

Each function takes the image's labels as shown and the line indices it acts on, and
returns an Intent for Session.apply -- or None when there is nothing to do. The core
locates every line again before writing, so an intent built from a stale view is
refused, never misapplied (docs/knowledge/label-files.md#locate-before-writing).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from ..core.edits import AddBox, DeleteLine, Intent, SetBox, SetClass
from ..core.geometry import Box, corners, px_to_norm
from ..core.labelio import parse_label_text
from ..core.store import ImageLabels


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}es"


def _rows(labels: ImageLabels, indices: Iterable[int]) -> list[int]:
    """The given indices that are boxes (parsed lines), in file order."""
    parsed = {i for i, _ in labels.boxes}
    return sorted(i for i in set(indices) if i in parsed)


def add_box(image, cls_id: int, bbox: Box) -> Intent:
    return Intent(Path(image), (AddBox(cls_id, bbox),), "draw a box")


def reclassify(image, labels: ImageLabels, indices: Iterable[int], cls_id: int) -> Intent | None:
    rows = [i for i in _rows(labels, indices) if labels.lines[i].cls_id != cls_id]
    if not rows:
        return None
    return Intent(Path(image), tuple(SetClass(labels.ref(i), cls_id) for i in rows),
                  f"reclassify {_plural(len(rows), 'box')}")


def delete(image, labels: ImageLabels, indices: Iterable[int]) -> Intent | None:
    rows = _rows(labels, indices)
    if not rows:
        return None
    return Intent(Path(image), tuple(DeleteLine(labels.ref(i)) for i in rows),
                  f"delete {_plural(len(rows), 'box')}")


def move(image, labels: ImageLabels, indices: Iterable[int], dx: float, dy: float) -> Intent | None:
    """Shift boxes by (dx, dy), normalised. Each keeps its size and stays inside the image."""
    rows = _rows(labels, indices)
    if not rows or (dx == 0 and dy == 0):
        return None
    ops = []
    for i in rows:
        cx, cy, w, h = labels.lines[i].bbox
        nx = min(max(cx + dx, w / 2), 1 - w / 2)
        ny = min(max(cy + dy, h / 2), 1 - h / 2)
        ops.append(SetBox(labels.ref(i), (nx, ny, w, h)))
    return Intent(Path(image), tuple(ops), f"move {_plural(len(rows), 'box')}")


def resize(image, labels: ImageLabels, index: int, bbox: Box) -> Intent | None:
    if not _rows(labels, [index]):
        return None
    return Intent(Path(image), (SetBox(labels.ref(index), bbox),), "resize a box")


def copy_text(labels: ImageLabels, indices: Iterable[int]) -> str:
    """The boxes as label-file lines; a polygon is copied as its extent."""
    out = []
    for i in _rows(labels, indices):
        line = labels.lines[i]
        cx, cy, w, h = line.bbox
        out.append(f"{line.cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
    return "".join(out)


def clamp_box(bbox: Box) -> Box | None:
    """The part of a normalised box inside the image, or None when nothing is left."""
    cx, cy, w, h = px_to_norm(*corners(bbox), 1, 1)
    return (cx, cy, w, h) if w > 0 and h > 0 else None


def paste(image, text: str, class_ok: Callable[[int], bool]) -> Intent | None:
    """Boxes from text in label-file form -- what copy_text writes, or lines of any label
    file -- clamped into the image. A line that is no box of a known class is skipped."""
    ops = []
    for line in parse_label_text(text):
        if not line.parsed or line.cls_id < 0 or not class_ok(line.cls_id):
            continue
        box = clamp_box(line.bbox)
        if box is not None:
            ops.append(AddBox(line.cls_id, box))
    if not ops:
        return None
    return Intent(Path(image), tuple(ops), f"paste {_plural(len(ops), 'box')}")
```

Create `src/deeplabeling/ui/selection.py`:

```python
"""The boxes selected on the image on screen.

Held by identity (LineRef: index hint, class and box), not by index: a stored index
moves when a line is added or removed, and acting on a stale one edits the wrong box
(docs/knowledge/label-files.md#locate-before-writing). The canvas and the inspector's
box list both show this one selection; neither keeps its own.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..core.edits import LineRef
from ..core.labelio import locate_line
from ..core.store import ImageLabels


class Selection(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image: Path | None = None
        self.refs: tuple[LineRef, ...] = ()

    def __len__(self) -> int:
        return len(self.refs)

    def set(self, image, refs: Iterable[LineRef]) -> None:
        image, refs = (Path(image) if image is not None else None), tuple(refs)
        if (image, refs) != (self.image, self.refs):
            self.image, self.refs = image, refs
            self.changed.emit()

    def select(self, labels: ImageLabels, indices: Iterable[int]) -> None:
        """Select these lines of `labels`; anything that is not a box is ignored."""
        parsed = {i for i, _ in labels.boxes}
        self.set(labels.image, (labels.ref(i) for i in sorted(set(indices)) if i in parsed))

    def clear(self) -> None:
        self.set(self.image, ())

    def indices(self, labels: ImageLabels) -> list[int]:
        """Where the selected boxes are now in `labels`; a box that is gone drops out."""
        if labels.image != self.image:
            return []
        found = []
        for ref in self.refs:
            i = locate_line(labels.lines, ref.cls_id, ref.bbox, ref.index)
            if i is not None and i not in found:
                found.append(i)
        return sorted(found)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_actions.py`
Expected: 14 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 457 passed.

```bash
git add src/deeplabeling/ui tests/ui
git commit -m "ui: every edit as an intent; the selection held by box identity" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Drawing, picking, moving and resizing on the canvas

**Files:**
- Modify: `src/deeplabeling/ui/canvas.py` (replaced whole)
- Create: `tests/ui/drive.py`
- Test: `tests/ui/test_canvas.py` (replaced whole)

**Interfaces:**
- Consumes: `BoxView` (plan 1b), with `.index`, `.rect` (pixels), `.polygon` and `.color`.
- Produces in `deeplabeling.ui.canvas`:
  - Signals, in image pixels:
    - `drawn(rect)`, where rect is `(x1, y1, x2, y2)` inside the image;
    - `picked(indices: list)`;
    - `moved(dx: float, dy: float)`;
    - `resized(index: int, rect)`.
  - On `Canvas`:
    - `.set_boxes(views, selected=())` and `.set_selected(indices)`. A selected box is filled; one selected box that is not a polygon shows eight handles.
    - `.set_draw_color(color)`, `.set_crosshair(on)` and `.show_crosshair`.
    - `.cancel_drag() -> bool`, True when a drag was showing.
    - `.handle_items()`.
  - The constants `DRAG_PX = 3`, `HANDLE_PX = 8`, `GRAB_PX = 6` and `HANDLES`.
- Produces in `tests/ui/drive.py`:
  - `vp(canvas, x, y)`;
  - `mouse(canvas, kind, pos, button=…, buttons=None, modifiers=…)`;
  - `drag(canvas, a, b, modifiers=…, release=True)` and `click(canvas, at, modifiers=…)`, which take scene points.

The gestures, in the order a left press is read:

1. A press on a handle of the one selected box starts a **resize**.
2. A press inside a selected box starts a **move**.
3. Any other press starts a **draw**.

A press that moves less than `DRAG_PX` before release is a **click**. A click selects the smallest box under the cursor. If the one selected box is under the cursor, the click selects the next box under it (the cycle). A Shift+click toggles the smallest box. A click on empty space clears the selection.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/drive.py`:

```python
"""Driving the UI as a person would: mouse gestures on the canvas, and a launched window."""

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication


def vp(canvas, x, y):
    """The viewport point showing scene (image pixel) point (x, y)."""
    return canvas.mapFromScene(QPointF(x, y))


def mouse(canvas, kind, pos, button=Qt.LeftButton, buttons=None, modifiers=Qt.NoModifier):
    if buttons is None:
        buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else button
    if kind == QEvent.MouseMove:
        button = Qt.NoButton
    event = QMouseEvent(kind, QPointF(pos), canvas.viewport().mapToGlobal(QPointF(pos)),
                        button, buttons, modifiers)
    QApplication.sendEvent(canvas.viewport(), event)


def drag(canvas, a, b, modifiers=Qt.NoModifier, release=True):
    """Press at scene point `a`, move to `b` in steps, and release there."""
    pa, pb = vp(canvas, *a), vp(canvas, *b)
    mouse(canvas, QEvent.MouseButtonPress, pa, modifiers=modifiers)
    for t in (0.25, 0.5, 1.0):
        mouse(canvas, QEvent.MouseMove, pa + (pb - pa) * t, modifiers=modifiers)
    if release:
        mouse(canvas, QEvent.MouseButtonRelease, pb, modifiers=modifiers)


def click(canvas, at, modifiers=Qt.NoModifier):
    drag(canvas, at, at, modifiers)
```

Replace `tests/ui/test_canvas.py` with:

```python
"""What the canvas shows, read back from its pixels (the run-and-verify-ui skill)."""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

from deeplabeling.ui.boxes import BoxView
from deeplabeling.ui.canvas import Canvas
from drive import click, drag, mouse, vp

GREY = QColor(80, 80, 80)
RED = BoxView(0, (50, 25, 150, 75), (), "#ff0000", "car", True, False)


def grey_image(w=200, h=100):
    image = QImage(w, h, QImage.Format_RGB32)
    image.fill(GREY)
    return image


@pytest.fixture
def canvas(qtbot):
    c = Canvas()
    qtbot.addWidget(c)
    c.resize(400, 300)
    c.show()
    qtbot.waitUntil(c.isVisible)
    return c


def shot(canvas):
    return canvas.viewport().grab().toImage()


def pixel(canvas, x, y, image=None):
    image = image or shot(canvas)
    return QColor(image.pixel(canvas.mapFromScene(QPointF(x, y))))


def is_red(c):
    return c.red() > 200 and c.green() < 80 and c.blue() < 80


def near(canvas, x, y, image=None, radius=2):
    """The pixels within `radius` of a scene point: a line on a pixel boundary is
    antialiased across two pixels, so one exact pixel can be half its colour."""
    image = image or shot(canvas)
    centre = canvas.mapFromScene(QPointF(x, y))
    return [QColor(image.pixel(centre.x() + dx, centre.y() + dy))
            for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)]


def test_a_box_is_drawn_in_its_colour_where_it_is(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    assert any(map(is_red, near(canvas, 100, 25))) and any(map(is_red, near(canvas, 150, 50)))
    assert pixel(canvas, 100, 50) == GREY


def test_the_caption_sits_on_a_plate_inside_the_top_edge(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    corner = canvas.mapFromScene(QPointF(50, 25))
    assert is_red(QColor(shot(canvas).pixel(corner + QPoint(4, 6))))
    [caption] = canvas.caption_items()
    assert caption.text == "car" and caption.isVisible()
    assert canvas.viewport().rect().contains(corner + QPoint(int(caption.boundingRect().width()) - 1, 6))


def test_an_unknown_class_is_drawn_grey_and_dashed(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BoxView(1, (50, 25, 150, 75), (), "#9e9e9e", "#99?", False, False)])
    image = shot(canvas)
    x = canvas.mapFromScene(QPointF(150, 50)).x()
    top, bottom = canvas.mapFromScene(QPointF(150, 35)).y(), canvas.mapFromScene(QPointF(150, 70)).y()
    # across the line only, row by row: dashes read near the pen's grey, gaps near the image's
    edge = [max(QColor(image.pixel(x + dx, y)).red() for dx in range(-2, 3)) for y in range(top, bottom)]
    assert any(v > 140 for v in edge) and any(v <= 110 for v in edge)


def test_a_highlighted_box_is_drawn_thicker(canvas):
    def thickness(view):
        canvas.set_image(grey_image())
        canvas.set_boxes([view])
        image = shot(canvas)
        x = canvas.mapFromScene(QPointF(120, 25)).x()
        y0 = canvas.mapFromScene(QPointF(120, 25)).y()
        return sum(is_red(QColor(image.pixel(x, y))) for y in range(y0 - 6, y0 + 7))

    plain = thickness(RED)
    thick = thickness(BoxView(0, RED.rect, (), "#ff0000", "car", True, True))
    assert thick > plain >= 1


def test_a_polygon_is_drawn_by_its_points(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BoxView(0, (20, 10, 60, 50), ((20, 10), (60, 10), (20, 50)), "#ff0000", "car", True, False)])
    assert is_red(pixel(canvas, 40, 30))           # on the diagonal
    assert pixel(canvas, 55, 45) == GREY           # inside the extent, outside the triangle


def test_layers_hide_the_labels_or_only_the_captions(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    canvas.set_layers(labels=True, captions=False)
    assert canvas.caption_items() == [] and is_red(pixel(canvas, 100, 25))
    canvas.set_layers(labels=False, captions=True)
    assert not is_red(pixel(canvas, 100, 25))


def test_no_image_shows_why(canvas):
    canvas.set_image(None, "cannot decode bad/images/corrupt.jpg")
    assert canvas.message == "cannot decode bad/images/corrupt.jpg" and canvas.image_size is None
    origin = canvas.mapFromScene(QPointF(0, 0))
    assert canvas.viewport().rect().contains(origin)
    image = shot(canvas)
    light = sum(QColor(image.pixel(origin.x() + dx, origin.y() + dy)).red() > 150
                for dx in range(0, 120) for dy in range(0, 14))
    assert light > 20


def test_a_new_image_drops_the_old_boxes(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    canvas.set_image(grey_image())
    assert canvas.caption_items() == [] and not is_red(pixel(canvas, 100, 25))


def test_fit_and_zoom(canvas):
    canvas.set_image(grey_image())
    assert canvas.transform().m11() == pytest.approx(2.0, rel=0.05)
    canvas.zoom_by(2)
    assert canvas.transform().m11() == pytest.approx(4.0, rel=0.05)
    canvas.fit()
    assert canvas.transform().m11() == pytest.approx(2.0, rel=0.05)


def test_resizing_refits_until_the_user_zooms(qtbot, canvas):
    canvas.set_image(grey_image())
    canvas.resize(800, 600)
    qtbot.waitUntil(lambda: canvas.transform().m11() == pytest.approx(4.0, rel=0.05))
    canvas.zoom_by(1.5)
    scale = canvas.transform().m11()
    canvas.resize(400, 300)
    qtbot.wait(20)
    assert canvas.transform().m11() == pytest.approx(scale)


def send(widget, kind, button, pos):
    buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else button
    event = QMouseEvent(kind, QPointF(pos), widget.mapToGlobal(QPointF(pos)), button, buttons, Qt.NoModifier)
    QApplication.sendEvent(widget, event)


def test_a_middle_drag_pans(canvas):
    canvas.set_image(grey_image())
    canvas.zoom_by(4)
    before = canvas.horizontalScrollBar().value()
    vp = canvas.viewport()
    send(vp, QEvent.MouseButtonPress, Qt.MiddleButton, QPoint(200, 150))
    send(vp, QEvent.MouseMove, Qt.MiddleButton, QPoint(150, 150))
    send(vp, QEvent.MouseButtonRelease, Qt.MiddleButton, QPoint(150, 150))
    assert canvas.horizontalScrollBar().value() == before + 50


# -- editing (plan 1c) ---------------------------------------------------------------

BIG = BoxView(0, (20, 10, 180, 90), (), "#ff0000", "bus", True, False)
SMALL = BoxView(1, (60, 30, 100, 70), (), "#ff0000", "car", True, False)
TRIANGLE = BoxView(0, (20, 10, 60, 50), ((20, 10), (60, 10), (20, 50)), "#ff0000", "car", True, False)


def record(canvas):
    seen = []
    canvas.drawn.connect(lambda rect: seen.append(("drawn", rect)))
    canvas.picked.connect(lambda indices: seen.append(("picked", indices)))
    canvas.moved.connect(lambda dx, dy: seen.append(("moved", (dx, dy))))
    canvas.resized.connect(lambda index, rect: seen.append(("resized", index, rect)))
    return seen


def test_a_drag_draws_a_box_and_shows_it_while_dragging(canvas):
    canvas.set_image(grey_image())
    canvas.set_draw_color("#00ff00")
    seen = record(canvas)
    drag(canvas, (20, 20), (80, 60), release=False)
    assert any(c.green() > 200 and c.red() < 80 for c in near(canvas, 80, 40))
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 80, 60))
    [(kind, rect)] = seen
    assert kind == "drawn" and rect == pytest.approx((20, 20, 80, 60), abs=1)
    assert all(c == GREY for c in near(canvas, 80, 40))     # the window draws the saved box


def test_a_drawn_box_is_clamped_to_the_image(canvas):
    canvas.set_image(grey_image())
    seen = record(canvas)
    drag(canvas, (150, 50), (190, 120))
    assert seen[0][1] == pytest.approx((150, 50, 190, 100), abs=1)


def test_a_drag_under_three_pixels_is_a_click(canvas):
    canvas.set_image(grey_image())
    seen = record(canvas)
    start = vp(canvas, 100, 50)
    mouse(canvas, QEvent.MouseButtonPress, start)
    mouse(canvas, QEvent.MouseMove, start + QPoint(2, 0), buttons=Qt.LeftButton)
    mouse(canvas, QEvent.MouseButtonRelease, start + QPoint(2, 0))
    assert seen == [("picked", [])]


def test_a_click_selects_the_smallest_box_under_the_cursor(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BIG, SMALL])
    seen = record(canvas)
    click(canvas, (80, 50))
    click(canvas, (30, 20))
    assert seen == [("picked", [1]), ("picked", [0])]


def test_clicking_a_selected_box_again_cycles_to_the_next_one_under_the_cursor(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BIG, SMALL], selected=[1])
    seen = record(canvas)
    click(canvas, (80, 50))
    canvas.set_selected([0])
    click(canvas, (80, 50))
    assert seen == [("picked", [0]), ("picked", [1])]


def test_shift_click_adds_to_and_removes_from_the_selection(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BIG, SMALL], selected=[0])
    seen = record(canvas)
    click(canvas, (80, 50), Qt.ShiftModifier)
    canvas.set_selected([0, 1])
    click(canvas, (80, 50), Qt.ShiftModifier)
    click(canvas, (190, 95), Qt.ShiftModifier)              # empty space: nothing changes
    assert seen == [("picked", [0, 1]), ("picked", [0])]


def test_a_click_on_empty_space_clears_the_selection(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([SMALL], selected=[1])
    seen = record(canvas)
    click(canvas, (190, 95))
    assert seen == [("picked", [])]


def test_a_click_inside_a_polygon_selects_it_and_outside_it_does_not(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([TRIANGLE])
    seen = record(canvas)
    click(canvas, (25, 15))
    click(canvas, (55, 45))                                  # inside the extent only
    assert seen == [("picked", [0]), ("picked", [])]


def test_a_selected_box_is_filled_and_one_selected_box_shows_eight_handles(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    assert pixel(canvas, 100, 50) == GREY and canvas.handle_items() == []
    canvas.set_selected([0])
    inside = pixel(canvas, 100, 50)
    assert inside.red() > inside.green() + 30
    assert len(canvas.handle_items()) == 8
    corner = vp(canvas, 150, 75)
    assert QColor(shot(canvas).pixel(corner + QPoint(2, -2))).lightness() > 200


def test_several_selected_boxes_or_a_polygon_show_no_handles(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BIG, SMALL], selected=[0, 1])
    assert canvas.handle_items() == []
    canvas.set_boxes([TRIANGLE], selected=[0])
    assert canvas.handle_items() == []


def test_dragging_a_selected_box_moves_it(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED], selected=[0])
    seen = record(canvas)
    drag(canvas, (100, 50), (120, 60), release=False)
    assert any(map(is_red, near(canvas, 170, 45))) and not any(map(is_red, near(canvas, 150, 40)))
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 120, 60))
    [(kind, delta)] = seen
    assert kind == "moved" and delta == pytest.approx((20, 10), abs=1)
    assert any(map(is_red, near(canvas, 150, 40)))          # back until the window redraws


def test_dragging_a_corner_handle_resizes_the_box(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED], selected=[0])
    seen = record(canvas)
    drag(canvas, (150, 75), (170, 90), release=False)
    assert any(map(is_red, near(canvas, 170, 82)))
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 170, 90))
    [(kind, index, rect)] = seen
    assert (kind, index) == ("resized", 0) and rect == pytest.approx((50, 25, 170, 90), abs=1)


def test_an_edge_handle_moves_one_edge_and_past_the_other_edge_flips(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED], selected=[0])
    seen = record(canvas)
    drag(canvas, (150, 50), (160, 70))                       # the right edge's handle
    drag(canvas, (50, 50), (170, 50))                        # the left edge, past the right
    assert seen[0][2] == pytest.approx((50, 25, 160, 75), abs=1)
    assert seen[1][2] == pytest.approx((150, 25, 170, 75), abs=1)


def test_esc_cancels_a_drag(canvas):
    canvas.set_image(grey_image())
    canvas.set_draw_color("#00ff00")
    seen = record(canvas)
    assert canvas.cancel_drag() is False
    drag(canvas, (20, 20), (80, 60), release=False)
    assert canvas.cancel_drag() is True
    assert all(c == GREY for c in near(canvas, 80, 40))
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 80, 60))
    assert seen == []


def test_labels_redrawn_during_a_drag_cancel_it(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED], selected=[0])
    seen = record(canvas)
    drag(canvas, (100, 50), (120, 60), release=False)
    canvas.set_boxes([RED], selected=[0])                    # the file changed meanwhile
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 120, 60))
    assert seen == []


def test_nothing_is_edited_without_an_image_or_with_the_labels_hidden(canvas):
    seen = record(canvas)
    canvas.set_image(None, "cannot decode")
    drag(canvas, (20, 20), (80, 60))
    canvas.set_image(grey_image())
    canvas.set_layers(labels=False, captions=True)
    drag(canvas, (20, 20), (80, 60))
    assert seen == []


def test_the_crosshair_follows_the_mouse(canvas):
    canvas.set_image(grey_image())
    canvas.set_crosshair(True)
    mouse(canvas, QEvent.MouseMove, vp(canvas, 100, 50), button=Qt.NoButton)
    assert any(c.lightness() > 200 for c in near(canvas, 100, 10))     # its column
    assert any(c.lightness() > 200 for c in near(canvas, 180, 50))     # its row
    QApplication.sendEvent(canvas.viewport(), QEvent(QEvent.Leave))
    assert all(c == GREY for c in near(canvas, 100, 10))
    mouse(canvas, QEvent.MouseMove, vp(canvas, 100, 50), button=Qt.NoButton)
    canvas.set_crosshair(False)
    assert all(c == GREY for c in near(canvas, 100, 10))
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_canvas.py`
Expected: 17 failed, 11 passed: the new tests fail on `AttributeError: 'Canvas' object has no attribute 'drawn'` (or `set_draw_color`, `handle_items`, `set_crosshair`) and on `set_boxes() got an unexpected keyword argument 'selected'`.

- [ ] **Step 3: Write the editing canvas**

Replace `src/deeplabeling/ui/canvas.py` with:

```python
"""The canvas: the whole frame and its labels (docs/design/2026-10-04-app-foundation.md#window).

Scene coordinates are image pixels. The canvas edits nothing itself: a finished drag
or click becomes a signal in image pixels -- drawn, picked, moved, resized -- and the
window turns it into an intent. While the mouse moves, the canvas only previews.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from .boxes import BoxView
from .classes import text_color

BACKGROUND = "#2b2b2b"
DRAG_PX = 3             #: a press that moves less than this far is a click (the spec)
HANDLE_PX = 8           #: a handle's size on screen, the same at every zoom
GRAB_PX = 6             #: how near a handle's centre a press takes the handle
SELECTED_ALPHA = 70     #: a selected box is filled with its colour at this opacity
CROSSHAIR = "#ffffff"
#: the eight handles of a box, as fractions of its width and height
HANDLES = ((0, 0), (0.5, 0), (1, 0), (1, 0.5), (1, 1), (0.5, 1), (0, 1), (0, 0.5))


@dataclass
class _Drag:
    kind: str                           #: "draw", "move" or "resize"
    press: QPointF                      #: where the button went down, in viewport pixels
    start: QPointF                      #: the same point in the scene
    shift: bool
    handle: tuple[float, float] | None = None
    active: bool = False                #: moved DRAG_PX or more: a drag, not a click
    origins: dict = field(default_factory=dict)     #: item -> its position at the press


class CaptionItem(QGraphicsItem):
    """A caption on a solid plate, inside its box's top edge. It ignores the view's
    zoom, so it stays readable; the plate keeps it legible on any image."""

    def __init__(self, text: str, color: str):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.text, self.color = text, QColor(color)
        self._font = QFont()
        self._font.setPointSize(9)
        metrics = QFontMetricsF(self._font)
        self._rect = QRectF(0, 0, metrics.horizontalAdvance(text) + 6, metrics.height() + 2)

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.fillRect(self._rect, self.color)
        painter.setPen(QColor(text_color(self.color.name())))
        painter.setFont(self._font)
        painter.drawText(self._rect.adjusted(3, 0, -3, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text)


class Canvas(QGraphicsView):
    drawn = Signal(object)              #: (x1, y1, x2, y2) in image pixels, inside the image
    picked = Signal(list)               #: the line indices to select now
    moved = Signal(float, float)        #: the selected boxes' shift, in image pixels
    resized = Signal(int, object)       #: a line index and its new (x1, y1, x2, y2)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor(BACKGROUND))
        self.setFocusPolicy(Qt.NoFocus)             # keys belong to the window's actions
        self._pixmap = QGraphicsPixmapItem()
        self._pixmap.setTransformationMode(Qt.SmoothTransformation)
        self.scene().addItem(self._pixmap)
        self._message = QGraphicsSimpleTextItem()
        self._message.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self._message.setBrush(QColor("#e0e0e0"))
        self.scene().addItem(self._message)
        self._items: list[QGraphicsItem] = []
        self._views: list[BoxView] = []
        self._size: tuple[int, int] | None = None
        self.show_labels = True
        self.show_captions = True
        self.show_crosshair = False
        self._fitted = True
        self._pan_from = None
        self._selected: frozenset[int] = frozenset()
        self._box_items: dict[int, list[QGraphicsItem]] = {}   #: line index -> its items
        self._handles: list[QGraphicsRectItem] = []
        self._drag: _Drag | None = None
        self._preview: QGraphicsRectItem | None = None
        self._draw_color = "#ffffff"
        self._mouse: QPointF | None = None          #: the crosshair's scene point
        self.viewport().setMouseTracking(True)

    # -- what is shown -----------------------------------------------------------

    @property
    def image_size(self) -> tuple[int, int] | None:
        return self._size

    @property
    def message(self) -> str:
        return self._message.text() if self._message.isVisible() else ""

    def set_image(self, image: QImage | None, message: str = "") -> None:
        """Show an image, fitted to the view; or no image and a message saying why."""
        self._views, self._selected = [], frozenset()
        self._clear()
        if image is None:
            self._pixmap.setPixmap(QPixmap())
            self._size = None
            self._message.setText(message)
            self._message.setVisible(bool(message))
            self.scene().setSceneRect(QRectF(0, 0, 1, 1))
            self.resetTransform()
            self._message.setPos(0, 0)
            self.centerOn(0, 0)
            return
        self._message.setVisible(False)
        self._pixmap.setPixmap(QPixmap.fromImage(image))
        self._size = (image.width(), image.height())
        self.scene().setSceneRect(QRectF(0, 0, image.width(), image.height()))
        self.fit()

    def set_boxes(self, views: list[BoxView], selected=()) -> None:
        self._views, self._selected = list(views), frozenset(selected)
        self._redraw()

    def set_selected(self, indices) -> None:
        self._selected = frozenset(indices)
        self._redraw()

    def set_layers(self, *, labels: bool, captions: bool) -> None:
        self.show_labels, self.show_captions = labels, captions
        self._redraw()

    def set_draw_color(self, color: str) -> None:
        """The colour of the box being drawn: the active class's."""
        self._draw_color = color

    def set_crosshair(self, on: bool) -> None:
        self.show_crosshair = on
        self.viewport().update()

    def caption_items(self) -> list[CaptionItem]:
        return [it for it in self._items if isinstance(it, CaptionItem)]

    def handle_items(self) -> list[QGraphicsRectItem]:
        return list(self._handles)

    def _clear(self) -> None:
        self._drag = None                           # whatever it previewed is gone
        for item in self._items + ([self._preview] if self._preview else []):
            self.scene().removeItem(item)
        self._items, self._box_items, self._handles, self._preview = [], {}, [], None

    def _redraw(self) -> None:
        self._clear()
        if not self.show_labels or self._size is None:
            return
        for view in self._views:
            self._draw(view)

    def _draw(self, view: BoxView) -> None:
        pen = QPen(QColor(view.color))
        pen.setCosmetic(True)                       # the same width at every zoom
        pen.setWidth(4 if view.highlighted else 2)
        if not view.known:
            pen.setStyle(Qt.DashLine)
        x1, y1, x2, y2 = view.rect
        if view.polygon:
            shape = self.scene().addPolygon(QPolygonF([QPointF(x, y) for x, y in view.polygon]), pen)
        else:
            shape = self.scene().addRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)), pen)
        shape.setZValue(1)
        items = [shape]
        if view.index in self._selected:
            fill = QColor(view.color)
            fill.setAlpha(SELECTED_ALPHA)
            shape.setBrush(QBrush(fill))
        if self.show_captions:
            caption = CaptionItem(view.caption, view.color)
            caption.setPos(x1, y1)
            caption.setZValue(2)
            self.scene().addItem(caption)
            items.append(caption)
        if self._selected == {view.index} and not view.polygon:
            for fx, fy in HANDLES:
                handle = QGraphicsRectItem(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX)
                handle.setFlag(QGraphicsItem.ItemIgnoresTransformations)
                handle.setBrush(QColor("#ffffff"))
                handle.setPen(QPen(QColor("#202020"), 0))
                handle.setPos(x1 + fx * (x2 - x1), y1 + fy * (y2 - y1))
                handle.setZValue(4)
                self.scene().addItem(handle)
                self._handles.append(handle)
            items += self._handles
        self._items += items
        self._box_items[view.index] = items

    # -- the mouse: draw, select, move, resize -------------------------------------------

    def _editable(self) -> bool:
        return self._size is not None and self.show_labels

    def _contains(self, view: BoxView, point: QPointF) -> bool:
        if view.polygon:
            return QPolygonF([QPointF(x, y) for x, y in view.polygon]).containsPoint(point, Qt.OddEvenFill)
        x1, y1, x2, y2 = view.rect
        return x1 <= point.x() <= x2 and y1 <= point.y() <= y2

    def _boxes_at(self, point: QPointF) -> list[int]:
        """The line indices of the boxes under a scene point, smallest first."""
        under = [v for v in self._views if self._contains(v, point)]
        under.sort(key=lambda v: ((v.rect[2] - v.rect[0]) * (v.rect[3] - v.rect[1]), v.index))
        return [v.index for v in under]

    def _handle_at(self, pos: QPointF) -> tuple[float, float] | None:
        """The handle of the one selected box nearest a viewport point, if near enough."""
        views = [v for v in self._views if v.index in self._selected]
        if len(self._selected) != 1 or len(views) != 1 or views[0].polygon:
            return None
        x1, y1, x2, y2 = views[0].rect
        best, handle = GRAB_PX, None
        for fx, fy in HANDLES:
            at = self.mapFromScene(QPointF(x1 + fx * (x2 - x1), y1 + fy * (y2 - y1)))
            distance = math.hypot(at.x() - pos.x(), at.y() - pos.y())
            if distance <= best:
                best, handle = distance, (fx, fy)
        return handle

    def _inside_image(self, point: QPointF) -> QPointF:
        w, h = self._size
        return QPointF(min(max(point.x(), 0.0), w), min(max(point.y(), 0.0), h))

    def _resized_rect(self, view: BoxView, handle, delta: QPointF) -> tuple[float, float, float, float]:
        """A box's rect with the handle's edges shifted by `delta`, inside the image."""
        x1, y1, x2, y2 = view.rect
        fx, fy = handle
        if fx == 0:
            x1 += delta.x()
        elif fx == 1:
            x2 += delta.x()
        if fy == 0:
            y1 += delta.y()
        elif fy == 1:
            y2 += delta.y()
        a, b = self._inside_image(QPointF(x1, y1)), self._inside_image(QPointF(x2, y2))
        return (min(a.x(), b.x()), min(a.y(), b.y()), max(a.x(), b.x()), max(a.y(), b.y()))

    def _view(self, index: int) -> BoxView:
        return next(v for v in self._views if v.index == index)

    def cancel_drag(self) -> bool:
        """Drop the drag in progress and its preview. True when a drag was showing."""
        drag = self._drag
        if drag is None:
            return False
        self._redraw()                              # puts back what the drag moved
        return drag.active

    def _start(self, drag: _Drag) -> None:
        drag.active = True
        if drag.kind == "draw":
            pen = QPen(QColor(self._draw_color))
            pen.setCosmetic(True)
            pen.setWidth(2)
            self._preview = self.scene().addRect(QRectF(drag.start, drag.start), pen)
            self._preview.setZValue(3)
        else:
            moving = self._selected if drag.kind == "move" else ()
            drag.origins = {item: item.pos() for i in moving for item in self._box_items.get(i, ())}

    def _preview_to(self, drag: _Drag, point: QPointF) -> None:
        delta = point - drag.start
        if drag.kind == "draw":
            self._preview.setRect(QRectF(drag.start, self._inside_image(point)).normalized())
        elif drag.kind == "move":
            for item, origin in drag.origins.items():
                item.setPos(origin + delta)
        else:
            [index] = self._selected
            x1, y1, x2, y2 = self._resized_rect(self._view(index), drag.handle, delta)
            shape, *rest = self._box_items[index]
            shape.setRect(QRectF(x1, y1, x2 - x1, y2 - y1))
            for item in rest:
                if isinstance(item, CaptionItem):
                    item.setPos(x1, y1)
            for handle, (fx, fy) in zip(self._handles, HANDLES):
                handle.setPos(x1 + fx * (x2 - x1), y1 + fy * (y2 - y1))

    def _finish(self, drag: _Drag, point: QPointF) -> None:
        self._redraw()                              # the window shows the saved result
        if drag.kind == "draw":
            a, b = drag.start, self._inside_image(point)
            rect = (min(a.x(), b.x()), min(a.y(), b.y()), max(a.x(), b.x()), max(a.y(), b.y()))
            if rect[2] - rect[0] >= 1 and rect[3] - rect[1] >= 1:
                self.drawn.emit(rect)
        elif drag.kind == "move":
            delta = point - drag.start
            if delta.x() or delta.y():
                self.moved.emit(delta.x(), delta.y())
        else:
            [index] = self._selected
            view = self._view(index)
            rect = self._resized_rect(view, drag.handle, point - drag.start)
            if rect != view.rect and rect[2] - rect[0] >= 1 and rect[3] - rect[1] >= 1:
                self.resized.emit(index, rect)

    def _click(self, point: QPointF, shift: bool) -> None:
        under = self._boxes_at(point)
        if shift:
            if under:
                self.picked.emit(sorted(self._selected ^ {under[0]}))
            return
        if not under:
            self.picked.emit([])
        elif len(self._selected) == 1 and next(iter(self._selected)) in under:
            at = under.index(next(iter(self._selected)))
            self.picked.emit([under[(at + 1) % len(under)]])
        else:
            self.picked.emit([under[0]])

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if not self.show_crosshair or self._mouse is None or self._size is None:
            return
        w, h = self._size
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(QColor(CROSSHAIR))
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(QPointF(self._mouse.x(), 0), QPointF(self._mouse.x(), h))
        painter.drawLine(QPointF(0, self._mouse.y()), QPointF(w, self._mouse.y()))
        painter.restore()

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Leave and self._mouse is not None:
            self._mouse = None
            self.viewport().update()
        return super().viewportEvent(event)

    # -- zoom and pan --------------------------------------------------------------

    def fit(self) -> None:
        if self._size is not None:
            self.fitInView(self._pixmap, Qt.KeepAspectRatio)
            self._fitted = True

    def zoom_by(self, factor: float) -> None:
        if self._size is not None:
            self.scale(factor, factor)
            self._fitted = False

    def wheelEvent(self, event) -> None:
        self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fitted:
            self.fit()

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = event.position().toPoint()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._editable() and self._drag is None:
            pos = event.position()
            point = self.mapToScene(pos.toPoint())
            handle = self._handle_at(pos)
            selected = any(self._contains(v, point) for v in self._views if v.index in self._selected)
            kind = "resize" if handle else "move" if selected else "draw"
            self._drag = _Drag(kind, pos, point, bool(event.modifiers() & Qt.ShiftModifier), handle)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.show_crosshair:
            self._mouse = self.mapToScene(event.position().toPoint())
            self.viewport().update()
        if self._pan_from is not None:
            point = event.position().toPoint()
            delta, self._pan_from = point - self._pan_from, point
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._fitted = False
            event.accept()
            return
        drag = self._drag
        if drag is not None:
            pos = event.position()
            if not drag.active and math.hypot(pos.x() - drag.press.x(), pos.y() - drag.press.y()) < DRAG_PX:
                return
            if not drag.active:
                self._start(drag)
            self._preview_to(drag, self.mapToScene(pos.toPoint()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_from is not None and event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = None
            self.viewport().unsetCursor()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._drag is not None:
            drag, self._drag = self._drag, None
            point = self.mapToScene(event.position().toPoint())
            if drag.active:
                self._finish(drag, point)
            else:
                self._click(drag.start, drag.shift)
            event.accept()
            return
        super().mouseReleaseEvent(event)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_canvas.py`
Expected: 28 passed.

- [ ] **Step 5: Look at it**

Run, from the repository root:

```bash
SHOT=$(mktemp -d) && QT_QPA_PLATFORM=offscreen PYTHONPATH=src:tests:tests/ui /home/sonnn/miniconda3/bin/python3 - "$SHOT" <<'EOF'
import sys
from PySide6.QtWidgets import QApplication
app = QApplication([])
from deeplabeling.ui.boxes import BoxView
from deeplabeling.ui.canvas import Canvas
from drive import drag
from test_canvas import BIG, grey_image
c = Canvas(); c.resize(400, 300); c.show(); app.processEvents()
c.set_image(grey_image())
c.set_boxes([BIG, BoxView(1, (60, 30, 100, 70), (), "#00aaff", "car", True, False)], selected=[1])
c.set_draw_color("#00ff00"); c.set_crosshair(True)
drag(c, (120, 60), (170, 85), release=False)
c.viewport().grab().save(sys.argv[1] + "/canvas_edit.png")
print(sys.argv[1] + "/canvas_edit.png")
EOF
```

Open the printed PNG. Expected: a red "bus" box; inside it, a blue "car" box filled with its colour, with eight white handles; a green rectangle being drawn from the centre to the lower right; and white crosshair lines through the cursor.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 474 passed.

```bash
git add src/deeplabeling/ui/canvas.py tests/ui
git commit -m "ui: draw, pick, cycle, move and resize on the canvas; handles and crosshair" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Editing in the window: gestures and keys become edits

**Files:**
- Create: `src/deeplabeling/ui/editing.py`, `src/deeplabeling/ui/class_picker.py`
- Modify: `src/deeplabeling/ui/keymap.py`, `src/deeplabeling/ui/settings_ui.py`, `src/deeplabeling/ui/prompter.py`, `src/deeplabeling/ui/main_window.py` (replaced whole)
- Test: `tests/ui/test_editing.py`, `tests/ui/test_class_picker.py`, `tests/ui/drive.py`, `tests/ui/test_main_window.py`, `tests/fixtures.py`

**Interfaces:**
- Consumes:
  - Task 1: `class_infos` and `class_with_hotkey`;
  - Task 2: `actions` and `Selection`;
  - Task 3: the canvas signals, `set_selected`, `set_draw_color`, `set_crosshair` and `cancel_drag`;
  - from the core: `ACTIVE_CLASS`, an opening-scope setting holding a class name or None.
- Produces in `deeplabeling.ui.editing`: `Editing(session, canvas, prompter)`.
  - The signal `activeChanged()`, and `.selection` (the one `Selection`).
  - Reading: `.selected() -> list[int]`, `.classes() -> list[ClassInfo]` and `.active_class() -> ClassInfo | None` (the stored name, else the first class).
  - Classes: `.set_active(info)`; `.choose_class(info)`, which reclassifies the selection, or sets the active class when nothing is selected; `.class_key(key)` and `.pick_class()`.
  - The canvas's gestures: `.draw(rect)`, `.pick(indices)`, `.move(dx, dy)` and `.resize(index, rect)`, in pixels.
  - Keys: `.delete()`, `.select_step(step)`, `.select_all()`, `.escape()`, `.copy()` and `.paste()`.
- Produces in `deeplabeling.ui.class_picker`: `ClassPicker(infos)`, with `.filter` (a `QLineEdit`), `.list` (a `QListWidget`) and `.chosen() -> ClassInfo | None`.
- Produces in the prompters:
  - `QtPrompter.pick_class(infos) -> ClassInfo | None`;
  - `FakePrompter(class_name=…)`, whose `.pick_class(infos)` records `("class", names)`.
- Produces in `deeplabeling.ui.keymap`:
  - the actions `class_1` … `class_9`, `class_0`, `pick_class` (`C`), `delete` (`Del`, `Backspace`), `select_next` (`Tab`), `select_previous` (`Shift+Tab`), `select_all` (`Ctrl+A`), `escape` (`Esc`), `copy` (`Ctrl+C`) and `paste` (`Ctrl+V`);
  - `toggle_crosshair`, checkable and with no key.
- Produces in `deeplabeling.ui.settings_ui`: `SHOW_CROSSHAIR`, global, default False.
- Produces in `MainWindow`: `.editing`.
- Produces in `tests/ui/drive.py`: `start(qtbot, argv, prompter=None)`, which launches the app, shows and activates it, and waits for the queue and the first image.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/drive.py`:

```python
def start(qtbot, argv, prompter=None):
    """The app launched on `argv`, shown and active, its queue built and image shown."""
    from deeplabeling.__main__ import launch
    from fixtures import FakePrompter

    w = launch(argv, prompter or FakePrompter())
    qtbot.addWidget(w)
    w.resize(1440, 900)
    with qtbot.waitActive(w):
        w.show()
        w.activateWindow()
    if w.session.workspace is not None:
        qtbot.waitUntil(lambda: w.session.queue is not None and w.session.queue.complete)
        qtbot.waitUntil(lambda: w.canvas.image_size is not None)
    return w
```

In `tests/ui/test_main_window.py`, replace:

```python
from deeplabeling.ui.settings_ui import SHOW_LABELS
from fixtures import FakePrompter


def start(qtbot, argv, prompter=None):
    w = launch(argv, prompter or FakePrompter())
    qtbot.addWidget(w)
    w.resize(1440, 900)
    with qtbot.waitActive(w):
        w.show()
        w.activateWindow()
    if w.session.workspace is not None:
        qtbot.waitUntil(lambda: w.session.queue is not None and w.session.queue.complete)
        qtbot.waitUntil(lambda: w.canvas.image_size is not None)
    return w
```

with:

```python
from deeplabeling.ui.settings_ui import SHOW_LABELS
from drive import start
from fixtures import FakePrompter
```

In `tests/fixtures.py`, replace:

```python
    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
```

with:

```python
    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
```

In `tests/fixtures.py`, replace:

```python
    def ask_text(self, title, label):
        self.asked.append(("text", title))
        return self.text
```

with:

```python
    def ask_text(self, title, label):
        self.asked.append(("text", title))
        return self.text

    def pick_class(self, infos):
        self.asked.append(("class", tuple(info.name for info in infos)))
        return next((info for info in infos if info.name == self.class_name), None)
```

Create `tests/ui/test_class_picker.py`:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from deeplabeling.ui.class_picker import ClassPicker
from deeplabeling.ui.classes import ClassInfo

INFOS = [ClassInfo(0, "person", "#e6194b", "1"), ClassInfo(1, "car", "#3cb44b", "2"),
         ClassInfo(2, "bus_m", "#4363d8", "3"), ClassInfo(3, "bus_l", "#f58231", "4")]


def picker(qtbot):
    dialog = ClassPicker(INFOS)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.list.isVisible)
    return dialog


def shown(dialog):
    return [dialog.list.item(i).text().split()[-1] for i in range(dialog.list.count())]


def test_typing_filters_and_enter_chooses_the_highlighted_class(qtbot):
    dialog = picker(qtbot)
    qtbot.keyClicks(dialog.filter, "BUS")
    assert shown(dialog) == ["bus_m", "bus_l"] and dialog.list.height() > 0
    qtbot.keyClick(dialog.filter, Qt.Key_Down)
    qtbot.keyClick(dialog.filter, Qt.Key_Return)
    assert dialog.result() == QDialog.Accepted and dialog.chosen() == INFOS[3]


def test_enter_with_no_match_chooses_nothing(qtbot):
    dialog = picker(qtbot)
    qtbot.keyClicks(dialog.filter, "tram")
    qtbot.keyClick(dialog.filter, Qt.Key_Return)
    assert shown(dialog) == [] and dialog.isVisible() and dialog.chosen() is None
```

Create `tests/ui/test_editing.py`:

```python
"""Editing in the assembled window: the mouse on the canvas and the editing keys, read back
from the label files and from what is on screen (CLAUDE.md landmines 1 and 4)."""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QGuiApplication

from deeplabeling.core.labelio import parse_label_bytes
from deeplabeling.core.workspace import ACTIVE_CLASS
from deeplabeling.ui.settings_ui import SHOW_CROSSHAIR
from drive import click, drag, mouse, start, vp
from fixtures import CAMA_0001, FakePrompter, read_exact

# camA/0001.jpg is 64 x 48: person (line 0) spans x 25.6-38.4, y 16.8-31.2; car (line 1)
# spans x 12.8-19.2, y 9.6-14.4.
PERSON, CAR = (32, 24), (16, 12)


@pytest.fixture
def window(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)])
    yield w
    w.close()


def go(qtbot, window, key):
    window.session.go_to(key)
    path = window.session.current().entry.path
    qtbot.waitUntil(lambda: window._shown == path)


def lines(path):
    return [(line.cls_id, line.bbox) for line in parse_label_bytes(path.read_bytes())]


def selected(window):
    return window.editing.selection.indices(window.session.labels(window.session.current().entry))


def test_a_drawn_box_is_written_in_the_active_class_and_selected(qtbot, window, ds):
    go(qtbot, window, "camA/images/0003.jpg")
    drag(window.canvas, (10, 10), (30, 40))
    [(cls_id, bbox)] = lines(ds.lbl("camA/0003"))
    assert cls_id == 0 and bbox == pytest.approx((20 / 64, 25 / 48, 20 / 64, 30 / 48), abs=0.01)
    assert selected(window) == [0] and len(window.canvas.handle_items()) == 8
    qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert not ds.lbl("camA/0003").exists()


def test_a_digit_with_nothing_selected_sets_the_active_class_for_this_opening(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_2)
    assert window.editing.active_class().name == "car"
    assert window.session.workspace.opening_settings.get(ACTIVE_CLASS) == "car"
    go(qtbot, window, "camA/images/0003.jpg")
    drag(window.canvas, (10, 10), (30, 40))
    assert lines(ds.lbl("camA/0003"))[0][0] == 1
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert again.editing.active_class().name == "car"
    again.close()


def test_a_click_selects_and_a_digit_reclassifies_the_selection(qtbot, window, ds):
    click(window.canvas, PERSON)
    assert selected(window) == [0]
    qtbot.keyClick(window, Qt.Key_3)
    assert read_exact(ds.lbl("camA/0001")) == "2" + CAMA_0001[1:]
    assert selected(window) == [0] and window.editing.active_class().name == "person"


def test_a_digit_no_class_has_changes_nothing(qtbot, window, ds):
    click(window.canvas, PERSON)
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_9)
    assert said.args == ["no class has the key 9"]
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_the_class_picker_chooses_a_class_without_a_digit(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)], FakePrompter(class_name="bus_l"))
    qtbot.keyClick(w, Qt.Key_C)
    assert w.editing.active_class().name == "bus_l"
    assert ("class", ("person", "car", "bus_m", "bus_l")) in w.prompter.asked
    w.close()


def test_ctrl_a_then_delete_empties_the_file_and_keeps_it(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_A, Qt.ControlModifier)
    assert selected(window) == [0, 1]
    qtbot.keyClick(window, Qt.Key_Delete)
    assert ds.lbl("camA/0001").read_bytes() == b""      # a negative sample, never a deletion
    assert selected(window) == []


def test_backspace_deletes_too(qtbot, window, ds):
    click(window.canvas, CAR)
    qtbot.keyClick(window, Qt.Key_Backspace)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001.splitlines(keepends=True)[0]


def test_tab_and_shift_tab_step_through_the_boxes(qtbot, window):
    seen = []
    for key, modifier in ((Qt.Key_Tab, Qt.NoModifier), (Qt.Key_Tab, Qt.NoModifier),
                          (Qt.Key_Tab, Qt.NoModifier), (Qt.Key_Backtab, Qt.ShiftModifier)):
        qtbot.keyClick(window, key, modifier)
        seen.append(selected(window))
    assert seen == [[0], [1], [0], [1]]


def test_esc_cancels_a_drag_first_and_then_clears_the_selection(qtbot, window, ds):
    click(window.canvas, PERSON)
    drag(window.canvas, (50, 40), (60, 45), release=False)
    qtbot.keyClick(window, Qt.Key_Escape)
    mouse(window.canvas, QEvent.MouseButtonRelease, vp(window.canvas, 60, 45))
    assert selected(window) == [0] and read_exact(ds.lbl("camA/0001")) == CAMA_0001
    qtbot.keyClick(window, Qt.Key_Escape)
    assert selected(window) == [] and window.canvas.handle_items() == []


def test_dragging_a_selected_box_moves_it_in_the_file(qtbot, window, ds):
    click(window.canvas, PERSON)
    drag(window.canvas, PERSON, (PERSON[0] + 10, PERSON[1]))
    assert lines(ds.lbl("camA/0001"))[0][1] == pytest.approx((0.5 + 10 / 64, 0.5, 0.2, 0.3), abs=0.01)
    assert read_exact(ds.lbl("camA/0001")).endswith(CAMA_0001.splitlines(keepends=True)[1])
    assert selected(window) == [0]


def test_dragging_a_handle_resizes_the_box_in_the_file(qtbot, window, ds):
    click(window.canvas, PERSON)
    drag(window.canvas, (38.4, 31.2), (44.8, 36))
    assert lines(ds.lbl("camA/0001"))[0][1] == pytest.approx((0.55, 0.55, 0.3, 0.4), abs=0.01)
    assert selected(window) == [0]


def test_moving_a_polygon_is_refused_where_it_can_be_seen(qtbot, window, ds):
    go(qtbot, window, "seg/images/poly1.jpg")
    before = read_exact(ds.lbl("seg/poly1"))
    click(window.canvas, (9.6, 7.2))
    assert selected(window) == [0]
    drag(window.canvas, (9.6, 7.2), (20, 15))
    assert read_exact(ds.lbl("seg/poly1")) == before
    qtbot.waitUntil(window.notices.isVisible)
    assert any("polygon cannot be moved" in t for t in window.notices.texts())


def test_copy_and_paste_carry_boxes_to_another_image_as_one_edit(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClick(window, Qt.Key_C, Qt.ControlModifier)
    assert QGuiApplication.clipboard().text() == CAMA_0001
    go(qtbot, window, "camA/images/0003.jpg")
    qtbot.keyClick(window, Qt.Key_V, Qt.ControlModifier)
    assert read_exact(ds.lbl("camA/0003")) == CAMA_0001
    assert selected(window) == [0, 1]
    qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert not ds.lbl("camA/0003").exists()


def test_hiding_the_labels_clears_the_selection(qtbot, window, ds):
    click(window.canvas, PERSON)
    qtbot.keyClick(window, Qt.Key_L)
    assert selected(window) == []
    qtbot.keyClick(window, Qt.Key_Delete)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_the_crosshair_is_a_layer_that_persists(qtbot, window, ds):
    window.actions["toggle_crosshair"].trigger()
    assert window.canvas.show_crosshair and window.session.settings.get(SHOW_CROSSHAIR) is True
    assert window.state_bar.layers.full_text == "Layers: labels, captions, crosshair"
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert again.canvas.show_crosshair
    again.close()


def test_the_box_being_drawn_shows_the_active_class_colour(qtbot, window):
    go(qtbot, window, "camA/images/0003.jpg")
    qtbot.keyClick(window, Qt.Key_2)                            # car
    drag(window.canvas, (10, 10), (30, 40), release=False)
    want = QColor(window.editing.active_class().color)
    shot = window.canvas.viewport().grab().toImage()
    edge = vp(window.canvas, 30, 25)                            # the preview's right edge
    near = [QColor(shot.pixel(edge.x() + dx, edge.y() + dy)) for dx in range(-2, 3) for dy in range(-2, 3)]
    assert any(abs(c.red() - want.red()) + abs(c.green() - want.green()) + abs(c.blue() - want.blue()) < 40
               for c in near)
    window.canvas.cancel_drag()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_editing.py`
Expected: `ImportError: cannot import name 'SHOW_CROSSHAIR' from 'deeplabeling.ui.settings_ui'`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_class_picker.py`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.ui.class_picker'`.

- [ ] **Step 3: The crosshair setting, the editing keys and the class picker**

In `src/deeplabeling/ui/settings_ui.py`, replace:

```python
SHOW_CAPTIONS = define("view.captions", "global", True, lambda v: isinstance(v, bool))
```

with:

```python
SHOW_CAPTIONS = define("view.captions", "global", True, lambda v: isinstance(v, bool))
SHOW_CROSSHAIR = define("view.crosshair", "global", False, lambda v: isinstance(v, bool))
```

In `src/deeplabeling/ui/keymap.py`, replace:

```python
are window-wide; Qt keeps them quiet while a text field has focus. Plan 1c adds the
editing actions here.
"""
```

with:

```python
are window-wide; Qt keeps them quiet while a text field has focus.
"""
```

In `src/deeplabeling/ui/keymap.py`, replace:

```python
from PySide6.QtWidgets import QDialog, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
```

with:

```python
from PySide6.QtWidgets import QDialog, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from .classes import DEFAULT_HOTKEYS
```

In `src/deeplabeling/ui/keymap.py`, replace:

```python
    ActionSpec("mark_negative", "Mark negative (an image with no label file and no boxes)", ("N",)),
```

with:

```python
    ActionSpec("mark_negative", "Mark negative (an image with no label file and no boxes)", ("N",)),
    *(ActionSpec(f"class_{key}", f"Class {key}: reclassify the selection, or set the active class",
                 (key,)) for key in DEFAULT_HOTKEYS),
    ActionSpec("pick_class", "Class picker: type to filter, Enter to choose", ("C",)),
    ActionSpec("delete", "Delete the selected boxes", ("Delete", "Backspace")),
    ActionSpec("select_next", "Select the next box", ("Tab",)),
    ActionSpec("select_previous", "Select the previous box", ("Shift+Tab",)),
    ActionSpec("select_all", "Select every box", ("Ctrl+A",)),
    ActionSpec("escape", "Cancel the drawing, or clear the selection", ("Esc",)),
    ActionSpec("copy", "Copy the selected boxes", ("Ctrl+C",)),
    ActionSpec("paste", "Paste boxes, clamped into the image, as one edit", ("Ctrl+V",)),
```

In `src/deeplabeling/ui/keymap.py`, replace:

```python
    ActionSpec("toggle_captions", "Captions", ("T",), checkable=True),
```

with:

```python
    ActionSpec("toggle_captions", "Captions", ("T",), checkable=True),
    ActionSpec("toggle_crosshair", "Crosshair", (), checkable=True),
```

Create `src/deeplabeling/ui/class_picker.py`:

```python
"""The class picker (key C): type to filter the classes, Enter to choose. It reaches the
classes past the tenth, which have no digit key."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from .classes import ClassInfo
from .inspector import swatch


class ClassPicker(QDialog):
    def __init__(self, infos: Sequence[ClassInfo], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose a class")
        self._infos = list(infos)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Type to filter")
        self.list = QListWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.filter)
        layout.addWidget(self.list)
        self.filter.textChanged.connect(self._fill)
        self.filter.returnPressed.connect(self._choose)
        self.list.itemActivated.connect(self._choose)
        self.filter.installEventFilter(self)        # Up and Down move through the list
        self._fill("")
        self.resize(320, 360)

    def _fill(self, text: str) -> None:
        self.list.clear()
        for info in self._infos:
            if text.lower() in info.name.lower():
                item = QListWidgetItem(swatch(info.color), f"{info.hotkey or ' '}   {info.name}")
                item.setData(Qt.UserRole, info.cls_id)
                self.list.addItem(item)
        self.list.setCurrentRow(0)

    def chosen(self) -> ClassInfo | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return next(info for info in self._infos if info.cls_id == item.data(Qt.UserRole))

    def _choose(self, *_) -> None:
        if self.chosen() is not None:
            self.accept()

    def eventFilter(self, watched, event) -> bool:
        if (watched is self.filter and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Up, Qt.Key_Down)):
            step = 1 if event.key() == Qt.Key_Down else -1
            row = self.list.currentRow() + step
            if 0 <= row < self.list.count():
                self.list.setCurrentRow(row)
            return True
        return super().eventFilter(watched, event)
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
from .queue_editor import QueueEditor
```

with:

```python
from .class_picker import ClassPicker
from .classes import ClassInfo
from .queue_editor import QueueEditor
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
    def ask_text(self, title: str, label: str) -> str | None:
        text, ok = QInputDialog.getText(self.parent, title, label)
        return text if ok else None
```

with:

```python
    def ask_text(self, title: str, label: str) -> str | None:
        text, ok = QInputDialog.getText(self.parent, title, label)
        return text if ok else None

    def pick_class(self, infos: list[ClassInfo]) -> ClassInfo | None:
        dialog = ClassPicker(infos, self.parent)
        return dialog.chosen() if dialog.exec() == QDialog.Accepted else None
```

- [ ] **Step 4: Gestures and keys become edits**

Create `src/deeplabeling/ui/editing.py`:

```python
"""What the mouse and the editing keys do to the image on screen
(docs/design/2026-10-04-app-foundation.md#window).

Each gesture becomes an intent built by ui/actions.py and goes through Session.apply;
nothing here writes a file. This holds the one Selection and reads and sets the active
class, which is stored by name for each opening.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

from ..core.edits import Intent
from ..core.geometry import px_to_norm
from ..core.store import ImageLabels
from ..core.workspace import ACTIVE_CLASS, CLASS_COLORS, CLASS_HOTKEYS
from . import actions
from .canvas import Canvas
from .classes import ClassInfo, class_infos, class_with_hotkey
from .selection import Selection
from .session import Session


def _last(n: int) -> Callable[[ImageLabels], list[int]]:
    """The last `n` boxes of a file: where added boxes land."""
    return lambda labels: [i for i, _ in labels.boxes][-n:]


class Editing(QObject):
    activeChanged = Signal()

    def __init__(self, session: Session, canvas: Canvas, prompter, parent=None):
        super().__init__(parent)
        self.session, self.canvas, self.prompter = session, canvas, prompter
        self.selection = Selection(self)
        canvas.drawn.connect(self.draw)
        canvas.picked.connect(self.pick)
        canvas.moved.connect(self.move)
        canvas.resized.connect(self.resize)
        self.selection.changed.connect(self._selection_changed)
        session.cursorChanged.connect(self.selection.clear)
        session.opened.connect(self._active_changed)

    # -- the image being edited ----------------------------------------------------------

    def _current(self) -> tuple[Path, ImageLabels] | None:
        """The current image and its labels, while that image is on the canvas."""
        item = self.session.current()
        if item is None or self.session.workspace is None or self.canvas.image_size is None:
            return None
        return item.entry.path, self.session.labels(item.entry)

    def selected(self) -> list[int]:
        current = self._current()
        return self.selection.indices(current[1]) if current else []

    def _selection_changed(self) -> None:
        self.canvas.set_selected(self.selected())

    def _apply(self, intent: Intent | None, select=None) -> None:
        """Apply an intent; then select `select` -- indices, or a function of the new labels."""
        if intent is None or self.session.apply(intent) is None or select is None:
            return
        labels = self.session.workspace.store.get(intent.image)
        self.selection.select(labels, select(labels) if callable(select) else select)

    def _norm(self, rect):
        return px_to_norm(*rect, *self.canvas.image_size)

    # -- classes ------------------------------------------------------------------------------

    def classes(self) -> list[ClassInfo]:
        ws = self.session.workspace
        if ws is None:
            return []
        return class_infos(ws.dataset, ws.root_settings.get(CLASS_COLORS), ws.root_settings.get(CLASS_HOTKEYS))

    def active_class(self) -> ClassInfo | None:
        """The class a drawn box gets: the one chosen for this opening, else the first."""
        infos = self.classes()
        if not infos:
            return None
        name = self.session.workspace.opening_settings.get(ACTIVE_CLASS)
        return next((info for info in infos if info.name == name), infos[0])

    def set_active(self, info: ClassInfo) -> None:
        self.session.workspace.opening_settings.set(ACTIVE_CLASS, info.name)
        self.session.saver.schedule()
        self._active_changed()

    def _active_changed(self) -> None:
        active = self.active_class()
        if active is not None:
            self.canvas.set_draw_color(active.color)
        self.activeChanged.emit()

    def choose_class(self, info: ClassInfo) -> None:
        """Reclassify the selection, or make `info` the active class when nothing is selected."""
        current = self._current()
        indices = self.selected()
        if current and indices:
            image, labels = current
            self._apply(actions.reclassify(image, labels, indices, info.cls_id), select=indices)
        elif self.session.workspace is not None:
            self.set_active(info)

    def class_key(self, key: str) -> None:
        info = class_with_hotkey(self.classes(), key)
        if info is None:
            if self.session.workspace is not None:
                self.session.status.emit(f"no class has the key {key}")
            return
        self.choose_class(info)

    def pick_class(self) -> None:
        infos = self.classes()
        if infos:
            chosen = self.prompter.pick_class(infos)
            if chosen is not None:
                self.choose_class(chosen)

    # -- the canvas's gestures ------------------------------------------------------------

    def draw(self, rect) -> None:
        current, active = self._current(), self.active_class()
        if current and active is not None:
            self._apply(actions.add_box(current[0], active.cls_id, self._norm(rect)), select=_last(1))

    def pick(self, indices: list[int]) -> None:
        current = self._current()
        if current:
            self.selection.select(current[1], indices)

    def move(self, dx: float, dy: float) -> None:
        current = self._current()
        if current:
            image, labels = current
            w, h = self.canvas.image_size
            indices = self.selection.indices(labels)
            self._apply(actions.move(image, labels, indices, dx / w, dy / h), select=indices)

    def resize(self, index: int, rect) -> None:
        current = self._current()
        if current:
            image, labels = current
            self._apply(actions.resize(image, labels, index, self._norm(rect)), select=[index])

    # -- the editing keys -----------------------------------------------------------------

    def delete(self) -> None:
        current = self._current()
        if current:
            image, labels = current
            self._apply(actions.delete(image, labels, self.selection.indices(labels)), select=[])

    def select_step(self, step: int) -> None:
        """Select the next (+1) or previous (-1) box after the selection, wrapping round."""
        current = self._current()
        if not current:
            return
        labels = current[1]
        boxes = [i for i, _ in labels.boxes]
        if not boxes:
            return
        indices = self.selection.indices(labels)
        if not indices:
            target = boxes[0] if step > 0 else boxes[-1]
        else:
            at = boxes.index(indices[-1] if step > 0 else indices[0])
            target = boxes[(at + step) % len(boxes)]
        self.selection.select(labels, [target])

    def select_all(self) -> None:
        current = self._current()
        if current:
            self.selection.select(current[1], [i for i, _ in current[1].boxes])

    def escape(self) -> None:
        if not self.canvas.cancel_drag():
            self.selection.clear()

    def copy(self) -> None:
        current = self._current()
        if not current:
            return
        indices = self.selected()
        text = actions.copy_text(current[1], indices)
        if text:
            QGuiApplication.clipboard().setText(text)
            n = len(text.splitlines())
            self.session.status.emit(f"copied {n} box" if n == 1 else f"copied {n} boxes")

    def paste(self) -> None:
        current = self._current()
        if not current:
            return
        intent = actions.paste(current[0], QGuiApplication.clipboard().text(),
                               self.session.workspace.dataset.known)
        if intent is None:
            self.session.status.emit("the clipboard holds no boxes to paste")
            return
        self._apply(intent, select=_last(len(intent.ops)))
```

Replace `src/deeplabeling/ui/main_window.py` with:

```python
"""The main window: layout A (docs/design/2026-10-04-app-foundation.md#window).

The state bar spans the top; the queue is docked left and the inspector right; the
notice strip sits above the canvas. Everything shown comes from the Session.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget

from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .canvas import Canvas
from .classes import DEFAULT_HOTKEYS
from .editing import Editing
from .inspector import Inspector
from .keymap import HelpDialog, build_actions
from .notices import NoticeStrip
from .queue_panel import QueuePanel
from .session import Session
from .settings_ui import (RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_LABELS, WINDOW_GEOMETRY, WINDOW_STATE,
                          bind_toggle)
from .state_bar import StateBar

MIN_SIZE = (1024, 640)


class MainWindow(QMainWindow):
    def __init__(self, session: Session, prompter, parent=None):
        super().__init__(parent)
        self.session, self.prompter = session, prompter
        self.setWindowTitle("DeepLabeling")
        self.setMinimumSize(*MIN_SIZE)
        self.resize(1440, 900)
        self.state_bar = StateBar(session)
        self.setMenuWidget(self.state_bar)          # spans the window, above the docks
        self.notices = NoticeStrip()
        self.canvas = Canvas()
        self.editing = Editing(session, self.canvas, prompter, self)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.notices)
        layout.addWidget(self.canvas, 1)
        self.setCentralWidget(central)
        self.queue_panel = QueuePanel(session)
        self.queue_dock = self._dock("Queue", "queue", self.queue_panel, Qt.LeftDockWidgetArea)
        self.inspector = Inspector(session)
        self.inspector_dock = self._dock("Inspector", "inspector", self.inspector, Qt.RightDockWidgetArea)
        self.resizeDocks([self.queue_dock, self.inspector_dock], [280, 280], Qt.Horizontal)
        self.status_text = QLabel()
        self.statusBar().addWidget(self.status_text, 1)
        self._shown: Path | None = None
        self._written: float | None = None
        self._help: HelpDialog | None = None
        self.actions = build_actions(self, {
            "next": lambda: session.move(1),
            "previous": lambda: session.move(-1),
            "done_next": session.done_and_next,
            "toggle_reviewed": session.toggle_reviewed,
            "mark_negative": session.mark_negative,
            "undo": session.undo,
            "redo": session.redo,
            "fit": self.canvas.fit,
            "zoom_in": lambda: self.canvas.zoom_by(1.25),
            "zoom_out": lambda: self.canvas.zoom_by(0.8),
            "go_to": self.go_to,
            "help": self.show_help,
            **{f"class_{key}": (lambda k=key: self.editing.class_key(k)) for key in DEFAULT_HOTKEYS},
            "pick_class": self.editing.pick_class,
            "delete": self.editing.delete,
            "select_next": lambda: self.editing.select_step(1),
            "select_previous": lambda: self.editing.select_step(-1),
            "select_all": self.editing.select_all,
            "escape": self.editing.escape,
            "copy": self.editing.copy,
            "paste": self.editing.paste,
        })
        layers = self.state_bar.layers.menu()
        for key, setting in (("toggle_labels", SHOW_LABELS), ("toggle_captions", SHOW_CAPTIONS),
                             ("toggle_crosshair", SHOW_CROSSHAIR)):
            bind_toggle(self.actions[key], session.settings, setting, self._layers_changed)
            layers.addAction(self.actions[key])
        self.panels_menu = layers.addMenu("Panels")     # a closed dock comes back from here
        self.panels_menu.addAction(self.queue_dock.toggleViewAction())
        self.panels_menu.addAction(self.inspector_dock.toggleViewAction())
        self._layers_changed()
        self.state_bar.dataset.menu().aboutToShow.connect(self._fill_dataset_menu)
        self.state_bar.queue.clicked.connect(self.edit_queue)
        session.cursorChanged.connect(self.show_current)
        session.opened.connect(self.show_current)
        session.closed.connect(self._closed)
        session.images.ready.connect(self._image_event)
        session.images.failed.connect(lambda path, why: self._image_event(path))
        session.labelsChanged.connect(self._labels_changed)
        session.historyChanged.connect(self._history_changed)
        session.reviewChanged.connect(self._update_status)
        session.notice.connect(lambda level, text, image: self.notices.add(level, text, image))
        session.standing.connect(lambda key, text: self.notices.add("warning", text, key=key))
        session.status.connect(lambda text: self.statusBar().showMessage(text, 4000))
        self._restore_layout()
        self.show_current()

    def _dock(self, title: str, name: str, widget: QWidget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)                    # saveState needs a name per dock
        dock.setWidget(widget)
        widget.setMinimumWidth(160)
        self.addDockWidget(area, dock)
        return dock

    # -- what is shown ---------------------------------------------------------------

    def show_current(self) -> None:
        session, item = self.session, self.session.current()
        if session.workspace is None:
            self._shown = None
            self.canvas.set_image(None, "No dataset is open: click the dataset chip to open one.")
        elif item is None:
            self._shown = None
            building = session.queue is not None and not session.queue.complete
            self.canvas.set_image(None, "Building the queue…" if building else "No images in this queue.")
        else:
            path = item.entry.path
            image, why = session.images.get(path), session.images.error(path)
            if why is not None:
                self._shown = None
                self.canvas.set_image(None, f"Cannot decode {item.key}: {why}")
                self.notices.add("error", f"{item.key}: the image cannot be decoded ({why}); "
                                 "its labels are not edited", image=path, key=f"decode:{item.key}")
            elif image is None:
                self._shown = None
                self.canvas.set_image(None, "Loading…")
            else:
                if self._shown != path:
                    self.canvas.set_image(image)
                    self._shown = path
                self._show_boxes()
        self._update_status()

    def _show_boxes(self) -> None:
        session, item = self.session, self.session.current()
        if item is None or self.canvas.image_size is None:
            return
        ws = session.workspace
        labels = session.labels(item.entry)
        highlight = session.queue.source.highlight(labels, ws.dataset)
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
                                        ws.root_settings.get(CLASS_COLORS), highlight),
                              selected=self.editing.selection.indices(labels))

    def _image_event(self, path) -> None:
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self.show_current()

    def _labels_changed(self, images) -> None:
        self.notices.clear_image(images)
        item = self.session.current()
        if item is not None and item.entry.path in set(images):
            self._show_boxes()
        self._update_status()

    def _history_changed(self) -> None:
        self._written = time.time()
        self._update_status()

    def _closed(self) -> None:
        self.notices.clear()
        self.show_current()

    def _layers_changed(self, _=None) -> None:
        labels = self.actions["toggle_labels"].isChecked()
        if not labels:
            self.editing.selection.clear()          # hidden boxes are not acted on
        self.canvas.set_layers(labels=labels, captions=self.actions["toggle_captions"].isChecked())
        self.canvas.set_crosshair(self.actions["toggle_crosshair"].isChecked())
        self.session.saver.schedule()
        self.state_bar.refresh()

    def _update_status(self) -> None:
        session, item = self.session, self.session.current()
        if item is None or session.workspace is None:
            self.status_text.setText("")
            return
        parts = [item.key]
        if self.canvas.image_size is not None and self._shown == item.entry.path:
            parts.append("{} × {}".format(*self.canvas.image_size))
        parts.append(f"item {session.queue.position() + 1:,} / {len(session.queue):,}")
        if self._written is not None:
            parts.append("written " + time.strftime("%H:%M:%S", time.localtime(self._written)))
        parts.append(f"↶ {session.workspace.history.depth}")
        self.status_text.setText(" · ".join(parts))

    # -- what the chips and keys do --------------------------------------------------

    def _fill_dataset_menu(self) -> None:
        menu = self.state_bar.dataset.menu()
        menu.clear()
        menu.addAction("Open dataset yaml…", self.open_yaml)
        menu.addAction("Open image folder…", self.open_folder)
        recent = self.session.settings.get(RECENT)
        if recent:
            menu.addSeparator()
        for entry in recent:
            name = Path(entry["source"])
            menu.addAction(f"{name.name} — {name.parent}",
                           lambda e=entry: self.session.open(e["source"], e["labels"]))

    def open_yaml(self) -> None:
        path = self.prompter.choose_yaml()
        if path:
            self.session.open(path)

    def open_folder(self) -> None:
        folder = self.prompter.choose_folder("Image folder")
        if not folder:
            return
        labels = None
        if "images" not in Path(folder).resolve().parts:
            labels = self.prompter.choose_folder("Label folder for these images")
            if not labels:
                return
        self.session.open(folder, labels)

    def edit_queue(self) -> None:
        if self.session.queue is None:
            return
        current = self.session.queue.source
        chosen = self.prompter.edit_queue(self.session.workspace.dataset, current)
        if chosen is not None:                      # the same filter again is a refresh
            self.session.set_queue(chosen)

    def go_to(self) -> None:
        text = self.prompter.ask_text("Go to", "Item number, or part of its path:")
        if text:
            self.session.go_to_text(text)

    def show_help(self) -> None:
        self._help = HelpDialog(self)
        self._help.show()

    # -- the window's own state ----------------------------------------------------------

    def _restore_layout(self) -> None:
        settings = self.session.settings
        geometry, state = settings.get(WINDOW_GEOMETRY), settings.get(WINDOW_STATE)
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
        if state:
            self.restoreState(QByteArray.fromBase64(state.encode()))

    def closeEvent(self, event) -> None:
        settings = self.session.settings
        settings.set(WINDOW_GEOMETRY, bytes(self.saveGeometry().toBase64()).decode())
        settings.set(WINDOW_STATE, bytes(self.saveState().toBase64()).decode())
        self.session.close()
        self.session.saver.flush()
        super().closeEvent(event)
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_editing.py tests/ui/test_class_picker.py tests/ui/test_keymap.py tests/ui/test_main_window.py`
Expected: 43 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 492 passed.

```bash
git add src/deeplabeling/ui tests
git commit -m "ui: the mouse and the editing keys edit; the class picker; the crosshair layer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The inspector acts on the selection

**Files:**
- Modify: `src/deeplabeling/ui/inspector.py` (replaced whole), `src/deeplabeling/ui/main_window.py`
- Test: `tests/ui/test_panels.py`, `tests/ui/test_editing.py`

**Interfaces:**
- Consumes: `Editing` (Task 4), with `.selection`, `.selected()`, `.classes()`, `.active_class()`, `.choose_class(info)`, `.pick(indices)` and `activeChanged`.
- Produces in `deeplabeling.ui.inspector`:
  - `Inspector(session, editing)`.
  - `ACTIVE_MARK = "✎"`, which follows the active class's palette row.
  - A palette row carries its class id in `Qt.UserRole`; clicking it calls `editing.choose_class`.
  - A box-list row carries its line index in `Qt.UserRole`. The list allows extended selection and mirrors `editing.selection` in both directions.

- [ ] **Step 1: Write the failing tests**

In `tests/ui/test_panels.py`, replace:

```python
from deeplabeling.ui.inspector import Inspector
from deeplabeling.ui.queue_panel import QueuePanel
```

with:

```python
from deeplabeling.ui.canvas import Canvas
from deeplabeling.ui.editing import Editing
from deeplabeling.ui.inspector import Inspector
from deeplabeling.ui.queue_panel import QueuePanel
from fixtures import FakePrompter
```

In `tests/ui/test_panels.py`, replace:

```python
def inspector(qtbot, session):
    i = Inspector(session)
```

with:

```python
def inspector(qtbot, session):
    canvas = Canvas()
    qtbot.addWidget(canvas)
    i = Inspector(session, Editing(session, canvas, FakePrompter()))
```

In `tests/ui/test_panels.py`, replace:

```python
        "1   person   1", "2   car   1", "3   bus_m   0", "4   bus_l   0"]
```

with:

```python
        "1   person   1   ✎", "2   car   1", "3   bus_m   0", "4   bus_l   0"]
```

Append to `tests/ui/test_panels.py`:

```python
def test_clicking_a_class_with_nothing_selected_makes_it_the_active_class(qtbot, inspector):
    row = inspector.classes.item(2)
    qtbot.mouseClick(inspector.classes.viewport(), Qt.LeftButton,
                     pos=inspector.classes.visualItemRect(row).center())
    assert inspector.classes.item(2).text() == "3   bus_m   0   ✎"
    assert inspector.classes.item(0).text() == "1   person   1"
```

Append to `tests/ui/test_editing.py`:

```python
def click_row(qtbot, listview, row, modifier=Qt.NoModifier):
    item = listview.item(row)
    qtbot.mouseClick(listview.viewport(), Qt.LeftButton, modifier, listview.visualItemRect(item).center())


def test_clicking_a_class_in_the_inspector_reclassifies_the_selection(qtbot, window, ds):
    click(window.canvas, PERSON)
    click_row(qtbot, window.inspector.classes, 3)                # bus_l
    assert read_exact(ds.lbl("camA/0001")) == "3" + CAMA_0001[1:]
    assert window.editing.active_class().name == "person"


def test_the_box_list_and_the_canvas_show_one_selection(qtbot, window):
    boxes = window.inspector.boxes
    qtbot.waitUntil(lambda: boxes.count() == 2)
    click(window.canvas, CAR)
    assert [boxes.item(i).isSelected() for i in range(2)] == [False, True]
    assert boxes.viewport().rect().contains(boxes.visualItemRect(boxes.item(1)))
    click_row(qtbot, boxes, 0)
    assert selected(window) == [0] and len(window.canvas.handle_items()) == 8
    click_row(qtbot, boxes, 1, Qt.ControlModifier)
    assert selected(window) == [0, 1] and window.canvas.handle_items() == []


def test_the_box_list_keeps_the_selection_through_an_edit(qtbot, window):
    boxes = window.inspector.boxes
    click(window.canvas, PERSON)
    qtbot.keyClick(window, Qt.Key_2)                             # reclassify: the list is rebuilt
    qtbot.waitUntil(lambda: boxes.count() == 2)
    assert [boxes.item(i).isSelected() for i in range(2)] == [True, False]
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_panels.py tests/ui/test_editing.py`
Expected: 3 failed, 22 passed, 6 errors. The six errors are the inspector fixture's `TypeError: 'PySide6.QtWidgets.QWidget.__init__' called with wrong argument types`: the old `Inspector` takes the editing as its parent. The three new window tests fail because the palette and the box list do not act yet.

- [ ] **Step 3: Write the inspector**

Replace `src/deeplabeling/ui/inspector.py` with:

```python
"""The inspector (docs/design/2026-10-04-app-foundation.md#window): the current image, its
classes and its boxes. Clicking a class reclassifies the selection, or makes it the active
class (marked ✎); the box list shows the one selection and sets it."""

from __future__ import annotations

import time
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.store import LabelState
from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .session import Session

#: After the active class's name in the palette.
ACTIVE_MARK = "✎"


def swatch(color: str) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class Inspector(QWidget):
    def __init__(self, session: Session, editing, parent=None):
        super().__init__(parent)
        self._session, self._editing = session, editing
        self._syncing = False                       # the box list is being set, not clicked
        self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label = (
            QLabel() for _ in range(5))
        for label in self._fields():
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form = QFormLayout()
        form.addRow("Image", self.path_label)
        form.addRow("Size", self.size_label)
        form.addRow("Labels", self.state_label)
        form.addRow("Unparsable lines", self.unparsed_label)
        form.addRow("Reviewed", self.reviewed_label)
        self.classes = QListWidget()
        self.boxes = QListWidget()
        for widget in (self.classes, self.boxes):
            widget.setFocusPolicy(Qt.NoFocus)
        self.classes.setSelectionMode(QAbstractItemView.NoSelection)    # ✎ marks the active class
        self.boxes.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(form)
        layout.addWidget(QLabel("Classes"))
        layout.addWidget(self.classes, 1)
        layout.addWidget(QLabel("Boxes"))
        layout.addWidget(self.boxes, 1)
        for signal in (session.cursorChanged, session.reviewChanged, session.opened, session.closed):
            signal.connect(self.refresh)
        session.labelsChanged.connect(self._labels_event)
        session.images.ready.connect(self._image_event)
        session.images.failed.connect(lambda path, why: self._image_event(path))
        self.classes.itemClicked.connect(self._class_clicked)
        self.boxes.itemSelectionChanged.connect(self._boxes_clicked)
        editing.selection.changed.connect(self._show_selection)
        editing.activeChanged.connect(self.refresh)
        self.refresh()

    def _fields(self) -> tuple[QLabel, ...]:
        # *_label names: a field called `size` would shadow QWidget.size()
        return (self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label)

    def _labels_event(self, images) -> None:
        item = self._session.current()
        if item is not None and item.entry.path in images:
            self.refresh()                          # another image's change is not shown here

    def _image_event(self, path) -> None:
        item = self._session.current()
        if item is not None and item.entry.path == path:
            self.refresh()

    def _class_clicked(self, row: QListWidgetItem) -> None:
        info = next(i for i in self._editing.classes() if i.cls_id == row.data(Qt.UserRole))
        self._editing.choose_class(info)

    def _boxes_clicked(self) -> None:
        if not self._syncing:
            self._editing.pick([row.data(Qt.UserRole) for row in self.boxes.selectedItems()])

    def _show_selection(self) -> None:
        selected = set(self._editing.selected())
        self._syncing = True
        try:
            first = None
            for i in range(self.boxes.count()):
                row = self.boxes.item(i)
                row.setSelected(row.data(Qt.UserRole) in selected)
                if first is None and row.isSelected():
                    first = row
            if first is not None:
                self.boxes.scrollToItem(first)
        finally:
            self._syncing = False

    def refresh(self) -> None:
        session, item = self._session, self._session.current()
        self._syncing = True
        try:
            self._fill(session, item)
        finally:
            self._syncing = False
        self._show_selection()

    def _fill(self, session, item) -> None:
        self.classes.clear()
        self.boxes.clear()
        if session.workspace is None or item is None:
            for label in self._fields():
                label.setText("—")
            return
        ws, entry = session.workspace, item.entry
        labels = session.labels(entry)
        image, why = session.images.get(entry.path), session.images.error(entry.path)
        self.path_label.setText(entry.rel)
        self.size_label.setText(f"cannot decode: {why}" if why else
                          f"{image.width()} × {image.height()}" if image is not None else "decoding…")
        self.state_label.setText(self._state_text(labels))
        self.unparsed_label.setText(str(labels.unparsed))
        marked = ws.review.marked_at(entry.rel)
        self.reviewed_label.setText(time.strftime("%Y-%m-%d %H:%M", time.localtime(marked)) if marked else "not yet")
        colors = ws.root_settings.get(CLASS_COLORS)
        counts = Counter(line.cls_id for _, line in labels.boxes)
        active = self._editing.active_class()
        for info in self._editing.classes():
            text = f"{info.hotkey or ' '}   {info.name}   {counts.get(info.cls_id, 0)}"
            row = QListWidgetItem(swatch(info.color), text + (f"   {ACTIVE_MARK}" if info == active else ""))
            row.setData(Qt.UserRole, info.cls_id)
            self.classes.addItem(row)
        if image is not None:
            for view in box_views(labels, ws.dataset, (image.width(), image.height()), colors):
                x1, y1, x2, y2 = view.rect
                row = QListWidgetItem(swatch(view.color), f"{view.caption}   {round(x2 - x1)} × {round(y2 - y1)} px")
                row.setData(Qt.UserRole, view.index)
                self.boxes.addItem(row)

    @staticmethod
    def _state_text(labels) -> str:
        if labels.state is LabelState.ERROR:
            return labels.error
        if labels.state is LabelState.SHARED:
            return f"read-only: {labels.error}"
        if labels.raw is None:
            return "no label file"
        if labels.negative:
            return "negative sample (no boxes)"
        n = len(labels.boxes)
        return f"{n} box" if n == 1 else f"{n} boxes"
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        self.inspector = Inspector(session)
```

with:

```python
        self.inspector = Inspector(session, self.editing)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_panels.py tests/ui/test_editing.py`
Expected: 31 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 496 passed.

```bash
git add src/deeplabeling/ui tests/ui
git commit -m "ui: the inspector's palette and box list act on the one selection" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: End to end, and the docs

**Files:**
- Test: `tests/ui/test_editing.py`
- Modify:
  - `docs/design/2026-10-04-app-foundation.md` (the status line, the Mouse bullet and classes for a folder pair);
  - `CLAUDE.md` (the status line);
  - `.claude/skills/run-and-verify-ui/SKILL.md` (the lessons).

**Interfaces:**
- Consumes: everything above.
- Produces: one test that pins the slice end to end, plus the docs.

- [ ] **Step 1: Write the end-to-end test**

Append to `tests/ui/test_editing.py`:

```python
def test_every_kind_of_edit_undoes_back_to_the_bytes_it_started_from(qtbot, window, ds):
    before = ds.snapshot()
    go(qtbot, window, "camA/images/0003.jpg")
    drag(window.canvas, (5, 5), (20, 20))                       # draw a person
    qtbot.keyClick(window, Qt.Key_2)                            # it is a car
    drag(window.canvas, (12, 12), (22, 17))                     # move it by (10, 5)
    drag(window.canvas, (30, 25), (35, 32))                     # its bottom-right handle
    [(cls_id, bbox)] = lines(ds.lbl("camA/0003"))
    assert cls_id == 1 and bbox == pytest.approx((25 / 64, 21 / 48, 20 / 64, 22 / 48), abs=0.01)
    qtbot.keyClick(window, Qt.Key_C, Qt.ControlModifier)
    go(qtbot, window, "camA/images/0001.jpg")
    qtbot.keyClick(window, Qt.Key_V, Qt.ControlModifier)        # pasted, and selected
    assert len(lines(ds.lbl("camA/0001"))) == 3 and selected(window) == [2]
    qtbot.keyClick(window, Qt.Key_Delete)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001
    assert window.session.workspace.history.depth == 6
    for _ in range(6):
        qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert ds.snapshot() == before
    assert window.session.current().key == "camA/images/0003.jpg"   # undo went to its image
```

- [ ] **Step 2: Run it**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_editing.py -k every_kind`
Expected: 1 passed, 19 deselected. Every piece it uses already exists, so it passes at once. It pins the slice end to end: draw, reclassify, move, resize, copy, paste, delete, then six undos back to byte-identical files.

To see that it can fail, change `select=_last(1)` in `Editing.draw` to `select=[]` and run it again. Expected: it fails, because `2` now sets the active class instead of reclassifying the drawn box. Put the line back.

- [ ] **Step 3: Update the spec, the status line and the UI skill**

In `docs/design/2026-10-04-app-foundation.md`, replace:

```markdown
**Status:** approved 2026-10-04 · slices 1a (the core) and 1b (the viewer) implemented; the amendments found while building them are folded in; 1c (editing) next
```

with:

```markdown
**Status:** approved 2026-10-04 · slices 1a (the core), 1b (the viewer) and 1c (editing) implemented; the amendments found while building them are folded in; 1d (the queue grid) next
```

In `docs/design/2026-10-04-app-foundation.md`, replace:

```markdown
  to move it, or a handle to resize it. A drag under 3 px is a click. The wheel zooms
  about the cursor; middle- or right-drag pans. Each new image is fitted to the view.
```

with:

```markdown
  to move it, or a handle to resize it. A drag under 3 px is a click. The wheel zooms
  about the cursor; middle- or right-drag pans. Each new image is fitted to the view.
  A drawn or pasted box is selected, and a box stays selected through a reclassify, a
  move or a resize. With the labels layer off, the mouse only zooms and pans, and the
  selection is cleared: hidden boxes are never acted on. The crosshair layer has no key.
```

In `docs/design/2026-10-04-app-foundation.md`, replace:

```markdown
`classes.txt` from its label folder if there is one, and otherwise shows bare ids. The
```

with:

```markdown
`classes.txt` from its label folder if there is one, and otherwise shows bare ids, offering
ids 0–9 on the digit keys. The
```

In `CLAUDE.md`, replace:

```markdown
**Status:** slice 1's core and its viewer UI are built; editing on the canvas (plan 1c)
is next. The design and the plans are in [docs/design/](docs/design/).
```

with:

```markdown
**Status:** slice 1's core, its viewer UI and editing on the canvas are built; the queue
grid (plan 1d) is next. The design and the plans are in [docs/design/](docs/design/).
```

Append to `.claude/skills/run-and-verify-ui/SKILL.md`:

```markdown
Lessons from building editing (plan 1c):

- **A script outside `tests/` runs on the real display.** Only `tests/conftest.py` sets
  offscreen: a spike run from elsewhere opened on `:0`, where synthetic keys never reached
  the window and every shortcut looked broken. Set `QT_QPA_PLATFORM=offscreen` yourself.
- **Drive the canvas with `tests/ui/drive.py`**: `drag` and `click` take scene (image
  pixel) points and send real mouse events to the viewport.
- **Sample a box edge between its handles.** A selected box's handles sit on its corners
  and edge midpoints and are drawn white over the edge.
```

- [ ] **Step 4: Look at the window**

Run, from the repository root:

```bash
SHOT=$(mktemp -d) && QT_QPA_PLATFORM=offscreen DEEPLABELING_STATE_DIR=$SHOT/state PYTHONPATH=src:tests:tests/ui /home/sonnn/miniconda3/bin/python3 - "$SHOT" <<'EOF'
import sys, time
from pathlib import Path
from PySide6.QtWidgets import QApplication
app = QApplication([])
from deeplabeling.__main__ import launch
from drive import click
from fixtures import FakePrompter, build_dataset
shot = Path(sys.argv[1])
ds = build_dataset(shot / "ds")
w = launch([str(ds.yaml)], FakePrompter()); w.resize(1024, 640); w.show()
for _ in range(300):
    app.processEvents(); time.sleep(0.01)
    if w.canvas.image_size and w.inspector.boxes.count() == 2:
        break
w.editing.class_key("2")
click(w.canvas, (32, 24))
app.processEvents()
w.grab().save(str(shot / "window.png"))
print(shot / "window.png")
w.close()
EOF
```

Open the printed PNG. Expected: the person box is filled, with eight white handles, and the inspector's Boxes list highlights `person`. In Classes, `car` carries the ✎ mark: `2` set the active class while nothing was selected.

- [ ] **Step 5: Check the docs and run everything**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 497 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/ui/test_editing.py docs CLAUDE.md .claude/skills/run-and-verify-ui/SKILL.md
git commit -m "ui: an end-to-end editing test; docs match the editor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short
```

Expected: `git status --short` prints nothing.
