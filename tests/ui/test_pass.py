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


def test_loading_another_model_stops_the_pass(qtbot, session, gate, made, tmp_path):
    gate.clear()
    session.model.infer_queue()
    time.sleep(0.1)                                           # the first batch is in hand
    other = tmp_path / "other.pt"
    other.write_bytes(b"other")
    session.model.factory = lambda path: made.append(FakePredictor(path)) or made[-1]
    session.model.load(other)
    assert not session.model.passing
    gate.set()
    qtbot.waitUntil(lambda: session.model.state == "ready", timeout=5000)
    qtbot.wait(300)
    assert made[-1].asked == ["0001.jpg", "0002.jpg", "0003.jpg"]    # the screen's, nothing more


def test_a_model_that_fails_to_load_mid_pass_leaves_no_pass_behind(qtbot, session, gate, tmp_path):
    gate.clear()
    session.model.infer_queue()
    time.sleep(0.1)
    broken = tmp_path / "broken.pt"
    broken.write_bytes(b"x")
    session.model.load(broken)
    gate.set()
    qtbot.waitUntil(lambda: session.model.state == "failed", timeout=5000)
    assert not session.model.passing


def test_an_image_a_pass_could_not_store_is_no_longer_failed_once_a_later_pass_stores_it(qtbot, session,
                                                                                        monkeypatch):
    import sqlite3

    store, put_many = session.workspace.predictions, session.workspace.predictions.put_many

    def full(model, rows):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(store, "put_many", full)
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info"):
        session.model.infer_queue()
    entry = session.queue.items[5].entry                      # camB/0001
    assert "disk is full" in session.model.failure(entry)
    monkeypatch.setattr(store, "put_many", put_many)
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info"):
        session.model.infer_queue()
    assert session.model.failure(entry) is None and session.model.predictions(entry) == []


def test_a_pass_over_images_already_inferred_walks_them_a_few_at_a_time(qtbot, session, monkeypatch):
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info"):
        session.model.infer_queue()                         # everything inferred but ok.jpg
    monkeypatch.setattr(model_module, "PASS_WALK", 4)
    walked = []
    session.model.progress.connect(lambda: walked.append(session.model.pass_walked))
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info"):
        session.model.infer_queue()                         # a resumed pass: a walk, and ok.jpg again
    assert walked[:3] == [4, 8, 12] and walked[-1] == 15    # the thread free between, for the screen
