# Slice 4b: Find Bad in the full frame — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put plan 4a's findings on screen in the full frame:
- a findings queue in the session, scanning with progress and counting each kind;
- the one-key fixes `M`, `B` and `D`, moving on to the next finding;
- the list rows, the inspector's *Finding* line and the canvas spotlight;
- the queue editor's *Source: Images / Findings* switch.

**Architecture:**
- `ui/session.py` serves a `Findings` source as it serves an `ImageFilter`. Several items stand behind one image, so it asks `Queue.has_image` and `keys_of` where it asked `rel in queue`, and review marks go by `item.entry.rel`. A build sends `Scanned(done, total)` among its batches for the chip.
- `ui/editing.py` selects the finding's label line when the cursor arrives. It owns `M` and `B`; the session owns `D`, which is not an edit.
- `ui/findview.py` says what a finding shows, without Qt: the row's text, the inspector's line and the spotlight. `ui/canvas.py` draws the spotlight: everything outside the crop is dimmed, and the model's box is dashed.

**Tech Stack:** Python 3.10 (conda base), PySide6, pytest-qt; plan 4a's core.

**Spec:** [2026-10-06-find-bad.md](2026-10-06-find-bad.md). This plan implements:
- *The queue*, in the session;
- *Window*: the list and the chip, the full frame, the keys, the queue editor.

Plan 4c builds the grid (crop tiles, multi-select actions) and the measurements.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)).
- **`src/deeplabeling/core/` imports no Qt** (`tests/core/test_core_imports_no_qt.py`); `ui/findview.py` imports no Qt either, so it is tested headless.
- **Every label change is an `Intent` through `Editor`** ([landmine 1](../../CLAUDE.md#landmines)), and the labels have one owner ([landmine 2](../../CLAUDE.md#landmines)). A dismissal is not an edit: undo leaves it alone.
- **A UI change is verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines)): the spotlight's dimming is read from pixels, and the editor's rows by their geometry.
- **The editor is seeded from the queue in force** ([landmine 7](../../CLAUDE.md#landmines)): a findings queue reopens its own settings, and Find Bad's floor starts at 0.40, never at the model's threshold.
- **Tests write only to temporary folders** ([landmine 10](../../CLAUDE.md#landmines)).
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice4-find-bad-frame` from `main`. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone cleaning in the full frame. Each has a named test:

1. **Switching from an image queue to Find Bad.** The cursor lands on a finding of the image it was on, not on the first finding. *(Task 2 `test_a_finding_arrives_with_its_label_selected`.)*
2. **A line above the finding is deleted, then `M`.** The finding's index is stale, so its line is found by its content. *(Task 2 `test_m_finds_the_finding_s_line_after_a_line_above_it_is_deleted`.)*
3. **An image with two findings, marked reviewed.** Both rows tick, and *left* counts the image once. *(Task 1 `test_review_marks_and_left_go_by_image`.)*
4. **A relaunch on a findings queue.** It reopens on the same finding, with its settings. *(Task 1 `test_a_findings_queue_and_its_place_survive_a_relaunch`.)*
5. **An edit beside the finding.** The canvas redraws once, and the spotlight stays. *(Task 3 `test_an_edit_beside_the_finding_redraws_once_and_keeps_the_spotlight`.)*

## Found while building this plan

The plan's code was built in a scratch copy first, and its suite ran green there (873 passed).

- **The session assumed one item per image**, with the item's key as the image's `rel`: review marks, rechecks, late joins, undo's "show the change" and the status bar. Task 1 moves each to `item.entry.rel`, `Queue.has_image` and `Queue.keys_of`. Task 3 fixes the status bar and two notices, which showed a finding's key.
- **Following the cursor across kinds of queue.** An image queue's sort key is `(order,)`, and a finding's is `(kind, −score, order, line)`. When they differ in length, `Queue._is_followed` matches by image, so switching to Find Bad lands on the image you were on.
- **An unmapped nearest box had no name.** `Finding.model_cls` is None for an unmapped class. Task 3 adds `Finding.model_raw`, the model's own class, so the spotlight can caption it `truck? 0.60`. The 4a review asked for this.
- **The spotlight redrew the canvas twice per edit:** once from `set_spotlight`, once from `set_boxes`. `Canvas.set_spotlight` now redraws only when the spotlight changes. `test_an_edit_redraws_the_canvas_once` caught it.

## Decisions this plan makes

- **A cursor saved by a findings queue is `rel#line#kind`.** On relaunch, its image is the part before the first `#`, and the queue follows that `QueueItem`.
- **Fixing the finding's line moves on; editing another line does not.** This holds for `M`, `B`, a class key and `Delete`. "The finding's line" is located by its content (`locate_line`).
- **`M` on a not-an-object finding refuses,** even when its nearest box has a class: the label is not the model's object.
- **A row is `· rel  —  wrong class: car → person 0.80`.** A finding's badge replaces the box count, with ` · fixed` or ` · dismissed` added.
- **The inspector's line is `wrong class · 0.80 · the model: person 0.80`.** With no box near: `the model: nothing near`.
- **The spotlight dims at alpha 110,** under the predictions and the labels. The model's box is drawn even with the predictions layer off: it is the finding.
- **The editor refuses a Find Bad with every kind off** ("choose at least one kind of finding"): such a queue could never report.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/queue.py` | `Scanned`; `Queue.scanned`, `following`; following across kinds; `left` by image | 1 |
| `src/deeplabeling/ui/session.py` | findings queues: restore, follow, scan progress, the chip, review by image, rechecks, late joins; `finding_state`, `dismiss_current`; a finding's badge | 1, 2, 3 |
| `src/deeplabeling/ui/editing.py`, `keymap.py`, `main_window.py` | arriving selected; `M`, `B`; moving on; the keys | 2 |
| `src/deeplabeling/core/findings.py` | `Finding.model_raw` | 3 |
| `src/deeplabeling/ui/findview.py` | `finding_text`, `finding_detail`, `spotlight` | 3 |
| `src/deeplabeling/ui/canvas.py`, `main_window.py`, `inspector.py`, `queue_panel.py`, `model.py` | the spotlight; the *Finding* line; tiles and notices by image | 3 |
| `src/deeplabeling/ui/queue_editor.py`, `prompter.py` | *Source: Images / Findings* and Find Bad's settings | 4 |
| `CLAUDE.md`, the spec | the status | 5 |

---

### Task 1: A findings queue in the session

**Files:**
- Create: `tests/ui/finding_rows.py`, `tests/ui/test_findings_queue.py`
- Modify: `src/deeplabeling/core/queue.py`, `src/deeplabeling/ui/session.py`

**Interfaces:**
- Consumes, from plan 4a:
  - `Findings(scope, settings)`, with `items_for`, `build(ctx, emit, cancelled, *, progress=None)` and `still`;
  - `QueueItem(key, entry, rank, focus, finding)` and `.sort_key`;
  - `Queue.has_image(rel)`, `Queue.keys_of(rel)`;
  - `BuildContext.dismissed`, `Workspace.dismissals.snapshot()`, `source_from_json`.
- Produces:
  - in `deeplabeling.core.queue`: `Scanned(done, total)`, `Queue.scanned: Scanned | None`, and `Queue.following`, a property;
  - in `Session`:
    - `set_queue(source, follow: ImageEntry | QueueItem | None = None)`, which defaults to following `self.current()`;
    - `progress_text()`: ` · scanning N / M` while scanning, then ` · 2 wrong class · 1 not an object · 9 not inferred`;
    - review marks, `left`, `describe_item` and rechecks by `item.entry.rel`;
  - the test helper `tests/ui/finding_rows.py`: `KEY`, `MODEL`, `CAR`, `PERSON`, `BUS`, `P`, `ROWS`, `FOUND`, `put_rows`, `factory`, `load`.

- [ ] **Step 1: Commit this plan, on a new branch**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout -b slice4-find-bad-frame main
git add docs/design/2026-10-06-find-bad-frame-plan.md
git commit -m "docs: the slice 4b plan, Find Bad in the full frame" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/ui/finding_rows.py`:

```python
"""A session with a fake model whose rows are already in the store: what the Find Bad tests
judge (docs/design/2026-10-06-find-bad.md)."""

from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import image_stamp
from fixtures import FakePredictor

KEY = "fake:best.pt"
MODEL = ("car", "person", "bus", "truck")       # car -> car, person -> person, bus -> bus_m (set), truck unmapped
CAR, PERSON, BUS = (0.25, 0.25, 0.1, 0.1), (0.5, 0.5, 0.2, 0.3), (0.75, 0.75, 0.15, 0.15)


def P(cls, box, conf):
    return Prediction(cls, box, conf)


ROWS = {
    "camA/images/0001.jpg": [P(1, CAR, 0.8), P(1, PERSON, 0.9)],        # the car: a person, 0.8
    "camA/images/0002.jpg": [],                                          # a negative
    "camA/images/0003.jpg": [P(0, CAR, 0.9)],                            # no label file
    "camA/images/sub/0005.jpg": [P(0, BUS, 0.95)],                       # the bus_m: a car, 0.95
    "camB/images/0001.jpg": [],                                          # the bus_m: nothing there
    "weird/images/имя пробел.jpg": [P(1, (0.5, 0.5, 0.1, 0.1), 0.5)],    # the person, seen weakly
}
FOUND = ["camA/images/sub/0005.jpg#0#wrong class", "camA/images/0001.jpg#1#wrong class",
         "camB/images/0001.jpg#0#not an object"]


def put_rows(session, rows=ROWS):
    ws = session.workspace
    for rel, preds in rows.items():
        ws.predictions.put(KEY, rel, image_stamp(ws.dataset.root / rel), preds)


def factory(path):
    return FakePredictor(path, names=MODEL)


def load(qtbot, session, weights):
    """Rows first, then the model: the screen's requests find them stored."""
    put_rows(session)
    session.model.factory = factory
    session.model.load(weights)
    qtbot.waitUntil(lambda: session.model.state == "ready", timeout=5000)
    session.model.set_class_map(session.model.class_map.with_target(2, "bus_m"))
```

Create `tests/ui/test_findings_queue.py`:

```python
"""A Find Bad queue in the session (docs/design/2026-10-06-find-bad.md#the-queue)."""

import pytest

from deeplabeling.core.edits import Intent, SetClass
from deeplabeling.core.findings import Findings
from deeplabeling.core.queue import Scanned
from finding_rows import FOUND, KEY, P, load, put_rows
from fixtures import open_session


@pytest.fixture
def weights(tmp_path):
    path = tmp_path / "best.pt"
    path.write_bytes(b"weights")
    return path


@pytest.fixture
def session(qtbot, ds, weights):
    s = open_session(qtbot, ds.yaml)
    load(qtbot, s, weights)
    yield s
    s.close()


def found(qtbot, session, source=Findings()):
    session.set_queue(source)
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    return [item.key for item in session.queue.items]


def test_a_findings_queue_lists_them_in_order_and_counts_them_by_kind(qtbot, session):
    assert found(qtbot, session) == FOUND
    assert session.progress_text() == " · 2 wrong class · 1 not an object · 9 not inferred"


def test_while_it_scans_the_chip_says_how_far(qtbot, session):
    found(qtbot, session)
    queue = session.queue
    queue.complete = False
    session._grew(queue, Scanned(5, 15))
    assert session.progress_text() == " · scanning 5 / 15"


def test_a_dismissed_finding_is_left_out_of_the_next_scan(qtbot, session):
    session.workspace.dismissals.dismiss("camA/images/0001.jpg", "1 0.250000 0.250000 0.100000 0.100000",
                                         "wrong class")
    assert found(qtbot, session) == [FOUND[0], FOUND[2]]


def test_review_marks_and_left_go_by_image(qtbot, session):
    found(qtbot, session)
    session.go_to(FOUND[1])
    rows = []
    session.itemsChanged.connect(lambda keys: rows.append(list(keys)))
    session.done_and_next()
    assert session.workspace.review.is_marked("camA/images/0001.jpg")
    assert rows[-1] == [FOUND[1]] and session.left() == 2
    assert session.describe_item(session.queue.items[1]).startswith("✓ ")


def test_an_edit_that_fixes_a_finding_shows_it_fixed(qtbot, session, ds):
    found(qtbot, session)
    item = session.queue.items[1]                     # the car the model calls a person
    from fixtures import wait_decoded

    wait_decoded(qtbot, session, item.entry.path)
    session.apply(Intent(item.entry.path, (SetClass(item.focus, 0),), "take the model's class"))
    assert session.queue.stale == {FOUND[1]}


def test_findings_of_an_image_inferred_later_join_in_their_place(qtbot, session, ds):
    found(qtbot, session)
    put_rows(session, {"camB/images/rot.jpg": [P(0, (0.75, 0.75, 0.15, 0.15), 0.85)]})   # a bus_m called a car
    with qtbot.waitSignal(session.itemInserted):
        session.model.ready.emit(ds.root / "camB/images/rot.jpg")
    assert [item.key for item in session.queue.items] == [
        FOUND[0], "camB/images/rot.jpg#0#wrong class", FOUND[1], FOUND[2]]
    assert session.progress_text().endswith(" · 8 not inferred")


def test_a_rebuild_keeps_the_finding_the_cursor_is_on(qtbot, session):
    found(qtbot, session)
    session.go_to(FOUND[1])
    session.model.set_class_map(session.model.class_map.with_target(3, "car"))    # rebuilds
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    assert session.current().key == FOUND[1]


def test_a_findings_queue_and_its_place_survive_a_relaunch(qtbot, ds, weights, monkeypatch):
    import deeplabeling.ui.model as model_module
    from drive import start
    from finding_rows import factory

    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    window = start(qtbot, [str(ds.yaml)])
    load(qtbot, window.session, weights)
    found(qtbot, window.session)
    window.session.go_to(FOUND[2])
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert again.session.queue.source == Findings()
    qtbot.waitUntil(lambda: again.session.queue.complete and len(again.session.queue) == 3, timeout=5000)
    assert again.session.current().key == FOUND[2]
    again.close()


def test_without_a_model_it_waits_says_so_and_builds_when_one_is_loaded(qtbot, ds, weights):
    s = open_session(qtbot, ds.yaml)
    s.set_queue(Findings())
    assert s.queue.waiting and len(s.queue) == 0 and s.progress_text() == " · needs a model"
    load(qtbot, s, weights)
    qtbot.waitUntil(lambda: not s.queue.waiting and s.queue.complete, timeout=5000)
    assert [item.key for item in s.queue.items] == FOUND
    s.close()
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_findings_queue.py`
Expected: `cannot import name 'Scanned'`.

- [ ] **Step 4: Serve findings from the session**

In `src/deeplabeling/core/queue.py`, replace:

```python
#: half a step of it (10 px of a 48 px side is 0.208333, so 9.999984 px).
HALF_STEP = 5e-7


```

with:

```python
#: half a step of it (10 px of a 48 px side is 0.208333, so 9.999984 px).
HALF_STEP = 5e-7


@dataclass(frozen=True)
class Scanned:
    """A build's progress, sent among its batches: images looked at, of how many."""

    done: int
    total: int


```

In `src/deeplabeling/core/queue.py`, replace:

```python
        self.left_out: dict[str, set[str]] = {}
        self.waiting = False        #: a model condition waits for a model: nothing is built yet
        self.built_with = None      #: the model (key, class map) its build read, if any
        self._rank: dict[str, tuple] = {}           #: each item's sort key, by key
```

with:

```python
        self.left_out: dict[str, set[str]] = {}
        self.waiting = False        #: a model condition waits for a model: nothing is built yet
        self.scanned: Scanned | None = None     #: how far a scanning build has got
        self.built_with = None      #: the model (key, class map) its build read, if any
        self._rank: dict[str, tuple] = {}           #: each item's sort key, by key
```

In `src/deeplabeling/core/queue.py`, replace:

```python
            self.cursor = self.items[0].key

    def _is_followed(self, item: QueueItem) -> bool:
        f = self._follow
        return item.key == f.key if isinstance(f, QueueItem) else item.entry.rel == f.rel

    def _comes_after(self, item: QueueItem) -> bool:
```

with:

```python
            self.cursor = self.items[0].key

    @property
    def following(self) -> bool:
        """Whether the cursor still waits for its place from before the rebuild."""
        return self._follow is not None and not self._moved

    def _is_followed(self, item: QueueItem) -> bool:
        f = self._follow
        if not isinstance(f, QueueItem):
            return item.entry.rel == f.rel
        if len(item.sort_key) != len(f.sort_key):      # from another kind of queue: its image
            return item.entry.rel == f.entry.rel
        return item.key == f.key

    def _comes_after(self, item: QueueItem) -> bool:
```

In `src/deeplabeling/core/queue.py`, replace:

```python

    def left(self, is_reviewed: Callable[[str], bool]) -> int:
        return sum(1 for item in self.items if not is_reviewed(item.key))

    def recheck(self, entry: ImageEntry, ctx: BuildContext) -> None:
```

with:

```python

    def left(self, is_reviewed: Callable[[str], bool]) -> int:
        """Items whose image is not reviewed: review marks are an image's."""
        return sum(1 for item in self.items if not is_reviewed(item.entry.rel))

    def recheck(self, entry: ImageEntry, ctx: BuildContext) -> None:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol
```

with:

```python
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Protocol
```

In `src/deeplabeling/ui/session.py`, replace:

```python
from ..core.dataset import DatasetError, ImageEntry
from ..core.edits import CreateEmpty, Edit, Intent, Refused
from ..core.queue import BuildContext, ImageFilter, ModelSnapshot, Queue, QueueItem
from ..core.state import Locked
from ..core.store import ImageLabels, LabelState
```

with:

```python
from ..core.dataset import DatasetError, ImageEntry
from ..core.edits import CreateEmpty, Edit, Intent, Refused
from ..core.findings import KINDS, Findings
from ..core.queue import BuildContext, ImageFilter, ModelSnapshot, Queue, QueueItem, Scanned, source_from_json
from ..core.state import Locked
from ..core.store import ImageLabels, LabelState
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self._build = None
        self._by_rel: dict[str, ImageEntry] = {}
        self._follow: ImageEntry | None = None      # where a rebuilding queue must land
        self._seen: tuple | None = None             # (image, raw, state) last reported on screen
        self._keys: frozenset[str] | None = None    # review marks, snapshotted until they change
```

with:

```python
        self._build = None
        self._by_rel: dict[str, ImageEntry] = {}
        self._follow: ImageEntry | QueueItem | None = None  # where a rebuilding queue must land
        self._seen: tuple | None = None             # (image, raw, state) last reported on screen
        self._keys: frozenset[str] | None = None    # review marks, snapshotted until they change
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        try:
            stored = opening.get(QUEUE_SOURCE)
            source = ImageFilter.from_json(stored) if stored else ImageFilter()
        except ValueError:
            source = ImageFilter()
        cursor = opening.get(QUEUE_CURSOR)
        self.set_queue(source, follow=self._by_rel.get(cursor) if cursor else None)

    def set_queue(self, source: ImageFilter, follow: ImageEntry | None = None) -> None:
        """Rebuild the queue from `source`, keeping the cursor on its image if it is still in."""
        ws = self._require()
        if self._build is not None:
```

with:

```python
        try:
            stored = opening.get(QUEUE_SOURCE)
            source = source_from_json(stored) if stored else ImageFilter()
        except ValueError:
            source = ImageFilter()
        cursor = opening.get(QUEUE_CURSOR)
        entry = self._by_rel.get(cursor.split("#")[0]) if cursor else None    # a finding's key starts with its image
        self.set_queue(source, follow=QueueItem(cursor, entry) if entry is not None else None)

    def set_queue(self, source, follow: ImageEntry | QueueItem | None = None) -> None:
        """Rebuild the queue from `source` (images, or findings), keeping the cursor on its
        item if it is still in."""
        ws = self._require()
        if self._build is not None:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            # A rebuild that has not yet reached the user's place still owes it: follow
            # that, not the item the unfinished queue happens to show.
            follow = self._follow or (self.current().entry if self.current() is not None else None)
        self._follow = follow
        queue = self.queue = Queue(source, follow=follow)
```

with:

```python
            # A rebuild that has not yet reached the user's place still owes it: follow
            # that, not the item the unfinished queue happens to show.
            follow = self._follow or self.current()
        self._follow = follow
        queue = self.queue = Queue(source, follow=follow)
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        ctx = self.context()
        self._build = self.io.start(
            lambda emit, cancelled: source.build(ctx, emit, cancelled),
            batch=lambda items: self._grew(queue, items),
            done=lambda finished: self._built(queue, finished, left_out=ctx.left_out),
```

with:

```python
        ctx = self.context()
        self._build = self.io.start(
            lambda emit, cancelled: source.build(ctx, emit, cancelled,
                                                 progress=lambda done, total: emit(Scanned(done, total))),
            batch=lambda items: self._grew(queue, items),
            done=lambda finished: self._built(queue, finished, left_out=ctx.left_out),
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        except KeyError:
            return
        if entry.rel in queue:
            self._recheck((path,))
            return
```

with:

```python
        except KeyError:
            return
        if queue.has_image(entry.rel):
            self._recheck((path,))
            return
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            return
        waiting.discard(entry.rel)
        if queue.source.matches(entry, self.context()):
            empty = queue.cursor is None
            row = queue.insert(QueueItem(entry.rel, entry))
            if row is not None:
                self.itemInserted.emit(row)
            if empty and queue.cursor is not None:
                self._cursor_moved()                # the first image of an empty queue: shown
        self.queueGrew.emit()

```

with:

```python
            return
        waiting.discard(entry.rel)
        empty = queue.cursor is None
        for item in queue.source.items_for(entry, self.context()):     # an image, or its findings
            row = queue.insert(item)
            if row is not None:
                self.itemInserted.emit(row)
        if empty and queue.cursor is not None:
            self._cursor_moved()                    # the first item of an empty queue: shown
        self.queueGrew.emit()

```

In `src/deeplabeling/ui/session.py`, replace:

```python
        snapshot = (ModelSnapshot(model.key, ws.predictions, model.class_map)
                    if model.state == "ready" and model.class_map is not None else None)
        return BuildContext(ws.dataset, ws.store, self._keys, sizes=ws.sizes, model=snapshot)

    def _grew(self, queue: Queue, items: list[QueueItem]) -> None:
        if queue is not self.queue:
            return                                  # a cancelled build's last batch
        before = queue.cursor
        queue.extend(items)
        if self._follow is not None and queue.cursor == self._follow.rel:
            self._follow = None                     # the user's place has arrived
        self.queueGrew.emit()
```

with:

```python
        snapshot = (ModelSnapshot(model.key, ws.predictions, model.class_map)
                    if model.state == "ready" and model.class_map is not None else None)
        return BuildContext(ws.dataset, ws.store, self._keys, sizes=ws.sizes, model=snapshot,
                            dismissed=ws.dismissals.snapshot())

    def _grew(self, queue: Queue, items: list[QueueItem]) -> None:
        if queue is not self.queue:
            return                                  # a cancelled build's last batch
        if isinstance(items, Scanned):
            queue.scanned = items
            self.queueGrew.emit()
            return
        before = queue.cursor
        queue.extend(items)
        if self._follow is not None and not queue.following:
            self._follow = None                     # the user's place has arrived
        self.queueGrew.emit()
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            return " · build failed"
        if not queue.complete:
            return " · building…"
        return "".join(f" · {UNSETTLED[what](len(rels))}" for what, rels in sorted(queue.left_out.items())
                       if rels and what in UNSETTLED)

    def left(self) -> int:
```

with:

```python
            return " · build failed"
        if not queue.complete:
            if queue.scanned is not None:
                return f" · scanning {queue.scanned.done:,} / {queue.scanned.total:,}"
            return " · building…"
        text = ""
        if isinstance(queue.source, Findings):
            counts = Counter(item.finding.kind for item in queue.items)
            text = "".join(f" · {counts[kind]:,} {kind}" for kind in KINDS if counts[kind])
        return text + "".join(f" · {UNSETTLED[what](len(rels))}" for what, rels in sorted(queue.left_out.items())
                              if rels and what in UNSETTLED)

    def left(self) -> int:
```

In `src/deeplabeling/ui/session.py`, replace:

```python

    def describe_item(self, item: QueueItem) -> str:
        tick = "✓" if self._require().review.is_marked(item.key) else "·"
        return f"{tick} {item.key}  —  {self.badge(item)}"

    def reviewed_counts(self) -> tuple[int, int]:
```

with:

```python

    def describe_item(self, item: QueueItem) -> str:
        tick = "✓" if self._require().review.is_marked(item.entry.rel) else "·"
        return f"{tick} {item.entry.rel}  —  {self.badge(item)}"

    def reviewed_counts(self) -> tuple[int, int]:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        if item is None:
            return
        if self._require().review.mark(item.key):
            self._review_changed([item.key])
        self.move(1)

```

with:

```python
        if item is None:
            return
        if self._require().review.mark(item.entry.rel):
            self._review_changed([item.entry.rel])
        self.move(1)

```

In `src/deeplabeling/ui/session.py`, replace:

```python
        if item is None:
            return
        self._require().review.toggle(item.key)
        self._review_changed([item.key])

    def mark_reviewed(self, keys, left: int = 0) -> int:
```

with:

```python
        if item is None:
            return
        self._require().review.toggle(item.entry.rel)
        self._review_changed([item.entry.rel])

    def mark_reviewed(self, keys, left: int = 0) -> int:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        if ws is None:
            return 0
        newly = [key for key in keys if ws.review.mark(key)]
        if newly:
            self._review_changed(newly)
```

with:

```python
        if ws is None:
            return 0
        rels = dict.fromkeys(self.queue.items[self.queue.index_of(key)].entry.rel for key in keys
                             if self.queue is not None and key in self.queue)
        newly = [rel for rel in rels if ws.review.mark(rel)]
        if newly:
            self._review_changed(newly)
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        return len(newly)

    def _review_changed(self, keys: list[str]) -> None:
        self._keys = None                           # the marks snapshot is out of date
        self.saver.schedule()
        self.reviewChanged.emit()
        self.itemsChanged.emit(keys)

    # -- edits -----------------------------------------------------------------
```

with:

```python
        return len(newly)

    def _review_changed(self, rels: list[str]) -> None:
        """These images' marks changed: every item they stand behind is redrawn."""
        self._keys = None                           # the marks snapshot is out of date
        self.saver.schedule()
        self.reviewChanged.emit()
        queue = self.queue
        self.itemsChanged.emit([key for rel in rels for key in queue.keys_of(rel)] if queue is not None else rels)

    # -- edits -----------------------------------------------------------------
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        rel = ws.dataset.entry(image).rel
        current = self.current()
        if self.queue is not None and rel in self.queue and (current is None or current.key != rel):
            self.go_to(rel)                         # the change happens in view
        if len(edit.changes) > chunked.CHUNK:
            self._restore_in_chunks(edit, undo)
```

with:

```python
        rel = ws.dataset.entry(image).rel
        current = self.current()
        if (self.queue is not None and self.queue.has_image(rel)
                and (current is None or current.entry.rel != rel)):
            self.go_to(self.queue.keys_of(rel)[0])  # the change happens in view
        if len(edit.changes) > chunked.CHUNK:
            self._restore_in_chunks(edit, undo)
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            except KeyError:
                continue
            if entry.rel not in self.queue:
                continue
            ctx = ctx or self.context()
            self.queue.recheck(entry, ctx)
            keys.append(entry.rel)
        if keys:
            self.itemsChanged.emit(keys)
```

with:

```python
            except KeyError:
                continue
            if not self.queue.has_image(entry.rel):
                continue
            ctx = ctx or self.context()
            self.queue.recheck(entry, ctx)
            keys.extend(self.queue.keys_of(entry.rel))
        if keys:
            self.itemsChanged.emit(keys)
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_findings_queue.py tests/core/test_queue.py tests/ui/test_filter_queue.py tests/ui/test_panels.py`
Expected: 80 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 842 passed.

```bash
git add src/deeplabeling/core/queue.py src/deeplabeling/ui/session.py tests/ui/finding_rows.py tests/ui/test_findings_queue.py
git commit -m "ui: a findings queue in the session, scanning with progress and counted by kind" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `M`, `B`, `D`, and moving on

**Files:**
- Create: `tests/ui/test_finding_keys.py`
- Modify: `src/deeplabeling/ui/editing.py`, `src/deeplabeling/ui/session.py`, `src/deeplabeling/ui/keymap.py`, `src/deeplabeling/ui/main_window.py`

**Interfaces:**
- Consumes:
  - from Task 1: `tests/ui/finding_rows.py`, and `Session.set_queue` following the current item;
  - from slices 1 and 4a: `SetClass`, `SetBox`, `locate_line(lines, cls_id, bbox, index)`, `actions.clamp_box`, `Dismissals.toggle`/`has`.
- Produces:
  - `Editing.take_model_class()`: `M`. It refuses when there is no mapped model class, or the kind is "not an object", saying "the model has no class for it".
  - `Editing.take_model_box()`: `B`. It refuses with no model box, saying "this finding has no model box".
  - `Session.finding_state(item) -> "dismissed" | "fixed" | ""`.
  - `Session.dismiss_current()`: `D`. It says "dismissed: {kind}" and moves on, or "the dismissal is taken back".
  - the actions `take_model_class`, `take_model_box` and `dismiss`, on `M`, `B` and `D`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_finding_keys.py`:

```python
"""Fixing and dismissing findings from the full frame
(docs/design/2026-10-06-find-bad.md#keys)."""

import pytest
from PySide6.QtCore import Qt

import deeplabeling.ui.model as model_module
from deeplabeling.core.dismissals import Dismissals
from deeplabeling.core.findings import Findings
from drive import start
from finding_rows import FOUND, PERSON, P, factory, load, put_rows
from fixtures import CAMA_0001, read_exact

BUS_M = "2 0.750000 0.750000 0.150000 0.150000\n"


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    load(qtbot, w.session, weights)
    yield w
    w.close()


def findings(qtbot, window, rows=None):
    if rows:
        put_rows(window.session, rows)
    window.session.set_queue(Findings())
    qtbot.waitUntil(lambda: window.session.queue.complete and window.canvas.image_size is not None, timeout=5000)


def on(qtbot, window, key):
    window.session.go_to(key)
    qtbot.waitUntil(lambda: window._shown == window.session.current().entry.path, timeout=5000)


def test_a_finding_arrives_with_its_label_selected(qtbot, window):
    findings(qtbot, window)
    assert window.session.current().key == FOUND[1]          # the image the cursor was on: camA/0001
    assert window.editing.selected() == [1]
    on(qtbot, window, FOUND[0])
    assert window.editing.selected() == [0]


def test_m_takes_the_model_s_class_and_moves_on(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[0])
    qtbot.keyClick(window, Qt.Key_M)                         # sub/0005's bus_m: the model says car
    assert read_exact(ds.lbl("camA/sub/0005")) == "1 0.750000 0.750000 0.150000 0.150000\n"
    assert window.session.current().key == FOUND[1]
    assert window.session.finding_state(window.session.queue.items[0]) == "fixed"


def test_b_takes_the_model_s_box_keeping_the_class(qtbot, window, ds):
    findings(qtbot, window, {"camA/images/0001.jpg": [P(1, (0.26, 0.25, 0.1, 0.1), 0.95), P(1, PERSON, 0.9)]})
    on(qtbot, window, FOUND[1])
    qtbot.keyClick(window, Qt.Key_B)
    assert read_exact(ds.lbl("camA/0001")).splitlines()[1] == "1 0.260000 0.250000 0.100000 0.100000"
    assert window.session.current().key == FOUND[0]          # 0.95 at camA/0001 now sorts first


def test_a_key_that_cannot_apply_says_why_and_changes_nothing(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[2])                              # camB/0001: not an object, no model box
    for key, why in ((Qt.Key_M, "the model has no class for it"), (Qt.Key_B, "this finding has no model box")):
        with qtbot.waitSignal(window.session.status) as said:
            qtbot.keyClick(window, key)
        assert said.args == [why]
    assert read_exact(ds.lbl("camB/0001")) == BUS_M and window.session.current().key == FOUND[2]


def test_d_dismisses_moves_on_and_d_again_takes_it_back(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[0])
    qtbot.keyClick(window, Qt.Key_D)
    first = window.session.queue.items[0]
    assert window.session.finding_state(first) == "dismissed" and window.session.current().key == FOUND[1]
    on(qtbot, window, FOUND[0])
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_D)
    assert said.args == ["the dismissal is taken back"] and window.session.finding_state(first) == ""
    assert window.session.current().key == FOUND[0]
    qtbot.keyClick(window, Qt.Key_D)
    path = window.session.workspace.dismissals.path
    window.close()
    assert Dismissals(path, ds.root).has("camA/images/sub/0005.jpg", BUS_M.strip(), "wrong class")


def test_deleting_a_finding_s_label_moves_on(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[1])
    qtbot.keyClick(window, Qt.Key_Delete)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001.splitlines(keepends=True)[0]
    assert window.session.current().key == FOUND[2]


def test_m_finds_the_finding_s_line_after_a_line_above_it_is_deleted(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[1])                              # camA/0001's car, line 1
    window.editing.pick([0], window.session.labels(window.session.current().entry))
    qtbot.keyClick(window, Qt.Key_Delete)                    # the person: the car is line 0 now
    assert window.session.current().key == FOUND[1]          # not the finding's line: no moving on
    qtbot.keyClick(window, Qt.Key_M)
    assert read_exact(ds.lbl("camA/0001")) == "0 0.250000 0.250000 0.100000 0.100000\n"
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_finding_keys.py`
Expected: 7 failed: no key acts yet, and a finding arrives with nothing selected.

- [ ] **Step 3: Select the finding on arrival; fix, dismiss and move on**

In `src/deeplabeling/ui/session.py`, replace:

```python
        return text

    def describe_item(self, item: QueueItem) -> str:
        tick = "✓" if self._require().review.is_marked(item.entry.rel) else "·"
```

with:

```python
        return text

    def finding_state(self, item: QueueItem) -> str:
        """"dismissed", "fixed" (it no longer holds), or "" for a finding still open."""
        f = item.finding
        if f is None:
            return ""
        if self._require().dismissals.has(item.entry.rel, f.text, f.kind):
            return "dismissed"
        return "fixed" if self.queue is not None and item.key in self.queue.stale else ""

    def dismiss_current(self) -> None:
        """D: dismiss the finding on screen and move on, or take its dismissal back."""
        item = self.current()
        if item is None or item.finding is None:
            return
        f = item.finding
        dismissed = self._require().dismissals.toggle(item.entry.rel, f.text, f.kind)
        self.saver.schedule()
        self.itemsChanged.emit([item.key])
        if dismissed:
            self.status.emit(f"dismissed: {f.kind}")
            self.move(1)
        else:
            self.status.emit("the dismissal is taken back")

    def describe_item(self, item: QueueItem) -> str:
        tick = "✓" if self._require().review.is_marked(item.entry.rel) else "·"
```

In `src/deeplabeling/ui/editing.py`, replace:

```python

from ..core.assist import Shown, accept_image, accept_one
from ..core.edits import Intent
from ..core.geometry import px_to_norm
from ..core.store import ImageLabels
from ..core.workspace import ACTIVE_CLASS, CLASS_COLORS, CLASS_HOTKEYS
```

with:

```python

from ..core.assist import Shown, accept_image, accept_one
from ..core.edits import Intent, SetBox, SetClass
from ..core.geometry import px_to_norm
from ..core.labelio import locate_line
from ..core.store import ImageLabels
from ..core.workspace import ACTIVE_CLASS, CLASS_COLORS, CLASS_HOTKEYS
```

In `src/deeplabeling/ui/editing.py`, replace:

```python
        canvas.resized.connect(self.resize)
        self.selection.changed.connect(self._selection_changed)
        session.cursorChanged.connect(self.selection.clear)
        session.opened.connect(self._active_changed)
        # Before the window and the inspector redraw for an edit, the edit's selection is
```

with:

```python
        canvas.resized.connect(self.resize)
        self.selection.changed.connect(self._selection_changed)
        session.cursorChanged.connect(self._cursor_changed)
        session.opened.connect(self._active_changed)
        # Before the window and the inspector redraw for an edit, the edit's selection is
```

In `src/deeplabeling/ui/editing.py`, replace:

```python

    # -- the image being edited ----------------------------------------------------------

    def show(self, labels: ImageLabels) -> None:
```

with:

```python

    # -- the image being edited ----------------------------------------------------------

    def _cursor_changed(self) -> None:
        """A new item: a finding arrives with its label selected; anything else with none."""
        self.selection.clear()
        item = self.session.current()
        if item is None or item.focus is None or self.session.workspace is None:
            return
        labels = self.session.labels(item.entry)
        index = locate_line(labels.lines, item.focus.cls_id, item.focus.bbox, item.focus.index)
        if index is not None:
            self.selection.select(labels, [index])

    def _on_finding(self, labels: ImageLabels, indices) -> bool:
        """Whether these lines include the current finding's: fixing it moves on."""
        item = self.session.current()
        if item is None or item.focus is None:
            return False
        f = item.focus
        return locate_line(labels.lines, f.cls_id, f.bbox, f.index) in set(indices)

    def show(self, labels: ImageLabels) -> None:
```

In `src/deeplabeling/ui/editing.py`, replace:

```python
        if current and indices:
            image, labels = current
            self._apply(actions.reclassify(image, labels, indices, info.cls_id), select=indices)
        elif self.session.workspace is not None:
            self.set_active(info)
```

with:

```python
        if current and indices:
            image, labels = current
            on_finding = self._on_finding(labels, indices)
            if self._apply(actions.reclassify(image, labels, indices, info.cls_id), select=indices) and on_finding:
                self.session.move(1)
        elif self.session.workspace is not None:
            self.set_active(info)
```

In `src/deeplabeling/ui/editing.py`, replace:

```python
        self._apply(intent, select=_last(1))

    # -- the editing keys -----------------------------------------------------------------

```

with:

```python
        self._apply(intent, select=_last(1))

    # -- Find Bad's keys (docs/design/2026-10-06-find-bad.md#keys) ----------------------------

    def _finding(self):
        """The finding on screen with its label shown, or None."""
        item, current = self.session.current(), self._current()
        if item is None or item.finding is None or not current:
            return None
        return item

    def take_model_class(self) -> None:
        """M: the label becomes the class the model gives it; then the next finding."""
        item = self._finding()
        if item is None:
            return
        if item.finding.model_cls is None or item.finding.kind == "not an object":
            self.session.status.emit("the model has no class for it")
            return
        intent = Intent(item.entry.path, (SetClass(item.focus, item.finding.model_cls),), "take the model's class")
        if self._apply(intent, select=[]):
            self.session.move(1)

    def take_model_box(self) -> None:
        """B: the label takes the model's box, keeping its class; then the next finding."""
        item = self._finding()
        if item is None:
            return
        box = item.finding.model_box and actions.clamp_box(item.finding.model_box)
        if box is None:
            self.session.status.emit("this finding has no model box")
            return
        if self._apply(Intent(item.entry.path, (SetBox(item.focus, box),), "take the model's box"), select=[]):
            self.session.move(1)

    # -- the editing keys -----------------------------------------------------------------

```

In `src/deeplabeling/ui/editing.py`, replace:

```python
        if current:
            image, labels = current
            self._apply(actions.delete(image, labels, self.selection.indices(labels)), select=[])

    def select_step(self, step: int) -> None:
```

with:

```python
        if current:
            image, labels = current
            indices = self.selection.indices(labels)
            on_finding = self._on_finding(labels, indices)
            if self._apply(actions.delete(image, labels, indices), select=[]) and on_finding:
                self.session.move(1)

    def select_step(self, step: int) -> None:
```

In `src/deeplabeling/ui/keymap.py`, replace:

```python
    ActionSpec("toggle_predictions", "Predictions", ("P",), checkable=True),
    ActionSpec("accept_missing", "Accept the missing predictions on this image", ("A",)),
)

```

with:

```python
    ActionSpec("toggle_predictions", "Predictions", ("P",), checkable=True),
    ActionSpec("accept_missing", "Accept the missing predictions on this image", ("A",)),
    ActionSpec("take_model_class", "Find Bad: the label takes the model's class", ("M",)),
    ActionSpec("take_model_box", "Find Bad: the label takes the model's box, keeping its class", ("B",)),
    ActionSpec("dismiss", "Find Bad: dismiss the finding, or take the dismissal back", ("D",)),
)

```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
            "paste": self.editing.paste,
            "accept_missing": self.editing.accept_missing,
        })
        layers = self.state_bar.layers.menu()
```

with:

```python
            "paste": self.editing.paste,
            "accept_missing": self.editing.accept_missing,
            "take_model_class": self.editing.take_model_class,
            "take_model_box": self.editing.take_model_box,
            "dismiss": session.dismiss_current,
        })
        layers = self.state_bar.layers.menu()
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_finding_keys.py tests/ui/test_editing.py tests/ui/test_keymap.py`
Expected: 40 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 849 passed.

```bash
git add src/deeplabeling/ui/editing.py src/deeplabeling/ui/session.py src/deeplabeling/ui/keymap.py src/deeplabeling/ui/main_window.py tests/ui/test_finding_keys.py
git commit -m "ui: M, B and D fix or dismiss the finding on screen, then move on" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: What a finding shows

**Files:**
- Create: `src/deeplabeling/ui/findview.py`, `tests/ui/test_finding_view.py`
- Modify: `src/deeplabeling/core/findings.py`, `tests/core/test_findings.py`, `src/deeplabeling/ui/session.py`, `src/deeplabeling/ui/canvas.py`, `src/deeplabeling/ui/main_window.py`, `src/deeplabeling/ui/inspector.py`, `src/deeplabeling/ui/queue_panel.py`, `src/deeplabeling/ui/model.py`

**Interfaces:**
- Consumes:
  - from Tasks 1 and 2: `Session.finding_state`, `Session.dismiss_current`, `finding_rows`;
  - from plan 4a: `crop_rect(label, model, w, h)`;
  - from slice 2: `PredictionView`, `class_color`, `UNKNOWN`, `ModelSession.names`.
- Produces:
  - `Finding.model_raw: int | None`, the model's own class of the model's box;
  - in `deeplabeling.ui.findview`:
    - `finding_text(f, dataset)`;
    - `finding_detail(f, dataset, model_names)`;
    - `spotlight(f, dataset, size, colors, model_names) -> (crop, PredictionView | None) | None`;
  - `Canvas.set_spotlight(rect, view=None)` and `Canvas.spotlight`, reset by `set_image`;
  - `Inspector.finding_label`;
  - `tile_text`, the status bar and the decode and predict notices, by `item.entry.rel`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/core/test_findings.py`:

```python
def test_a_finding_keeps_the_model_s_own_class_even_when_it_is_unmapped(labels, dataset, cmap):
    far = (0.33, 0.25, 0.1, 0.1)                                 # a truck near the car: unmapped
    [f] = judge(labels("camA/images/0001.jpg"), [P(1, PERSON, 0.9), P(3, far, 0.9)], cmap, dataset, FindSettings())
    assert f.kind == "not an object" and f.model_cls is None and f.model_raw == 3
```

Create `tests/ui/test_finding_view.py`:

```python
"""What a finding shows: its row, the inspector's line, and the spotlight
(docs/design/2026-10-06-find-bad.md#window)."""

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage

import deeplabeling.ui.model as model_module
from deeplabeling.core.findings import Finding, Findings
from deeplabeling.ui.boxes import PredictionView
from deeplabeling.ui.canvas import Canvas
from deeplabeling.ui.findview import finding_text
from deeplabeling.ui.queue_panel import tile_text
from drive import start
from finding_rows import FOUND, factory, load

CAR = (0.25, 0.25, 0.1, 0.1)


@pytest.mark.parametrize("finding, text", [
    (Finding(1, "", "wrong class", 0.82, 1, CAR, 0, CAR, 0.82), "wrong class: car → person 0.82"),
    (Finding(1, "", "not an object", 0.97, 2, CAR), "not an object: bus_m (nearest 0.03)"),
    (Finding(1, "", "not an object", 0.8, 2, CAR, None, CAR, 0.6, model_raw=3), "not an object: bus_m (nearest 0.20)"),
    (Finding(1, "", "weakly seen", 0.59, 1, CAR, 1, CAR, 0.41), "weakly seen: car 0.41"),
    (Finding(1, "", "wrong class", 0.9, 9, CAR, 0, CAR, 0.9), "wrong class: #9? → person 0.90"),
])
def test_a_finding_reads_as_words(ds, finding, text):
    from deeplabeling.core.dataset import Dataset

    assert finding_text(finding, Dataset.open(ds.yaml)) == text


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    load(qtbot, w.session, weights)
    w.session.set_queue(Findings())
    qtbot.waitUntil(lambda: w.session.queue.complete and w.canvas.image_size is not None, timeout=5000)
    yield w
    w.close()


def test_rows_name_the_finding_and_say_when_it_is_fixed_or_dismissed(qtbot, window):
    session = window.session
    rows = [session.describe_item(item) for item in session.queue.items]
    assert rows == ["· camA/images/sub/0005.jpg  —  wrong class: bus_m → car 0.95",
                    "· camA/images/0001.jpg  —  wrong class: car → person 0.80",
                    "· camB/images/0001.jpg  —  not an object: bus_m (nearest 0.00)"]
    session.go_to(FOUND[0])
    session.dismiss_current()
    assert session.describe_item(session.queue.items[0]).endswith("car 0.95 · dismissed")


def test_a_tile_names_its_image_and_is_ticked_by_it(qtbot, window):
    session = window.session
    item = session.queue.items[1]
    assert tile_text(session, item) == "0001.jpg · wrong class: car → person 0.80"
    session.mark_reviewed([item.key])
    assert tile_text(session, item).startswith("✓ 0001.jpg")


def test_the_inspector_has_a_finding_line(qtbot, window):
    assert window.inspector.finding_label.text() == "wrong class · 0.80 · the model: person 0.80"
    window.session.set_queue(window.session.queue.source.scope)          # an image queue
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    assert window.inspector.finding_label.text() == "—"


def test_the_full_frame_dims_around_the_finding_and_draws_the_model_s_box(qtbot, window):
    canvas = window.canvas
    rect, view = canvas.spotlight                              # camA/0001's car: (13, 10)-(19, 14) of 64 x 48
    assert rect == (9, 6, 23, 18) and view.caption == "person 0.80"
    window.session.set_queue(window.session.queue.source.scope)
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    assert canvas.spotlight is None


def test_a_spotlight_is_drawn_dimmed_outside_and_plain_inside(qtbot):
    canvas = Canvas()
    qtbot.addWidget(canvas)
    canvas.resize(400, 300)
    canvas.show()
    image = QImage(200, 100, QImage.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    canvas.set_image(image)
    view = PredictionView(-1, (60, 30, 100, 60), "#00ff00", "car 0.90", False)
    canvas.set_spotlight((50, 20, 110, 70), view)
    canvas.set_boxes([])
    shot = canvas.viewport().grab().toImage()

    def grey(x, y):
        return QColor(shot.pixel(canvas.mapFromScene(QPointF(x, y)))).red()

    assert grey(80, 45) > 180 and grey(20, 50) < 140             # inside plain, outside dimmed
    assert QColor(shot.pixel(canvas.mapFromScene(QPointF(80, 30)))).green() > 150    # the model's box


def test_the_status_bar_names_the_image_not_the_finding_key(qtbot, window):
    assert window.status_text.text().startswith("camA/images/0001.jpg · 64 × 48 · item 2 / 3")


def test_an_edit_beside_the_finding_redraws_once_and_keeps_the_spotlight(qtbot, window, monkeypatch):
    session, editing = window.session, window.editing
    editing.pick([0], session.labels(session.current().entry))              # the person, not the finding
    lit, redraws, redraw = window.canvas.spotlight, [], window.canvas._redraw
    monkeypatch.setattr(window.canvas, "_redraw", lambda: (redraws.append(1), redraw()))
    editing.choose_class(next(i for i in editing.classes() if i.name == "bus_m"))
    assert len(redraws) == 1 and window.canvas.spotlight == lit
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_findings.py`
Expected: 1 failed, 21 passed: `model_raw`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_finding_view.py`
Expected: `No module named 'deeplabeling.ui.findview'`.

- [ ] **Step 3: Keep the model's own class; say and draw what a finding is**

In `src/deeplabeling/ui/session.py`, replace:

```python
from .chunked import Chunked
from .classes import assign_classes
from .images import THUMB_BYTES, ImageCache, decode_thumb
from .model import ModelSession
```

with:

```python
from .chunked import Chunked
from .classes import assign_classes
from .findview import finding_text
from .images import THUMB_BYTES, ImageCache, decode_thumb
from .model import ModelSession
```

In `src/deeplabeling/ui/session.py`, replace:

```python

    def badge(self, item: QueueItem, labels: ImageLabels | None = None) -> str:
        labels = self.labels(item.entry) if labels is None else labels
        if labels.state is LabelState.ERROR:
```

with:

```python

    def badge(self, item: QueueItem, labels: ImageLabels | None = None) -> str:
        if item.finding is not None:
            state = self.finding_state(item)
            return finding_text(item.finding, self._require().dataset) + (f" · {state}" if state else "")
        labels = self.labels(item.entry) if labels is None else labels
        if labels.state is LabelState.ERROR:
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
from .classes import DEFAULT_HOTKEYS
from .editing import Editing
from .inspector import Inspector
from .keymap import HelpDialog, build_actions
```

with:

```python
from .classes import DEFAULT_HOTKEYS
from .editing import Editing
from .findview import spotlight
from .inspector import Inspector
from .keymap import HelpDialog, build_actions
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
            if why is not None:
                self._shown = None
                self.canvas.set_image(None, f"Cannot decode {item.key}: {why}")
                self.notices.add("error", f"{item.key}: the image cannot be decoded ({why}); "
                                 "its labels are not edited", image=path, key=f"decode:{item.key}")
            elif image is None:
                self._shown = None
```

with:

```python
            if why is not None:
                self._shown = None
                self.canvas.set_image(None, f"Cannot decode {item.entry.rel}: {why}")
                self.notices.add("error", f"{item.entry.rel}: the image cannot be decoded ({why}); "
                                 "its labels are not edited", image=path, key=f"decode:{item.entry.rel}")
            elif image is None:
                self._shown = None
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        highlight = session.queue.source.highlight(labels, ws.dataset, self._seen(item))
        self.editing.show(labels)
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
                                        ws.root_settings.get(CLASS_COLORS), highlight),
```

with:

```python
        highlight = session.queue.source.highlight(labels, ws.dataset, self._seen(item))
        self.editing.show(labels)
        lit = None if item.finding is None else spotlight(
            item.finding, ws.dataset, self.canvas.image_size, ws.root_settings.get(CLASS_COLORS), session.model.names)
        self.canvas.set_spotlight(*(lit or (None,)))
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
                                        ws.root_settings.get(CLASS_COLORS), highlight),
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
            self.status_text.setText("")
            return
        parts = [item.key]
        if self.canvas.image_size is not None and self._shown == item.entry.path:
            parts.append("{} × {}".format(*self.canvas.image_size))
```

with:

```python
            self.status_text.setText("")
            return
        parts = [item.entry.rel]
        if self.canvas.image_size is not None and self._shown == item.entry.path:
            parts.append("{} × {}".format(*self.canvas.image_size))
```

In `src/deeplabeling/core/findings.py`, replace:

```python
    model_box: Box | None = None    #: the deciding prediction, or the nearest from NEAREST_MIN_IOU
    model_conf: float | None = None


```

with:

```python
    model_box: Box | None = None    #: the deciding prediction, or the nearest from NEAREST_MIN_IOU
    model_conf: float | None = None
    model_raw: int | None = None    #: the model's own class of that box, mapped or not


```

In `src/deeplabeling/core/findings.py`, replace:

```python
            if cls is None:
                continue                            # inconclusive: no weaker mapped box overrules it
            model = dict(model_cls=cls, model_box=p.box, model_conf=p.conf)
            if not agrees(cls, line.cls_id, dataset):
                if settings.wrong_class and p.conf <= settings.ceiling:
```

with:

```python
            if cls is None:
                continue                            # inconclusive: no weaker mapped box overrules it
            model = dict(model_cls=cls, model_box=p.box, model_conf=p.conf, model_raw=p.cls)
            if not agrees(cls, line.cls_id, dataset):
                if settings.wrong_class and p.conf <= settings.ceiling:
```

In `src/deeplabeling/core/findings.py`, replace:

```python
            if settings.band[0] <= near <= settings.band_hi:
                kept = nearest if nearest is not None and near >= NEAREST_MIN_IOU else None
                model = (dict(model_cls=cmap.translate(kept.cls, dataset), model_box=kept.box, model_conf=kept.conf)
                         if kept is not None else {})
                found.append(Finding(kind="not an object", score=1 - near, **base, **model))
```

with:

```python
            if settings.band[0] <= near <= settings.band_hi:
                kept = nearest if nearest is not None and near >= NEAREST_MIN_IOU else None
                model = (dict(model_cls=cmap.translate(kept.cls, dataset), model_box=kept.box, model_conf=kept.conf,
                              model_raw=kept.cls)
                         if kept is not None else {})
                found.append(Finding(kind="not an object", score=1 - near, **base, **model))
```

Create `src/deeplabeling/ui/findview.py`:

```python
"""What a finding shows -- its row, the inspector's line and the spotlight -- computed
without Qt so it is tested headless (docs/design/2026-10-06-find-bad.md#window)."""

from __future__ import annotations

from ..core.crops import crop_rect
from ..core.dataset import Dataset
from ..core.findings import Finding
from ..core.geometry import norm_to_px
from .boxes import PredictionView
from .classes import UNKNOWN, class_color


def _name(cls: int, dataset: Dataset) -> str:
    return dataset.names[cls] if 0 <= cls < len(dataset.names) else f"#{cls}?"


def _model_name(f: Finding, dataset: Dataset, model_names: tuple[str, ...]) -> str:
    """The dataset class of the model's box, or the model's own name with `?` when unmapped."""
    if f.model_cls is not None:
        return _name(f.model_cls, dataset)
    raw = f.model_raw
    return f"{model_names[raw] if raw is not None and 0 <= raw < len(model_names) else raw}?"


def finding_text(f: Finding, dataset: Dataset) -> str:
    """`wrong class: car → truck 0.82`, `not an object: bus_m (nearest 0.03)`, `weakly seen: car 0.41`."""
    label = _name(f.label_cls, dataset)
    if f.kind == "wrong class":
        return f"wrong class: {label} → {_name(f.model_cls, dataset)} {f.model_conf:.2f}"
    if f.kind == "not an object":
        return f"not an object: {label} (nearest {1 - f.score:.2f})"
    return f"weakly seen: {label} {f.model_conf:.2f}"


def finding_detail(f: Finding, dataset: Dataset, model_names: tuple[str, ...]) -> str:
    """The inspector's line: the kind, the score, the model's class and confidence."""
    model = ("nothing near" if f.model_box is None
             else f"{_model_name(f, dataset, model_names)} {f.model_conf:.2f}")
    return f"{f.kind} · {f.score:.2f} · the model: {model}"


def spotlight(f: Finding, dataset: Dataset, size: tuple[int, int], colors: dict[str, str],
              model_names: tuple[str, ...]):
    """(the crop in pixels, the model's box as drawn or None), or None when the crop is empty."""
    w, h = size
    rect = crop_rect(f.label_box, f.model_box, w, h)
    if rect is None:
        return None
    if f.model_box is None:
        return rect, None
    name = _model_name(f, dataset, model_names)
    color = UNKNOWN if f.model_cls is None else class_color(f.model_cls, name, colors)
    return rect, PredictionView(-1, norm_to_px(f.model_box, w, h), color, f"{name} {f.model_conf:.2f}",
                                False, emphasised=True)
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
def tile_text(session: Session, item: QueueItem, labels=None) -> str:
    """A tile's caption: the reviewed tick, the file name and the badge."""
    tick = "✓ " if session.workspace.review.is_marked(item.key) else ""
    return f"{tick}{Path(item.key).name} · {session.badge(item, labels)}"


```

with:

```python
def tile_text(session: Session, item: QueueItem, labels=None) -> str:
    """A tile's caption: the reviewed tick, the file name and the badge."""
    tick = "✓ " if session.workspace.review.is_marked(item.entry.rel) else ""
    return f"{tick}{Path(item.entry.rel).name} · {session.badge(item, labels)}"


```

In `src/deeplabeling/ui/inspector.py`, replace:

```python
from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .session import Session

```

with:

```python
from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .findview import finding_detail
from .session import Session

```

In `src/deeplabeling/ui/inspector.py`, replace:

```python
        self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label = (
            QLabel() for _ in range(5))
        self.predictions_label = QLabel()
        for label in self._fields():
            label.setWordWrap(True)
```

with:

```python
        self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label = (
            QLabel() for _ in range(5))
        self.predictions_label, self.finding_label = QLabel(), QLabel()
        for label in self._fields():
            label.setWordWrap(True)
```

In `src/deeplabeling/ui/inspector.py`, replace:

```python
        form.addRow("Reviewed", self.reviewed_label)
        form.addRow("Predictions", self.predictions_label)
        self.classes = QListWidget()
        self.boxes = QListWidget()
```

with:

```python
        form.addRow("Reviewed", self.reviewed_label)
        form.addRow("Predictions", self.predictions_label)
        form.addRow("Finding", self.finding_label)
        self.classes = QListWidget()
        self.boxes = QListWidget()
```

In `src/deeplabeling/ui/inspector.py`, replace:

```python
        # *_label names: a field called `size` would shadow QWidget.size()
        return (self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label,
                self.predictions_label)

    def _labels_event(self, images) -> None:
```

with:

```python
        # *_label names: a field called `size` would shadow QWidget.size()
        return (self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label,
                self.predictions_label, self.finding_label)

    def _labels_event(self, images) -> None:
```

In `src/deeplabeling/ui/inspector.py`, replace:

```python
        self.reviewed_label.setText(time.strftime("%Y-%m-%d %H:%M", time.localtime(marked)) if marked else "not yet")
        self.predictions_label.setText(self._predictions_text(session.model, entry))
        colors = ws.root_settings.get(CLASS_COLORS)
        counts = Counter(line.cls_id for _, line in labels.boxes)
```

with:

```python
        self.reviewed_label.setText(time.strftime("%Y-%m-%d %H:%M", time.localtime(marked)) if marked else "not yet")
        self.predictions_label.setText(self._predictions_text(session.model, entry))
        self.finding_label.setText("—" if item.finding is None else
                                   finding_detail(item.finding, ws.dataset, session.model.names))
        colors = ws.root_settings.get(CLASS_COLORS)
        counts = Counter(line.cls_id for _, line in labels.boxes)
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
```

with:

```python

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
SELECTED_ALPHA = 70     #: a selected box is filled with its colour at this opacity
FAINT_ALPHA = 90        #: a prediction an accept would not add is drawn at this opacity
CROSSHAIR = "#ffffff"
#: the eight handles of a box, as fractions of its width and height
```

with:

```python
SELECTED_ALPHA = 70     #: a selected box is filled with its colour at this opacity
FAINT_ALPHA = 90        #: a prediction an accept would not add is drawn at this opacity
DIM_ALPHA = 110         #: a finding's spotlight darkens the frame around its crop this much
CROSSHAIR = "#ffffff"
#: the eight handles of a box, as fractions of its width and height
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
        self._predictions: list[PredictionView] = []
        self._pred_items: list[QGraphicsItem] = []
        self.show_predictions = True
        self._size: tuple[int, int] | None = None
```

with:

```python
        self._predictions: list[PredictionView] = []
        self._pred_items: list[QGraphicsItem] = []
        self._spotlight: tuple[tuple[int, int, int, int], PredictionView | None] | None = None
        self._spot_items: list[QGraphicsItem] = []
        self.show_predictions = True
        self._size: tuple[int, int] | None = None
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
    def set_image(self, image: QImage | None, message: str = "") -> None:
        """Show an image, fitted to the view; or no image and a message saying why."""
        self._views, self._selected, self._predictions = [], frozenset(), []
        self._clear()
        if image is None:
```

with:

```python
    def set_image(self, image: QImage | None, message: str = "") -> None:
        """Show an image, fitted to the view; or no image and a message saying why."""
        self._views, self._selected, self._predictions, self._spotlight = [], frozenset(), [], None
        self._clear()
        if image is None:
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
        self._redraw()

    def prediction_caption_items(self) -> list[CaptionItem]:
        return [it for it in self._pred_items if isinstance(it, CaptionItem)]
```

with:

```python
        self._redraw()

    @property
    def spotlight(self):
        """(the crop, the model's box) a finding is shown with, or None."""
        return self._spotlight

    def set_spotlight(self, rect: tuple[int, int, int, int] | None, view: PredictionView | None = None) -> None:
        """Dim everything outside `rect` and draw the model's box `view` dashed; None: no spotlight.
        The view keeps its zoom (docs/design/2026-10-06-find-bad.md#the-full-frame)."""
        spot = None if rect is None else (rect, view)
        if spot != self._spotlight:                 # an edit re-shows the same one: drawn once
            self._spotlight = spot
            self._redraw()

    def prediction_caption_items(self) -> list[CaptionItem]:
        return [it for it in self._pred_items if isinstance(it, CaptionItem)]
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
    def _clear(self) -> None:
        self._drag = None                           # whatever it previewed is gone
        for item in self._items + self._pred_items + ([self._preview] if self._preview else []):
            self.scene().removeItem(item)
        self._items, self._box_items, self._handles, self._preview = [], {}, [], None
        self._pred_items = []

    def _redraw(self) -> None:
```

with:

```python
    def _clear(self) -> None:
        self._drag = None                           # whatever it previewed is gone
        for item in self._items + self._pred_items + self._spot_items + ([self._preview] if self._preview else []):
            self.scene().removeItem(item)
        self._items, self._box_items, self._handles, self._preview = [], {}, [], None
        self._pred_items, self._spot_items = [], []

    def _redraw(self) -> None:
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
        if self._size is None:
            return
        if self.show_predictions:                   # shown with the labels hidden, too
            for view in self._predictions:
```

with:

```python
        if self._size is None:
            return
        if self._spotlight is not None:
            self._draw_spotlight(*self._spotlight)
        if self.show_predictions:                   # shown with the labels hidden, too
            for view in self._predictions:
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
            self._draw(view)

    def _draw_prediction(self, view: PredictionView) -> None:
        color = QColor(view.color)
        if view.faint:
```

with:

```python
            self._draw(view)

    def _draw_spotlight(self, rect, view: PredictionView | None) -> None:
        w, h = self._size
        x1, y1, x2, y2 = rect
        around = QPainterPath()
        around.setFillRule(Qt.OddEvenFill)
        around.addRect(QRectF(0, 0, w, h))
        around.addRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)))
        dim = self.scene().addPath(around, QPen(Qt.NoPen), QBrush(QColor(0, 0, 0, DIM_ALPHA)))
        dim.setZValue(0.4)                          # under the predictions and the labels
        self._spot_items.append(dim)
        if view is not None:
            self._draw_prediction(view, self._spot_items)

    def _draw_prediction(self, view: PredictionView, into: list | None = None) -> None:
        into = self._pred_items if into is None else into
        color = QColor(view.color)
        if view.faint:
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
        shape = self.scene().addRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)), pen)
        shape.setZValue(0.5)                        # under the labels
        self._pred_items.append(shape)
        if self.show_captions and not view.faint:   # a faint one's label names it already
            caption = CaptionItem(view.caption, view.color, above=True)
```

with:

```python
        shape = self.scene().addRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)), pen)
        shape.setZValue(0.5)                        # under the labels
        into.append(shape)
        if self.show_captions and not view.faint:   # a faint one's label names it already
            caption = CaptionItem(view.caption, view.color, above=True)
```

In `src/deeplabeling/ui/canvas.py`, replace:

```python
            caption.setZValue(0.6)
            self.scene().addItem(caption)
            self._pred_items.append(caption)

    def _draw(self, view: BoxView) -> None:
```

with:

```python
            caption.setZValue(0.6)
            self.scene().addItem(caption)
            into.append(caption)

    def _draw(self, view: BoxView) -> None:
```

In `src/deeplabeling/ui/model.py`, replace:

```python
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self.session.notice.emit("error", f"{item.key}: the model could not predict ({why})", path)
        self.failed.emit(path, why)
```

with:

```python
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self.session.notice.emit("error", f"{item.entry.rel}: the model could not predict ({why})", path)
        self.failed.emit(path, why)
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_findings.py tests/ui/test_finding_view.py tests/ui/test_grid.py tests/ui/test_editing.py tests/ui/test_accepting.py`
Expected: 100 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 862 passed.

- [ ] **Step 5: Look at it**

Save a screenshot of the window on a finding, and open it. Write this to a file in the scratchpad (not under `tests/`), and run it with `-p no:cacheprovider --rootdir tests/ui`:

```python
from test_finding_view import window  # noqa: F401


def test_shot(qtbot, window):
    window.resize(1200, 800)
    qtbot.wait(300)
    window.grab().save("spot.png")
```

Expected, in `spot.png`:
- the crop around camA/0001's car is plain, and the frame around it is darker;
- the model's box is dashed and captioned `person 0.80`, and the car is selected;
- the inspector's *Finding* line reads `wrong class · 0.80 · the model: person 0.80`;
- the status bar starts `camA/images/0001.jpg`.

- [ ] **Step 6: Commit**

```bash
git add src/deeplabeling/core/findings.py src/deeplabeling/ui/findview.py src/deeplabeling/ui/session.py src/deeplabeling/ui/canvas.py src/deeplabeling/ui/main_window.py src/deeplabeling/ui/inspector.py src/deeplabeling/ui/queue_panel.py src/deeplabeling/ui/model.py tests/core/test_findings.py tests/ui/test_finding_view.py
git commit -m "ui: a finding's row, its inspector line, and the spotlight around it in the full frame" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The queue editor's source

**Files:**
- Modify: `src/deeplabeling/ui/queue_editor.py`, `src/deeplabeling/ui/prompter.py`, `tests/ui/test_queue_editor.py`, `tests/ui/test_finding_view.py`

**Interfaces:**
- Consumes: `Findings`, `FindSettings` (plan 4a), and `MainWindow.edit_queue`, which passes the chosen source to `Session.set_queue`.
- Produces:
  - `QueueEditor(dataset, current: ImageFilter | Findings, …)`;
  - its widgets: `source_kind` ("Images" / "Findings"), and in `find_rows`: `find_floor`, `find_iou`, `find_wrong`, `find_ceiling`, `find_not_object`, `find_band_lo`, `find_band_hi` (blank: up to the matching IoU), `find_weak`, `find_cutoff`;
  - `source() -> ImageFilter | Findings` and `settings() -> FindSettings`. They refuse with "Find Bad — …" (`ValueError`), and `chosen` is what OK took;
  - `QtPrompter.edit_queue`, typed for both sources.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_finding_view.py`:

```python
def test_the_queue_editor_opens_a_findings_queue_and_is_offered_it_back(qtbot, window):
    session = window.session
    session.set_queue(session.queue.source.scope)
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    window.prompter.queue = Findings()
    window.edit_queue()
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    assert [item.key for item in session.queue.items] == FOUND
    window.edit_queue()
    assert window.prompter.asked[-1][1] == Findings()
```

In `tests/ui/test_queue_editor.py`, replace:

```python

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.queue import (
    Boxes,
```

with:

```python

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.findings import FindSettings, Findings
from deeplabeling.core.queue import (
    Boxes,
```

In `tests/ui/test_queue_editor.py`, replace:

```python
    current = ImageFilter(conditions=(ModelDisagrees("unseen", 0.55, (0.123456789, 1.0)),))
    assert editor(qtbot, dataset, current).filter() == current
```

with:

```python
    current = ImageFilter(conditions=(ModelDisagrees("unseen", 0.55, (0.123456789, 1.0)),))
    assert editor(qtbot, dataset, current).filter() == current


@pytest.mark.parametrize("current", [
    Findings(),
    Findings(ImageFilter(("val",), (NameContains("cam"),)),
             FindSettings(floor=0.5, match_iou=0.6, ceiling=0.9, band=(0.05, 0.3), weak=True, cutoff=0.7)),
    Findings(settings=FindSettings(wrong_class=False, band=(0.123456789, None))),
])
def test_a_findings_queue_seeds_its_scope_and_its_settings(qtbot, dataset, current):
    assert editor(qtbot, dataset, current).source() == current


def test_findings_start_from_the_default_settings_and_their_rows_show_only_for_findings(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter(conditions=(Reviewed(False),)), conf=0.25)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    assert dialog.source() == ImageFilter(conditions=(Reviewed(False),)) and not dialog.find_rows.isVisible()
    dialog.source_kind.setCurrentText("Findings")
    assert dialog.find_rows.isVisible() and dialog.find_floor.text() == "0.4"      # never the model's 0.25
    assert dialog.source() == Findings(ImageFilter(conditions=(Reviewed(False),)), FindSettings())
    dialog.accept()
    assert dialog.chosen == Findings(ImageFilter(conditions=(Reviewed(False),)), FindSettings())


@pytest.mark.parametrize("setup, why", [
    (lambda d: d.find_floor.setText("x"), "Find Bad — confidence floor: “x” is not a number"),
    (lambda d: d.find_floor.setText("0.05"), "Find Bad — confidence floor: must be from 0.1 to 1"),
    (lambda d: (d.find_weak.setChecked(True), d.find_cutoff.setText("0.3")),
     "Find Bad — weak cutoff: 0.3 is not above the confidence floor 0.4"),
    (lambda d: d.find_band_hi.setText("abc"), "Find Bad — not-an-object band: “abc” is not a number"),
    (lambda d: (d.find_wrong.setChecked(False), d.find_not_object.setChecked(False)),
     "Find Bad — choose at least one kind of finding"),
])
def test_find_bad_settings_are_refused_by_name(qtbot, dataset, setup, why):
    dialog = editor(qtbot, dataset, Findings())
    dialog.show()
    setup(dialog)
    dialog.accept()
    assert dialog.isVisible() and dialog.result() != QDialog.Accepted
    assert dialog.error.text() == why and dialog.error.isVisible()


def test_the_find_bad_rows_are_visible_inside_the_dialog_and_none_overlaps(qtbot, dataset):
    from PySide6.QtCore import QPoint, QRect

    dialog = editor(qtbot, dataset, Findings())
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    widgets = [dialog.source_kind, dialog.find_floor, dialog.find_iou, dialog.find_wrong, dialog.find_ceiling,
               dialog.find_not_object, dialog.find_band_lo, dialog.find_band_hi, dialog.find_weak, dialog.find_cutoff,
               dialog.model_mode, dialog.model_hi]
    rects = []
    for w in widgets:
        rect = QRect(w.mapTo(dialog, QPoint(0, 0)), w.size())
        assert w.isVisible() and w.width() >= 30 and dialog.rect().contains(rect)
        assert not any(rect.intersects(r) for r in rects)
        rects.append(rect)
    assert dialog.height() <= 800
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_editor.py`
Expected: 10 failed, 21 passed: `object has no attribute`.

- [ ] **Step 3: Add the source switch and Find Bad's settings**

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
"""The queue editor: splits and conditions for slice 1's one source, ImageFilter
(docs/design/2026-10-04-app-foundation.md#queue), with slice 3's box size, overlap and
model rows (docs/design/2026-10-06-filters.md#the-queue-editor). It is seeded from the
queue in force, so it never shows a filter the queue is not using (CLAUDE.md landmine 7).
A value it cannot use is refused when OK is pressed, by row and field, and the dialog stays
```

with:

```python
"""The queue editor: splits and conditions for slice 1's one source, ImageFilter
(docs/design/2026-10-04-app-foundation.md#queue), with slice 3's box size, overlap and
model rows (docs/design/2026-10-06-filters.md#the-queue-editor), and slice 4's second
source, Findings, whose scope is those rows (docs/design/2026-10-06-find-bad.md#the-queue-editor).
It is seeded from the
queue in force, so it never shows a filter the queue is not using (CLAUDE.md landmine 7).
A value it cannot use is refused when OK is pressed, by row and field, and the dialog stays
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python

from ..core.dataset import Dataset
from ..core.queue import (
    UNITS,
```

with:

```python

from ..core.dataset import Dataset
from ..core.findings import FindSettings, Findings
from ..core.queue import (
    UNITS,
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
MODEL_MODES = {"off": None, "labels the model does not see": "unseen",
               "predictions nobody labelled": "unlabelled", "either": "either"}


```

with:

```python
MODEL_MODES = {"off": None, "labels the model does not see": "unseen",
               "predictions nobody labelled": "unlabelled", "either": "either"}
SOURCES = ("Images", "Findings")


```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python

class QueueEditor(QDialog):
    def __init__(self, dataset: Dataset, current: ImageFilter, parent=None, *, conf: float = 0.25):
        super().__init__(parent)
        self.setWindowTitle("Queue")
        self.splits = {name: QCheckBox(name) for name in dataset.splits}
        split_row = QWidget()
```

with:

```python

class QueueEditor(QDialog):
    def __init__(self, dataset: Dataset, current: ImageFilter | Findings, parent=None, *, conf: float = 0.25):
        super().__init__(parent)
        self.setWindowTitle("Queue")
        self.source_kind = QComboBox()
        self.source_kind.addItems(SOURCES)
        self.splits = {name: QCheckBox(name) for name in dataset.splits}
        split_row = QWidget()
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
        self.error.setWordWrap(True)
        self.error.hide()
        self.chosen: ImageFilter | None = None      #: what OK took
        form = QFormLayout()
        form.addRow("Splits", split_row)
        form.addRow("Classes", self.class_mode)
```

with:

```python
        self.error.setWordWrap(True)
        self.error.hide()
        self.chosen: ImageFilter | Findings | None = None      #: what OK took
        self.find_rows = self._find_rows()
        form = QFormLayout()
        form.addRow("Source", self.source_kind)
        form.addRow("Splits", split_row)
        form.addRow("Classes", self.class_mode)
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self._seed(current)

    def _seed(self, current: ImageFilter) -> None:
```

with:

```python
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.find_rows)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self.source_kind.currentTextChanged.connect(lambda kind: self.find_rows.setVisible(kind == "Findings"))
        if isinstance(current, Findings):
            self.source_kind.setCurrentText("Findings")
            self._seed(current.scope)
            self._seed_settings(current.settings)
        else:
            self._seed(current)
            self._seed_settings(FindSettings())
        self.find_rows.setVisible(self.source_kind.currentText() == "Findings")

    def _find_rows(self) -> QWidget:
        """Find Bad's settings: shown for a Findings queue, whose scope is the rows above."""
        self.find_floor, self.find_iou, self.find_ceiling = _edit(), _edit(), _edit()
        self.find_band_lo, self.find_band_hi, self.find_cutoff = _edit(), _edit(), _edit()
        self.find_band_hi.setPlaceholderText("matching IoU")
        self.find_wrong, self.find_not_object, self.find_weak = (
            QCheckBox("wrong class"), QCheckBox("not an object"), QCheckBox("weakly seen"))
        rows = QWidget()
        form = QFormLayout(rows)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Find Bad", _row(QLabel("confidence floor"), self.find_floor,
                                     QLabel("matching IoU"), self.find_iou))
        form.addRow("", _row(self.find_wrong, QLabel("up to conf"), self.find_ceiling))
        form.addRow("", _row(self.find_not_object, QLabel("nearest IoU"), self.find_band_lo,
                             QLabel("–"), self.find_band_hi))
        form.addRow("", _row(self.find_weak, QLabel("below conf"), self.find_cutoff))
        return rows

    def _seed_settings(self, settings: FindSettings) -> None:
        for edit, value in ((self.find_floor, settings.floor), (self.find_iou, settings.match_iou),
                            (self.find_ceiling, settings.ceiling), (self.find_band_lo, settings.band[0]),
                            (self.find_band_hi, settings.band[1]), (self.find_cutoff, settings.cutoff)):
            edit.setText(_text(value))
        self.find_wrong.setChecked(settings.wrong_class)
        self.find_not_object.setChecked(settings.not_object)
        self.find_weak.setChecked(settings.weak)

    def _seed(self, current: ImageFilter) -> None:
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
        """OK: take the queue the rows describe, or say why not and stay open."""
        try:
            self.chosen = self.filter()
        except ValueError as e:
            self.error.setText(str(e))
```

with:

```python
        """OK: take the queue the rows describe, or say why not and stay open."""
        try:
            self.chosen = self.source()
        except ValueError as e:
            self.error.setText(str(e))
```

In `src/deeplabeling/ui/queue_editor.py`, replace:

```python
        self.error.hide()
        super().accept()

    def filter(self) -> ImageFilter:
```

with:

```python
        self.error.hide()
        super().accept()

    def source(self) -> ImageFilter | Findings:
        """The queue the dialog describes: its image filter, or the findings in it."""
        if self.source_kind.currentText() == "Images":
            return self.filter()
        return Findings(self.filter(), self.settings())

    def settings(self) -> FindSettings:
        """Find Bad's settings; ValueError naming the field when they cannot be used."""
        try:
            settings = FindSettings(
                _number(self.find_floor, "confidence floor"), _number(self.find_iou, "matching IoU"),
                self.find_wrong.isChecked(), _number(self.find_ceiling, "wrong-class ceiling"),
                self.find_not_object.isChecked(),
                (_number(self.find_band_lo, "not-an-object band"),
                 _number(self.find_band_hi, "not-an-object band", blank=True)),
                self.find_weak.isChecked(), _number(self.find_cutoff, "weak cutoff"))
        except ValueError as e:
            raise ValueError(f"Find Bad — {e}") from e
        if not settings.kinds:
            raise ValueError("Find Bad — choose at least one kind of finding")
        return settings

    def filter(self) -> ImageFilter:
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
from ..core.classmap import ClassMap
from ..core.dataset import Dataset
from ..core.inference import FLOOR
from ..core.queue import ImageFilter
```

with:

```python
from ..core.classmap import ClassMap
from ..core.dataset import Dataset
from ..core.findings import Findings
from ..core.inference import FLOOR
from ..core.queue import ImageFilter
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
        return QFileDialog.getExistingDirectory(self.parent, title) or None

    def edit_queue(self, dataset: Dataset, current: ImageFilter, conf: float = 0.25) -> ImageFilter | None:
        dialog = QueueEditor(dataset, current, self.parent, conf=conf)
        try:
```

with:

```python
        return QFileDialog.getExistingDirectory(self.parent, title) or None

    def edit_queue(self, dataset: Dataset, current: ImageFilter | Findings,
                   conf: float = 0.25) -> ImageFilter | Findings | None:
        dialog = QueueEditor(dataset, current, self.parent, conf=conf)
        try:
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_editor.py tests/ui/test_prompter.py tests/ui/test_finding_view.py tests/ui/test_filter_view.py`
Expected: 54 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 873 passed.

- [ ] **Step 5: Look at it**

Screenshot `QueueEditor(Dataset.open(ds.yaml), Findings())`, shown, with `find_floor` set to `x` and OK pressed. Open the screenshot. Expected:
- *Source* reads `Findings`;
- the Find Bad rows sit under the *Model* row, each field wide enough to read;
- the band's open end shows `matching IoU` greyed;
- the error reads `Find Bad — confidence floor: “x” is not a number`.

- [ ] **Step 6: Commit**

```bash
git add src/deeplabeling/ui/queue_editor.py src/deeplabeling/ui/prompter.py tests/ui/test_queue_editor.py tests/ui/test_finding_view.py
git commit -m "ui: the queue editor chooses images or findings, with Find Bad's settings refused by name" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The status

**Files:**
- Modify: `CLAUDE.md`, `docs/design/2026-10-06-find-bad.md`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: the status.

- [ ] **Step 1: Update the status**

In `CLAUDE.md`, replace:

````markdown
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. Slice 4 (Find Bad) has its core built; its full frame (plan 4b) is next. The
design and the plans are in [docs/design/](docs/design/).

```sh
````

with:

````markdown
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. Slice 4 (Find Bad) has its core and its full frame built; its grid (plan 4c)
is next. The design and the plans are in [docs/design/](docs/design/).

```sh
````

In `docs/design/2026-10-06-find-bad.md`, replace:

```markdown
# DeepLabeling — slice 4: Find Bad

**Status:** approved 2026-10-06 · plan 4a (the core) implemented; 4b (the full frame) and 4c (the grid) next
**Scope:** slice 4 of [the app foundation](2026-10-04-app-foundation.md#slices): a queue whose
items are the labels the model disagrees with, each focused on its label line; crop tiles in
```

with:

```markdown
# DeepLabeling — slice 4: Find Bad

**Status:** approved 2026-10-06 · plans 4a (the core) and 4b (the full frame) implemented; 4c (the grid) next
**Scope:** slice 4 of [the app foundation](2026-10-04-app-foundation.md#slices): a queue whose
items are the labels the model disagrees with, each focused on its label line; crop tiles in
```

- [ ] **Step 2: Check the docs, run the full suite, and commit**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 873 passed.

```bash
git add CLAUDE.md docs/design/2026-10-06-find-bad.md
git commit -m "docs: slice 4's full frame is built" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
