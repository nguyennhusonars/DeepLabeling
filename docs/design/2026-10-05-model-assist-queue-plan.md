# Slice 2c: a whole queue at once — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Work on a whole queue at once:
- infer it ahead of time, behind the image on screen;
- accept every missing box in it as one edit;
- undo or redo that edit without freezing the window;
- measure slice 2's performance targets with the real model.

**Architecture:**
- **Long writes stay on the GUI thread's one write path.** They run a chunk per event-loop turn behind a modal progress dialog (`ui/chunked.py`); the queue accept's look over the images and its write, and the undo and redo of a large edit, all run there.
- **The core gains `Editor.restoring`.** It undoes or redoes one edit file by file. Stopped part-way, it splits the edit, so nothing is lost.
- **The dataset pass runs on the model's thread** (`ui/model.py`), in batches after the screen's requests.

**Tech Stack:** Python 3.10 (conda base), PySide6, pytest-qt; plan 2a's core and plan 2b's UI.

**Spec:** [2026-10-05-model-assist.md](2026-10-05-model-assist.md). This plan implements what plans 2a and 2b left:
- *A dataset pass*;
- the model chip's `N / M inferred` count, and its menu's pass and queue-accept entries;
- *Accepting*: the queue accept, with chunked undo and redo;
- the *Errors* rows for a queue accept;
- *Performance targets*: measured and recorded.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)).
- **One write path, one owner** ([landmines 1 and 2](../../CLAUDE.md#landmines)). Every label file is written on the GUI thread, through `LabelStore`: a chunk per event-loop turn, never from a worker.
- **The GUI thread never waits on the model; the thread never touches a widget** ([landmine 3](../../CLAUDE.md#landmines)). The pass talks to the GUI through queued signals and the prediction store.
- **A UI change is verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines)). The progress dialog and the confirmation are each driven through `QtPrompter` once.
- **Unmapped is never accepted, and a negative sample is never written to** ([landmines 1 and 5](../../CLAUDE.md#landmines)).
- **The disk is nearly full** ([landmine 9](../../CLAUDE.md#landmines)). The measurement reads pvn-vehicle in place; its store and app state go to a temporary folder that is deleted afterwards.
- **Tests never load a real model**, and write only to temporary folders ([landmines 8 and 10](../../CLAUDE.md#landmines)).
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice2-model-assist-queue`, from `main`. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone using this. Each has a named test:

1. **Cancelling, or closing the dataset, part-way through a queue accept or its undo.** What was written stays one edit, both halves stay undoable, and no file is left half-written. *(Task 1 `test_stopped_part_way_what_was_written_is_an_edit_of_its_own_and_the_rest_stays`; Task 2 `test_a_cancelled_undo_keeps_what_it_wrote_as_an_edit_of_its_own`, `test_closing_the_dataset_stops_it_before_its_next_chunk`; Task 3 `test_a_cancel_while_writing_keeps_the_chunks_written_as_one_edit`.)*
2. **The disk filling up part-way.**
   - A queue accept puts every file back.
   - An undo stops at the file that failed and keeps the rest for a retry.
   - A pass fails those images and goes on.

   *(Task 1 `test_a_write_failing_part_way_stops_at_that_file_and_loses_nothing`; Task 2 `test_a_write_failing_part_way_says_so_and_keeps_the_rest_for_a_retry`; Task 3 `test_a_write_failing_part_way_puts_every_file_back_and_says_why`; Task 4 `test_a_store_that_cannot_be_written_fails_the_pass_images_and_the_pass_goes_on`.)*
3. **A label file changed by hand between the accept and its undo.** The undo is refused whole, before anything is written, and dropped from the history. *(Task 1 `test_a_file_changed_since_refuses_the_whole_undo_before_anything_is_written`.)*
4. **Keys pressed while a long write or a pass runs.** An edit or a second undo waits and says so, and the image on screen goes ahead of the pass. *(Task 2 `test_nothing_else_edits_while_it_runs`; Task 4 `test_the_image_on_screen_goes_ahead_of_a_pass`; Task 5's measurement of paging during a pass.)*
5. **An image edited on disk after a pass inferred it.** The next pass infers it again. *(Task 4 `test_an_image_changed_on_disk_since_is_inferred_again`.)*

## Found while building this plan

The plan's code was built in a scratch copy first, and its suite ran green there (678 passed). Task 5's script was then run three times with the real `yolo26n_vehicle` model on `data_13class.yaml`. Every target was met:
- a pass ran at 117–141 images/s;
- the worst page while a pass ran was 9 ms;
- predictions for a new image arrived 99 ms after it showed, at worst;
- the store took 1,647 bytes per image.

The first run had one page of 121 ms while a pass ran; the other two had none over 9 ms. `~/.config/Ultralytics/settings.json` kept its md5.

- **A cancelled job sends neither `done` nor `failed`** (`src/deeplabeling/ui/workers.py::Job`). The first design planned the queue accept on a job. A cancel, or closing the dataset, then left its progress dialog open for good. Looking at the images now runs on the GUI thread, 500 per event-loop turn, behind the same kind of dialog. They are reads of label files and store rows, as the GUI already does.
- **`QtPrompter` lacked `confirm_queue_accept`.** Every test used the fake, so the real app would have raised on the confirmation. A prompter test now drives the real dialog.
- **A `QMessageBox` can show after a 0 ms timer has fired**, so the test that answers it retries until it shows.
- **`LabelStore.restore` of a many-file edit can stop part-way through its writes**, with the files before it already written. The chunked undo therefore writes file by file, and knows exactly what was written when it stops.

## Decisions this plan makes

- **An edit of more than `CHUNK` = 50 files is undone and redone in chunks.** A smaller one is undone at once, as before.
- **Stopping part-way splits the edit.** What was written goes to the other list, the rest stays where it was, and both stay undoable.
- **While a long write runs, an edit or an undo waits** and says `wait: … is under way`. The modal dialog already blocks the mouse; this covers keys and code.
- **The pass asks for `PASS_BATCH` = 8 images at a time** and writes each batch in one transaction. It reads the store's rows for the model once per pass, on the model's thread.
- **The chip counts the queue's images that have a row**, by path. An image edited since still counts until a pass sees it.
- **A pass ends with an info notice:** how many images were inferred, and how many failed.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/store.py`, `history.py`, `editor.py` | `LabelStore.check`; `History.drop`, `move`, `split`; `Editor.restoring` and `Restoring` | 1 |
| `src/deeplabeling/ui/chunked.py`, `prompter.py`, `session.py` | `Chunked`; the progress dialog; `Session.run_chunked` and chunked undo and redo | 2 |
| `src/deeplabeling/ui/queue_accept.py`, `prompter.py`, `session.py`, `main_window.py` | the queue accept: look, confirm, write; its menu entry | 3 |
| `src/deeplabeling/ui/model.py`, `state_bar.py`, `main_window.py` | the dataset pass; the chip's count and progress; its menu entries | 4 |
| `tools/measure_assist.py`, the spec, `CLAUDE.md`, the run-and-verify-ui skill | the measurements; the status | 5 |

---

### Task 1: Undo and redo a chunk at a time

**Files:**
- Create: `tests/core/test_restoring.py`
- Modify: `src/deeplabeling/core/store.py`, `src/deeplabeling/core/history.py`, `src/deeplabeling/core/editor.py`

**Interfaces:**
- Consumes: slice 1's `LabelStore.restore`, `History`, `Conflict` and `Refused`; plan 2a's `Editor.apply_many`.
- Produces:
  - `LabelStore.check(changes, *, undo)`, which raises `Conflict` when a file no longer holds what its change left (undo) or found (redo). It only reads; `restore` uses it.
  - In `History`, for the last edit on the undo list (`undo=True`) or the redo list:
    - `drop(edit, *, undo)`;
    - `move(edit, *, undo)`;
    - `split(edit, *, undo, done, rest)`.
  - `Editor.restoring(*, undo) -> Restoring | None`, for the last edit or the last one undone.
  - `Restoring`:
    - `.edit`, `.undo`, `.total` (files), `.checked`, `.written`;
    - `check(n)`: on a `Conflict` the edit is dropped and `Refused` is raised;
    - `write(n) -> tuple[Path, ...]`: the images written, each reported through `on_labels_changed`;
    - `finish()`;
    - `stop()`: what was written becomes its own edit on the other list. Nothing written changes nothing, and everything written is the same as `finish()`.

- [ ] **Step 1: Commit this plan, on its branch**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout -b slice2-model-assist-queue main
git add docs/design/2026-10-05-model-assist-queue-plan.md
git commit -m "docs: the slice 2c model-assist queue plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/core/test_restoring.py`:

```python
"""Undo and redo of an edit across many images, a chunk of files at a time
(docs/design/2026-10-05-model-assist.md#accepting)."""

import pytest

from deeplabeling.core import store as store_module
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, Intent, Refused
from deeplabeling.core.editor import Editor
from deeplabeling.core.history import History
from deeplabeling.core.review import ReviewMarks
from deeplabeling.core.store import LabelStore
from fixtures import assert_only_changed

BOX = (0.5, 0.5, 0.2, 0.2)
IMAGES = ("camA/0001.jpg", "camA/0003.jpg", "camA/0004.JPG", "camB/0001.jpg")


class Recorder:
    def __init__(self):
        self.labels, self.history = [], 0

    def labels_changed(self, images):
        self.labels.append(images)

    def history_changed(self):
        self.history += 1


@pytest.fixture
def rec():
    return Recorder()


@pytest.fixture
def editor(ds, tmp_path, rec):
    dataset = Dataset.open(ds.yaml)
    store = LabelStore(dataset)
    return Editor(store, History(store), ReviewMarks(tmp_path / "review.json", dataset.root),
                  on_labels_changed=rec.labels_changed, on_history_changed=rec.history_changed)


@pytest.fixture
def accepted(editor, ds):
    """A four-image edit, and the files before and after it."""
    before = ds.snapshot()
    editor.apply_many([Intent(ds.img(n), (AddBox(1, BOX),), "accept") for n in IMAGES], "accept 4")
    return before, ds.snapshot()


def run(restoring, n=2):
    while restoring.checked < restoring.total:
        restoring.check(n)
    while restoring.written < restoring.total:
        restoring.write(n)
    restoring.finish()


def test_an_edit_is_undone_and_redone_a_chunk_at_a_time(editor, ds, rec, accepted):
    before, after = accepted
    undoing = editor.restoring(undo=True)
    assert (undoing.total, undoing.checked, undoing.written) == (4, 0, 0)
    undoing.check(2)
    assert_only_changed(after, ds.snapshot(), set())          # checking writes nothing
    undoing.check(2)
    written = undoing.write(2)
    assert written == (ds.img(IMAGES[0]), ds.img(IMAGES[1])) and rec.labels[-1] == written
    undoing.write(2)
    undoing.finish()
    assert_only_changed(before, ds.snapshot(), set())
    assert not editor.history.can_undo and editor.history.can_redo
    run(editor.restoring(undo=False))
    assert_only_changed(after, ds.snapshot(), set())
    assert editor.history.depth == 1 and not editor.history.can_redo


def test_a_file_changed_since_refuses_the_whole_undo_before_anything_is_written(editor, ds, accepted):
    _, after = accepted
    ds.lbl("camB/0001").write_bytes(b"0 0.1 0.1 0.1 0.1\n")   # changed by hand since
    undoing = editor.restoring(undo=True)
    undoing.check(2)
    with pytest.raises(Refused, match="0001.txt has changed since.*dropped from the history"):
        undoing.check(2)
    assert_only_changed(after, ds.snapshot(), {"camB/labels/0001.txt"})
    assert not editor.history.can_undo


def test_stopped_part_way_what_was_written_is_an_edit_of_its_own_and_the_rest_stays(editor, ds, accepted):
    before, after = accepted
    undoing = editor.restoring(undo=True)
    undoing.check(4)
    undoing.write(2)
    undoing.stop()                                          # cancelled
    assert_only_changed(after, ds.snapshot(), {"camA/labels/0001.txt", "camA/labels/0003.txt"})
    rest, done = editor.history.peek_undo(), editor.history.peek_redo()
    assert [c.path.name for c in rest.changes] == ["0004.txt", "0001.txt"]
    assert rest.images == (ds.img(IMAGES[2]), ds.img(IMAGES[3])) and done.images == (ds.img(IMAGES[0]), ds.img(IMAGES[1]))
    run(editor.restoring(undo=True))                        # the rest, undone later
    assert_only_changed(before, ds.snapshot(), set())
    editor.redo()
    editor.redo()
    assert_only_changed(after, ds.snapshot(), set())


def test_a_write_failing_part_way_stops_at_that_file_and_loses_nothing(editor, ds, accepted, monkeypatch):
    before, after = accepted
    real, calls = store_module.write_atomic, []

    def failing(path, data):
        calls.append(path)
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", failing)
    undoing = editor.restoring(undo=True)
    undoing.check(4)
    with pytest.raises(Refused, match="No space left on device"):
        undoing.write(4)
    undoing.stop()
    monkeypatch.setattr(store_module, "write_atomic", real)
    # 0001 had a file: written back. 0003 had none, so undoing it is a delete, not a write.
    # camB/0001 had a file: its write failed and it holds what the accept left.
    assert undoing.written == 3
    assert_only_changed(after, ds.snapshot(), {"camA/labels/0001.txt", "camA/labels/0003.txt",
                                               "camA/labels/0004.txt"})
    assert editor.history.peek_undo().images == (ds.img(IMAGES[3]),)
    run(editor.restoring(undo=True))                        # the disk freed: the rest goes back
    assert_only_changed(before, ds.snapshot(), set())


def test_stopped_before_writing_anything_the_history_is_as_it_was(editor, accepted):
    edit = editor.history.peek_undo()
    undoing = editor.restoring(undo=True)
    undoing.check(2)
    undoing.stop()
    assert editor.history.peek_undo() is edit and not editor.history.can_redo


def test_nothing_to_restore_is_none(editor):
    assert editor.restoring(undo=True) is None and editor.restoring(undo=False) is None


def test_stopped_after_the_last_file_it_is_done_whole(editor, ds, accepted):
    before, _ = accepted
    undoing = editor.restoring(undo=True)
    undoing.check(4)
    undoing.write(4)
    undoing.stop()                                          # a cancel just after the last chunk
    assert_only_changed(before, ds.snapshot(), set())
    assert not editor.history.can_undo and len(editor.history.peek_redo().changes) == 4
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_restoring.py`
Expected: 7 failed: `'Editor' object has no attribute 'restoring'`.

- [ ] **Step 4: Check, move, split, and restore file by file**

In `src/deeplabeling/core/store.py`, replace:

```python
        """
        self._check_thread()
        for change in edit.changes:
            expected = change.after if undo else change.before
            if _read_or_none(change.path) != expected:
                raise Conflict(f"{change.path.name} has changed since, so it is left as it is")
        for change in edit.changes:
            target = change.before if undo else change.after
```

with:

```python
        """
        self._check_thread()
        self.check(edit.changes, undo=undo)
        for change in edit.changes:
            target = change.before if undo else change.after
```

In `src/deeplabeling/core/store.py`, replace:

```python
            self._load(self.dataset.entry(image), notify=False)

    def _write(self, path: Path, data: bytes) -> None:
        try:
```

with:

```python
            self._load(self.dataset.entry(image), notify=False)

    def check(self, changes, *, undo: bool) -> None:
        """Conflict if any file no longer holds what its change left (undo) or found
        (redo). Reads only."""
        for change in changes:
            expected = change.after if undo else change.before
            if _read_or_none(change.path) != expected:
                raise Conflict(f"{change.path.name} has changed since, so it is left as it is")

    def _write(self, path: Path, data: bytes) -> None:
        try:
```

In `src/deeplabeling/core/history.py`, replace:

```python
        self._undo.append(self._redo.pop())
        return edit
```

with:

```python
        self._undo.append(self._redo.pop())
        return edit

    # -- an edit undone or redone in chunks (editor.py::Restoring) ------------------------

    def drop(self, edit: Edit, *, undo: bool) -> None:
        """Forget `edit`, the last on the undo (or redo) list: it can never succeed."""
        stack = self._undo if undo else self._redo
        assert stack and stack[-1] is edit
        stack.pop()
        self._bytes -= edit.nbytes

    def move(self, edit: Edit, *, undo: bool) -> None:
        """`edit` was undone (or redone) whole: on to the other list."""
        (self._undo if undo else self._redo).pop()
        (self._redo if undo else self._undo).append(edit)

    def split(self, edit: Edit, *, undo: bool, done: Edit, rest: Edit) -> None:
        """`edit` was undone (or redone) part-way: `done` goes on to the other list and
        `rest` stays where `edit` was."""
        stack = self._undo if undo else self._redo
        assert stack and stack[-1] is edit
        stack[-1] = rest
        (self._redo if undo else self._undo).append(done)
```

In `src/deeplabeling/core/editor.py`, replace:

```python
from pathlib import Path

from .edits import Edit, FileChange, Intent, Refused
from .history import History
from .review import ReviewMarks
```

with:

```python
from pathlib import Path

from .edits import Conflict, Edit, FileChange, Intent, Refused
from .history import History
from .review import ReviewMarks
```

In `src/deeplabeling/core/editor.py`, replace:

```python
        batch.apply(intents)
        return batch.finish()

    def undo(self) -> Edit | None:
```

with:

```python
        batch.apply(intents)
        return batch.finish()

    def restoring(self, *, undo: bool) -> Restoring | None:
        """The last edit (or the last undone), to undo (or redo) a chunk at a time."""
        edit = self.history.peek_undo() if undo else self.history.peek_redo()
        return None if edit is None else Restoring(self, edit, undo)

    def undo(self) -> Edit | None:
```

In `src/deeplabeling/core/editor.py`, replace:

```python
            self._editor._history_changed()
        return edit
```

with:

```python
            self._editor._history_changed()
        return edit


class Restoring:
    """Undo (or redo) of one edit a chunk of files at a time, for an edit too big to write
    at once without freezing the window (docs/design/2026-10-05-model-assist.md#accepting).

    Every file is checked before any is written, as LabelStore.restore does: an edit any
    file of which has changed since is refused whole, and dropped. Then the files are
    written a chunk at a time, each on its own, so a refusal stops at the file it names.
    Stopped part-way -- cancelled, or a write refused -- what was written becomes an edit
    of its own on the other list and the rest stays where it was: both stay undoable, and
    nothing is lost.
    """

    def __init__(self, editor: Editor, edit: Edit, undo: bool):
        self._editor, self.edit, self.undo = editor, edit, undo
        self._changes = list(edit.changes)
        self.checked = self.written = 0
        self._images: dict[Path, list[Path]] = {}       # label file -> its images in the edit
        for image in edit.images:
            self._images.setdefault(editor.store.dataset.entry(image).label_path, []).append(image)

    @property
    def total(self) -> int:
        return len(self._changes)

    def _verb(self) -> str:
        return "undo" if self.undo else "redo"

    def check(self, n: int) -> None:
        """Check the next `n` files. A file changed since: the edit is dropped, Refused."""
        chunk = self._changes[self.checked:self.checked + n]
        try:
            self._editor.store.check(chunk, undo=self.undo)
        except Conflict as e:
            self._editor.history.drop(self.edit, undo=self.undo)
            self._editor._history_changed()
            raise Refused(f"cannot {self._verb()} “{self.edit.description}”: {e}. "
                          "It has been dropped from the history.") from e
        self.checked += len(chunk)

    def write(self, n: int) -> tuple[Path, ...]:
        """Write the next `n` files, every one checked; the images they belong to. A
        refusal stops at the file it names: stop() then keeps what was written."""
        assert self.checked == self.total, "every file is checked first"
        images: list[Path] = []
        try:
            for change in self._changes[self.written:self.written + n]:
                mine = tuple(self._images.get(change.path, ()))
                self._editor.store.restore(Edit((change,), mine, self.edit.description), undo=self.undo)
                self.written += 1
                images.extend(mine)
        finally:
            if images:
                self._editor._labels_changed(tuple(images))
        return tuple(images)

    def finish(self) -> None:
        """Every file written: the edit moves to the other list."""
        assert self.written == self.total
        self._editor.history.move(self.edit, undo=self.undo)
        self._editor._history_changed()

    def stop(self) -> None:
        """Stop part-way: what was written goes to the other list, the rest stays."""
        if not self.written:
            return
        if self.written == self.total:
            self.finish()
            return
        done, rest = self._changes[:self.written], self._changes[self.written:]
        self._editor.history.split(self.edit, undo=self.undo, done=self._part(done), rest=self._part(rest))
        self._editor._history_changed()

    def _part(self, changes: list[FileChange]) -> Edit:
        paths = {change.path for change in changes}
        images = tuple(i for i in self.edit.images if self._editor.store.dataset.entry(i).label_path in paths)
        return Edit(tuple(changes), images, self.edit.description)
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_restoring.py tests/core/test_history.py tests/core/test_batch.py`
Expected: 28 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 653 passed.

```bash
git add src/deeplabeling/core/store.py src/deeplabeling/core/history.py src/deeplabeling/core/editor.py tests/core/test_restoring.py
git commit -m "core: undo and redo an edit a chunk at a time; stopped part-way, nothing is lost" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: A long write behind a progress dialog

**Files:**
- Create: `src/deeplabeling/ui/chunked.py`, `tests/ui/test_chunked.py`
- Modify: `src/deeplabeling/ui/prompter.py`, `src/deeplabeling/ui/session.py`, `tests/fixtures.py`, `tests/ui/test_prompter.py`

**Interfaces:**
- Consumes: from Task 1, `Editor.restoring` and `Restoring`.
- Produces:
  - In `deeplabeling.ui.chunked`:
    - `CHUNK = 50`;
    - `Chunked(progress, step, end, parent=None)`, which calls `step()` once per event-loop turn while it returns `True`, then `end(cancelled, error)` once. `stop()` ends it between two chunks.
  - `QtPrompter.progress(title, total) -> Progress`, a modal `QProgressDialog` with `set(value)`, `cancelled()` and `close()`. The session's `Prompter` protocol gains `progress`.
  - In `Session`:
    - `running: Chunked | None`;
    - `run_chunked(title, total, step, end)`, where `step(progress) -> bool` and `end(progress, cancelled, error)`;
    - `_busy()`: while something runs, `apply`, `undo` and `redo` say `wait: <title> is under way` and do nothing;
    - `close()` stops a run first;
    - an undo or redo of an edit of more than `chunked.CHUNK` files runs in chunks: `Undoing <description>`, with a total of 2 × files, checked and then written.
  - In `tests/fixtures.py`:
    - `FakeProgress(title, total, cancel_at)`, with `.values` and `.closed`;
    - `FakePrompter(cancel_at=…)`, a value or `{title: value}`, and `.progresses`.

- [ ] **Step 1: Write the failing tests and the fake progress**

In `tests/fixtures.py`, replace:

```python


class FakePrompter:
    """Answers the UI's dialogs from preset values and records what was asked."""

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
        self.weights, self.threshold = weights, threshold
        self.class_map = class_map          #: {model class name: dataset class name or None}
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

with:

```python


class FakeProgress:
    """A progress dialog that records its values and is cancelled at `cancel_at`."""

    def __init__(self, title, total, cancel_at=None):
        self.title, self.total, self.cancel_at = title, total, cancel_at
        self.values: list[int] = []
        self.closed = False

    def set(self, value):
        self.values.append(value)

    def cancelled(self):
        return self.cancel_at is not None and bool(self.values) and self.values[-1] >= self.cancel_at

    def close(self):
        self.closed = True


class FakePrompter:
    """Answers the UI's dialogs from preset values and records what was asked."""

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None, cancel_at=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
        self.weights, self.threshold = weights, threshold
        self.class_map = class_map          #: {model class name: dataset class name or None}
        self.cancel_at = cancel_at          #: a progress is cancelled once it reaches this ({title: n}, or n)
        self.progresses: list[FakeProgress] = []
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

In `tests/fixtures.py`, replace:

```python
        self.asked.append(("threshold", current))
        return self.threshold

    def edit_class_map(self, cmap, dataset_names):
```

with:

```python
        self.asked.append(("threshold", current))
        return self.threshold

    def progress(self, title, total):
        at = self.cancel_at.get(title) if isinstance(self.cancel_at, dict) else self.cancel_at
        self.progresses.append(FakeProgress(title, total, at))
        return self.progresses[-1]

    def edit_class_map(self, cmap, dataset_names):
```

Create `tests/ui/test_chunked.py`:

```python
"""An edit across many images is undone and redone a chunk at a time, behind a progress
dialog that can cancel (docs/design/2026-10-05-model-assist.md#accepting)."""

import pytest
from PySide6.QtCore import QTimer

from deeplabeling.core import store as store_module
from deeplabeling.core.edits import AddBox, Intent
from deeplabeling.ui import chunked
from fixtures import FakePrompter, assert_only_changed, open_session, wait_decoded

BOX = (0.5, 0.5, 0.2, 0.2)
IMAGES = ("camA/0001.jpg", "camA/0003.jpg", "camA/0004.JPG", "camB/0001.jpg", "weird/имя пробел.jpg")


@pytest.fixture
def small_chunks(monkeypatch):
    monkeypatch.setattr(chunked, "CHUNK", 2)                 # 5 files: three chunks


@pytest.fixture
def prompter():
    return FakePrompter()


@pytest.fixture
def session(qtbot, ds, prompter, small_chunks):
    s = open_session(qtbot, ds.yaml, prompter)
    yield s
    s.close()


@pytest.fixture
def accepted(session, ds):
    before = ds.snapshot()
    session.workspace.editor.apply_many([Intent(ds.img(n), (AddBox(1, BOX),), "accept") for n in IMAGES],
                                        "accept missing boxes in this queue")
    return before, ds.snapshot()


def finished(session):
    return session.running is None


def test_a_big_edit_is_undone_and_redone_in_chunks_while_the_window_keeps_turning(qtbot, session, prompter,
                                                                                ds, accepted):
    before, after = accepted
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(0)
    session.undo()
    assert session.running is not None                      # not done at once
    qtbot.waitUntil(lambda: finished(session))
    timer.stop()
    assert_only_changed(before, ds.snapshot(), set())
    progress = prompter.progresses[-1]
    assert progress.title == "Undoing accept missing boxes in this queue" and progress.total == 10
    assert progress.values == sorted(progress.values) and progress.values[-1] == 10 and progress.closed
    assert len(ticks) >= 3                                   # the event loop ran between chunks
    with qtbot.waitSignal(session.status) as said:
        session.redo()
        qtbot.waitUntil(lambda: finished(session))
    assert said.args == ["redid accept missing boxes in this queue: 5 files"]
    assert_only_changed(after, ds.snapshot(), set())


def test_a_cancelled_undo_keeps_what_it_wrote_as_an_edit_of_its_own(qtbot, session, prompter, ds, accepted):
    before, after = accepted
    prompter.cancel_at = 7                                  # 5 checked, then 2 written
    with qtbot.waitSignal(session.status, timeout=5000) as said:
        session.undo()
        qtbot.waitUntil(lambda: finished(session))
    assert said.args == ["undo stopped: 2 of 5 files undone; the rest is still in the history"]
    assert_only_changed(after, ds.snapshot(), {"camA/labels/0001.txt", "camA/labels/0003.txt"})
    history = session.workspace.history
    assert len(history.peek_undo().changes) == 3 and len(history.peek_redo().changes) == 2
    prompter.cancel_at = None
    session.undo()
    qtbot.waitUntil(lambda: finished(session))
    assert_only_changed(before, ds.snapshot(), set())


def test_a_write_failing_part_way_says_so_and_keeps_the_rest_for_a_retry(qtbot, session, ds, accepted,
                                                                        monkeypatch):
    before, after = accepted
    real, calls = store_module.write_atomic, []

    def failing(path, data):
        calls.append(path)
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", failing)
    with qtbot.waitSignal(session.notice, timeout=5000) as said:
        session.undo()
        qtbot.waitUntil(lambda: finished(session))
    assert "No space left on device" in said.args[1]
    assert said.args[1].endswith("3 of 5 files were undone; the rest is still in the history: undo again")
    monkeypatch.setattr(store_module, "write_atomic", real)
    session.undo()
    qtbot.waitUntil(lambda: finished(session))
    assert_only_changed(before, ds.snapshot(), set())


def test_nothing_else_edits_while_it_runs(qtbot, session, ds, accepted):
    wait_decoded(qtbot, session, session.current().entry.path)
    session.undo()
    with qtbot.waitSignal(session.status) as said:
        assert session.apply(Intent(ds.img("camA/0002.jpg"), (AddBox(0, BOX),), "draw")) is None
    assert said.args == ["wait: undoing accept missing boxes in this queue is under way"]
    with qtbot.waitSignal(session.status) as said:
        session.undo()                                      # a second undo, pressed meanwhile
    assert said.args == ["wait: undoing accept missing boxes in this queue is under way"]
    qtbot.waitUntil(lambda: finished(session))
    assert session.workspace.history.can_redo and not session.workspace.history.can_undo


def test_closing_the_dataset_stops_it_before_its_next_chunk(qtbot, session, prompter, ds, accepted):
    _, after = accepted
    session.undo()
    session.close()                                          # before the first chunk ran
    assert finished(session) and prompter.progresses[-1].closed
    qtbot.wait(50)
    assert_only_changed(after, ds.snapshot(), set())         # no chunk ran after the close


def test_a_small_edit_is_undone_at_once(qtbot, session, ds, small_chunks):
    wait_decoded(qtbot, session, ds.img("camA/0001.jpg"))
    before = ds.snapshot()
    session.apply(Intent(ds.img("camA/0001.jpg"), (AddBox(1, BOX),), "draw"))
    session.undo()
    assert finished(session)
    assert_only_changed(before, ds.snapshot(), set())
```

Append to `tests/ui/test_prompter.py`:

```python
def test_the_progress_dialog_is_modal_visible_and_cancels(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QProgressDialog

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(600, 400)
    parent.show()
    progress = QtPrompter(parent).progress("Undoing accept", 10)
    dialog = parent.findChild(QProgressDialog)
    qtbot.waitUntil(dialog.isVisible)
    assert dialog.windowModality() == Qt.ApplicationModal and dialog.labelText() == "Undoing accept"
    progress.set(4)
    assert dialog.value() == 4 and not progress.cancelled()
    dialog.cancel()
    assert progress.cancelled()
    progress.close()
    qtbot.waitUntil(lambda: not parent.findChildren(QProgressDialog))
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_chunked.py`
Expected: `cannot import name 'chunked'`.

- [ ] **Step 3: Write the runner, the dialog, and the session's chunked undo**

Create `src/deeplabeling/ui/chunked.py`:

```python
"""A long write on the GUI thread, a chunk per event-loop turn, behind a modal progress
dialog (docs/design/2026-10-05-model-assist.md#accepting).

Every label file is written on the GUI thread's one write path (CLAUDE.md landmine 2). A
write across a whole queue done at once would freeze the window (about 2 ms a file), so it
goes a chunk at a time: the window keeps painting between chunks, the modal dialog keeps
anything else from editing, and its Cancel stops the run between two chunks.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

from ..core.edits import Refused

CHUNK = 50      #: files written per event-loop turn: about 0.1 s


class Chunked(QObject):
    """Calls `step` once per event-loop turn while it returns True; then `end(cancelled,
    error)` once: cancelled from the dialog or by stop(), or stopped by a Refused."""

    def __init__(self, progress, step: Callable[[], bool],
                 end: Callable[[bool, Refused | None], None], parent=None):
        super().__init__(parent)
        self._progress, self._step, self._end = progress, step, end
        self._over = False
        QTimer.singleShot(0, self._next)

    def _next(self) -> None:
        if self._over:
            return
        if self._progress.cancelled():
            self._finish(cancelled=True)
            return
        try:
            more = self._step()
        except Refused as e:
            self._finish(error=e)
            return
        if more:
            QTimer.singleShot(0, self._next)
        else:
            self._finish()

    def stop(self) -> None:
        """Stop now, between two chunks, as a cancel does."""
        if not self._over:
            self._finish(cancelled=True)

    def _finish(self, *, cancelled: bool = False, error: Refused | None = None) -> None:
        self._over = True
        self._progress.close()
        self._end(cancelled, error)
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from ..core.classmap import ClassMap
```

with:

```python
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox, QProgressDialog

from ..core.classmap import ClassMap
```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
            "A label file's ids mean one class list. Under the wrong one every name shown is "
            "wrong, and every edit writes wrong ids. Open with the new class list?")


```

with:

```python
            "A label file's ids mean one class list. Under the wrong one every name shown is "
            "wrong, and every edit writes wrong ids. Open with the new class list?")


class Progress:
    """A modal progress dialog with a Cancel button. The window keeps painting behind it,
    and nothing else in the app can be clicked while it shows."""

    def __init__(self, dialog: QProgressDialog):
        self._dialog = dialog
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        dialog.show()

    def set(self, value: int) -> None:
        self._dialog.setValue(value)

    def cancelled(self) -> bool:
        return self._dialog.wasCanceled()

    def close(self) -> None:
        self._dialog.close()
        self._dialog.deleteLater()


```

In `src/deeplabeling/ui/prompter.py`, replace:

```python
            return dialog.class_map() if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()
```

with:

```python
            return dialog.class_map() if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()

    def progress(self, title: str, total: int) -> Progress:
        return Progress(QProgressDialog(title, "Cancel", 0, total, self.parent))
```

In `src/deeplabeling/ui/session.py`, replace:

```python
from ..core.taxonomy import count_out_of_range
from ..core.workspace import CLASS_COLORS, CLASS_HOTKEYS, QUEUE_CURSOR, QUEUE_SOURCE, OpenCancelled, Workspace
from .classes import assign_classes
from .images import THUMB_BYTES, ImageCache, decode_thumb
```

with:

```python
from ..core.taxonomy import count_out_of_range
from ..core.workspace import CLASS_COLORS, CLASS_HOTKEYS, QUEUE_CURSOR, QUEUE_SOURCE, OpenCancelled, Workspace
from . import chunked
from .chunked import Chunked
from .classes import assign_classes
from .images import THUMB_BYTES, ImageCache, decode_thumb
```

In `src/deeplabeling/ui/session.py`, replace:

```python

    def error(self, title: str, text: str) -> None: ...


```

with:

```python

    def error(self, title: str, text: str) -> None: ...

    def progress(self, title: str, total: int): ...


```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self._watch.timeout.connect(self.check_current)
        self._watch.start()
        self.model = ModelSession(self, self)

```

with:

```python
        self._watch.timeout.connect(self.check_current)
        self._watch.start()
        self.running: Chunked | None = None         # a long write under way (ui/chunked.py)
        self._running_title = ""
        self.model = ModelSession(self, self)

```

In `src/deeplabeling/ui/session.py`, replace:

```python
        if ws is None:
            return
        self.io.cancel_all()
        self.model.release()                        # before the store it writes to closes
```

with:

```python
        if ws is None:
            return
        if self.running is not None:
            self.running.stop()                     # between two chunks: nothing half-written
        self.io.cancel_all()
        self.model.release()                        # before the store it writes to closes
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        """Every label change goes through here; a refusal becomes a notice."""
        ws = self._require()
        rel = ws.dataset.entry(intent.image).rel
        why = self.images.error(intent.image)
```

with:

```python
        """Every label change goes through here; a refusal becomes a notice."""
        ws = self._require()
        if self._busy():
            return None
        rel = ws.dataset.entry(intent.image).rel
        why = self.images.error(intent.image)
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self._step(undo=False)

    def _step(self, *, undo: bool) -> None:
        ws = self.workspace
        edit = None if ws is None else ws.history.peek_undo() if undo else ws.history.peek_redo()
        if edit is None:
```

with:

```python
        self._step(undo=False)

    def _busy(self) -> bool:
        """While a long write runs, nothing else edits; a key that would says so."""
        if self.running is None:
            return False
        self.status.emit(f"wait: {self._running_title[0].lower()}{self._running_title[1:]} is under way")
        return True

    def run_chunked(self, title: str, total: int, step, end) -> None:
        """Run `step` a chunk per event-loop turn behind a progress dialog (ui/chunked.py)."""
        progress = self.prompter.progress(title, total)

        def ended(cancelled, error):
            self.running = None
            end(progress, cancelled, error)

        self._running_title = title
        self.running = Chunked(progress, lambda: step(progress), ended, self)

    def _step(self, *, undo: bool) -> None:
        ws = self.workspace
        if self._busy():
            return
        edit = None if ws is None else ws.history.peek_undo() if undo else ws.history.peek_redo()
        if edit is None:
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        if self.queue is not None and rel in self.queue and (current is None or current.key != rel):
            self.go_to(rel)                         # the change happens in view
        try:
            (ws.editor.undo if undo else ws.editor.redo)()
```

with:

```python
        if self.queue is not None and rel in self.queue and (current is None or current.key != rel):
            self.go_to(rel)                         # the change happens in view
        if len(edit.changes) > chunked.CHUNK:
            self._restore_in_chunks(edit, undo)
            return
        try:
            (ws.editor.undo if undo else ws.editor.redo)()
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            return
        self.status.emit(f"{'undid' if undo else 'redid'} {edit.description}: {rel}")

    def _recheck(self, images) -> None:
```

with:

```python
            return
        self.status.emit(f"{'undid' if undo else 'redid'} {edit.description}: {rel}")

    def _restore_in_chunks(self, edit: Edit, undo: bool) -> None:
        """Undo (or redo) an edit across many images: every file checked, then written, a
        chunk at a time. Stopped part-way, what was written stays an edit of its own."""
        restoring = self._require().editor.restoring(undo=undo)
        verb, past = ("undo", "undone") if undo else ("redo", "redone")

        def step(progress) -> bool:
            if restoring.checked < restoring.total:
                restoring.check(chunked.CHUNK)
            else:
                restoring.write(chunked.CHUNK)
            progress.set(restoring.checked + restoring.written)
            return restoring.written < restoring.total

        def end(progress, cancelled, error) -> None:
            n, w = restoring.total, restoring.written
            if error is None and not cancelled:
                restoring.finish()
                self.status.emit(f"{'undid' if undo else 'redid'} {edit.description}: {n:,} files")
            elif error is not None and restoring.checked < n:
                self.notice.emit("error", str(error), None)     # a file changed since: dropped
            elif error is not None:
                restoring.stop()
                self.notice.emit("error", f"cannot {verb} “{edit.description}”: {error}. {w:,} of {n:,} "
                                 f"files were {past}; the rest is still in the history: {verb} again", None)
            else:
                restoring.stop()
                self.status.emit(f"{verb} stopped: {w:,} of {n:,} files {past}; the rest is still in the history"
                                 if w else f"{verb} stopped before anything was written")

        self.run_chunked(f"{'Undoing' if undo else 'Redoing'} {edit.description}", 2 * restoring.total, step, end)

    def _recheck(self, images) -> None:
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_chunked.py tests/ui/test_prompter.py tests/ui/test_session.py`
Expected: 43 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 660 passed.

```bash
git add src/deeplabeling/ui/chunked.py src/deeplabeling/ui/prompter.py src/deeplabeling/ui/session.py tests/fixtures.py tests/ui/test_chunked.py tests/ui/test_prompter.py
git commit -m "ui: a large undo or redo runs a chunk at a time behind a progress dialog that can cancel" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Accept missing boxes in this queue

**Files:**
- Create: `src/deeplabeling/ui/queue_accept.py`, `tests/ui/test_queue_accept.py`
- Modify: `src/deeplabeling/ui/prompter.py`, `src/deeplabeling/ui/session.py`, `src/deeplabeling/ui/main_window.py`, `tests/fixtures.py`, `tests/ui/test_prompter.py`, `tests/ui/test_model_chip.py`

**Interfaces:**
- Consumes:
  - from Task 2: `Session.run_chunked`, `Session._busy`, `chunked.CHUNK` and `FakePrompter(cancel_at=…)`;
  - from plan 2a: `plan_queue_accept`, `QueueAccept`, `Editor.batch` and `image_stamp`;
  - from plan 2b: `ModelSession` (`state`, `key`, `class_map`, `conf`).
- Produces in `deeplabeling.ui.queue_accept`:
  - `DESCRIPTION = "accept missing boxes in this queue"`;
  - `PLAN_BATCH = 500`;
  - `queue_accept_question(plan) -> str`;
  - `accept_queue(session)`:
    - **Look:** it looks at the queue a `PLAN_BATCH` at a time (`Looking at N images`).
    - **Confirm:** it asks `prompter.confirm_queue_accept(text) -> bool`.
    - **Write:** it writes a `CHUNK` at a time (`Accepting N boxes on M images`).
    - **Statuses:**
      - `accepted N boxes on M images`;
      - `accept stopped: … kept, as one edit`;
      - `accept cancelled: nothing was written`;
      - `no missing boxes to accept in this queue; …`.
    - **On a failed write:** an error notice, `nothing was accepted: <why>`.
- Produces elsewhere:
  - `QtPrompter.confirm_queue_accept(text)`: a Yes/No box, No by default. `FakePrompter(accept_queue=True)` answers it and records `("queue accept", text)`.
  - `MainWindow.accept_queue()` and the model menu's `Accept missing boxes in this queue…`, enabled when a model is ready and the queue is complete.

- [ ] **Step 1: Write the failing tests**

In `tests/fixtures.py`, replace:

```python

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None, cancel_at=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
```

with:

```python

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None, cancel_at=None, accept_queue=True):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
```

In `tests/fixtures.py`, replace:

```python
        self.cancel_at = cancel_at          #: a progress is cancelled once it reaches this ({title: n}, or n)
        self.progresses: list[FakeProgress] = []
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

with:

```python
        self.cancel_at = cancel_at          #: a progress is cancelled once it reaches this ({title: n}, or n)
        self.progresses: list[FakeProgress] = []
        self.accept_queue = accept_queue    #: the answer to the queue accept's confirmation
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
```

In `tests/fixtures.py`, replace:

```python
        self.asked.append(("threshold", current))
        return self.threshold

    def progress(self, title, total):
```

with:

```python
        self.asked.append(("threshold", current))
        return self.threshold

    def confirm_queue_accept(self, text):
        self.asked.append(("queue accept", text))
        return self.accept_queue

    def progress(self, title, total):
```

Append to `tests/ui/test_prompter.py`:

```python
def test_the_queue_accept_is_confirmed_with_yes_and_declined_otherwise(qtbot):
    from PySide6.QtWidgets import QMessageBox

    parent = QWidget()
    qtbot.addWidget(parent)
    prompter = QtPrompter(parent)
    def press_yes():
        box = QApplication.activeModalWidget()
        if box is None:
            QTimer.singleShot(10, press_yes)                 # not shown yet
        else:
            box.button(QMessageBox.Yes).click()

    QTimer.singleShot(0, press_yes)
    assert prompter.confirm_queue_accept("Accept 1 box on 1 image?") is True
    answer_with_cancel()
    assert prompter.confirm_queue_accept("Accept 1 box on 1 image?") is False
```

Create `tests/ui/test_queue_accept.py`:

```python
"""Accepting the missing predictions across a queue: planned on a job, confirmed, then
written a chunk at a time as one edit (docs/design/2026-10-05-model-assist.md#accepting)."""

import pytest

from deeplabeling.core import store as store_module
from deeplabeling.core.assist import QueueAccept
from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import image_stamp
from deeplabeling.ui import chunked, queue_accept
from deeplabeling.ui.queue_accept import accept_queue, queue_accept_question
from fixtures import CAMA_0001, FakePredictor, FakePrompter, assert_only_changed, open_session, read_exact

CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9)              # the model's car: the dataset's car (1)
HUMAN = Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)            # unmapped
CAR_LINE = "1 0.800000 0.800000 0.100000 0.100000\n"
ROWS = {"camA/images/0001.jpg": [CAR, HUMAN], "camA/images/0002.jpg": [CAR],      # 0002: a negative
        "camA/images/0003.jpg": [CAR], "camA/images/0004.JPG": [CAR], "camB/images/0001.jpg": [CAR],
        "camB/images/twin.jpg": [CAR],                                              # shares its file
        "weird/images/имя пробел.jpg": [CAR]}
WRITTEN = {"camA/labels/0001.txt", "camA/labels/0003.txt", "camA/labels/0004.txt",
           "camB/labels/0001.txt", "weird/labels/имя пробел.txt"}


@pytest.fixture
def prompter():
    return FakePrompter()


@pytest.fixture
def session(qtbot, ds, prompter, tmp_path, monkeypatch):
    """The dataset open, ROWS in the store, and the fake model that found them loaded."""
    monkeypatch.setattr(chunked, "CHUNK", 2)
    s = open_session(qtbot, ds.yaml, prompter)
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    for rel, preds in ROWS.items():
        entry = s.workspace.dataset.entry(ds.root / rel)
        s.workspace.predictions.put("fake:best.pt", rel, image_stamp(entry.path), preds)
    s.model.factory = FakePredictor
    s.model.load(weights)
    qtbot.waitUntil(lambda: s.model.state == "ready", timeout=5000)
    yield s
    s.close()


def accepted(qtbot, session):
    with qtbot.waitSignal(session.status, timeout=5000) as said:
        accept_queue(session)
        qtbot.waitUntil(lambda: session.running is None and said.signal_triggered, timeout=5000)
    return said.args[0]


def test_the_question_says_what_it_adds_and_what_it_skips():
    plan = QueueAccept(intents=(None,) * 567, boxes=1234, uninferred=89, unmapped=40, read_only=3, negative=12)
    assert queue_accept_question(plan) == (
        "Accept 1,234 boxes on 567 images?\n\n"
        "Skipped: 89 images not inferred yet; 12 negative samples (an empty label file is "
        "someone's decision); 3 images whose label file cannot be edited; "
        "40 predictions of a class the map leaves out.\n\n"
        "It is one edit: one undo takes it all back. Nothing is marked reviewed.")
    one = QueueAccept(intents=(None,), boxes=1, uninferred=0, unmapped=0, read_only=0, negative=0)
    assert queue_accept_question(one) == ("Accept 1 box on 1 image?\n\n"
                                          "It is one edit: one undo takes it all back. Nothing is marked reviewed.")


def test_the_queue_accept_writes_one_edit_that_marks_nothing_and_undoes_whole(qtbot, session, prompter, ds):
    before = ds.snapshot()
    assert accepted(qtbot, session) == "accepted 5 boxes on 5 images"
    [(_, text)] = [a for a in prompter.asked if a[0] == "queue accept"]
    assert text.startswith("Accept 5 boxes on 5 images?\n\nSkipped: 8 images not inferred yet; 1 negative sample")
    assert [p.title for p in prompter.progresses] == ["Looking at 15 images", "Accepting 5 boxes on 5 images"]
    assert_only_changed(before, ds.snapshot(), WRITTEN)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + CAR_LINE
    assert read_exact(ds.lbl("camA/0003")) == CAR_LINE
    assert session.workspace.history.depth == 1 and session.workspace.review.count() == 0
    session.undo()                                          # 5 files > CHUNK: in chunks too
    qtbot.waitUntil(lambda: session.running is None)
    assert_only_changed(before, ds.snapshot(), set())


def test_declined_nothing_is_written(qtbot, session, prompter, ds):
    prompter.accept_queue = False
    before = ds.snapshot()
    accept_queue(session)
    qtbot.waitUntil(lambda: any(a[0] == "queue accept" for a in prompter.asked))
    qtbot.wait(50)
    assert_only_changed(before, ds.snapshot(), set()) and session.workspace.history.depth == 0


def test_nothing_missing_says_so_without_asking(qtbot, session, prompter):
    session.model.set_conf(0.95)                            # above every prediction
    assert accepted(qtbot, session) == (
        "no missing boxes to accept in this queue; 8 images are not inferred yet; 1 negative sample "
        "(an empty label file is someone's decision); 1 image whose label file cannot be edited")
    assert not any(a[0] == "queue accept" for a in prompter.asked)


def test_a_cancel_while_writing_keeps_the_chunks_written_as_one_edit(qtbot, session, prompter, ds):
    before = ds.snapshot()
    prompter.cancel_at = {"Accepting 5 boxes on 5 images": 2}
    assert accepted(qtbot, session) == "accept stopped: 2 boxes on 2 images kept, as one edit"
    assert_only_changed(before, ds.snapshot(), {"camA/labels/0001.txt", "camA/labels/0003.txt"})
    assert session.workspace.history.depth == 1
    session.undo()
    assert_only_changed(before, ds.snapshot(), set())       # 2 files: undone at once


def test_a_cancel_while_looking_writes_nothing(qtbot, session, prompter, ds, monkeypatch):
    monkeypatch.setattr(queue_accept, "PLAN_BATCH", 1)
    prompter.cancel_at = 3
    before = ds.snapshot()
    assert accepted(qtbot, session) == "accept cancelled: nothing was written"
    assert not any(a[0] == "queue accept" for a in prompter.asked)
    assert_only_changed(before, ds.snapshot(), set())


def test_a_write_failing_part_way_puts_every_file_back_and_says_why(qtbot, session, ds, monkeypatch):
    before = ds.snapshot()
    real, calls = store_module.write_atomic, []

    def failing(path, data):
        calls.append(path)
        if len(calls) == 3:
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", failing)
    with qtbot.waitSignal(session.notice, timeout=5000) as said:
        accept_queue(session)
    qtbot.waitUntil(lambda: session.running is None)
    assert said.args[1].startswith("nothing was accepted: could not write") and "No space left" in said.args[1]
    monkeypatch.setattr(store_module, "write_atomic", real)
    assert_only_changed(before, ds.snapshot(), set())
    assert session.workspace.history.depth == 0


def test_without_a_model_or_a_whole_queue_it_says_why(qtbot, session):
    session.model.unload()
    with qtbot.waitSignal(session.status) as said:
        accept_queue(session)
    assert said.args == ["no model is loaded"]
```

Append to `tests/ui/test_model_chip.py`:

```python
def test_the_queue_accept_waits_for_a_model_and_runs_from_the_menu(qtbot, window, ds):
    assert not menu(window)["Accept missing boxes in this queue…"].isEnabled()
    load(qtbot, window)
    with qtbot.waitSignal(window.session.status, timeout=5000,
                          check_params_cb=lambda text: text.startswith("accepted")) as said:
        menu(window)["Accept missing boxes in this queue…"].trigger()
    assert said.args == ["accepted 1 box on 1 image"]
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_accept.py`
Expected: `cannot import name 'queue_accept'`.

- [ ] **Step 3: Look, confirm, write**

In `src/deeplabeling/ui/prompter.py`, replace:

```python
    def progress(self, title: str, total: int) -> Progress:
        return Progress(QProgressDialog(title, "Cancel", 0, total, self.parent))
```

with:

```python
    def progress(self, title: str, total: int) -> Progress:
        return Progress(QProgressDialog(title, "Cancel", 0, total, self.parent))

    def confirm_queue_accept(self, text: str) -> bool:
        answer = QMessageBox.question(self.parent, "Accept missing boxes in this queue", text,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes
```

In `src/deeplabeling/ui/session.py`, replace:

```python

    def progress(self, title: str, total: int): ...


```

with:

```python

    def progress(self, title: str, total: int): ...

    def confirm_queue_accept(self, text: str) -> bool: ...


```

Create `src/deeplabeling/ui/queue_accept.py`:

```python
"""Accept missing boxes in this queue… (docs/design/2026-10-05-model-assist.md#accepting).

It looks at every image a chunk at a time, behind a progress dialog, and asks first. Then it
writes a chunk at a time on the GUI thread's write path, as one edit that marks nothing. A cancel
keeps the chunks already written, as one edit; a write that fails puts every file back.
"""

from __future__ import annotations

from ..core.assist import QueueAccept, plan_queue_accept
from ..core.predstore import image_stamp
from . import chunked

DESCRIPTION = "accept missing boxes in this queue"
PLAN_BATCH = 500        #: images looked at per event-loop turn: label files and store rows, read


def _count(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def _skipped(plan: QueueAccept) -> list[str]:
    return [text for n, text in (
        (plan.uninferred, _count(plan.uninferred, "image", "images") + " not inferred yet"),
        (plan.negative, _count(plan.negative, "negative sample", "negative samples")
         + " (an empty label file is someone's decision)"),
        (plan.read_only, _count(plan.read_only, "image", "images") + " whose label file cannot be edited"),
        (plan.unmapped, _count(plan.unmapped, "prediction", "predictions") + " of a class the map leaves out"),
    ) if n]


def queue_accept_question(plan: QueueAccept) -> str:
    text = f"Accept {_count(plan.boxes, 'box', 'boxes')} on {_count(len(plan.intents), 'image', 'images')}?\n\n"
    skipped = _skipped(plan)
    if skipped:
        text += "Skipped: " + "; ".join(skipped) + ".\n\n"
    return text + "It is one edit: one undo takes it all back. Nothing is marked reviewed."


def accept_queue(session) -> None:
    """Look, confirm and write; each step says how it ended in the status bar."""
    model, ws, queue = session.model, session.workspace, session.queue
    if ws is None or session._busy():
        return
    if model.state != "ready":
        session.status.emit("the model is still loading" if model.state == "loading" else "no model is loaded")
        return
    if queue is None or not queue.complete:
        session.status.emit("the queue is still being built")
        return
    entries = [item.entry for item in queue.items]
    key, preds, cmap, conf = model.key, ws.predictions, model.class_map, model.conf
    plan, looked = QueueAccept((), 0, 0, 0, 0, 0), 0

    def preds_of(entry):
        try:
            return preds.get(key, entry.rel, image_stamp(entry.path))
        except OSError:
            return None

    def step(progress) -> bool:                     # reads only: label files and the store
        nonlocal plan, looked
        part = plan_queue_accept(entries[looked:looked + PLAN_BATCH], ws.store.get, preds_of,
                                 cmap, ws.dataset, conf)
        plan = QueueAccept(plan.intents + part.intents, *(a + b for a, b in zip(
            (plan.boxes, plan.uninferred, plan.unmapped, plan.read_only, plan.negative),
            (part.boxes, part.uninferred, part.unmapped, part.read_only, part.negative))))
        looked += PLAN_BATCH
        progress.set(min(looked, len(entries)))
        return looked < len(entries)

    def end(progress, cancelled, error) -> None:
        if cancelled or error is not None or session.workspace is not ws:
            session.status.emit("accept cancelled: nothing was written")
        elif not plan.intents:
            session.status.emit("; ".join(["no missing boxes to accept in this queue"]
                                          + [s.replace(" not inferred yet", " are not inferred yet")
                                             for s in _skipped(plan)]))
        elif session.prompter.confirm_queue_accept(queue_accept_question(plan)):
            _write(session, plan)

    session.run_chunked(f"Looking at {len(entries):,} images", len(entries), step, end)


def _write(session, plan: QueueAccept) -> None:
    batch = session.workspace.editor.batch(DESCRIPTION)
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
            session.notice.emit("error", f"nothing was accepted: {error}", None)
            return
        batch.finish()
        boxes = sum(len(intent.ops) for intent in intents[:written])
        what = f"{_count(boxes, 'box', 'boxes')} on {_count(written, 'image', 'images')}"
        session.status.emit(f"accept stopped: {what} kept, as one edit" if cancelled else f"accepted {what}")

    session.run_chunked(f"Accepting {_count(plan.boxes, 'box', 'boxes')} on {_count(len(intents), 'image', 'images')}",
                        len(intents), step, end)
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
from .model import RECENT_MODELS
from .notices import NoticeStrip
from .queue_panel import QueuePanel
from .session import Session
```

with:

```python
from .model import RECENT_MODELS
from .notices import NoticeStrip
from .queue_accept import accept_queue
from .queue_panel import QueuePanel
from .session import Session
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        menu.addAction("Threshold…", self.ask_threshold).setEnabled(ws is not None)
        menu.addAction("Class map…", self.edit_class_map).setEnabled(ws is not None and model.state == "ready")

    def load_model(self) -> None:
```

with:

```python
        menu.addAction("Threshold…", self.ask_threshold).setEnabled(ws is not None)
        menu.addAction("Class map…", self.edit_class_map).setEnabled(ws is not None and model.state == "ready")
        menu.addSeparator()
        queue = self.session.queue
        menu.addAction("Accept missing boxes in this queue…", self.accept_queue).setEnabled(
            model.state == "ready" and queue is not None and queue.complete)

    def accept_queue(self) -> None:
        accept_queue(self.session)

    def load_model(self) -> None:
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_queue_accept.py tests/ui/test_prompter.py tests/ui/test_model_chip.py`
Expected: 24 passed.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 670 passed.

```bash
git add src/deeplabeling/ui/queue_accept.py src/deeplabeling/ui/prompter.py src/deeplabeling/ui/session.py src/deeplabeling/ui/main_window.py tests/fixtures.py tests/ui/test_queue_accept.py tests/ui/test_prompter.py tests/ui/test_model_chip.py
git commit -m "ui: accept missing boxes in this queue: look, confirm, then one edit written a chunk at a time" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The dataset pass

**Files:**
- Create: `tests/ui/test_pass.py`
- Modify: `src/deeplabeling/ui/model.py`, `src/deeplabeling/ui/state_bar.py`, `src/deeplabeling/ui/main_window.py`, `tests/ui/test_model_chip.py`

**Interfaces:**
- Consumes: from plan 2b, `_Worker`, `ModelSession`, `model_text` and `MainWindow._fill_model_menu`; from plan 2a, `PredictionStore.put_many` and `inferred`.
- Produces in `deeplabeling.ui.model`:
  - `PASS_BATCH = 8`;
  - in `_Worker`:
    - signals: `passProgress(walked, total)` and `passEnded(inferred, failed, cancelled)`;
    - `start_pass(store, items)` and `cancel_pass()`;
    - priority: control first, then the screen, then one pass batch;
  - in `ModelSession`:
    - a `progress` signal;
    - `passing`, `pass_walked` and `pass_total`;
    - `infer_queue()` and `cancel_pass()`;
    - `inferred_count() -> (with a row, of) | None`;
    - the end is an info notice: `inferred N images; F failed`, or `inferring stopped: N images inferred, F failed`.
- Produces elsewhere:
  - `model_text` appends ` · inferring W / T` while a pass runs, or ` · N / M inferred` otherwise;
  - the model menu offers `Infer this queue`, or `Cancel inferring` while a pass runs.
- The 2b chip tests now wait for the count: how many neighbours are inferred when the chip is read depends on timing.

- [ ] **Step 1: Write the failing tests**

In `tests/ui/test_model_chip.py`, replace:

```python
def test_loading_from_the_chip_names_the_model_and_draws_its_predictions(qtbot, window):
    load(qtbot, window)
    assert window.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.25"
    assert captions(window) == ["car 0.90", "human? 0.70"]

```

with:

```python
def test_loading_from_the_chip_names_the_model_and_draws_its_predictions(qtbot, window):
    load(qtbot, window)
    qtbot.waitUntil(lambda: window.state_bar.model.full_text
                    == "Model: best.pt · 3 classes · conf 0.25 · 3 / 15 inferred")   # and its neighbours
    assert captions(window) == ["car 0.90", "human? 0.70"]

```

In `tests/ui/test_model_chip.py`, replace:

```python
    menu(window)["Threshold…"].trigger()
    assert ("threshold", 0.25) in prompter.asked
    assert window.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.80"
    assert captions(window) == ["car 0.90"]         # the person's is faint: no caption

```

with:

```python
    menu(window)["Threshold…"].trigger()
    assert ("threshold", 0.25) in prompter.asked
    qtbot.waitUntil(lambda: window.state_bar.model.full_text
                    == "Model: best.pt · 3 classes · conf 0.80 · 3 / 15 inferred")   # and its neighbours
    assert captions(window) == ["car 0.90"]         # the person's is faint: no caption

```

In `tests/ui/test_model_chip.py`, replace:

```python
    again = start(qtbot, [str(ds.yaml)], FakePrompter())
    qtbot.waitUntil(lambda: len(again.canvas._predictions) == 3, timeout=5000)
    assert again.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.50"
    assert captions(again) == ["car 0.90", "person 0.70"]
    again.close()
```

with:

```python
    again = start(qtbot, [str(ds.yaml)], FakePrompter())
    qtbot.waitUntil(lambda: len(again.canvas._predictions) == 3, timeout=5000)
    qtbot.waitUntil(lambda: again.state_bar.model.full_text
                    == "Model: best.pt · 3 classes · conf 0.50 · 3 / 15 inferred")   # and its neighbours
    assert captions(again) == ["car 0.90", "person 0.70"]
    again.close()
```

In `tests/ui/test_model_chip.py`, replace:

```python
    assert said.args == ["accepted 1 box on 1 image"]
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"
```

with:

```python
    assert said.args == ["accepted 1 box on 1 image"]
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"


def test_infer_this_queue_runs_from_the_menu_and_can_be_cancelled_there(qtbot, window, monkeypatch):
    assert not menu(window)["Infer this queue"].isEnabled()
    load(qtbot, window)
    with qtbot.waitSignal(window.session.notice, timeout=5000,
                          check_params_cb=lambda level, text, image: level == "info") as said:
        menu(window)["Infer this queue"].trigger()
    assert said.args[1] == "inferred 12 images; 0 failed"   # the screen had done the first three
    assert window.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.25 · 15 / 15 inferred"
    cancelled = []
    monkeypatch.setattr(window.session.model, "cancel_pass", lambda: cancelled.append(1))
    window.session.model.passing = True                      # as while a pass runs
    assert "Infer this queue" not in menu(window)
    menu(window)["Cancel inferring"].trigger()
    assert cancelled == [1]
```

Create `tests/ui/test_pass.py`:

```python
"""Inferring a whole queue on the model's thread, behind the image on screen
(docs/design/2026-10-05-model-assist.md#a-dataset-pass)."""

import threading
import time

import pytest

from deeplabeling.ui import model as model_module
from deeplabeling.ui.state_bar import model_text
from fixtures import FakePredictor, open_session

QUEUE = ["0001.jpg", "0002.jpg", "0003.jpg", "0004.JPG", "0005.jpg", "0001.jpg", "rot.jpg", "twin.jpg",
         "twin.png", "имя пробел.jpg", "corrupt.jpg", "ok.jpg", "c.jpg", "mixed.jpg", "poly1.jpg"]


@pytest.fixture
def gate():
    g = threading.Event()
    g.set()
    yield g
    g.set()                                                   # never leave the thread waiting


@pytest.fixture
def made():
    return []


@pytest.fixture
def session(qtbot, ds, tmp_path, gate, made, monkeypatch):
    """The dataset open, the fake model loaded, and the screen's three images inferred."""
    monkeypatch.setattr(model_module, "PASS_BATCH", 2)
    s = open_session(qtbot, ds.yaml)
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")

    def factory(path):
        made.append(FakePredictor(path, gate=gate, fail={"ok.jpg"}))
        return made[-1]

    s.model.factory = factory
    s.model.load(weights)
    items = s.queue.items
    qtbot.waitUntil(lambda: all(s.model.predictions(items[i].entry) is not None for i in range(3)), timeout=5000)
    yield s
    s.close()


def ended(qtbot, session):
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info") as said:
        pass
    return said


def test_a_pass_infers_the_rest_of_the_queue_in_order_and_says_how_it_went(qtbot, session, made):
    assert model_text(session.model) == "Model: best.pt · 3 classes · conf 0.25 · 3 / 15 inferred"
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info") as said:
        session.model.infer_queue()
    assert said.args[1] == "inferred 11 images; 1 failed"
    assert made[-1].asked == QUEUE                           # the first three by the screen, each once
    assert model_text(session.model) == "Model: best.pt · 3 classes · conf 0.25 · 14 / 15 inferred"


def test_the_chip_shows_a_pass_under_way(qtbot, session, gate):
    gate.clear()
    session.model.infer_queue()
    assert session.model.passing
    assert model_text(session.model) == "Model: best.pt · 3 classes · conf 0.25 · inferring 0 / 15"
    gate.set()
    qtbot.waitUntil(lambda: not session.model.passing, timeout=5000)


def test_a_cancelled_pass_keeps_its_batches_and_a_second_resumes(qtbot, session, gate, made):
    gate.clear()                                              # the first batch waits in the model
    session.model.infer_queue()
    qtbot.waitUntil(lambda: made[-1].gate is gate and session.model._worker is not None)
    time.sleep(0.1)                                           # the batch is in hand
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info") as said:
        session.model.cancel_pass()
        gate.set()
    assert said.args[1] == "inferring stopped: 2 images inferred, 0 failed"
    assert made[-1].asked == QUEUE[:5]
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info") as said:
        session.model.infer_queue()
    assert said.args[1] == "inferred 9 images; 1 failed"
    assert made[-1].asked == QUEUE                           # nothing inferred twice


def test_the_image_on_screen_goes_ahead_of_a_pass(qtbot, session, gate, made):
    gate.clear()
    session.model.infer_queue()
    time.sleep(0.1)                                           # the first batch is in hand
    session.go_to("seg/images/poly1.jpg")                     # the last in the queue
    gate.set()
    qtbot.waitUntil(lambda: not session.model.passing, timeout=5000)
    assert made[-1].asked[:6] == QUEUE[:5] + ["poly1.jpg"]
    assert made[-1].asked.count("poly1.jpg") == 1


def test_closing_during_a_pass_stops_it(qtbot, session, gate):
    gate.clear()
    session.model.infer_queue()
    time.sleep(0.1)
    started = time.monotonic()
    session.close()
    assert time.monotonic() - started < 2.5 and not session.model.passing


def test_a_store_that_cannot_be_written_fails_the_pass_images_and_the_pass_goes_on(qtbot, session, monkeypatch):
    import sqlite3

    def full(model, rows):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(session.workspace.predictions, "put_many", full)
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info") as said:
        session.model.infer_queue()
    assert said.args[1] == "inferred 0 images; 12 failed"


def test_an_image_changed_on_disk_since_is_inferred_again(qtbot, session, made, ds):
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info"):
        session.model.infer_queue()
    image = ds.img("camA/0004.JPG")
    image.write_bytes(image.read_bytes() + b"\0")             # edited elsewhere: a new stamp
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info") as said:
        session.model.infer_queue()
    assert said.args[1] == "inferred 1 image; 1 failed"      # it; and ok.jpg failed again
    assert made[-1].asked.count("0004.JPG") == 2
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_pass.py`
Expected: `has no attribute 'PASS_BATCH'`.

- [ ] **Step 3: The pass on the model's thread, its count and its entries**

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        menu.addSeparator()
        queue = self.session.queue
        menu.addAction("Accept missing boxes in this queue…", self.accept_queue).setEnabled(
            model.state == "ready" and queue is not None and queue.complete)

    def accept_queue(self) -> None:
```

with:

```python
        menu.addSeparator()
        queue = self.session.queue
        whole = model.state == "ready" and queue is not None and queue.complete
        if model.passing:
            menu.addAction("Cancel inferring", model.cancel_pass)
        else:
            menu.addAction("Infer this queue", model.infer_queue).setEnabled(whole)
        menu.addAction("Accept missing boxes in this queue…", self.accept_queue).setEnabled(whole)

    def accept_queue(self) -> None:
```

In `src/deeplabeling/ui/model.py`, replace:

```python
SHUTDOWN_MS = 2000      #: the longest closing waits for a prediction in hand
NEIGHBOURS = (1, 2, -1)  #: queue offsets predicted after the image on screen, as images are kept

Wanted = tuple[str, Path, Stamp]   #: (dataset-relative path, file, stamp)
```

with:

```python
SHUTDOWN_MS = 2000      #: the longest closing waits for a prediction in hand
NEIGHBOURS = (1, 2, -1)  #: queue offsets predicted after the image on screen, as images are kept
PASS_BATCH = 8          #: images a pass asks the model for at once, decoded in parallel

Wanted = tuple[str, Path, Stamp]   #: (dataset-relative path, file, stamp)
```

In `src/deeplabeling/ui/model.py`, replace:

```python
class _Worker(QThread):
    """The thread that owns the predictor. Control jobs (load, unload, stop) go first, then
    the images wanted on screen, in order."""

    loaded = Signal(object, object, object)   # path, key, names
```

with:

```python
class _Worker(QThread):
    """The thread that owns the predictor. Control jobs (load, unload, stop) go first, then
    the images wanted on screen, in order, then a batch of the dataset pass."""

    loaded = Signal(object, object, object)   # path, key, names
```

In `src/deeplabeling/ui/model.py`, replace:

```python
    ready = Signal(object)                    # image path: its row is in the store
    failed = Signal(object, str)              # image path, why

    def __init__(self):
```

with:

```python
    ready = Signal(object)                    # image path: its row is in the store
    failed = Signal(object, str)              # image path, why
    passProgress = Signal(int, int)           # queue images walked, of how many
    passEnded = Signal(int, int, bool)        # inferred, failed, cancelled

    def __init__(self):
```

In `src/deeplabeling/ui/model.py`, replace:

```python
        self._store: PredictionStore | None = None
        self._predictor = None

    # -- asked from the GUI thread ----------------------------------------------------
```

with:

```python
        self._store: PredictionStore | None = None
        self._predictor = None
        self._known: dict[str, Stamp] | None = None    # the store's rows for this model, once a pass asks
        self._pass: collections.deque = collections.deque()
        self._pass_store: PredictionStore | None = None
        self._passing = self._pass_cancelled = False
        self._walked = self._total = self._inferred = self._failed = 0

    # -- asked from the GUI thread ----------------------------------------------------
```

In `src/deeplabeling/ui/model.py`, replace:

```python
        self._put(("unload",))

    def stop(self) -> None:
        """Stop after the job in hand: a load queued but not started is dropped."""
        self.want(None, [])
        with self._cond:
            self._control.clear()
            self._control.append(("stop",))
```

with:

```python
        self._put(("unload",))

    def start_pass(self, store: PredictionStore, items: list[tuple[str, Path]]) -> None:
        """Infer these (dataset-relative path, file) in order, those the store has no row
        for, after whatever the screen wants."""
        with self._cond:
            self._pass_store, self._pass = store, collections.deque(items)
            self._passing, self._pass_cancelled = True, False
            self._walked, self._total, self._inferred, self._failed = 0, len(items), 0, 0
            self._cond.notify()

    def cancel_pass(self) -> None:
        """Stop after the batch in hand; what it inferred is kept. passEnded says so."""
        with self._cond:
            if self._passing:
                self._pass.clear()
                self._pass_cancelled = True
                self._cond.notify()

    def stop(self) -> None:
        """Stop after the job in hand: a load queued but not started is dropped."""
        self.want(None, [])
        with self._cond:
            self._pass.clear()
            self._passing = False
            self._control.clear()
            self._control.append(("stop",))
```

In `src/deeplabeling/ui/model.py`, replace:

```python
        while True:
            with self._cond:
                while not self._control and not (self._screen and self._predictor is not None):
                    self._cond.wait()
                if self._control:
                    job, item, store = self._control.popleft(), None, None
                else:
                    job, item, store = None, self._screen.pop(0), self._store
            if job is not None:
                if job[0] == "stop":
                    self._close()
                    return
                if job[0] == "unload":
                    self._close()
                else:
```

with:

```python
        while True:
            with self._cond:
                while not self._control and not ((self._screen or self._passing) and self._predictor is not None):
                    self._cond.wait()
                if self._control:
                    job, item, store = self._control.popleft(), None, None
                elif self._screen:
                    job, item, store = None, self._screen.pop(0), self._store
                else:
                    job, item, store = ("pass",), None, None
            if job is not None:
                if job[0] == "stop":
                    self._close()
                    return
                if job[0] == "pass":
                    self._pass_step()
                elif job[0] == "unload":
                    self._close()
                else:
```

In `src/deeplabeling/ui/model.py`, replace:

```python

    def _close(self) -> None:
        if self._predictor is not None:
            self._predictor.close()
```

with:

```python

    def _close(self) -> None:
        self._known = None
        if self._predictor is not None:
            self._predictor.close()
```

In `src/deeplabeling/ui/model.py`, replace:

```python
            self.failed.emit(path, f"its predictions could not be stored: {e}")
            return
        self.ready.emit(path)


```

with:

```python
            self.failed.emit(path, f"its predictions could not be stored: {e}")
            return
        if self._known is not None:
            self._known[rel] = stamp                  # a pass under way skips it
        self.ready.emit(path)

    def _pass_step(self) -> None:
        """One batch of the pass: up to PASS_BATCH images the store has no row for, asked
        at once and written in one transaction, so a cancel keeps every batch done."""
        store, key = self._pass_store, self._predictor.key
        if self._known is None:
            self._known = store.inferred(key)
        todo = []
        while len(todo) < PASS_BATCH:
            with self._cond:
                if not self._pass:
                    break
                rel, path = self._pass.popleft()
            self._walked += 1
            try:
                stamp = image_stamp(path)
            except OSError as e:
                self._failed += 1
                self.failed.emit(path, f"it cannot be read: {e.strerror or e}")
                continue
            if self._known.get(rel) != stamp:
                todo.append((rel, path, stamp))
        if todo:
            try:
                answers = self._predictor.predict([path for _, path, _ in todo])
            except Exception as e:                    # whatever the model raises: the batch fails
                answers = [Failure(str(e))] * len(todo)
            rows = [(rel, stamp, found) for (rel, _, stamp), found in zip(todo, answers)
                    if not isinstance(found, Failure)]
            try:
                store.put_many(key, rows)
            except Exception as e:                    # the disk full, the store broken
                answers = [Failure(f"its predictions could not be stored: {e}")] * len(todo)
            for (rel, path, stamp), found in zip(todo, answers):
                if isinstance(found, Failure):
                    self._failed += 1
                    self.failed.emit(path, found.why)
                else:
                    self._inferred += 1
                    self._known[rel] = stamp
                    self.ready.emit(path)
        self.passProgress.emit(self._walked, self._total)
        with self._cond:
            if self._pass or not self._passing:
                return
            self._passing = False
            ended = (self._inferred, self._failed, self._pass_cancelled)
        self.passEnded.emit(*ended)


```

In `src/deeplabeling/ui/model.py`, replace:

```python
    ready = Signal(object)              # image path: predictions for it are in the store
    failed = Signal(object, str)        # image path, why

    def __init__(self, session, parent=None):
```

with:

```python
    ready = Signal(object)              # image path: predictions for it are in the store
    failed = Signal(object, str)        # image path, why
    progress = Signal()                 # the dataset pass moved on

    def __init__(self, session, parent=None):
```

In `src/deeplabeling/ui/model.py`, replace:

```python
        self.class_map: ClassMap | None = None
        self._failures: dict[Path, str] = {}
        self._worker: _Worker | None = None        # runs while a model is loaded or loading
        session.cursorChanged.connect(self.want_screen)
```

with:

```python
        self.class_map: ClassMap | None = None
        self._failures: dict[Path, str] = {}
        self._known: set[str] = set()               # images the store has a row for, by rel
        self.passing = False
        self.pass_walked = self.pass_total = 0
        self._worker: _Worker | None = None        # runs while a model is loaded or loading
        session.cursorChanged.connect(self.want_screen)
```

In `src/deeplabeling/ui/model.py`, replace:

```python
        worker.ready.connect(self._ready)
        worker.failed.connect(self._failed)
        worker.start()
        return worker
```

with:

```python
        worker.ready.connect(self._ready)
        worker.failed.connect(self._failed)
        worker.passProgress.connect(self._pass_progress)
        worker.passEnded.connect(self._pass_ended)
        worker.start()
        return worker
```

In `src/deeplabeling/ui/model.py`, replace:

```python
            return
        for signal, slot in ((worker.loaded, self._loaded), (worker.loadFailed, self._load_failed),
                             (worker.ready, self._ready), (worker.failed, self._failed)):
            signal.disconnect(slot)                   # a late answer is for a dataset now gone
        worker.stop()
```

with:

```python
            return
        for signal, slot in ((worker.loaded, self._loaded), (worker.loadFailed, self._load_failed),
                             (worker.ready, self._ready), (worker.failed, self._failed),
                             (worker.passProgress, self._pass_progress), (worker.passEnded, self._pass_ended)):
            signal.disconnect(slot)                   # a late answer is for a dataset now gone
        worker.stop()
```

In `src/deeplabeling/ui/model.py`, replace:

```python
    def _forget(self) -> None:
        self.state, self.path, self.key, self.names, self.error = "none", None, None, (), ""
        self.class_map, self._failures = None, {}
        self.changed.emit()

```

with:

```python
    def _forget(self) -> None:
        self.state, self.path, self.key, self.names, self.error = "none", None, None, (), ""
        self.class_map, self._failures, self._known = None, {}, set()
        self.passing = False
        self.changed.emit()

```

In `src/deeplabeling/ui/model.py`, replace:

```python
            self.class_map = load_class_map(ws.root_settings, self.names, ws.dataset.names)
            ws.opening_settings.set(MODEL_PATH, str(path))
        settings = self.session.settings
        recent = [str(path)] + [p for p in settings.get(RECENT_MODELS) if p != str(path)]
```

with:

```python
            self.class_map = load_class_map(ws.root_settings, self.names, ws.dataset.names)
            ws.opening_settings.set(MODEL_PATH, str(path))
            self._known = set(ws.predictions.inferred(key))
        settings = self.session.settings
        recent = [str(path)] + [p for p in settings.get(RECENT_MODELS) if p != str(path)]
```

In `src/deeplabeling/ui/model.py`, replace:

```python
        self._worker.want(ws.predictions, wanted)

    def _ready(self, path) -> None:
        self.ready.emit(path)

```

with:

```python
        self._worker.want(ws.predictions, wanted)

    # -- the dataset pass ---------------------------------------------------------------------

    def infer_queue(self) -> None:
        """Infer the queue's images, in queue order, that the store has no row for."""
        session, ws = self.session, self.session.workspace
        queue = session.queue
        if self.state != "ready" or ws is None or queue is None or not queue.complete or self.passing:
            return
        items = [(item.entry.rel, item.entry.path) for item in queue.items]
        self.passing, self.pass_walked, self.pass_total = True, 0, len(items)
        self._worker.start_pass(ws.predictions, items)
        self.changed.emit()

    def cancel_pass(self) -> None:
        if self.passing and self._worker is not None:
            self._worker.cancel_pass()

    def inferred_count(self) -> tuple[int, int] | None:
        """How many of the queue's images the store has a row for, of how many."""
        queue = self.session.queue
        if queue is None:
            return None
        return sum(1 for item in queue.items if item.entry.rel in self._known), len(queue.items)

    def _pass_progress(self, walked: int, total: int) -> None:
        self.pass_walked, self.pass_total = walked, total
        self.progress.emit()

    def _pass_ended(self, inferred: int, failed: int, cancelled: bool) -> None:
        self.passing = False
        images = f"{inferred:,} image" + ("" if inferred == 1 else "s")
        self.session.notice.emit("info", f"inferring stopped: {images} inferred, {failed:,} failed"
                                 if cancelled else f"inferred {images}; {failed:,} failed", None)
        self.changed.emit()

    def _ready(self, path) -> None:
        ws = self.session.workspace
        if ws is not None:
            self._known.add(ws.dataset.entry(path).rel)
        self.ready.emit(path)

```

In `src/deeplabeling/ui/state_bar.py`, replace:

```python
    if model.state == "failed":
        return f"Model: {name} · not loaded"
    return f"Model: {name} · {len(model.names)} classes · conf {model.conf:.2f}"


```

with:

```python
    if model.state == "failed":
        return f"Model: {name} · not loaded"
    text = f"Model: {name} · {len(model.names)} classes · conf {model.conf:.2f}"
    if model.passing:
        return text + f" · inferring {model.pass_walked:,} / {model.pass_total:,}"
    counted = model.inferred_count()
    return text if counted is None else text + f" · {counted[0]:,} / {counted[1]:,} inferred"


```

In `src/deeplabeling/ui/state_bar.py`, replace:

```python
            signal.connect(self.refresh)
        session.model.changed.connect(self.refresh)
        # A building queue grows every 0.2 s, and each refresh counts what is left across
        # the whole queue; while it builds, refresh at most every REFRESH_MS.
```

with:

```python
            signal.connect(self.refresh)
        session.model.changed.connect(self.refresh)
        session.model.progress.connect(self._refresh_model)
        session.model.ready.connect(self._refresh_model)
        # A building queue grows every 0.2 s, and each refresh counts what is left across
        # the whole queue; while it builds, refresh at most every REFRESH_MS.
```

In `src/deeplabeling/ui/state_bar.py`, replace:

```python
        if not self._soon.isActive():
            self._soon.start()

    def refresh(self) -> None:
```

with:

```python
        if not self._soon.isActive():
            self._soon.start()

    def _refresh_model(self, _=None) -> None:
        self.model.set_full_text(model_text(self._session.model))

    def refresh(self) -> None:
```

- [ ] **Step 4: Run the tests to see them pass, three times**

Run: `for i in 1 2 3; do /home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_pass.py tests/ui/test_model.py tests/ui/test_model_chip.py | tail -1; done`
Expected: three lines, each `30 passed`.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 678 passed.

```bash
git add src/deeplabeling/ui/model.py src/deeplabeling/ui/state_bar.py src/deeplabeling/ui/main_window.py tests/ui/test_pass.py tests/ui/test_model_chip.py
git commit -m "ui: infer this queue on the model's thread, behind the image on screen; the chip counts what is inferred" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The measurements, and the docs

**Files:**
- Create: `tools/measure_assist.py`
- Modify:
  - `docs/design/2026-10-05-model-assist.md` (the status, chunked undo, the measured targets);
  - `CLAUDE.md` (the status);
  - `.claude/skills/run-and-verify-ui/SKILL.md` (cancelling a long write in a test).

**Interfaces:**
- Consumes: everything above; `launch` from `deeplabeling.__main__`.
- Produces: `tools/measure_assist.py DATA.yaml WEIGHTS [--pass-seconds N]`. It prints one line for each target, and whether the ultralytics settings file is unchanged.

- [ ] **Step 1: Write the script**

Create `tools/measure_assist.py`:

```python
#!/usr/bin/env python3
"""Measure slice 2's performance targets with a real model on a real dataset, read-only
(docs/design/2026-10-05-model-assist.md#performance-targets).

App state -- the prediction store included -- goes to a temporary folder, deleted at the
end. Nothing in the dataset is written and no label is edited. Run it from the repository
root, so that `ultralytics` is the editable install
(docs/knowledge/environment.md#which-ultralytics-gets-imported).

  /home/sonnn/miniconda3/bin/python3 tools/measure_assist.py DATA.yaml WEIGHTS [--pass-seconds 60]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = Path.home() / ".config" / "Ultralytics" / "settings.json"


class Answers:
    """A prompter for an unattended run: open whatever is asked, stop on any error."""

    def confirm_taxonomy(self, *args):
        return True

    def error(self, title, text):
        raise SystemExit(f"{title}: {text}")

    def choose_yaml(self):
        return None


def wait(app, condition, timeout=120.0) -> float:
    """Seconds until `condition()` holds, processing Qt events meanwhile."""
    start = time.perf_counter()
    while not condition():
        app.processEvents()
        if time.perf_counter() - start > timeout:
            raise SystemExit("timed out")
        time.sleep(0.0005)
    return time.perf_counter() - start


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else "absent"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    ap.add_argument("weights", type=Path)
    ap.add_argument("--pass-seconds", type=float, default=60.0)
    args = ap.parse_args(argv)
    tmp = tempfile.TemporaryDirectory(prefix="measure-assist-")
    os.environ["DEEPLABELING_STATE_DIR"] = str(Path(tmp.name) / "state")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))
    print("ultralytics:", importlib.util.find_spec("ultralytics").origin)     # found, not imported
    settings_before = md5(SETTINGS)

    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch

    app = QApplication.instance() or QApplication(sys.argv[:1])
    rows = []
    window = launch([str(args.yaml)], Answers())
    window.resize(1440, 900)
    window.show()
    s, model = window.session, window.session.model
    wait(app, lambda: window.canvas.image_size is not None and s.queue is not None and s.queue.complete)

    t0 = time.perf_counter()
    model.load(args.weights)
    wait(app, lambda: model.state in ("ready", "failed"))
    if model.state == "failed":
        raise SystemExit(model.error)
    first = s.current().entry
    wait(app, lambda: model.predictions(first) is not None)
    rows.append(("loading the model, to the first image's predictions", time.perf_counter() - t0, "(none)"))

    def page() -> float:
        """Seconds to show the next image, prefetched: what the GUI thread does."""
        nxt = s.queue.items[s.queue.position() + 1].entry.path
        wait(app, lambda: s.images.get(nxt) is not None)
        t = time.perf_counter()
        s.move(1)
        return time.perf_counter() - t + wait(app, lambda: window._shown == nxt)

    alone = [page() for _ in range(10)]
    rows.append(("paging, no pass (worst of 10)", max(alone), "≤ 100 ms"))

    fresh, served = [], []
    for i in range(1, 11):
        item = s.queue.items[min(s.queue.position() + 200 * i, len(s.queue) - 1)]
        s.go_to(item.key)
        wait(app, lambda: window._shown == item.entry.path)
        fresh.append(wait(app, lambda: window.inspector.predictions_label.text() not in ("not inferred yet", "loading")))
        t = time.perf_counter()
        window._predictions_changed()                       # read from the store, matched, drawn
        served.append(time.perf_counter() - t)
    rows.append(("predictions not in the store, after the image shows (worst of 10)", max(fresh), "≤ 500 ms"))
    rows.append(("predictions in the store, read and drawn (worst of 10)", max(served), "≤ 50 ms"))

    store = s.workspace.predictions
    before = len(store.inferred(model.key))
    t = time.perf_counter()
    model.infer_queue()
    paging = []
    while time.perf_counter() - t < args.pass_seconds:
        end = time.perf_counter() + 0.5
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.001)
        paging.append(page())
    model.cancel_pass()
    wait(app, lambda: not model.passing)
    elapsed = time.perf_counter() - t
    rows_now = store.inferred(model.key)
    rate = (len(rows_now) - before) / elapsed
    rows.append((f"paging while a pass runs (worst of {len(paging)})", max(paging), "≤ 100 ms"))
    rows.append((f"a dataset pass, images/s over {elapsed:.0f} s", rate, "≥ 20"))

    t = time.perf_counter()
    store.inferred(model.key)
    rows.append((f"the store's rows read when a model loads ({len(rows_now):,} rows)", time.perf_counter() - t, "(none)"))
    files = [store.path, store.path.with_name(store.path.name + "-wal")]
    size = sum(f.stat().st_size for f in files if f.exists())
    rows.append(("the store, bytes per image", size / max(len(rows_now), 1), "≤ 2048"))
    window.close()

    for name, value, target in rows:
        if "images/s" in name or "bytes" in name:
            shown = f"{value:,.0f}"
        else:
            shown = f"{value * 1000:.0f} ms" if value < 1 else f"{value:.2f} s"
        print(f"{name:70s} {shown:>10s}   target {target}")
    print(f"median paging during the pass {statistics.median(paging) * 1000:.0f} ms; "
          f"median fresh predictions {statistics.median(fresh) * 1000:.0f} ms")
    print("ultralytics settings unchanged:", md5(SETTINGS) == settings_before)
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it once, from the repository root, read-only**

Run: `/home/sonnn/miniconda3/bin/python3 tools/measure_assist.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml /home/sonnn/Documents/ultralytics/runs/detect/backup/yolo26n_vehicle/weights/best.pt --pass-seconds 30`
Expected:
- `ultralytics: /home/sonnn/Documents/ultralytics/ultralytics/__init__.py`;
- a line for each target, each within it (2026-10-06: 2 ms, 99 ms, 9 ms, 141 images/s, 1,647 bytes);
- `ultralytics settings unchanged: True`;
- `git status` shows nothing new in the dataset or in `.deeplabeling/`.

A missed target is a finding: run the script twice more, then record what was measured.

- [ ] **Step 3: Record the measurements, and update the status and the skill**

The table below holds the 2026-10-06 figures. Where your run's figures differ, write yours, with your date: the table records what was measured.

In `CLAUDE.md`, replace:

````markdown

**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 (model assist) has its core and its on-screen UI built; the dataset pass and
the queue accept (plan 2c) are next. The design and the plans are in [docs/design/](docs/design/).

```sh
````

with:

````markdown

**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. The design and the plans are in [docs/design/](docs/design/).

```sh
````

In `docs/design/2026-10-05-model-assist.md`, replace:

```markdown
# DeepLabeling — slice 2: model assist

**Status:** approved 2026-10-05 · plans 2a (the core) and 2b (the UI on screen) implemented;
2c (the dataset pass and the queue accept) next
**Scope:** slice 2 of [the app foundation](2026-10-04-app-foundation.md#slices): load a
model, see its predictions beside the labels, accept them (one box, one image, or a whole
```

with:

```markdown
# DeepLabeling — slice 2: model assist

**Status:** approved 2026-10-05 · implemented: plans 2a (the core), 2b (the UI on screen) and
2c (the dataset pass and the queue accept)
**Scope:** slice 2 of [the app foundation](2026-10-04-app-foundation.md#slices): load a
model, see its predictions beside the labels, accept them (one box, one image, or a whole
```

In `docs/design/2026-10-05-model-assist.md`, replace:

```markdown
- **Undo and redo of a queue accept are written in chunks too**, behind the same dialog:
  45k files undone at once would freeze the window as long as writing them at once.
  `LabelStore.restore` and `History` gain a chunked form in plan 2c.
- An accept that skips unmapped predictions says how many it skipped.

```

with:

```markdown
- **Undo and redo of a queue accept are written in chunks too**, behind the same dialog:
  45k files undone at once would freeze the window as long as writing them at once.
  Every file is checked first, as slice 1 does, then written a chunk at a time. Stopped
  part-way, by a cancel or a failed write, what was written becomes an edit of its own and
  the rest stays in the history: both stay undoable, and nothing is lost.
- An accept that skips unmapped predictions says how many it skipped.

```

In `docs/design/2026-10-05-model-assist.md`, replace:

```markdown
measured value, not quietly dropped.

| Action | Target |
|---|---|
| predictions for the image on screen, already in the store | ≤ 50 ms |
| predictions for the image on screen, not in the store | ≤ 500 ms after it is shown |
| paging while a pass runs | ≤ 100 ms, as without one: the test of the in-app thread |
| a dataset pass | ≥ 20 images/s |
| the store | ≤ 2 KB per image (the legacy store: 209 MB for 201,301 rows, about 1 KB) |

## Testing
```

with:

````markdown
measured value, not quietly dropped.

| Action | Target | Measured 2026-10-06 |
|---|---|---|
| predictions for the image on screen, already in the store | ≤ 50 ms | 2 ms, read, matched and drawn, the worst of 10 |
| predictions for the image on screen, not in the store | ≤ 500 ms after it is shown | 99 ms, the worst of 10 (median 46 ms) |
| paging while a pass runs | ≤ 100 ms, as without one: the test of the in-app thread | 9 ms, the worst of 60 (3 ms without a pass) |
| a dataset pass | ≥ 20 images/s | 141 images/s over 30 s |
| the store | ≤ 2 KB per image (the legacy store: 209 MB for 201,301 rows, about 1 KB) | 1,647 bytes |

- With `runs/detect/backup/yolo26n_vehicle/weights/best.pt` on the GTX 1660 SUPER. Of
  three runs, the first had one page of 121 ms while a pass ran; the other two had none
  over 9 ms.
- Reproduce, read-only (app state, the store included, goes to a temporary folder):

```sh
/home/sonnn/miniconda3/bin/python3 tools/measure_assist.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml /home/sonnn/Documents/ultralytics/runs/detect/backup/yolo26n_vehicle/weights/best.pt --pass-seconds 30
```

## Testing
````

In `.claude/skills/run-and-verify-ui/SKILL.md`, replace:

```markdown
  process with `os._exit` (`src/deeplabeling/__main__.py::main`). Test it in a subprocess,
  by its exit code (`tests/ui/test_quit.py`).
```

with:

```markdown
  process with `os._exit` (`src/deeplabeling/__main__.py::main`). Test it in a subprocess,
  by its exit code (`tests/ui/test_quit.py`).
- **Cancel a long write from the fake, not by racing it.** A write behind a progress
  dialog runs a chunk per event-loop turn; by the time a test polls for a value part-way,
  the run may be over. Give `tests/fixtures.py::FakePrompter` a `cancel_at` (a value, or
  `{title: value}`), and its progress cancels exactly there.
```

- [ ] **Step 4: Check the docs, and run the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 678 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/measure_assist.py docs/design/2026-10-05-model-assist.md CLAUDE.md .claude/skills/run-and-verify-ui/SKILL.md
git commit -m "docs: slice 2 is built; its targets measured with the real model" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
