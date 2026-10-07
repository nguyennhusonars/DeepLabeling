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
    menu(window)["📂 Load…"].trigger()
    qtbot.waitUntil(lambda: len(window.canvas._predictions) == 3, timeout=5000)


def captions(window):
    return [c.text for c in window.canvas.prediction_caption_items()]


def test_without_a_model_the_chip_invites_one(window):
    assert window.state_bar.model.full_text == "🧠 load a model"
    assert not menu(window)["⇄ Class map…"].isEnabled()


def test_loading_from_the_chip_names_the_model_and_draws_its_predictions(qtbot, window):
    load(qtbot, window)
    qtbot.waitUntil(lambda: window.state_bar.model.full_text
                    == "🧠 best.pt · ≥0.25 · 3/15 inferred")   # and its neighbours
    assert captions(window) == ["car 0.90", "human? 0.70"]


def test_while_it_loads_the_chip_says_so(qtbot, window, weights):
    gate = threading.Event()
    window.session.model.factory = lambda path: (gate.wait(5), fake(path))[1]
    menu(window)["📂 Load…"].trigger()
    assert window.state_bar.model.full_text == "🧠 best.pt · loading…"
    gate.set()
    qtbot.waitUntil(lambda: window.session.model.state == "ready")


def test_a_model_that_does_not_load_says_why(qtbot, window, prompter, tmp_path):
    prompter.weights = tmp_path / "broken.pt"
    prompter.weights.write_bytes(b"not a model")
    window.session.model.factory = FakePredictor
    menu(window)["📂 Load…"].trigger()
    qtbot.waitUntil(lambda: window.state_bar.model.full_text == "🧠 broken.pt · failed")
    assert "broken.pt could not be loaded: not a model" in window.notices.texts()


def test_recent_models_are_listed_newest_first_and_load_again(qtbot, window, prompter, weights, tmp_path):
    load(qtbot, window)
    other = tmp_path / "other.pt"
    other.write_bytes(b"other")
    prompter.weights = other
    menu(window)["📂 Load…"].trigger()
    qtbot.waitUntil(lambda: window.session.model.state == "ready" and window.session.model.path == other)
    texts = list(menu(window))
    first, second = texts.index(f"other.pt — {tmp_path}"), texts.index(f"best.pt — {weights.parent}")
    assert first < second
    menu(window)[f"best.pt — {weights.parent}"].trigger()
    qtbot.waitUntil(lambda: window.session.model.state == "ready" and window.session.model.path == weights)


def test_the_threshold_hides_weaker_predictions(qtbot, window, prompter):
    load(qtbot, window)
    prompter.threshold = 0.8
    menu(window)["⚖ Threshold…"].trigger()
    assert ("threshold", 0.25) in prompter.asked
    qtbot.waitUntil(lambda: window.state_bar.model.full_text
                    == "🧠 best.pt · ≥0.80 · 3/15 inferred")   # and its neighbours
    assert captions(window) == ["car 0.90"]         # the person's is faint: no caption


def test_the_class_map_redraws_at_once_and_a_accepts_what_it_maps(qtbot, window, prompter, ds):
    load(qtbot, window)
    prompter.class_map = {"human": "person"}
    menu(window)["⇄ Class map…"].trigger()
    assert ("class map", ("car", "truck", "human"), ("person", "car", "bus_m", "bus_l")) in prompter.asked
    assert captions(window) == ["car 0.90", "person 0.70"]
    qtbot.keyClick(window, Qt.Key_A)
    assert read_exact(ds.lbl("camA/0001")) == (CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"
                                              "0 0.100000 0.900000 0.100000 0.100000\n")


def test_the_model_its_threshold_and_its_map_survive_a_relaunch(qtbot, window, prompter, ds):
    load(qtbot, window)
    prompter.threshold, prompter.class_map = 0.5, {"human": "person"}
    menu(window)["⚖ Threshold…"].trigger()
    menu(window)["⇄ Class map…"].trigger()
    window.close()
    again = start(qtbot, [str(ds.yaml)], FakePrompter())
    qtbot.waitUntil(lambda: len(again.canvas._predictions) == 3, timeout=5000)
    qtbot.waitUntil(lambda: again.state_bar.model.full_text
                    == "🧠 best.pt · ≥0.50 · 3/15 inferred")   # and its neighbours
    assert captions(again) == ["car 0.90", "person 0.70"]
    again.close()


def test_without_a_dataset_only_loading_is_offered(qtbot, monkeypatch, prompter):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", fake)
    w = start(qtbot, [], prompter)
    actions = menu(w)
    assert actions["📂 Load…"].isEnabled()
    assert not actions["⚖ Threshold…"].isEnabled() and not actions["⇄ Class map…"].isEnabled()
    w.close()


def test_a_remembered_model_that_is_gone_is_not_loaded(qtbot, window, weights, ds):
    load(qtbot, window)
    window.close()
    weights.unlink()
    again = start(qtbot, [str(ds.yaml)], FakePrompter())
    assert again.session.model.state == "none"
    assert again.state_bar.model.full_text == "🧠 load a model"
    again.close()


def test_quitting_with_no_dataset_open_lets_the_model_go(qtbot, monkeypatch, prompter):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", fake)
    w = start(qtbot, [], prompter)
    menu(w)["📂 Load…"].trigger()
    qtbot.waitUntil(lambda: w.session.model.state == "ready", timeout=5000)
    worker = w.session.model._worker
    w.close()
    assert w.session.model.state == "none" and worker.isFinished()


def test_the_queue_accept_waits_for_a_model_and_runs_from_the_menu(qtbot, window, ds):
    assert not menu(window)["✚ Accept missing boxes…"].isEnabled()
    load(qtbot, window)
    with qtbot.waitSignal(window.session.status, timeout=5000,
                          check_params_cb=lambda text: text.startswith("accepted")) as said:
        menu(window)["✚ Accept missing boxes…"].trigger()
    assert said.args == ["accepted 1 box on 1 image"]
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"


def test_infer_this_queue_runs_from_the_menu_and_can_be_cancelled_there(qtbot, window, monkeypatch):
    assert not menu(window)["▶ Infer the queue"].isEnabled()
    load(qtbot, window)
    with qtbot.waitSignal(window.session.notice, timeout=5000,
                          check_params_cb=lambda level, text, image: level == "info") as said:
        menu(window)["▶ Infer the queue"].trigger()
    assert said.args[1] == "inferred 12 images; 0 failed"   # the screen had done the first three
    assert window.state_bar.model.full_text == "🧠 best.pt · ≥0.25 · 15/15 inferred"
    cancelled = []
    monkeypatch.setattr(window.session.model, "cancel_pass", lambda: cancelled.append(1))
    window.session.model.passing = True                      # as while a pass runs
    assert "▶ Infer the queue" not in menu(window)
    menu(window)["■ Stop inferring"].trigger()
    assert cancelled == [1]


def test_a_model_loaded_before_the_dataset_opens_is_remembered_and_counts_its_rows(qtbot, ds, weights):
    from deeplabeling.core.predstore import image_stamp
    from deeplabeling.ui.model import MODEL_PATH
    from fixtures import FakePrompter, open_session
    from deeplabeling.ui.session import Session

    first = open_session(qtbot, ds.yaml)                    # rows stored, no model remembered
    for entry in first.workspace.dataset.images:
        first.workspace.predictions.put("fake:best.pt", entry.rel, image_stamp(entry.path), [])
    first.close()
    s = Session(FakePrompter())
    s.model.factory = fake
    s.model.load(weights)                                   # no dataset open yet
    qtbot.waitUntil(lambda: s.model.state == "ready", timeout=5000)
    with qtbot.waitSignal(s.queueDone, timeout=5000):
        assert s.open(ds.yaml)
    assert s.workspace.opening_settings.get(MODEL_PATH) == str(weights)
    assert s.model.inferred_count() == (15, 15)
    s.close()


def test_a_recent_model_whose_file_is_gone_is_shown_but_not_offered(qtbot, window, weights, tmp_path):
    gone = tmp_path / "gone" / "yolov8n.pt"
    window.session.settings.set(model_module.RECENT_MODELS, [str(gone), str(weights)])
    actions = menu(window)
    assert not actions[f"yolov8n.pt — {gone.parent} (missing)"].isEnabled()
    assert actions[f"best.pt — {weights.parent}"].isEnabled()


def test_answers_queued_before_a_switch_are_dropped(qtbot, window, ds, tmp_path):
    model = window.session.model
    load(qtbot, window)
    notices = []
    window.session.notice.connect(lambda *args: notices.append(args))
    model._pass_ended(3, 0, False)                          # a pass that ended for another dataset
    model._ready(tmp_path / "elsewhere.jpg")                # an image of another dataset: no KeyError
    model.load(model.path)                                  # a model switch: loading again
    model._failed(ds.img("camA/0001.jpg"), "the old model failed")
    assert notices == [] and model._failures == {}
