"""What a slice 3 queue shows on the canvas: the boxes and the predictions that made an
image match (docs/design/2026-10-06-filters.md#the-canvas)."""

import pytest
from PySide6.QtCore import Qt

import deeplabeling.ui.model as model_module
from deeplabeling.core.inference import Prediction
from deeplabeling.core.queue import Boxes, ImageFilter, ModelDisagrees
from drive import start, vp
from fixtures import CAMA_0001, FakePredictor, read_exact

WEAK_CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.2)          # nobody labelled it; below 0.25


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor",
                        lambda path: FakePredictor(path, found={"0001.jpg": [WEAK_CAR]}))
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    w.session.model.load(weights)
    qtbot.waitUntil(lambda: w.session.model.predictions(w.session.current().entry) is not None, timeout=5000)
    yield w
    w.close()


def queue(qtbot, window, *conditions):
    window.session.set_queue(ImageFilter(conditions=conditions))
    qtbot.waitUntil(lambda: window.session.queue.complete and window._shown is not None, timeout=5000)


def test_a_size_in_pixels_highlights_its_boxes_on_screen(qtbot, window):
    queue(qtbot, window, Boxes((), w=(None, 7), unit="px"))             # camA/0001's car, 6.4 px
    assert window.session.current().key == "camA/images/0001.jpg"
    assert {v.index: v.highlighted for v in window.canvas._views} == {0: False, 1: True}


def test_a_prediction_nobody_labelled_is_emphasised_even_below_the_display_threshold(qtbot, window):
    assert window.canvas._predictions == []                    # 0.2 is below the threshold, 0.25
    queue(qtbot, window, ModelDisagrees("unlabelled", conf=(0.1, 1.0)))
    [view] = window.canvas._predictions
    assert view.emphasised and view.caption == "car 0.20"
    assert [c.text for c in window.canvas.prediction_caption_items()] == ["car 0.20"]


def test_an_emphasised_prediction_can_be_accepted_with_a_double_click(qtbot, window, ds):
    queue(qtbot, window, ModelDisagrees("unlabelled", conf=(0.1, 1.0)))
    qtbot.mouseDClick(window.canvas.viewport(), Qt.LeftButton, pos=vp(window.canvas, 51.2, 38.4))
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"



def test_the_queue_editor_offers_the_root_s_threshold_as_the_model_s_confidence(qtbot, window):
    window.session.model.set_conf(0.4)
    window.edit_queue()
    assert window.prompter.asked[-1][2] == 0.4
