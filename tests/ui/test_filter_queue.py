"""Slice 3's conditions in the session: what a build is given, what it could not settle,
waiting for the model, and keeping a model queue current
(docs/design/2026-10-06-filters.md#building-and-keeping-current)."""

import pytest

from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import image_stamp
from deeplabeling.core.queue import Boxes, ImageFilter, ModelDisagrees
from fixtures import FakePredictor, open_session

CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.95)           # the model's car: nobody labelled it


@pytest.fixture
def weights(tmp_path):
    path = tmp_path / "best.pt"
    path.write_bytes(b"weights")
    return path


def load(qtbot, session, weights, **kw):
    session.model.factory = lambda path: FakePredictor(path, **kw)
    session.model.load(weights)
    qtbot.waitUntil(lambda: session.model.state == "ready", timeout=5000)


def built(qtbot, session, source):
    session.set_queue(source)
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    return [item.key for item in session.queue.items]


def test_a_build_is_given_the_dataset_s_size_cache(session):
    assert session.context().sizes is session.workspace.sizes


def test_a_build_is_given_the_model_once_it_is_ready(qtbot, session, weights):
    assert session.context().model is None
    load(qtbot, session, weights)
    model = session.context().model
    assert (model.key, model.store, model.class_map) == (
        "fake:best.pt", session.workspace.predictions, session.model.class_map)


def test_the_queue_says_what_its_build_could_not_settle(qtbot, session):
    built(qtbot, session, ImageFilter(conditions=(Boxes((), w=(0, None), unit="px"),)))
    assert session.queue.left_out == {"could not be sized": {"bad/images/corrupt.jpg"}}
    assert session.progress_text() == " · 1 image could not be sized"


def test_the_queue_counts_the_images_never_inferred(qtbot, session, weights):
    load(qtbot, session, weights, found={"0001.jpg": [CAR]})
    qtbot.waitUntil(lambda: all(session.model.predictions(session.queue.items[i].entry) is not None
                                for i in range(3)), timeout=5000)      # the screen's three
    keys = built(qtbot, session, ImageFilter(conditions=(ModelDisagrees("unlabelled"),)))
    assert keys == ["camA/images/0001.jpg"]
    assert session.progress_text() == " · 12 not inferred"
