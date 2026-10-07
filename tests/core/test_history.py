import pytest

from deeplabeling.core import store as store_module
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, DeleteLine, Intent, Refused, SetClass
from deeplabeling.core.editor import Editor
from deeplabeling.core.history import History
from deeplabeling.core.review import ReviewMarks
from deeplabeling.core.store import LabelStore
from fixtures import CAMA_0001, GAUNTLET, read_exact

BOX = (0.5, 0.5, 0.2, 0.2)


class Recorder:
    def __init__(self):
        self.labels = []
        self.history = 0

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


def add(ds, name="camA/0003.jpg"):
    return Intent(ds.img(name), (AddBox(0, BOX),), "draw a box")


def test_an_applied_edit_is_written_recorded_and_marks_the_image(editor, ds, rec):
    edit = editor.apply(add(ds))
    assert ds.lbl("camA/0003").is_file()
    assert editor.history.peek_undo() is edit and editor.history.depth == 1
    assert editor.review.is_marked("camA/images/0003.jpg")
    assert rec.labels == [(ds.img("camA/0003.jpg"),)] and rec.history == 1


def test_an_edit_that_changes_nothing_records_nothing(editor, ds, rec):
    img = ds.img("camA/0001.jpg")
    same = Intent(img, (SetClass(editor.store.get(img).ref(0), 0),), "same class")
    assert editor.apply(same) is None
    assert editor.history.depth == 0 and editor.review.count() == 0 and rec.labels == []


def test_a_refused_edit_records_nothing(editor, ds, rec):
    with pytest.raises(Refused):
        editor.apply(Intent(ds.img("camB/twin.jpg"), (AddBox(0, BOX),), "draw"))
    assert editor.history.depth == 0 and editor.review.count() == 0 and rec.labels == []


def test_undo_then_redo_is_byte_exact_on_the_gauntlet(editor, ds):
    img = ds.img("bad/ok.jpg")
    before = ds.snapshot()
    editor.apply(Intent(img, (DeleteLine(editor.store.get(img).ref(6)),), "delete"))
    after = ds.snapshot()
    editor.undo()
    assert ds.snapshot() == before and read_exact(ds.lbl("bad/ok")) == GAUNTLET
    editor.redo()
    assert ds.snapshot() == after


def test_undo_walks_back_across_images(editor, ds, rec):
    first = editor.apply(add(ds, "camA/0003.jpg"))
    second = editor.apply(add(ds, "camA/0004.JPG"))
    assert editor.history.peek_undo() is second
    assert editor.undo() is second and not ds.lbl("camA/0004").exists()
    assert editor.history.peek_undo() is first and editor.history.peek_redo() is second
    assert rec.labels[-1] == (ds.img("camA/0004.JPG"),)


def test_a_new_edit_clears_redo(editor, ds):
    editor.apply(add(ds))
    editor.undo()
    editor.apply(add(ds, "camA/0004.JPG"))
    assert not editor.history.can_redo and editor.redo() is None


def test_nothing_to_undo_or_redo(editor):
    assert editor.undo() is None and editor.redo() is None


def test_undo_after_an_outside_change_is_refused_and_dropped(editor, ds):
    first = editor.apply(add(ds, "camA/0004.JPG"))
    editor.apply(add(ds))
    ds.lbl("camA/0003").write_bytes(b"outside\n")
    with pytest.raises(Refused, match="dropped"):
        editor.undo()
    assert ds.lbl("camA/0003").read_bytes() == b"outside\n"
    assert editor.history.depth == 1 and editor.history.peek_undo() is first
    assert editor.undo() is first and not ds.lbl("camA/0004").exists()


def test_redo_after_an_outside_change_is_refused_and_dropped(editor, ds):
    editor.apply(add(ds))
    editor.undo()
    ds.lbl("camA/0003").write_bytes(b"outside\n")
    with pytest.raises(Refused, match="dropped"):
        editor.redo()
    assert not editor.history.can_redo
    assert ds.lbl("camA/0003").read_bytes() == b"outside\n"


def full_disk(path, data):
    raise OSError(28, "No space left on device")


def test_an_undo_that_cannot_write_keeps_the_edit_for_a_retry(editor, ds, monkeypatch):
    img = ds.img("camA/0001.jpg")
    snap = editor.store.get(img)
    editor.apply(Intent(img, tuple(DeleteLine(snap.ref(i)) for i, _ in snap.boxes), "delete both"))
    with monkeypatch.context() as m:
        m.setattr(store_module, "write_atomic", full_disk)
        with pytest.raises(Refused, match="— try again$"):
            editor.undo()
    assert editor.history.can_undo and ds.lbl("camA/0001").read_bytes() == b""
    editor.undo()
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_a_redo_that_cannot_write_keeps_the_edit_for_a_retry(editor, ds, monkeypatch):
    img = ds.img("camA/0001.jpg")
    snap = editor.store.get(img)
    editor.apply(Intent(img, (DeleteLine(snap.ref(0)),), "delete one"))
    editor.undo()
    with monkeypatch.context() as m:
        m.setattr(store_module, "write_atomic", full_disk)
        with pytest.raises(Refused, match="— try again$"):
            editor.redo()
    assert editor.history.can_redo and read_exact(ds.lbl("camA/0001")) == CAMA_0001
    editor.redo()
    assert len(editor.store.get(img).boxes) == 1


def test_the_history_drops_its_oldest_edits_past_its_budget(ds, tmp_path):
    dataset = Dataset.open(ds.yaml)
    store = LabelStore(dataset)
    history = History(store, cap_bytes=1)
    editor = Editor(store, history, ReviewMarks(tmp_path / "r.json", dataset.root))
    editor.apply(add(ds))
    newest = editor.apply(add(ds, "camA/0004.JPG"))
    assert history.depth == 1 and history.peek_undo() is newest


def test_undo_keeps_the_review_mark(editor, ds):
    editor.apply(add(ds))
    editor.undo()
    assert editor.review.is_marked("camA/images/0003.jpg")


def test_a_refused_undo_still_reports_the_history_change(editor, ds, rec):
    editor.apply(add(ds))
    ds.lbl("camA/0003").write_bytes(b"outside\n")
    count = rec.history
    with pytest.raises(Refused):
        editor.undo()
    assert rec.history == count + 1
