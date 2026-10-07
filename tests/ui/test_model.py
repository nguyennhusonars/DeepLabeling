"""The model for the session: loading, the image on screen first, the store first, and a
GUI that never waits (docs/design/2026-10-05-model-assist.md#the-inference-thread)."""

import sqlite3
import threading
import time

import pytest

from deeplabeling.core.inference import Prediction
from deeplabeling.ui.model import MODEL_PATH, PRED_CONF, RECENT_MODELS
from fixtures import FakePredictor, open_session

CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9)
HUMAN = Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)


@pytest.fixture
def made():
    return []


@pytest.fixture
def factory(made):
    """The fake predictor every load makes; made[-1] is the latest."""
    def make(path, **kw):
        predictor = FakePredictor(path, found={"0001.jpg": [CAR, HUMAN]}, **kw)
        made.append(predictor)
        return predictor
    return make


@pytest.fixture
def weights(tmp_path):
    path = tmp_path / "best.pt"
    path.write_bytes(b"weights")
    return path


def load(qtbot, session, weights, factory):
    session.model.factory = factory
    with qtbot.waitSignal(session.model.changed, timeout=5000,
                          check_params_cb=lambda: session.model.state == "ready"):
        session.model.load(weights)


def test_loading_a_model_names_it_and_remembers_it(qtbot, session, weights, factory):
    load(qtbot, session, weights, factory)
    model = session.model
    assert (model.state, model.key, model.names) == ("ready", "fake:best.pt", ("car", "truck", "human"))
    assert session.workspace.opening_settings.get(MODEL_PATH) == str(weights)
    assert session.settings.get(RECENT_MODELS)[0] == str(weights)


def test_a_file_that_does_not_load_says_why_and_leaves_no_model(qtbot, session, tmp_path, factory):
    session.model.factory = factory
    broken = tmp_path / "broken.pt"
    broken.write_bytes(b"x")
    with qtbot.waitSignal(session.notice, timeout=5000) as said:
        session.model.load(broken)
    assert said.args[1] == "broken.pt failed to load: not a model"
    assert session.model.state == "failed" and session.model.key is None


def test_the_image_on_screen_is_predicted_and_then_served_from_the_store(qtbot, session, weights, factory, made):
    load(qtbot, session, weights, factory)
    entry = session.current().entry                          # camA/0001
    qtbot.waitUntil(lambda: session.model.predictions(entry) is not None)
    assert session.model.predictions(entry) == [CAR, HUMAN]
    asked = made[-1].asked.count("0001.jpg")
    session.move(1)
    session.move(-1)
    qtbot.wait(100)
    assert made[-1].asked.count("0001.jpg") == asked == 1


def test_the_image_on_screen_goes_before_its_neighbours(qtbot, session, weights, factory, made):
    load(qtbot, session, weights, factory)
    qtbot.waitUntil(lambda: len(made[-1].asked) >= 3)
    assert made[-1].asked[0] == "0001.jpg"


def test_paging_fast_predicts_where_the_cursor_stops_first(qtbot, session, weights, factory, made):
    gate = threading.Event()
    load(qtbot, session, weights, lambda path: factory(path, gate=gate))
    for _ in range(6):
        session.move(1)                                      # the GUI never waits on the model
    stop = session.current().entry.path.name
    gate.set()
    qtbot.waitUntil(lambda: stop in made[-1].asked)
    assert made[-1].asked.index(stop) <= 1                   # at most the one already in hand first


def test_a_failed_prediction_is_said_once_and_not_retried(qtbot, session, weights, factory, made):
    load(qtbot, session, weights, lambda path: factory(path, fail={"0002.jpg"}))
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda *a: "0002.jpg" in a[1]):
        session.move(1)
    entry = session.current().entry
    assert "CUDA out of memory" in session.model.failure(entry)
    session.move(1)
    session.move(-1)
    qtbot.wait(100)
    assert made[-1].asked.count("0002.jpg") == 1


def test_shown_predictions_follow_the_threshold_and_the_class_map(qtbot, session, weights, factory):
    load(qtbot, session, weights, factory)
    entry = session.current().entry
    qtbot.waitUntil(lambda: session.model.shown(entry) is not None)
    assert [(s.pred, s.cls) for s in session.model.shown(entry)] == [(CAR, 1), (HUMAN, None)]
    session.model.set_conf(0.8)
    assert session.workspace.root_settings.get(PRED_CONF) == 0.8
    assert [s.pred for s in session.model.shown(entry)] == [CAR]
    with pytest.raises(ValueError):
        session.model.set_conf(0.05)                         # nothing below the floor is offered
    session.model.set_class_map(session.model.class_map.with_target(2, "person"))
    session.model.set_conf(0.25)
    assert [s.cls for s in session.model.shown(entry)] == [1, 0]


def test_closing_the_dataset_lets_the_model_go_and_reopening_loads_it_again(qtbot, session, weights,
                                                                             factory, made, ds):
    load(qtbot, session, weights, factory)
    first = made[-1]
    session.close()
    qtbot.waitUntil(lambda: first.closed)
    assert session.model.state == "none"
    with qtbot.waitSignal(session.model.changed, timeout=5000,
                          check_params_cb=lambda: session.model.state == "ready"):
        assert session.open(ds.yaml)
    assert made[-1] is not first and session.model.key == "fake:best.pt"


def test_shutting_down_waits_at_most_two_seconds_for_a_prediction_in_hand(qtbot, ds, weights, factory):
    gate = threading.Event()
    session = open_session(qtbot, ds.yaml)
    load(qtbot, session, weights, lambda path: factory(path, gate=gate))
    qtbot.wait(50)                                           # the image on screen is in hand
    started = time.monotonic()
    session.close()
    session.model.shutdown()
    assert time.monotonic() - started < 3
    gate.set()


def test_a_store_that_cannot_be_written_fails_that_image_and_the_model_goes_on(qtbot, session, weights, factory,
                                                                               monkeypatch):
    store, put = session.workspace.predictions, session.workspace.predictions.put

    def full(model, img, stamp, preds):
        if img.endswith("0001.jpg"):
            raise sqlite3.OperationalError("database or disk is full")
        put(model, img, stamp, preds)

    monkeypatch.setattr(store, "put", full)
    session.model.factory = factory
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda *a: "disk is full" in a[1]) as said:
        session.model.load(weights)
    assert said.args[1] == ("camA/images/0001.jpg: prediction failed — "
                            "predictions not stored: database or disk is full")
    session.move(1)                                          # the thread still answers
    qtbot.waitUntil(lambda: session.model.predictions(session.current().entry) == [], timeout=5000)
