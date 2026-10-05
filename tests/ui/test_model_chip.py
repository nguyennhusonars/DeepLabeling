"""The model chip and its menu (docs/design/2026-10-05-model-assist.md#the-model-chip)."""

import threading

import pytest
from PySide6.QtCore import Qt

import deeplabeling.ui.model as model_module
from deeplabeling.core.inference import Prediction
from drive import start
from fixtures import CAMA_0001, FakePredictor, FakePrompter, read_exact

MISSING_CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9)
ON_THE_PERSON = Prediction(0, (0.5, 0.5, 0.2, 0.3), 0.85)
HUMAN = Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)


def fake(path):
    return FakePredictor(path, found={"0001.jpg": [MISSING_CAR, ON_THE_PERSON, HUMAN]})


@pytest.fixture
def weights(tmp_path):
    path = tmp_path / "models" / "best.pt"
    path.parent.mkdir()
    path.write_bytes(b"weights")
    return path


@pytest.fixture
def prompter(weights):
    return FakePrompter(weights=weights)


@pytest.fixture
def window(qtbot, ds, prompter, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", fake)   # every launch path
    w = start(qtbot, [str(ds.yaml)], prompter)
    yield w
    w.close()


def menu(window) -> dict:
    m = window.state_bar.model.menu()
    m.aboutToShow.emit()
    return {a.text(): a for a in m.actions() if not a.isSeparator()}


def load(qtbot, window):
    menu(window)["Load a model…"].trigger()
    qtbot.waitUntil(lambda: len(window.canvas._predictions) == 3, timeout=5000)


def captions(window):
    return [c.text for c in window.canvas.prediction_caption_items()]


def test_without_a_model_the_chip_invites_one(window):
    assert window.state_bar.model.full_text == "Model: none · load one"
    assert not menu(window)["Class map…"].isEnabled()


def test_loading_from_the_chip_names_the_model_and_draws_its_predictions(qtbot, window):
    load(qtbot, window)
    assert window.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.25"
    assert captions(window) == ["car 0.90", "human? 0.70"]


def test_while_it_loads_the_chip_says_so(qtbot, window, weights):
    gate = threading.Event()
    window.session.model.factory = lambda path: (gate.wait(5), fake(path))[1]
    menu(window)["Load a model…"].trigger()
    assert window.state_bar.model.full_text == "Model: best.pt · loading…"
    gate.set()
    qtbot.waitUntil(lambda: window.session.model.state == "ready")


def test_a_model_that_does_not_load_says_why(qtbot, window, prompter, tmp_path):
    prompter.weights = tmp_path / "broken.pt"
    prompter.weights.write_bytes(b"not a model")
    window.session.model.factory = FakePredictor
    menu(window)["Load a model…"].trigger()
    qtbot.waitUntil(lambda: window.state_bar.model.full_text == "Model: broken.pt · not loaded")
    assert "broken.pt could not be loaded: not a model" in window.notices.texts()


def test_recent_models_are_listed_newest_first_and_load_again(qtbot, window, prompter, weights, tmp_path):
    load(qtbot, window)
    other = tmp_path / "other.pt"
    other.write_bytes(b"other")
    prompter.weights = other
    menu(window)["Load a model…"].trigger()
    qtbot.waitUntil(lambda: window.session.model.state == "ready" and window.session.model.path == other)
    texts = list(menu(window))
    first, second = texts.index(f"other.pt — {tmp_path}"), texts.index(f"best.pt — {weights.parent}")
    assert first < second
    menu(window)[f"best.pt — {weights.parent}"].trigger()
    qtbot.waitUntil(lambda: window.session.model.state == "ready" and window.session.model.path == weights)


def test_the_threshold_hides_weaker_predictions(qtbot, window, prompter):
    load(qtbot, window)
    prompter.threshold = 0.8
    menu(window)["Threshold…"].trigger()
    assert ("threshold", 0.25) in prompter.asked
    assert window.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.80"
    assert captions(window) == ["car 0.90"]         # the person's is faint: no caption


def test_the_class_map_redraws_at_once_and_a_accepts_what_it_maps(qtbot, window, prompter, ds):
    load(qtbot, window)
    prompter.class_map = {"human": "person"}
    menu(window)["Class map…"].trigger()
    assert ("class map", ("car", "truck", "human"), ("person", "car", "bus_m", "bus_l")) in prompter.asked
    assert captions(window) == ["car 0.90", "person 0.70"]
    qtbot.keyClick(window, Qt.Key_A)
    assert read_exact(ds.lbl("camA/0001")) == (CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"
                                              "0 0.100000 0.900000 0.100000 0.100000\n")


def test_the_model_its_threshold_and_its_map_survive_a_relaunch(qtbot, window, prompter, ds):
    load(qtbot, window)
    prompter.threshold, prompter.class_map = 0.5, {"human": "person"}
    menu(window)["Threshold…"].trigger()
    menu(window)["Class map…"].trigger()
    window.close()
    again = start(qtbot, [str(ds.yaml)], FakePrompter())
    qtbot.waitUntil(lambda: len(again.canvas._predictions) == 3, timeout=5000)
    assert again.state_bar.model.full_text == "Model: best.pt · 3 classes · conf 0.50"
    assert captions(again) == ["car 0.90", "person 0.70"]
    again.close()


def test_without_a_dataset_only_loading_is_offered(qtbot, monkeypatch, prompter):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", fake)
    w = start(qtbot, [], prompter)
    actions = menu(w)
    assert actions["Load a model…"].isEnabled()
    assert not actions["Threshold…"].isEnabled() and not actions["Class map…"].isEnabled()
    w.close()


def test_a_remembered_model_that_is_gone_is_not_loaded(qtbot, window, weights, ds):
    load(qtbot, window)
    window.close()
    weights.unlink()
    again = start(qtbot, [str(ds.yaml)], FakePrompter())
    assert again.session.model.state == "none"
    assert again.state_bar.model.full_text == "Model: none · load one"
    again.close()


def test_quitting_with_no_dataset_open_lets_the_model_go(qtbot, monkeypatch, prompter):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", fake)
    w = start(qtbot, [], prompter)
    menu(w)["Load a model…"].trigger()
    qtbot.waitUntil(lambda: w.session.model.state == "ready", timeout=5000)
    worker = w.session.model._worker
    w.close()
    assert w.session.model.state == "none" and worker.isFinished()
