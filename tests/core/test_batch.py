"""One edit across many images, written a chunk at a time
(docs/design/2026-10-05-model-assist.md#accepting)."""

import pytest

from deeplabeling.core import store as store_module
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, Intent, Refused
from deeplabeling.core.editor import Editor
from deeplabeling.core.history import History
from deeplabeling.core.review import ReviewMarks
from deeplabeling.core.store import LabelStore
from fixtures import CAMA_0001, assert_only_changed, read_exact

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


def adds(ds, names=IMAGES):
    return [Intent(ds.img(n), (AddBox(1, BOX),), "accept") for n in names]


def test_many_intents_are_one_edit_that_marks_nothing_and_undoes_as_one(editor, ds):
    before = ds.snapshot()
    edit = editor.apply_many(adds(ds), "accept 4 predictions on 4 images")
    assert len(edit.changes) == 4 and edit.description == "accept 4 predictions on 4 images"
    assert editor.history.depth == 1 and editor.review.count() == 0
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.500000 0.500000 0.200000 0.200000\n"
    editor.undo()
    assert_only_changed(before, ds.snapshot(), set())       # 0003 and 0004 had no file: gone again


def test_chunks_written_one_after_another_are_still_one_edit(editor, ds, rec):
    batch = editor.batch("accept")
    batch.apply(adds(ds, IMAGES[:2]))
    batch.apply(adds(ds, IMAGES[2:]))
    assert rec.history == 0 and len(rec.labels) == 2        # each chunk is shown as it lands
    edit = batch.finish()
    assert len(edit.changes) == 4 and editor.history.depth == 1 and rec.history == 1


def test_a_write_failing_partway_puts_back_every_file_already_written(editor, ds, rec, monkeypatch):
    before = ds.snapshot()
    batch = editor.batch("accept")
    batch.apply(adds(ds, IMAGES[:2]))
    real, calls = store_module.write_atomic, []

    def failing(path, data):
        calls.append(path)
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", failing)
    with pytest.raises(Refused, match="No space left on device"):
        batch.apply(adds(ds, IMAGES[2:]))
    monkeypatch.setattr(store_module, "write_atomic", real)
    assert_only_changed(before, ds.snapshot(), set())
    assert editor.history.depth == 0 and set(rec.labels[-1]) >= {ds.img(n) for n in IMAGES[:3]}
    with pytest.raises(RuntimeError):
        batch.apply(adds(ds, IMAGES[:1]))                   # a failed batch is spent


def test_an_image_written_twice_undoes_to_what_it_was_first(editor, ds):
    batch = editor.batch("accept")
    batch.apply(adds(ds, IMAGES[:1]))
    batch.apply([Intent(ds.img(IMAGES[0]), (AddBox(2, (0.2, 0.2, 0.1, 0.1)),), "accept")])
    edit = batch.finish()
    assert len(edit.changes) == 1
    editor.undo()
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_a_batch_that_changed_nothing_records_nothing(editor, ds, rec):
    batch = editor.batch("accept")
    batch.apply([])
    assert batch.finish() is None and editor.history.depth == 0 and rec.history == 0


def test_what_cannot_be_put_back_stays_recorded_so_undo_can_retry(editor, ds, monkeypatch):
    before = ds.snapshot()
    real, calls = store_module.write_atomic, []

    def full_from_the_third_write(path, data):
        calls.append(path)
        if len(calls) >= 3:
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", full_from_the_third_write)
    with pytest.raises(Refused, match="could not be put back"):
        editor.apply_many(adds(ds), "accept")               # 0001 and 0003 written, then full
    monkeypatch.setattr(store_module, "write_atomic", real)  # space freed
    assert editor.history.depth == 1
    editor.undo()
    assert_only_changed(before, ds.snapshot(), set())


def test_after_a_failed_batch_the_store_serves_the_files_as_they_are_again(editor, ds, monkeypatch):
    real, calls = store_module.write_atomic, []

    def fails_third(path, data):
        calls.append(path)
        if len(calls) == 3:
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", fails_third)
    with pytest.raises(Refused):
        editor.apply_many(adds(ds), "accept")
    assert editor.store.get(ds.img("camA/0001.jpg")).raw == CAMA_0001.encode()
    assert editor.store.get(ds.img("camA/0003.jpg")).raw is None
