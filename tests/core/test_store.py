import os
import threading

import pytest

from deeplabeling.core import store as store_module
from deeplabeling.core.atomic import write_atomic
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import (
    AddBox,
    CreateEmpty,
    DeleteLine,
    Edit,
    FileChange,
    Intent,
    Refused,
    SetClass,
)
from deeplabeling.core.store import LabelState, LabelStore
from fixtures import CAMA_0001, CRLF, GAUNTLET, assert_only_changed, make_image, read_exact

BOX = (0.5, 0.5, 0.2, 0.2)


@pytest.fixture
def store(ds):
    return LabelStore(Dataset.open(ds.yaml))


def intent(image, *ops):
    return Intent(image, ops, "test")


def test_an_existing_label_file(store, ds):
    snap = store.get(ds.img("camA/0001.jpg"))
    assert snap.state is LabelState.OK and snap.raw == CAMA_0001.encode()
    assert [i for i, _ in snap.boxes] == [0, 1]
    assert snap.editable and not snap.negative and snap.unparsed == 0


def test_an_empty_label_file_is_a_negative_sample(store, ds):
    snap = store.get(ds.img("camA/0002.jpg"))
    assert snap.state is LabelState.OK and snap.negative and snap.editable


def test_no_label_file_is_missing(store, ds):
    snap = store.get(ds.img("camA/0003.jpg"))
    assert snap.state is LabelState.MISSING and snap.raw is None
    assert snap.editable and not snap.negative


def test_twin_images_share_a_read_only_label_file(store, ds):
    for name in ("camB/twin.jpg", "camB/twin.png"):
        snap = store.get(ds.img(name))
        assert snap.state is LabelState.SHARED and not snap.editable
        assert len(snap.boxes) == 1 and "another image" in snap.error


def test_an_unreadable_label_file_is_an_error(store, ds):
    ds.lbl("camA/0003").mkdir()
    snap = store.get(ds.img("camA/0003.jpg"))
    assert snap.state is LabelState.ERROR and not snap.editable
    assert "cannot read" in snap.error


def test_an_unchanged_file_comes_from_the_cache(store, ds):
    img = ds.img("camA/0001.jpg")
    assert store.get(img) is store.get(img)


def test_an_outside_change_is_seen_and_reported(ds):
    seen = []
    store = LabelStore(Dataset.open(ds.yaml), on_reload=seen.append)
    img = ds.img("camA/0001.jpg")
    store.get(img)
    ds.lbl("camA/0001").write_bytes(b"3 0.5 0.5 0.1 0.1\n")
    assert store.get(img).raw == b"3 0.5 0.5 0.1 0.1\n"
    assert seen == [img]


def test_a_same_size_change_in_place_is_seen(store, ds):
    img, path = ds.img("camA/0001.jpg"), ds.lbl("camA/0001")
    store.get(img)
    st = os.stat(path)
    path.write_bytes(CAMA_0001.replace("1 0.25", "3 0.25").encode())
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert store.get(img).lines[1].cls_id == 3


def test_a_replaced_file_with_the_same_size_and_time_is_seen(store, ds):
    img, path = ds.img("camA/0001.jpg"), ds.lbl("camA/0001")
    store.get(img)
    st = os.stat(path)
    write_atomic(path, CAMA_0001.replace("1 0.25", "3 0.25").encode())
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert store.get(img).lines[1].cls_id == 3


def test_an_outside_deletion_is_seen_and_reported(ds):
    seen = []
    store = LabelStore(Dataset.open(ds.yaml), on_reload=seen.append)
    img = ds.img("camA/0001.jpg")
    store.get(img)
    ds.lbl("camA/0001").unlink()
    assert store.get(img).state is LabelState.MISSING
    assert seen == [img]


def test_adding_a_box_creates_the_file_and_nothing_else(store, ds):
    before = ds.snapshot()
    img = ds.img("camA/0003.jpg")
    edit = store.apply(intent(img, AddBox(1, BOX)))
    assert_only_changed(before, ds.snapshot(), {"camA/labels/0003.txt"})
    assert edit.changes == (
        FileChange(ds.lbl("camA/0003"), None, b"1 0.500000 0.500000 0.200000 0.200000\n"),)
    assert edit.images == (img,) and edit.description == "test"
    assert store.get(img).state is LabelState.OK


def test_a_missing_labels_folder_is_created(ds):
    make_image(ds.img("camA/fresh/0009.jpg"))
    store = LabelStore(Dataset.open(ds.yaml))
    store.apply(intent(ds.img("camA/fresh/0009.jpg"), AddBox(0, BOX)))
    assert ds.lbl("camA/fresh/0009").is_file()


def test_a_class_change_keeps_crlf_and_every_untouched_byte(store, ds):
    img = ds.img("crlf/c.jpg")
    store.apply(intent(img, SetClass(store.get(img).ref(0), 2)))
    assert read_exact(ds.lbl("crlf/c")) == "2" + CRLF[1:]


def test_a_shared_file_is_refused_and_nothing_is_written(store, ds):
    before = ds.snapshot()
    with pytest.raises(Refused, match="another image"):
        store.apply(intent(ds.img("camB/twin.jpg"), AddBox(0, BOX)))
    assert_only_changed(before, ds.snapshot(), set())


def test_an_unreadable_file_is_refused(store, ds):
    ds.lbl("camA/0003").mkdir()
    with pytest.raises(Refused, match="cannot read"):
        store.apply(intent(ds.img("camA/0003.jpg"), AddBox(0, BOX)))


def test_apply_refuses_a_box_that_changed_outside(store, ds):
    img = ds.img("camA/0001.jpg")
    ref = store.get(img).ref(1)
    ds.lbl("camA/0001").write_bytes(b"0 0.500000 0.500000 0.200000 0.300000\n")
    before = ds.snapshot()
    with pytest.raises(Refused):
        store.apply(intent(img, DeleteLine(ref)))
    assert_only_changed(before, ds.snapshot(), set())


def test_an_edit_that_changes_nothing_writes_nothing(store, ds):
    img, path = ds.img("camA/0001.jpg"), ds.lbl("camA/0001")
    mtime = os.stat(path).st_mtime_ns
    assert store.apply(intent(img, SetClass(store.get(img).ref(0), 0))) is None
    assert os.stat(path).st_mtime_ns == mtime


def test_a_failed_write_is_refused_and_leaves_the_file(store, ds, monkeypatch):
    img = ds.img("camA/0001.jpg")
    store.get(img)

    def full_disk(path, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(store_module, "write_atomic", full_disk)
    with pytest.raises(Refused, match="No space"):
        store.apply(intent(img, AddBox(0, BOX)))
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001
    assert store.get(img).raw == CAMA_0001.encode()


def test_writing_from_another_thread_is_an_error(store, ds):
    errors = []

    def write():
        try:
            store.apply(intent(ds.img("camA/0003.jpg"), AddBox(0, BOX)))
        except RuntimeError as e:
            errors.append(e)

    thread = threading.Thread(target=write)
    thread.start()
    thread.join()
    assert len(errors) == 1 and not ds.lbl("camA/0003").exists()


def test_reading_from_many_threads_agrees(ds):
    store = LabelStore(Dataset.open(ds.yaml), cache_bytes=1)   # forces real loads
    images = [e.path for e in store.dataset.images]
    expected = {img: store.get(img).raw for img in images}
    mismatches = []

    def read():
        for img in images * 20:
            if store.get(img).raw != expected[img]:
                mismatches.append(img)

    threads = [threading.Thread(target=read) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert mismatches == []


def test_undo_and_redo_are_byte_exact(store, ds):
    img, path = ds.img("bad/ok.jpg"), ds.lbl("bad/ok")
    edit = store.apply(intent(img, SetClass(store.get(img).ref(0), 2)))
    store.restore(edit, undo=True)
    assert read_exact(path) == GAUNTLET
    store.restore(edit, undo=False)
    assert read_exact(path) == "2" + GAUNTLET[1:]


def test_undoing_a_created_file_deletes_it(store, ds):
    img = ds.img("camA/0003.jpg")
    edit = store.apply(intent(img, AddBox(0, BOX)))
    store.restore(edit, undo=True)
    assert not ds.lbl("camA/0003").exists()
    assert store.get(img).state is LabelState.MISSING


def test_undoing_mark_negative_deletes_the_empty_file(store, ds):
    img = ds.img("camA/0003.jpg")
    edit = store.apply(intent(img, CreateEmpty()))
    assert ds.lbl("camA/0003").read_bytes() == b""
    store.restore(edit, undo=True)
    assert not ds.lbl("camA/0003").exists()


def test_restore_refuses_a_file_changed_since(store, ds):
    img, path = ds.img("camA/0001.jpg"), ds.lbl("camA/0001")
    edit = store.apply(intent(img, AddBox(0, BOX)))
    path.write_bytes(b"outside\n")
    with pytest.raises(Refused, match="changed since"):
        store.restore(edit, undo=True)
    assert path.read_bytes() == b"outside\n"


def test_restore_checks_every_file_before_writing_any(store, ds):
    a, b = ds.lbl("camA/0001"), ds.lbl("camB/0001")
    edit = Edit((FileChange(a, b"x\n", a.read_bytes()), FileChange(b, b"y\n", b"not there\n")),
                (ds.img("camA/0001.jpg"), ds.img("camB/0001.jpg")), "two files")
    before = ds.snapshot()
    with pytest.raises(Refused):
        store.restore(edit, undo=True)
    assert_only_changed(before, ds.snapshot(), set())


def test_the_cache_stays_within_its_budget(ds):
    store = LabelStore(Dataset.open(ds.yaml), cache_bytes=5000)
    for entry in store.dataset.images:
        store.get(entry.path)
    assert store.cached_bytes <= 5000
    assert store.cached_count < len(store.dataset.images)


def test_the_pinned_image_is_never_evicted(ds):
    store = LabelStore(Dataset.open(ds.yaml), cache_bytes=1)
    pinned = ds.img("camA/0001.jpg")
    store.pin(pinned)
    store.get(pinned)
    for entry in store.dataset.images:
        store.get(entry.path)
    assert store.is_cached(pinned)
