"""Predictions in the window, and accepting them on screen
(docs/design/2026-10-05-model-assist.md#accepting)."""

import threading

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor

from deeplabeling.core.inference import Prediction
from deeplabeling.ui.settings_ui import SHOW_PREDICTIONS
from drive import start, vp
from fixtures import CAMA_0001, FakePredictor, read_exact

# camA/0001 holds a person (0.5, 0.5, 0.2, 0.3) and a car. The model's classes are car,
# truck, human: car maps to car; truck and human map to nothing here.
MISSING_CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9)
ON_THE_PERSON = Prediction(0, (0.5, 0.5, 0.2, 0.3), 0.85)      # a label covers it: faint
HUMAN = Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)                # unmapped
CAR_LINE = "1 0.800000 0.800000 0.100000 0.100000\n"


@pytest.fixture
def window(qtbot, ds, tmp_path):
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    w.session.model.factory = lambda path: FakePredictor(
        path, found={"0001.jpg": [MISSING_CAR, ON_THE_PERSON, HUMAN]})
    w.session.model.load(weights)
    qtbot.waitUntil(lambda: len(w.canvas._predictions) == 3, timeout=5000)
    yield w
    w.close()


def colours_at(window, x, y):
    image = window.canvas.viewport().grab().toImage()
    at = window.canvas.mapFromScene(QPointF(x, y))
    return [QColor(image.pixel(at.x() + dx, at.y() + dy)) for dx in range(-2, 3) for dy in range(-2, 3)]


def is_car_green(c):                                            # #3cb44b
    return c.green() > 150 and c.red() < 100 and c.blue() < 120


def test_predictions_appear_on_the_image_on_screen(window):
    # the missing car's left edge, x = 0.75 of 64 px, half way down it
    assert any(map(is_car_green, colours_at(window, 48, 38.4)))
    captions = [c.text for c in window.canvas.prediction_caption_items()]
    assert captions == ["car 0.90", "human? 0.70"]              # the faint one has none


def test_a_accepts_the_missing_mapped_predictions_and_says_what_it_skipped(qtbot, window, ds):
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_A)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + CAR_LINE
    assert said.args == ["accepted 1 prediction; 1 of a class the map leaves out was skipped"]
    assert window.session.workspace.review.is_marked("camA/images/0001.jpg")
    qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_double_clicking_a_prediction_accepts_that_one_even_when_covered(qtbot, window, ds):
    qtbot.mouseDClick(window.canvas.viewport(), Qt.LeftButton, pos=vp(window.canvas, 32, 24))
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.500000 0.500000 0.200000 0.300000\n"


def test_double_clicking_an_unmapped_prediction_says_so_and_adds_nothing(qtbot, window, ds):
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.mouseDClick(window.canvas.viewport(), Qt.LeftButton, pos=vp(window.canvas, 6.4, 43.2))
    assert said.args == ["“human” is not mapped to a class of this dataset: map it in the class map"]
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_p_hides_the_predictions_and_the_choice_persists(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_P)
    assert not any(map(is_car_green, colours_at(window, 48, 38.4)))
    assert window.session.settings.get(SHOW_PREDICTIONS) is False
    assert window.state_bar.layers.full_text == "Layers: labels, captions"


def test_with_the_labels_hidden_predictions_show_but_none_is_accepted(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_L)
    assert any(map(is_car_green, colours_at(window, 48, 38.4)))
    qtbot.keyClick(window, Qt.Key_A)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_predictions_arriving_later_are_drawn_when_they_come(qtbot, window):
    window.session.move(1)                                      # camA/0002: nothing found
    qtbot.waitUntil(lambda: window.session.model.shown(window.session.current().entry) == [])
    window.session.move(-1)
    qtbot.waitUntil(lambda: len(window.canvas._predictions) == 3)


def test_an_accept_redraws_once_and_what_it_added_turns_faint(qtbot, window, monkeypatch):
    redraws, redraw = [], window.canvas._redraw
    monkeypatch.setattr(window.canvas, "_redraw", lambda: (redraws.append(1), redraw()))
    qtbot.keyClick(window, Qt.Key_A)
    assert len(redraws) == 1
    assert [c.text for c in window.canvas.prediction_caption_items()] == ["human? 0.70"]
    assert [p.faint for p in window.canvas._predictions] == [True, True, False]


def test_without_a_model_a_says_so(qtbot, window):
    window.session.model.unload()
    assert window.canvas._predictions == []
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_A)
    assert said.args == ["no model is loaded"]


def test_before_the_model_has_looked_a_says_so(qtbot, window, tmp_path):
    gate = threading.Event()
    other = tmp_path / "other.pt"
    other.write_bytes(b"other weights")
    window.session.model.factory = lambda path: FakePredictor(path, gate=gate)
    window.session.model.load(other)
    qtbot.waitUntil(lambda: window.session.model.state == "ready")
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_A)
    gate.set()
    assert said.args == ["the model has not looked at this image yet"]
