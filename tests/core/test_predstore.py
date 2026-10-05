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
    worker = threading.Thread(target=lambda: seen.append(store.get(MODEL, "a.jpg", stamp)))
    worker.start()
    worker.join()
    assert seen == [[CAR]]


def test_a_store_that_cannot_be_read_is_set_aside_and_started_again(tmp_path, image):
    (tmp_path / STORE_NAME).write_bytes(b"not a database, " * 200)
    store = PredictionStore(tmp_path / STORE_NAME)
    assert "predictions.sqlite could not be read" in store.warning
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
