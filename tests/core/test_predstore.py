"""The prediction store: what it serves, what counts as a miss, and what it survives
(docs/design/2026-10-05-model-assist.md#the-prediction-store)."""

import threading

import pytest

from deeplabeling.core.inference import FLOOR, Prediction
from deeplabeling.core.predstore import STORE_NAME, PredictionStore, image_stamp
from deeplabeling.core.workspace import Workspace

MODEL, OTHER = "best.pt:5396421:1787353306", "best.pt:5396421:1787353999"
CAR = Prediction(3, (0.25, 0.25, 0.1, 0.15), 0.96)
FAINT = Prediction(2, (0.5, 0.5, 0.2, 0.2), 0.15)


@pytest.fixture
def store(tmp_path):
    s = PredictionStore(tmp_path / STORE_NAME)
    yield s
    s.close()


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "a.jpg"
    path.write_bytes(b"pixels")
    return path


def test_a_row_is_served_while_the_image_is_unchanged(store, image):
    store.put(MODEL, "a.jpg", image_stamp(image), [CAR, FAINT])
    assert store.get(MODEL, "a.jpg", image_stamp(image)) == [CAR, FAINT]
    image.write_bytes(b"other pixels")                      # edited, or replaced, on disk
    assert store.get(MODEL, "a.jpg", image_stamp(image)) is None


def test_never_inferred_and_nothing_found_are_different_answers(store, image):
    stamp = image_stamp(image)
    assert store.get(MODEL, "a.jpg", stamp) is None
    store.put(MODEL, "a.jpg", stamp, [])
    assert store.get(MODEL, "a.jpg", stamp) == []


def test_another_model_is_a_miss(store, image):
    store.put(MODEL, "a.jpg", image_stamp(image), [CAR])
    assert store.get(OTHER, "a.jpg", image_stamp(image)) is None


def test_the_threshold_filters_on_read_and_nothing_below_the_floor_is_answered(store, image):
    stamp = image_stamp(image)
    store.put(MODEL, "a.jpg", stamp, [CAR, FAINT])
    assert store.get(MODEL, "a.jpg", stamp, conf=0.5) == [CAR]
    assert store.get(MODEL, "a.jpg", stamp, conf=FLOOR / 2) is None


def test_rows_survive_closing_and_a_batch_is_written_at_once(tmp_path, image):
    stamp = image_stamp(image)
    first = PredictionStore(tmp_path / STORE_NAME)
    first.put_many(MODEL, [("a.jpg", stamp, [CAR]), ("b.jpg", (1, 2), [])])
    first.close()
    again = PredictionStore(tmp_path / STORE_NAME)
    assert again.get(MODEL, "a.jpg", stamp) == [CAR]
    assert again.inferred(MODEL) == {"a.jpg": stamp, "b.jpg": (1, 2)}
    again.close()


def test_every_thread_reads_through_its_own_connection(store, image):
    stamp = image_stamp(image)
    store.put(MODEL, "a.jpg", stamp, [CAR])
    seen = []
    worker = threading.Thread(target=lambda: seen.append((store.get(MODEL, "a.jpg", stamp), store._connection())))
    worker.start()
    worker.join()
    assert seen[0][0] == [CAR] and seen[0][1] is not store._connection()     # its own, not a shared one


def test_a_store_that_cannot_be_read_is_set_aside_and_started_again(tmp_path, image):
    (tmp_path / STORE_NAME).write_bytes(b"not a database, " * 200)
    store = PredictionStore(tmp_path / STORE_NAME)
    assert "predictions.sqlite unreadable" in store.warning
    assert list(tmp_path.glob(f"{STORE_NAME}.unreadable-*"))
    store.put(MODEL, "a.jpg", image_stamp(image), [CAR])
    assert store.get(MODEL, "a.jpg", image_stamp(image)) == [CAR]
    store.close()


def test_the_workspace_keeps_one_store_per_root(ds):
    ws = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    try:
        assert ws.predictions.path == ws.directory / STORE_NAME
        ws.predictions.put(MODEL, "camA/images/0001.jpg", (1, 2), [CAR])
    finally:
        ws.close()
    again = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    try:
        assert again.predictions.get(MODEL, "camA/images/0001.jpg", (1, 2)) == [CAR]
    finally:
        again.close()


def test_a_store_that_can_neither_be_read_nor_moved_aside_refuses_as_an_os_error(tmp_path, monkeypatch):
    from deeplabeling.core import predstore

    (tmp_path / STORE_NAME).write_bytes(b"not a database, " * 200)
    monkeypatch.setattr(predstore, "set_aside", lambda path, e: ("predictions.sqlite could not be moved", False))
    with pytest.raises(OSError, match="predictions.sqlite could not be moved"):
        PredictionStore(tmp_path / STORE_NAME)


def test_a_store_that_is_locked_or_unwritable_is_not_set_aside(tmp_path, monkeypatch):
    import sqlite3

    from deeplabeling.core import predstore

    good = PredictionStore(tmp_path / STORE_NAME)
    good.close()

    def busy(*a, **kw):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(predstore.sqlite3, "connect", busy)
    with pytest.raises(OSError, match="database is locked"):
        PredictionStore(tmp_path / STORE_NAME)
    assert not list(tmp_path.glob(f"{STORE_NAME}.unreadable-*"))


def test_a_closed_store_answers_nothing_and_drops_late_writes(tmp_path, image):
    store = PredictionStore(tmp_path / STORE_NAME)
    store.put(MODEL, "a.jpg", image_stamp(image), [CAR])
    store.close()
    store.put(MODEL, "b.jpg", (1, 2), [CAR])                # an inference thread, after the close
    assert store.get(MODEL, "a.jpg", image_stamp(image)) is None and store.inferred(MODEL) == {}
    assert store._all == []                                  # no connection was opened again
    again = PredictionStore(tmp_path / STORE_NAME)
    assert again.inferred(MODEL) == {"a.jpg": image_stamp(image)}
    again.close()



def test_a_writer_and_a_reader_at_once_each_see_whole_rows(tmp_path, image):
    store, stamp = PredictionStore(tmp_path / STORE_NAME), image_stamp(image)
    done, wrong = threading.Event(), []

    def write():
        for i in range(200):
            store.put_many(MODEL, [(f"{i}.jpg", stamp, [CAR, FAINT])])
        done.set()

    def read():
        while not done.is_set():
            for i in range(200):
                got = store.get(MODEL, f"{i}.jpg", stamp, conf=FLOOR)
                if got is not None and got != [CAR, FAINT]:
                    wrong.append(got)

    threads = [threading.Thread(target=write), threading.Thread(target=read)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    store.close()
    assert not wrong


def test_a_store_of_another_version_is_set_aside_and_started_again(tmp_path, image):
    import sqlite3

    path = tmp_path / STORE_NAME
    old = sqlite3.connect(path)
    old.execute("PRAGMA user_version = 99")
    old.commit()
    old.close()
    store = PredictionStore(path)
    assert "of version 99" in store.warning and "kept as" in store.warning
    assert store.get(MODEL, "a.jpg", image_stamp(image)) is None
    store.close()
    again = sqlite3.connect(path)
    assert again.execute("PRAGMA user_version").fetchone()[0] == 1
    again.close()


def test_a_connection_opened_while_the_store_closes_is_not_kept(tmp_path, monkeypatch):
    import deeplabeling.core.predstore as module

    store = PredictionStore(tmp_path / STORE_NAME)
    real = module.sqlite3.connect

    def racing(*args, **kw):
        conn = real(*args, **kw)
        store.close()                                       # the dataset closes meanwhile
        return conn

    monkeypatch.setattr(module.sqlite3, "connect", racing)
    worker = threading.Thread(target=lambda: store.put(MODEL, "a.jpg", (1, 1), [CAR]))
    worker.start()
    worker.join()
    assert store._all == []


def test_a_read_only_store_still_opens_and_answers(tmp_path, image):
    path = tmp_path / STORE_NAME
    store = PredictionStore(path)
    store.put(MODEL, "a.jpg", image_stamp(image), [CAR])
    store.close()
    path.chmod(0o444)
    try:
        again = PredictionStore(path)
        assert again.get(MODEL, "a.jpg", image_stamp(image)) == [CAR]
        again.close()
    finally:
        path.chmod(0o644)
