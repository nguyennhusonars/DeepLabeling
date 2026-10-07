"""The model's side: predictions, the model key, and the real predictor's edges.

The real predictor is exercised by the measurement script, never here: tests never
import ultralytics (docs/design/2026-10-05-model-assist.md#testing)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from deeplabeling.core import inference
from deeplabeling.core.inference import (FLOOR, MAX_BOXES, Failure, ModelError, Prediction,
                                         UltralyticsPredictor, model_key, predictions_from)

SRC = Path(__file__).resolve().parents[2] / "src"


class Tensor(list):
    def tolist(self):
        return list(self)


class Boxes:
    def __init__(self, xywhn, cls, conf):
        self.xywhn, self.cls, self.conf = Tensor(xywhn), Tensor(cls), Tensor(conf)


class Result:
    def __init__(self, *rows):
        self.boxes = Boxes([r[1] for r in rows], [r[0] for r in rows], [r[2] for r in rows])


def test_the_model_key_names_the_file_its_size_and_its_time(tmp_path):
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"x" * 10)
    first = model_key(weights)
    assert first.startswith("best.pt:10:")
    weights.write_bytes(b"y" * 11)                          # retrained in place
    assert model_key(weights) != first


def test_a_result_becomes_normalised_predictions_strongest_first():
    result = Result((2.0, [0.5, 0.5, 0.2, 0.3], 0.40004), (0.0, [0.25, 0.25, 0.1, 0.1], 0.87654))
    assert predictions_from(result) == [Prediction(0, (0.25, 0.25, 0.1, 0.1), 0.876),
                                        Prediction(2, (0.5, 0.5, 0.2, 0.3), 0.4)]


def test_a_confidence_is_stored_rounded_down_so_a_threshold_never_lets_in_a_weaker_one():
    [p] = predictions_from(Result((0.0, [0.5, 0.5, 0.1, 0.1], 0.2496)))
    assert p.conf == 0.249                                  # 0.250 would pass a 0.25 threshold


def test_a_result_is_cut_at_the_floor_and_capped():
    rows = [(0.0, [0.5, 0.5, 0.1, 0.1], 0.5)] * (MAX_BOXES + 5) + [(1.0, [0.5, 0.5, 0.1, 0.1], FLOOR / 2)]
    kept = predictions_from(Result(*rows))
    assert len(kept) == MAX_BOXES and all(p.conf >= FLOOR for p in kept)


def test_an_empty_result_is_an_empty_list_not_nothing():
    assert predictions_from(Result()) == []


def test_importing_the_core_does_not_import_ultralytics():
    code = ("import sys\nimport deeplabeling.core.inference\n"
            "print('ultralytics' in sys.modules, 'torch' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(SRC)})
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["False", "False"]


def test_a_file_that_is_no_model_is_refused_with_its_name(tmp_path, monkeypatch):
    class Loader:
        def __init__(self, path):
            raise RuntimeError("invalid load key, 'x'")

    monkeypatch.setitem(sys.modules, "ultralytics", type("M", (), {"YOLO": Loader}))
    weights = tmp_path / "broken.pt"
    weights.write_bytes(b"x")
    with pytest.raises(ModelError, match="broken.pt failed to load: invalid load key"):
        UltralyticsPredictor(weights)


def test_a_model_that_does_not_detect_is_refused(tmp_path, monkeypatch):
    class Classifier:
        task, names = "classify", {0: "helmet"}

        def __init__(self, path):
            pass

    monkeypatch.setitem(sys.modules, "ultralytics", type("M", (), {"YOLO": Classifier}))
    weights = tmp_path / "helmet.pt"
    weights.write_bytes(b"x")
    with pytest.raises(ModelError, match="helmet.pt is a classify model, not a detection model"):
        UltralyticsPredictor(weights)


class Detector:
    """A stand-in for ultralytics' YOLO: fails any batch of more than one image when told
    to, and the image "poison" alone."""

    task, names, fail_batches = "detect", {0: "car", 1: "bus"}, False

    def __init__(self, path):
        pass

    def predict(self, images, **kw):
        if (self.fail_batches and len(images) > 1) or "poison" in images:
            raise RuntimeError("CUDA out of memory")
        return [Result((1.0, [0.5, 0.5, 0.2, 0.2], 0.9)) for _ in images]


@pytest.fixture
def predictor(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "ultralytics", type("M", (), {"YOLO": Detector}))
    monkeypatch.setattr(inference, "_read", lambda path: None if "bad" in path.name else path.stem)
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"x")
    return UltralyticsPredictor(weights)


CAR = [Prediction(1, (0.5, 0.5, 0.2, 0.2), 0.9)]


def test_the_predictor_names_its_model_and_its_classes(predictor, tmp_path):
    assert predictor.names == ("car", "bus") and predictor.key == model_key(tmp_path / "best.pt")


def test_an_image_that_cannot_be_read_fails_alone(predictor, tmp_path):
    out = predictor.predict([tmp_path / "a.jpg", tmp_path / "bad.jpg", tmp_path / "b.jpg"])
    assert out[0] == CAR and out[2] == CAR
    assert out[1] == Failure("bad.jpg could not be read as an image")


def test_a_batch_the_model_fails_on_is_retried_image_by_image(predictor, tmp_path, monkeypatch):
    monkeypatch.setattr(Detector, "fail_batches", True)
    out = predictor.predict([tmp_path / "a.jpg", tmp_path / "poison.jpg", tmp_path / "b.jpg"])
    assert out[0] == CAR and out[2] == CAR
    assert out[1] == Failure("RuntimeError: CUDA out of memory")


def test_a_box_at_the_frame_edge_stays_inside_the_image_and_is_writable():
    from deeplabeling.core.edits import AddBox, materialize

    # a real best.pt box: rounded field by field, its left edge came out at -5e-7
    [pred] = predictions_from(Result((0.0, [0.042312, 0.29193, 0.084625, 0.240948], 0.9)))
    cx, cy, w, h = pred.box
    assert cx - w / 2 >= 0 and cx + w / 2 <= 1
    materialize(None, (AddBox(0, pred.box),), class_ok=lambda c: True)    # not refused


def test_a_closed_predictor_lets_go_of_its_model_and_its_decoders(predictor, tmp_path):
    predictor.close()
    assert predictor._model is None and predictor._decoder._shutdown
    with pytest.raises(ModelError, match="closed"):
        predictor.predict([tmp_path / "a.jpg"])
    predictor.close()                                       # twice is harmless


def test_a_weights_file_that_is_not_there_is_refused_before_ultralytics_sees_it(tmp_path):
    from deeplabeling.core.inference import ModelError, UltralyticsPredictor

    with pytest.raises(ModelError, match=r"^yolov8n\.pt is not there"):
        UltralyticsPredictor(tmp_path / "yolov8n.pt")       # an official asset name: never downloaded



def test_importing_the_ui_does_not_import_ultralytics():
    code = ("import sys\nimport deeplabeling.ui.main_window, deeplabeling.ui.model, deeplabeling.ui.stats_dialog\n"
            "print('ultralytics' in sys.modules, 'torch' in sys.modules, 'matplotlib' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(SRC), "QT_QPA_PLATFORM": "offscreen"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["False", "False", "False"]


def test_a_float32_confidence_keeps_its_three_decimals():
    import numpy as np

    [p] = predictions_from(Result((0.0, [0.5, 0.5, 0.1, 0.1], float(np.float32(0.7)))))
    assert p.conf == 0.7                                    # not 0.699: a 0.70 threshold keeps it, as ultralytics does
