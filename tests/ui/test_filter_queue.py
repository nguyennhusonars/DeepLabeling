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


UNLABELLED = ImageFilter(conditions=(ModelDisagrees("unlabelled"),))


def test_without_a_model_a_model_queue_is_empty_and_says_it_needs_one(qtbot, session, weights):
    with qtbot.waitSignal(session.notice) as said:
        session.set_queue(UNLABELLED)
    assert said.args[1] == "this queue needs a model: load one"
    assert len(session.queue) == 0 and session.progress_text() == " · needs a model"
    load(qtbot, session, weights, found={"0001.jpg": [CAR]})
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    assert session.queue.source == UNLABELLED


def test_while_the_model_loads_the_queue_waits_then_builds(qtbot, session, weights):
    import threading

    gate = threading.Event()
    session.model.factory = lambda path: (gate.wait(5), FakePredictor(path, found={"0001.jpg": [CAR]}))[1]
    session.model.load(weights)
    notices = []
    session.notice.connect(lambda level, text, image: notices.append(text))
    session.set_queue(UNLABELLED)
    assert session.progress_text() == " · waiting for the model" and notices == []
    gate.set()
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    assert len(session.queue) == 0 and session.progress_text() == " · 15 not inferred"


def test_inferring_a_model_queue_infers_what_it_left_out_and_each_joins_as_it_comes(qtbot, session, weights):
    load(qtbot, session, weights, found={"0001.jpg": [CAR]})
    built(qtbot, session, UNLABELLED)
    with qtbot.waitSignal(session.notice, timeout=5000, check_params_cb=lambda level, text, image: level == "info"):
        session.model.infer_queue()
    assert [item.key for item in session.queue.items] == ["camA/images/0001.jpg", "camB/images/0001.jpg"]
    assert session.progress_text() == ""


def test_a_model_switch_or_a_class_map_change_rebuilds_but_a_threshold_does_not(qtbot, session, weights, tmp_path):
    load(qtbot, session, weights)
    built(qtbot, session, UNLABELLED)
    first = session.queue
    session.model.set_conf(0.5)
    assert session.queue is first
    session.model.set_class_map(session.model.class_map.with_target(0, None))
    assert session.queue is not first
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    second = session.queue
    other = tmp_path / "other.pt"
    other.write_bytes(b"other")
    session.model.load(other)
    qtbot.waitUntil(lambda: session.model.state == "ready" and session.queue is not second
                    and session.queue.complete, timeout=5000)


def test_an_image_left_out_joins_when_its_predictions_arrive(qtbot, session, weights):
    from deeplabeling.ui.queue_panel import QueuePanel

    load(qtbot, session, weights, found={"0001.jpg": [CAR]})
    qtbot.waitUntil(lambda: all(session.model.predictions(session.queue.items[i].entry) is not None
                                for i in range(3)), timeout=5000)
    panel = QueuePanel(session)
    qtbot.addWidget(panel)
    assert built(qtbot, session, UNLABELLED) == ["camA/images/0001.jpg"]
    ws = session.workspace
    for rel, preds in (("camB/images/0001.jpg", []), ("camA/images/0004.JPG", [CAR])):
        path = ws.dataset.root / rel
        ws.predictions.put(session.model.key, rel, image_stamp(path), preds)
        with qtbot.waitSignal(session.model.ready):
            session.model.ready.emit(path)                   # as the model's thread reports it
    assert [item.key for item in session.queue.items] == ["camA/images/0001.jpg", "camA/images/0004.JPG"]
    assert panel.model.rowCount() == 2 and session.progress_text() == " · 10 not inferred"


def test_a_model_queue_waits_for_the_remembered_model_after_a_relaunch(qtbot, ds, weights, monkeypatch):
    import deeplabeling.ui.model as model_module
    from drive import start

    monkeypatch.setattr(model_module, "UltralyticsPredictor",
                        lambda path: FakePredictor(path, found={"0001.jpg": [CAR]}))
    window = start(qtbot, [str(ds.yaml)])
    window.session.model.load(weights)
    qtbot.waitUntil(lambda: window.session.model.state == "ready", timeout=5000)
    window.session.set_queue(UNLABELLED)
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert again.session.queue.source == UNLABELLED
    qtbot.waitUntil(lambda: again.session.queue.complete and len(again.session.queue) == 1, timeout=5000)
    again.close()


def test_a_model_queue_says_it_waits_on_the_chip_the_panel_and_the_canvas(qtbot, ds, weights, monkeypatch):
    import threading

    import deeplabeling.ui.model as model_module
    from drive import start

    window = start(qtbot, [str(ds.yaml)])
    window.session.set_queue(UNLABELLED)                       # no model at all
    assert window.state_bar.queue.full_text.endswith(" · needs a model")
    assert window.queue_panel.title.text() == "Queue · 0 · needs a model"
    assert window.canvas.message == "This queue needs a model: load one."
    gate = threading.Event()
    window.session.model.factory = lambda path: (gate.wait(5), FakePredictor(path))[1]
    window.session.model.load(weights)                         # loading: now it waits
    assert window.state_bar.queue.full_text.endswith(" · waiting for the model")
    assert window.queue_panel.title.text() == "Queue · 0 · waiting for the model"
    assert window.canvas.message == "Waiting for the model…"
    gate.set()
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    qtbot.waitUntil(lambda: window.canvas.message == "No images in this queue.", timeout=5000)
    window.close()


def test_the_first_image_to_join_an_empty_queue_is_shown(qtbot, ds, weights):
    from drive import start

    window = start(qtbot, [str(ds.yaml)])
    session = window.session
    load(qtbot, session, weights)
    built(qtbot, session, UNLABELLED)
    assert len(session.queue) == 0
    path = ds.root / "camA/images/0004.JPG"
    session.workspace.predictions.put(session.model.key, "camA/images/0004.JPG", image_stamp(path), [CAR])
    session.model.ready.emit(path)
    assert session.current() is not None and session.current().key == "camA/images/0004.JPG"
    qtbot.waitUntil(lambda: window._shown == path, timeout=5000)
    window.close()


def test_on_a_model_queue_the_model_chip_counts_what_the_queue_left_out(qtbot, session, weights):
    from deeplabeling.ui.state_bar import model_text

    load(qtbot, session, weights, found={"0001.jpg": [CAR]})
    qtbot.waitUntil(lambda: all(session.model.predictions(session.queue.items[i].entry) is not None
                                for i in range(3)), timeout=5000)
    built(qtbot, session, UNLABELLED)
    assert model_text(session.model).endswith(" · 1/13 inferred")      # 1 in the queue, 12 left out


def test_closing_the_dataset_leaves_its_model_queue_alone(qtbot, ds, weights):
    s = open_session(qtbot, ds.yaml)
    load(qtbot, s, weights)
    built(qtbot, s, UNLABELLED)
    resets, notices = [], []
    s.queueReset.connect(lambda: resets.append(1))
    s.notice.connect(lambda level, text, image: notices.append(text))
    s.close()
    assert resets == [] and notices == []


def test_a_failed_build_keeps_what_it_left_out(qtbot, session, weights):
    from dataclasses import dataclass
    from typing import ClassVar

    from deeplabeling.core.queue import Condition

    @dataclass(frozen=True)
    class FailsLate(Condition):
        """Passes the first nine images, then meets an unreadable disk."""

        kind: ClassVar[str] = "fails-late"
        needs_labels: ClassVar[bool] = False

        def test(self, entry, ctx):
            if entry.order >= 9:
                raise OSError("the disk went away")
            return True

        def describe(self, dataset):
            return "fails late"

        def to_json(self):
            return {"kind": self.kind}

    load(qtbot, session, weights)
    qtbot.waitUntil(lambda: all(session.model.predictions(session.queue.items[i].entry) is not None
                                for i in range(3)), timeout=5000)
    session.set_queue(ImageFilter(conditions=(ModelDisagrees("unlabelled"), FailsLate())))
    qtbot.waitUntil(lambda: session.queue.failed is not None, timeout=5000)
    assert len(session.queue.left_out["not inferred"]) == 6           # images 3 to 8
