# Slice 5a: bulk reassign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reassign one class to another across the queue's images: asked first with counts, written as one edit that one undo takes back, and reached from the queue chip's new menu.

**Architecture:**
- `core/reassign.py` plans a reassign without writing: one `Intent` of `SetClass` ops per image, and the images skipped because their label file cannot be edited. Plans made a chunk at a time add up.
- `ui/reassign.py` runs it as accepting across a queue does:
  - asks From and To (`ui/reassign_dialog.py`);
  - looks a chunk at a time;
  - asks with the counts;
  - writes through `chunked.write_as_one_edit`, which accepting now shares.
- The session lists the queue's images once each (`queue_images`). It keeps the class ids the open-time check found that the yaml does not name, for *From*.
- The queue chip keeps its click, which edits the queue, and gains a menu.

**Tech Stack:** Python 3.10 (conda base), PySide6, pytest-qt; slices 1–4.

**Spec:** [2026-10-07-bulk-and-stats.md](2026-10-07-bulk-and-stats.md). This plan implements:
- *The queue's images*;
- *Bulk reassign*;
- *The queue chip*, without its Statistics entry.

Plan 5b builds the statistics, adds their entry to the chip, and measures both features.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)).
- **`src/deeplabeling/core/` imports no Qt** (`tests/core/test_core_imports_no_qt.py`).
- **The one write path** ([landmine 1](../../CLAUDE.md#landmines)). Every label change is an `Intent` through `Editor`. A reassign is one `Editor.batch` edit, undone whole, and it marks nothing reviewed.
- **A byte the user did not change is not rewritten** ([label-files.md](../knowledge/label-files.md#byte-preserving-round-trips)). A class change splices the first token: coordinates, polygons, extra columns and CRLF are kept. The one exception is a reclassified last line without a line ending, which gains one (`src/deeplabeling/core/labelio.py::LabelLine.with_class`).
- **A UI change is verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines)): the dialog's and the chip's geometry, and a screenshot.
- **Tests write only to temporary folders** ([landmine 10](../../CLAUDE.md#landmines)).
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice5-reassign`, which already holds the spec. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone reassigning a class. Each has a named test:

1. **A file with CRLF, a polygon, an extra column, three identical boxes and no final newline.** Only the class token changes, and the unparsable line stays as it is. *(Task 1 `test_every_box_of_the_class_becomes_the_other_and_nothing_else_changes`.)*
2. **Two images sharing one label file.** Both are skipped and counted, and nothing is written to their file. *(Task 1, the same test; Task 2 `test_it_asks_with_counts_writes_one_edit_and_marks_nothing`.)*
3. **A label file that cannot be read.** It is skipped and counted, because it may hold the class. *(Task 1 `test_an_unreadable_label_file_is_counted_as_it_may_hold_the_class`.)*
4. **Cancelling half-way through the write.** The chunks written stay as one edit, and one undo restores them. *(Task 2 `test_cancelling_the_write_keeps_the_chunks_written_as_one_edit`.)*
5. **A Find Bad queue with several findings on an image.** Each image is looked at once (`Session.queue_images`); accepting across a queue uses it too. *(Task 2; plan 4b's `test_accepting_missing_boxes_in_a_findings_queue_adds_each_box_once` still passes.)*

## Found while building this plan

The plan's code was built in a scratch copy first, and its suite ran green there (976 passed).

- **The out-of-range check kept only its message.** `Session._count_out_of_range` now also keeps the ids (`Session.unnamed_ids`), so *From* can offer `#99?`.
- **Accepting across a queue already wrote a chunk at a time as one edit.** Its `_write` becomes `chunked.write_as_one_edit`, which reassign shares. Accept's own wording, and its tests, are unchanged.
- **Two test files named `test_reassign.py`**, one under `tests/core` and one under `tests/ui`, could not both be collected. The UI one is `test_reassign_queue.py`.

## Decisions this plan makes

- **An unreadable label file counts as skipped whatever it holds:** it cannot be known not to hold the class. A shared one counts only when it holds the class.
- **Answering No, or cancelling the look, says `reassign cancelled: nothing was written`.**
- **A queue that waits for a model says `the queue waits for a model`; one still building says `the queue is still being built`.** In the chip's menu, reassign is disabled until the queue is complete.
- **The history's description is `reassign person to bus_l`**, with `#99?` for an id the yaml does not name.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/reassign.py` | `Reassign`, `plan_reassign` | 1 |
| `src/deeplabeling/ui/chunked.py`, `queue_accept.py` | `write_as_one_edit`, shared by accept and reassign | 2 |
| `src/deeplabeling/ui/session.py` | `queue_images`, `unnamed_ids` | 2 |
| `src/deeplabeling/ui/reassign_dialog.py`, `reassign.py`, `prompter.py` | the dialog, the flow, `ask_reassign` and `confirm_reassign` | 2 |
| `src/deeplabeling/ui/state_bar.py`, `main_window.py` | the queue chip's menu | 3 |
| `CLAUDE.md`, the spec | the status | 4 |

---

### Task 1: Planning a reassign

**Files:**
- Create: `src/deeplabeling/core/reassign.py`, `tests/core/test_reassign.py`

**Interfaces:**
- Consumes: `Intent`, `LineRef`, `SetClass`, `ImageLabels.boxes`/`.editable`/`.state`, and `Editor.apply_many` (used by the tests).
- Produces, in `deeplabeling.core.reassign`:
  - `Reassign(intents, boxes, read_only)`, which supports `+`;
  - `plan_reassign(entries, labels_of, source, target, description) -> Reassign`, which raises `ValueError("From and To are the same class")` when `source` equals `target`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_reassign.py`:

```python
"""Bulk reassign, planned and written as one edit
(docs/design/2026-10-07-bulk-and-stats.md#bulk-reassign)."""

import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.editor import Editor
from deeplabeling.core.history import History
from deeplabeling.core.reassign import Reassign, plan_reassign
from deeplabeling.core.review import ReviewMarks
from deeplabeling.core.store import LabelStore
from fixtures import CAMA_0001, CRLF, MIXED, POLY1, assert_only_changed, read_exact

#: Every class-0 box of the edge-case dataset, as person -> bus_l (3) writes it.
WRITTEN = {"camA/labels/0001.txt", "weird/labels/имя пробел.txt", "bad/labels/corrupt.txt",
           "bad/labels/ok.txt", "crlf/labels/c.txt", "seg/labels/poly1.txt", "seg/labels/mixed.txt"}
GAUNTLET_AFTER = (
    "1 0.5 0.5 0.2 0.2\n"
    "99 0.5 0.5 0.1 0.1\n"
    "-1 0.5 0.5 0.1 0.1\n"
    "3 1.4 0.5 0.2 0.2\n"
    "0 0.5 0.5\n"                   # unparsable: left as it is
    "3 0.5 0.5 0.2 0.2 0.95\n"
    "3 0.5 0.5 0.2 0.2\r\n"
    "abc 0.5 0.5 0.2 0.2\n"
    "\n"
    "   \n"
    "3 0.5 0.5 0.2 0.2\n"           # a reclassified last line gains its ending (labelio.py::LabelLine.with_class)
)


@pytest.fixture
def setup(ds, tmp_path):
    dataset = Dataset.open(ds.yaml)
    store = LabelStore(dataset)
    editor = Editor(store, History(store), ReviewMarks(tmp_path / "review.json", dataset.root))
    return dataset, store, editor


def test_every_box_of_the_class_becomes_the_other_and_nothing_else_changes(ds, setup):
    dataset, store, editor = setup
    plan = plan_reassign(dataset.images, store.get, 0, 3, "reassign person to bus_l")
    assert (plan.boxes, len(plan.intents), plan.read_only) == (10, 7, 2)      # the twins share a file
    before = ds.snapshot()
    editor.apply_many(plan.intents, "reassign person to bus_l")
    assert_only_changed(before, ds.snapshot(), WRITTEN)
    assert read_exact(ds.lbl("camA/0001")) == "3" + CAMA_0001[1:]
    assert read_exact(ds.lbl("crlf/c")) == "3" + CRLF[1:]                     # CRLF kept
    assert read_exact(ds.lbl("seg/poly1")) == "3" + POLY1[1:]                 # a polygon keeps its points
    assert read_exact(ds.lbl("seg/mixed")) == "3" + MIXED[1:]
    assert read_exact(ds.lbl("bad/ok")) == GAUNTLET_AFTER
    assert editor.history.depth == 1 and editor.undo() is not None                  # one edit, undone whole
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_an_id_the_yaml_does_not_name_can_be_reassigned(ds, setup):
    dataset, store, editor = setup
    plan = plan_reassign(dataset.images, store.get, 99, 1, "reassign #99 to car")
    assert (plan.boxes, len(plan.intents)) == (1, 1)
    editor.apply_many(plan.intents, "reassign #99 to car")
    assert read_exact(ds.lbl("bad/ok")).splitlines()[1] == "1 0.5 0.5 0.1 0.1"


def test_an_unreadable_label_file_is_counted_as_it_may_hold_the_class(ds, setup):
    dataset, store, _ = setup
    ds.lbl("camA/0001").chmod(0o000)
    try:
        plan = plan_reassign(dataset.images, LabelStore(dataset).get, 1, 2, "reassign car to bus_m")
    finally:
        ds.lbl("camA/0001").chmod(0o644)
    assert plan.read_only == 1 and all(i.image != ds.img("camA/0001.jpg") for i in plan.intents)


def test_plans_made_a_chunk_at_a_time_add_up(ds, setup):
    dataset, store, _ = setup
    whole = plan_reassign(dataset.images, store.get, 0, 3, "r")
    parts = [plan_reassign(dataset.images[i:i + 4], store.get, 0, 3, "r") for i in range(0, len(dataset.images), 4)]
    total = Reassign((), 0, 0)
    for part in parts:
        total += part
    assert total == whole


def test_a_class_onto_itself_is_refused(ds, setup):
    dataset, store, _ = setup
    with pytest.raises(ValueError, match="the same class"):
        plan_reassign(dataset.images, store.get, 1, 1, "r")
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_reassign.py`
Expected: `No module named 'deeplabeling.core.reassign'`.

- [ ] **Step 3: Plan a reassign**

Create `src/deeplabeling/core/reassign.py`:

```python
"""Bulk reassign, planned (docs/design/2026-10-07-bulk-and-stats.md#bulk-reassign): every box
of one class in some images becomes another class. It reads only, so it is looked at a chunk
at a time; its intents are written as one edit (`src/deeplabeling/core/editor.py::Editor.batch`).
A class id the yaml does not name can be reassigned too."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .dataset import ImageEntry
from .edits import Intent, LineRef, SetClass
from .store import ImageLabels, LabelState


@dataclass(frozen=True)
class Reassign:
    intents: tuple[Intent, ...]     #: one per image, setting the class of each of its boxes of it
    boxes: int
    read_only: int                  #: images skipped: their label file cannot be edited, and holds the class or cannot be read

    def __add__(self, other: Reassign) -> Reassign:
        return Reassign(self.intents + other.intents, self.boxes + other.boxes, self.read_only + other.read_only)


def plan_reassign(entries: Iterable[ImageEntry], labels_of: Callable[[Path], ImageLabels],
                  source: int, target: int, description: str) -> Reassign:
    """What turning every class-`source` box of these images into `target` would write."""
    if source == target:
        raise ValueError("From and To are the same class")
    intents, boxes, read_only = [], 0, 0
    for entry in entries:
        labels = labels_of(entry.path)
        lines = [(i, line) for i, line in labels.boxes if line.cls_id == source]
        if not labels.editable:
            read_only += bool(lines) or labels.state is LabelState.ERROR
            continue
        if lines:
            ops = tuple(SetClass(LineRef(i, line.cls_id, line.bbox), target) for i, line in lines)
            intents.append(Intent(entry.path, ops, description))
            boxes += len(lines)
    return Reassign(tuple(intents), boxes, read_only)
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_reassign.py tests/core/test_core_imports_no_qt.py`
Expected: 6 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 961 passed.

```bash
git add src/deeplabeling/core/reassign.py tests/core/test_reassign.py
git commit -m "core: a reassign planned, one SetClass intent per image, skipping files that cannot be edited" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Reassign a class in this queue

**Files:**
- Create: `src/deeplabeling/ui/reassign.py`, `src/deeplabeling/ui/reassign_dialog.py`, `tests/ui/test_reassign_queue.py`, `tests/ui/test_reassign_dialog.py`
- Modify: `src/deeplabeling/ui/chunked.py`, `src/deeplabeling/ui/queue_accept.py`, `src/deeplabeling/ui/session.py`, `src/deeplabeling/ui/prompter.py`, `tests/fixtures.py`

**Interfaces:**
- Consumes:
  - from Task 1: `plan_reassign`, `Reassign`;
  - from slice 2: `Session.run_chunked`, `Editor.batch`, `QtPrompter.progress`;
  - `count_out_of_range`'s `OutOfRange.ids`.
- Produces:
  - `chunked.write_as_one_edit(session, intents, description, title, said, *, failed, undone)`;
  - `Session.queue_images() -> list[ImageEntry]` and `Session.unnamed_ids: tuple[int, ...]`;
  - `ReassignDialog(names, unnamed_ids)`, with `.source`, `.target`, `.error` and `.chosen`, and `class_label(cls_id, names)`;
  - `QtPrompter.ask_reassign(names, unnamed_ids) -> (from, to) | None` and `QtPrompter.confirm_reassign(text) -> bool`; `FakePrompter(reassign=…, accept_reassign=…)` mirrors them;
  - `reassign.reassign_queue(session)` and `reassign_question(plan, source, target)`.

- [ ] **Step 1: Write the failing tests**

In `tests/fixtures.py`, replace:

```python

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None, cancel_at=None, accept_queue=True):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
```

with:

```python

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None, cancel_at=None, accept_queue=True,
                 reassign=None, accept_reassign=True):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
```

In `tests/fixtures.py`, replace:

```python
        self.progresses: list[FakeProgress] = []
        self.accept_queue = accept_queue    #: the answer to the queue accept's confirmation
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

with:

```python
        self.progresses: list[FakeProgress] = []
        self.accept_queue = accept_queue    #: the answer to the queue accept's confirmation
        self.reassign = reassign            #: (from, to) the reassign dialog answers, or None
        self.accept_reassign = accept_reassign
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

In `tests/fixtures.py`, replace:

```python
        self.asked.append(("queue accept", text))
        return self.accept_queue

    def progress(self, title, total):
```

with:

```python
        self.asked.append(("queue accept", text))
        return self.accept_queue

    def ask_reassign(self, names, unnamed_ids):
        self.asked.append(("reassign", tuple(names), tuple(unnamed_ids)))
        return self.reassign

    def confirm_reassign(self, text):
        self.asked.append(("reassign question", text))
        return self.accept_reassign

    def progress(self, title, total):
```

Create `tests/ui/test_reassign_queue.py`:

```python
"""Reassigning a class across the queue: looked at, asked, then written a chunk at a time
as one edit (docs/design/2026-10-07-bulk-and-stats.md#bulk-reassign)."""

import pytest

from deeplabeling.core.findings import Findings
from deeplabeling.core.queue import ImageFilter, NameContains
from deeplabeling.ui import chunked
from deeplabeling.ui.reassign import reassign_queue
from fixtures import FakePrompter, assert_only_changed, open_session, read_exact

WRITTEN = {"camA/labels/0001.txt", "weird/labels/имя пробел.txt", "bad/labels/corrupt.txt",
           "bad/labels/ok.txt", "crlf/labels/c.txt", "seg/labels/poly1.txt", "seg/labels/mixed.txt"}
QUESTION = ("Reassign 10 person boxes on 7 images to bus_l?\n\n"
            "Skipped: 2 images whose label file cannot be edited.\n\n"
            "It is one edit: one undo takes it all back. Nothing is marked reviewed.")


@pytest.fixture
def prompter():
    return FakePrompter(reassign=(0, 3))


@pytest.fixture
def session(qtbot, ds, prompter, monkeypatch):
    monkeypatch.setattr(chunked, "CHUNK", 2)
    s = open_session(qtbot, ds.yaml, prompter)
    yield s
    s.close()


def reassigned(qtbot, session):
    with qtbot.waitSignal(session.status, timeout=5000) as said:
        reassign_queue(session)
        qtbot.waitUntil(lambda: session.running is None and said.signal_triggered, timeout=5000)
    return said.args[0]


def test_it_asks_with_counts_writes_one_edit_and_marks_nothing(qtbot, session, prompter, ds):
    before = ds.snapshot()
    assert reassigned(qtbot, session) == ("reassigned 10 person boxes on 7 images to bus_l; "
                                          "skipped 2 images whose label file cannot be edited")
    assert ("reassign question", QUESTION) in prompter.asked
    assert_only_changed(before, ds.snapshot(), WRITTEN)
    assert len(session.workspace.review.keys()) == 0
    session.undo()                                          # one undo takes it all back
    qtbot.waitUntil(lambda: session.running is None, timeout=5000)
    assert ds.snapshot() == before


def test_the_from_list_offers_the_ids_the_yaml_does_not_name(qtbot, session, prompter, ds):
    qtbot.waitUntil(lambda: session.unnamed_ids == (-1, 99), timeout=5000)
    prompter.reassign = (99, 1)
    assert reassigned(qtbot, session) == "reassigned 1 #99? box on 1 image to car"
    assert ("reassign", ("person", "car", "bus_m", "bus_l"), (-1, 99)) in prompter.asked
    assert read_exact(ds.lbl("bad/ok")).splitlines()[1] == "1 0.5 0.5 0.1 0.1"


def test_a_queue_without_the_class_writes_nothing_and_says_so(qtbot, session, prompter, ds):
    session.set_queue(ImageFilter(conditions=(NameContains("camB"),)))
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    prompter.reassign = (3, 1)
    before = ds.snapshot()
    assert reassigned(qtbot, session) == "no bus_l boxes in this queue"
    assert ds.snapshot() == before


def test_answering_no_writes_nothing(qtbot, session, prompter, ds):
    prompter.accept_reassign = False
    before = ds.snapshot()
    assert reassigned(qtbot, session) == "reassign cancelled: nothing was written"
    assert ds.snapshot() == before


def test_cancelling_the_write_keeps_the_chunks_written_as_one_edit(qtbot, session, prompter, ds):
    prompter.cancel_at = {"Reassigning 10 person boxes on 7 images": 2}
    before = ds.snapshot()
    assert reassigned(qtbot, session) == "reassign stopped: 2 boxes on 2 images kept, as one edit"
    assert_only_changed(before, ds.snapshot(), {"camA/labels/0001.txt", "weird/labels/имя пробел.txt"})
    session.undo()
    qtbot.waitUntil(lambda: session.running is None, timeout=5000)
    assert ds.snapshot() == before


def test_a_queue_still_waiting_is_refused(qtbot, session, ds):
    session.set_queue(Findings())                           # no model: it waits
    before = ds.snapshot()
    with qtbot.waitSignal(session.status) as said:
        reassign_queue(session)
    assert said.args == ["the queue waits for a model"] and ds.snapshot() == before
```

Create `tests/ui/test_reassign_dialog.py`:

```python
"""The reassign dialog: From and To (docs/design/2026-10-07-bulk-and-stats.md#the-dialog)."""

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QDialog

from deeplabeling.ui.reassign_dialog import ReassignDialog

NAMES = ("person", "car", "bus_m", "bus_l")


def dialog(qtbot, ids=(-1, 99)):
    d = ReassignDialog(NAMES, ids)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(d.isVisible)
    return d


def items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def test_from_lists_the_classes_then_the_ids_the_yaml_does_not_name(qtbot):
    d = dialog(qtbot)
    assert items(d.source) == ["person", "car", "bus_m", "bus_l", "#-1?", "#99?"]
    assert items(d.target) == list(NAMES)


def test_ok_takes_from_and_to(qtbot):
    d = dialog(qtbot)
    d.source.setCurrentText("#99?")
    d.target.setCurrentText("car")
    d.accept()
    assert d.result() == QDialog.Accepted and d.chosen == (99, 1)


def test_a_class_onto_itself_is_refused_and_the_dialog_stays_open(qtbot):
    d = dialog(qtbot)
    d.source.setCurrentText("car")
    d.target.setCurrentText("car")
    d.accept()
    assert d.isVisible() and d.result() != QDialog.Accepted
    assert d.error.isVisible() and d.error.text() == "From and To are the same class"


def test_its_rows_are_visible_and_do_not_overlap(qtbot):
    d = dialog(qtbot)
    rects = []
    for w in (d.source, d.target):
        rect = QRect(w.mapTo(d, QPoint(0, 0)), w.size())
        assert w.isVisible() and w.width() >= 80 and d.rect().contains(rect)
        assert not any(rect.intersects(r) for r in rects)
        rects.append(rect)
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_reassign_queue.py tests/ui/test_reassign_dialog.py`
Expected: `No module named 'deeplabeling.ui.reassign'`.

- [ ] **Step 3: Share accept's write; ask, look, confirm and write a reassign**

Append to `src/deeplabeling/ui/chunked.py`:

```python
def write_as_one_edit(session, intents, description: str, title: str, said, *, failed: str, undone: str) -> None:
    """Write `intents` a chunk at a time, behind a progress dialog titled `title`, as one edit
    that marks nothing: what both bulk actions -- accepting across a queue, reassigning a
    class -- end with. At the end the status bar says `said(written, cancelled)`, `written`
    being the intents written. A write that fails has put every file back, and the notice
    begins `undone` ("nothing was accepted"); when some could not be put back, it begins
    `failed` ("the accept failed part-way") and they stay as an edit undo can retry."""
    history = session.workspace.history
    batch, last = session.workspace.editor.batch(description), history.peek_undo()
    written = 0

    def step(progress) -> bool:
        nonlocal written
        chunk = intents[written:written + CHUNK]
        batch.apply(chunk)                          # Refused: every file already put back
        written += len(chunk)
        progress.set(written)
        return written < len(intents)

    def end(progress, cancelled, error) -> None:
        if error is not None:
            kept = history.peek_undo() is not last     # files the rollback could not put back
            session.notice.emit("error", f"{failed}: {error}" if kept else f"{undone}: {error}", None)
            return
        batch.finish()
        session.status.emit(said(intents[:written], cancelled))

    session.run_chunked(title, len(intents), step, end)
```

In `src/deeplabeling/ui/queue_accept.py`, replace:

```python
        session.status.emit("the queue is still being built")
        return
    # Each image once: a findings queue has an item per finding, several to an image.
    entries = list({item.entry.rel: item.entry for item in queue.items}.values())
    key, preds, cmap, conf = model.key, ws.predictions, model.class_map, model.conf
    plan, looked = QueueAccept((), 0, 0, 0, 0, 0), 0
```

with:

```python
        session.status.emit("the queue is still being built")
        return
    entries = session.queue_images()
    key, preds, cmap, conf = model.key, ws.predictions, model.class_map, model.conf
    plan, looked = QueueAccept((), 0, 0, 0, 0, 0), 0
```

In `src/deeplabeling/ui/queue_accept.py`, replace:

```python

def _write(session, plan: QueueAccept) -> None:
    history = session.workspace.history
    batch, last = session.workspace.editor.batch(DESCRIPTION), history.peek_undo()
    intents, written = plan.intents, 0

    def step(progress) -> bool:
        nonlocal written
        chunk = intents[written:written + chunked.CHUNK]
        batch.apply(chunk)                          # Refused: every file already put back
        written += len(chunk)
        progress.set(written)
        return written < len(intents)

    def end(progress, cancelled, error) -> None:
        if error is not None:
            kept = history.peek_undo() is not last     # files the rollback could not put back
            session.notice.emit("error", f"the accept failed part-way: {error}" if kept
                                else f"nothing was accepted: {error}", None)
            return
        batch.finish()
        boxes = sum(len(intent.ops) for intent in intents[:written])
        what = f"{_count(boxes, 'box', 'boxes')} on {_count(written, 'image', 'images')}"
        session.status.emit(f"accept stopped: {what} kept, as one edit" if cancelled else f"accepted {what}")

    session.run_chunked(f"Accepting {_count(plan.boxes, 'box', 'boxes')} on {_count(len(intents), 'image', 'images')}",
                        len(intents), step, end)
```

with:

```python

def _write(session, plan: QueueAccept) -> None:
    def said(written, cancelled) -> str:
        boxes = sum(len(intent.ops) for intent in written)
        what = f"{_count(boxes, 'box', 'boxes')} on {_count(len(written), 'image', 'images')}"
        return f"accept stopped: {what} kept, as one edit" if cancelled else f"accepted {what}"

    chunked.write_as_one_edit(
        session, plan.intents, DESCRIPTION,
        f"Accepting {_count(plan.boxes, 'box', 'boxes')} on {_count(len(plan.intents), 'image', 'images')}", said,
        failed="the accept failed part-way", undone="nothing was accepted")
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self._build = None
        self._by_rel: dict[str, ImageEntry] = {}
        self._follow: ImageEntry | QueueItem | None = None  # where a rebuilding queue must land
        self._seen: tuple | None = None             # (image, raw, state) last reported on screen
```

with:

```python
        self._build = None
        self._by_rel: dict[str, ImageEntry] = {}
        self.unnamed_ids: tuple[int, ...] = ()      #: class ids the labels hold that the yaml does not name
        self._follow: ImageEntry | QueueItem | None = None  # where a rebuilding queue must land
        self._seen: tuple | None = None             # (image, raw, state) last reported on screen
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self.workspace, self.queue, self._build, self._by_rel = None, None, None, {}
        self._follow = self._seen = self._keys = None
        try:
            ws.close()
```

with:

```python
        self.workspace, self.queue, self._build, self._by_rel = None, None, None, {}
        self._follow = self._seen = self._keys = None
        self.unnamed_ids = ()
        try:
            ws.close()
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            self.status.emit("the dismissal is taken back")

    def crop_of(self, item: QueueItem, size=_UNREAD) -> Crop | None:
        """The crop a finding's tile shows; None for an image item, or when the image's
```

with:

```python
            self.status.emit("the dismissal is taken back")

    def queue_images(self) -> list[ImageEntry]:
        """The queue's images, each once, in queue order: a findings queue has an item per
        finding, several to an image (docs/design/2026-10-07-bulk-and-stats.md#the-queues-images)."""
        if self.queue is None:
            return []
        return list({item.entry.rel: item.entry for item in self.queue.items}.values())

    def crop_of(self, item: QueueItem, size=_UNREAD) -> Crop | None:
        """The crop a finding's tile shows; None for an image item, or when the image's
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        def found(result) -> None:
            if self.workspace is ws and result is not None:
                self.standing.emit(OUT_OF_RANGE, result.message(dataset))

```

with:

```python
        def found(result) -> None:
            if self.workspace is ws and result is not None:
                self.unnamed_ids = result.ids
                self.standing.emit(OUT_OF_RANGE, result.message(dataset))

```

Create `src/deeplabeling/ui/reassign_dialog.py`:

```python
"""The reassign dialog (docs/design/2026-10-07-bulk-and-stats.md#the-dialog): From and To.
From lists the yaml's classes, then the class ids the labels hold that it does not name; To
lists the yaml's classes. A class onto itself is refused, and the dialog stays open."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout


def class_label(cls_id: int, names) -> str:
    """A class as the app writes it: its name, or `#99?` for an id the yaml does not name."""
    return names[cls_id] if 0 <= cls_id < len(names) else f"#{cls_id}?"


class ReassignDialog(QDialog):
    def __init__(self, names, unnamed_ids=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reassign a class in this queue")
        self.source, self.target = QComboBox(), QComboBox()
        for cls_id in [*range(len(names)), *unnamed_ids]:
            self.source.addItem(class_label(cls_id, names), cls_id)
        for cls_id, name in enumerate(names):
            self.target.addItem(name, cls_id)
        for combo in (self.source, self.target):
            combo.setMinimumWidth(160)
        self.error = QLabel()
        self.error.setStyleSheet("color: #e05252;")
        self.error.hide()
        self.chosen: tuple[int, int] | None = None     #: (from, to), what OK took
        form = QFormLayout()
        form.addRow("From", self.source)
        form.addRow("To", self.target)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def accept(self) -> None:
        source, target = self.source.currentData(), self.target.currentData()
        if source == target:
            self.error.setText("From and To are the same class")
            self.error.show()
            return
        self.chosen = (source, target)
        super().accept()
```

Create `src/deeplabeling/ui/reassign.py`:

```python
"""Reassign a class in this queue… (docs/design/2026-10-07-bulk-and-stats.md#bulk-reassign).

It asks From and To, looks at every image of the queue a chunk at a time behind a progress
dialog, and asks first with the counts. Then it writes a chunk at a time on the GUI thread's
write path, as one edit that marks nothing, as accepting across a queue does
(`src/deeplabeling/ui/chunked.py::write_as_one_edit`).
"""

from __future__ import annotations

from ..core.reassign import Reassign, plan_reassign
from . import chunked
from .reassign_dialog import class_label

PLAN_BATCH = 500        #: images looked at per event-loop turn: their label files, read


def _count(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def _skipped(plan: Reassign) -> str:
    return _count(plan.read_only, "image", "images") + " whose label file cannot be edited" if plan.read_only else ""


def reassign_question(plan: Reassign, source: str, target: str) -> str:
    text = (f"Reassign {_count(plan.boxes, source + ' box', source + ' boxes')} on "
            f"{_count(len(plan.intents), 'image', 'images')} to {target}?\n\n")
    if plan.read_only:
        text += f"Skipped: {_skipped(plan)}.\n\n"
    return text + "It is one edit: one undo takes it all back. Nothing is marked reviewed."


def reassign_queue(session) -> None:
    """Ask, look, confirm and write; each step says how it ended in the status bar."""
    ws, queue = session.workspace, session.queue
    if ws is None or session._busy():
        return
    if queue is None or queue.waiting:
        session.status.emit("the queue waits for a model")
        return
    if not queue.complete:
        session.status.emit("the queue is still being built")
        return
    names = ws.dataset.names
    chosen = session.prompter.ask_reassign(names, session.unnamed_ids)
    if chosen is None:
        return
    source, target = chosen
    source_name, target_name = class_label(source, names), class_label(target, names)
    description = f"reassign {source_name} to {target_name}"
    entries = session.queue_images()
    plan, looked = Reassign((), 0, 0), 0

    def step(progress) -> bool:                     # reads only: the label files
        nonlocal plan, looked
        plan += plan_reassign(entries[looked:looked + PLAN_BATCH], ws.store.get, source, target, description)
        looked += PLAN_BATCH
        progress.set(min(looked, len(entries)))
        return looked < len(entries)

    def end(progress, cancelled, error) -> None:
        skipped = f"; skipped {_skipped(plan)}" if plan.read_only else ""
        if error is not None and session.workspace is ws:
            session.notice.emit("error", f"the queue could not be looked at: {error}", None)
        elif cancelled or session.workspace is not ws:
            session.status.emit("reassign cancelled: nothing was written")
        elif not plan.intents:
            session.status.emit(f"no {source_name} boxes in this queue{skipped}")
        elif not session.prompter.confirm_reassign(reassign_question(plan, source_name, target_name)):
            session.status.emit("reassign cancelled: nothing was written")
        else:
            _write(session, plan, description, source_name, target_name, skipped)

    session.run_chunked(f"Looking at {len(entries):,} images", len(entries), step, end)


def _write(session, plan: Reassign, description: str, source: str, target: str, skipped: str) -> None:
    def said(written, cancelled) -> str:
        boxes = sum(len(intent.ops) for intent in written)
        if cancelled:
            return (f"reassign stopped: {_count(boxes, 'box', 'boxes')} on "
                    f"{_count(len(written), 'image', 'images')} kept, as one edit")
        return (f"reassigned {_count(boxes, source + ' box', source + ' boxes')} on "
                f"{_count(len(written), 'image', 'images')} to {target}{skipped}")

    chunked.write_as_one_edit(
        session, plan.intents, description,
        f"Reassigning {_count(plan.boxes, source + ' box', source + ' boxes')} on "
        f"{_count(len(plan.intents), 'image', 'images')}", said,
        failed="the reassign failed part-way", undone="nothing was reassigned")
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
from .classes import ClassInfo
from .queue_editor import QueueEditor


```

with:

```python
from .classes import ClassInfo
from .queue_editor import QueueEditor
from .reassign_dialog import ReassignDialog


```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
        return Progress(QProgressDialog(title, "Cancel", 0, total, self.parent))

    def confirm_queue_accept(self, text: str) -> bool:
        answer = QMessageBox.question(self.parent, "Accept missing boxes in this queue", text,
```

with:

```python
        return Progress(QProgressDialog(title, "Cancel", 0, total, self.parent))

    def ask_reassign(self, names, unnamed_ids) -> tuple[int, int] | None:
        dialog = ReassignDialog(names, unnamed_ids, self.parent)
        try:
            return dialog.chosen if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()

    def confirm_reassign(self, text: str) -> bool:
        answer = QMessageBox.question(self.parent, "Reassign a class in this queue", text,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes

    def confirm_queue_accept(self, text: str) -> bool:
        answer = QMessageBox.question(self.parent, "Accept missing boxes in this queue", text,
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_reassign_queue.py tests/ui/test_reassign_dialog.py tests/ui/test_queue_accept.py tests/ui/test_findings_queue.py tests/ui/test_prompter.py`
Expected: 39 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 971 passed.

```bash
git add src/deeplabeling/ui/reassign.py src/deeplabeling/ui/reassign_dialog.py src/deeplabeling/ui/chunked.py src/deeplabeling/ui/queue_accept.py src/deeplabeling/ui/session.py src/deeplabeling/ui/prompter.py tests/fixtures.py tests/ui/test_reassign_queue.py tests/ui/test_reassign_dialog.py
git commit -m "ui: reassign a class across the queue's images, asked with counts and written as one edit" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The queue chip's menu

**Files:**
- Create: `tests/ui/test_queue_chip.py`
- Modify: `src/deeplabeling/ui/state_bar.py`, `src/deeplabeling/ui/main_window.py`

**Interfaces:**
- Consumes: Task 2's `reassign_queue`, and `MainWindow.edit_queue`.
- Produces:
  - the queue chip in `QToolButton.MenuButtonPopup` mode: a click still edits the queue;
  - the chip's menu, *Edit queue…* and *Reassign a class in this queue…*, filled each time it opens (`MainWindow._fill_queue_menu`);
  - `MainWindow.reassign_queue()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_queue_chip.py`:

```python
"""The queue chip's menu: what acts on the queue's images
(docs/design/2026-10-07-bulk-and-stats.md#the-queue-chip)."""

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QToolButton

from drive import start
from fixtures import FakePrompter, read_exact


@pytest.fixture
def prompter():
    return FakePrompter(reassign=(99, 1))


@pytest.fixture
def window(qtbot, ds, prompter):
    w = start(qtbot, [str(ds.yaml)], prompter)
    yield w
    w.close()


def menu(window) -> dict:
    m = window.state_bar.queue.menu()
    m.aboutToShow.emit()
    return {a.text(): a for a in m.actions() if not a.isSeparator()}


def test_the_chip_offers_the_queue_s_actions(qtbot, window):
    assert list(menu(window)) == ["Edit queue…", "Reassign a class in this queue…"]
    assert all(action.isEnabled() for action in menu(window).values())


def test_reassign_runs_from_the_menu(qtbot, window, prompter, ds):
    qtbot.waitUntil(lambda: window.session.unnamed_ids == (-1, 99), timeout=5000)
    with qtbot.waitSignal(window.session.status, timeout=5000) as said:
        menu(window)["Reassign a class in this queue…"].trigger()
        qtbot.waitUntil(lambda: window.session.running is None and said.signal_triggered, timeout=5000)
    assert said.args == ["reassigned 1 #99? box on 1 image to car"]
    assert read_exact(ds.lbl("bad/ok")).splitlines()[1] == "1 0.5 0.5 0.1 0.1"


def test_a_click_on_the_chip_still_opens_the_queue_editor(qtbot, window, prompter):
    chip = window.state_bar.queue
    qtbot.mouseClick(chip, Qt.LeftButton, pos=QPoint(10, chip.height() // 2))
    assert prompter.asked[-1][0] == "queue"
    menu(window)["Edit queue…"].trigger()
    assert prompter.asked[-1][0] == "queue"


def test_the_chip_shows_its_arrow_inside_the_bar(qtbot, window):
    chip = window.state_bar.queue
    assert chip.popupMode() == QToolButton.MenuButtonPopup
    rect = QRect(chip.mapTo(window.state_bar, QPoint(0, 0)), chip.size())
    assert chip.isVisible() and window.state_bar.rect().contains(rect) and chip.width() > 100


def test_reassign_is_offered_only_once_the_queue_is_built(qtbot, window):
    window.session.queue.complete = False
    assert not menu(window)["Reassign a class in this queue…"].isEnabled()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_chip.py`
Expected: 5 failed: the chip has no menu yet.

- [ ] **Step 3: Give the chip its menu**

In `src/deeplabeling/ui/state_bar.py`, replace:

```python
            chip.setPopupMode(QToolButton.InstantPopup)
            chip.setMenu(QMenu(chip))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
```

with:

```python
            chip.setPopupMode(QToolButton.InstantPopup)
            chip.setMenu(QMenu(chip))
        # A click on the queue chip edits the queue; its arrow offers what acts on the queue
        # (docs/design/2026-10-07-bulk-and-stats.md#the-queue-chip).
        self.queue.setPopupMode(QToolButton.MenuButtonPopup)
        self.queue.setMenu(QMenu(self.queue))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
from .queue_accept import accept_queue
from .queue_panel import QueuePanel
from .session import Session
from .settings_ui import (QUEUE_GRID_WIDTH, QUEUE_LIST_WIDTH, RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_GRID,
```

with:

```python
from .queue_accept import accept_queue
from .queue_panel import QueuePanel
from .reassign import reassign_queue
from .session import Session
from .settings_ui import (QUEUE_GRID_WIDTH, QUEUE_LIST_WIDTH, RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_GRID,
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        self.state_bar.model.menu().aboutToShow.connect(self._fill_model_menu)
        self.state_bar.queue.clicked.connect(self.edit_queue)
        session.cursorChanged.connect(self.show_current)
        session.opened.connect(self.show_current)
```

with:

```python
        self.state_bar.model.menu().aboutToShow.connect(self._fill_model_menu)
        self.state_bar.queue.clicked.connect(self.edit_queue)
        self.state_bar.queue.menu().aboutToShow.connect(self._fill_queue_menu)
        session.cursorChanged.connect(self.show_current)
        session.opened.connect(self.show_current)
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        accept_queue(self.session)

    def load_model(self) -> None:
        path = self.prompter.choose_weights()
```

with:

```python
        accept_queue(self.session)

    def _fill_queue_menu(self) -> None:
        menu, queue = self.state_bar.queue.menu(), self.session.queue
        menu.clear()
        menu.addAction("Edit queue…", self.edit_queue).setEnabled(queue is not None)
        built = queue is not None and queue.complete
        menu.addAction("Reassign a class in this queue…", self.reassign_queue).setEnabled(built)

    def reassign_queue(self) -> None:
        reassign_queue(self.session)

    def load_model(self) -> None:
        path = self.prompter.choose_weights()
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_chip.py tests/ui/test_state_bar.py tests/ui/test_model_chip.py`
Expected: 24 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 976 passed.

- [ ] **Step 5: Look at it**

Screenshot the state bar of `test_queue_chip.py`'s `window`, at 1200 px wide. Then screenshot a `ReassignDialog(("person", "car", "bus_m", "bus_l"), (-1, 99))` with car → car, after OK. Write the shot as a temporary test in `tests/ui/`, save the PNGs outside the repository, and delete the test after. Expected:
- the queue chip shows its arrow as a separate segment beside its text;
- the dialog shows From and To, one under the other, both wide enough to read;
- the red line reads `From and To are the same class`.

- [ ] **Step 6: Commit**

```bash
git add src/deeplabeling/ui/state_bar.py src/deeplabeling/ui/main_window.py tests/ui/test_queue_chip.py
git commit -m "ui: the queue chip's menu, to edit the queue or reassign a class in it" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The status

**Files:**
- Modify: `CLAUDE.md`, `docs/design/2026-10-07-bulk-and-stats.md`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: the status.

- [ ] **Step 1: Update the status**

In `CLAUDE.md`, replace:

```markdown
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. Slice 4 is built: Find Bad, the labels the model disagrees with as a queue,
fixed a key at a time in the full frame or many at once in a grid of crops. Slice 5 (bulk
reassign and statistics) is designed; plan 5a is next. The design and the plans are in
[docs/design/](docs/design/).

```

with:

```markdown
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. Slice 4 is built: Find Bad, the labels the model disagrees with as a queue,
fixed a key at a time in the full frame or many at once in a grid of crops. Slice 5 has
bulk reassign built; its statistics (plan 5b) are next. The design and the plans are in
[docs/design/](docs/design/).

```

In `docs/design/2026-10-07-bulk-and-stats.md`, replace:

```markdown
# DeepLabeling — slice 5: bulk reassign and statistics

**Status:** approved 2026-10-07 · plans 5a (bulk reassign) and 5b (statistics) next
**Scope:** slice 5 of [the app foundation](2026-10-04-app-foundation.md#slices), the last:
one class rewritten to another across a queue, as one edit; and the statistics of a queue,
```

with:

```markdown
# DeepLabeling — slice 5: bulk reassign and statistics

**Status:** approved 2026-10-07 · plan 5a (bulk reassign) implemented; 5b (statistics) next
**Scope:** slice 5 of [the app foundation](2026-10-04-app-foundation.md#slices), the last:
one class rewritten to another across a queue, as one edit; and the statistics of a queue,
```

- [ ] **Step 2: Check the docs, run the full suite, and commit**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 976 passed.

```bash
git add CLAUDE.md docs/design/2026-10-07-bulk-and-stats.md
git commit -m "docs: slice 5's bulk reassign is built" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
