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
    with pytest.raises(Refused, match="0001.txt changed since.*dropped from the history"):
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


def test_a_file_changed_between_its_check_and_its_write_drops_the_rest_and_says_so(editor, ds, accepted):
    undoing = editor.restoring(undo=True)
    undoing.check(4)                                        # every file as the accept left it
    undoing.write(1)
    ds.lbl("camA/0004").write_text("2 0.1 0.1 0.1 0.1\n")   # someone else, between check and write
    with pytest.raises(Refused, match="2 of 4 files were undone; the rest has been dropped from the history"):
        undoing.write(4)
    assert undoing.dropped
    assert editor.history.peek_undo() is None              # nothing left that undo would refuse
    assert editor.history.peek_redo().images == (ds.img(IMAGES[0]), ds.img(IMAGES[1]))    # what was undone
