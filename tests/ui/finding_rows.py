"""A session with a fake model whose rows are already in the store: what the Find Bad tests
judge (docs/design/2026-10-06-find-bad.md)."""

from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import image_stamp
from fixtures import FakePredictor

KEY = "fake:best.pt"
MODEL = ("car", "person", "bus", "truck")       # car -> car, person -> person, bus -> bus_m (set), truck unmapped
CAR, PERSON, BUS = (0.25, 0.25, 0.1, 0.1), (0.5, 0.5, 0.2, 0.3), (0.75, 0.75, 0.15, 0.15)


def P(cls, box, conf):
    return Prediction(cls, box, conf)


ROWS = {
    "camA/images/0001.jpg": [P(1, CAR, 0.8), P(1, PERSON, 0.9)],        # the car: a person, 0.8
    "camA/images/0002.jpg": [],                                          # a negative
    "camA/images/0003.jpg": [P(0, CAR, 0.9)],                            # no label file
    "camA/images/sub/0005.jpg": [P(0, BUS, 0.95)],                       # the bus_m: a car, 0.95
    "camB/images/0001.jpg": [],                                          # the bus_m: nothing there
    "weird/images/имя пробел.jpg": [P(1, (0.5, 0.5, 0.1, 0.1), 0.5)],    # the person, seen weakly
}
FOUND = ["camA/images/sub/0005.jpg#0#wrong class", "camA/images/0001.jpg#1#wrong class",
         "camB/images/0001.jpg#0#not an object"]


def put_rows(session, rows=ROWS):
    ws = session.workspace
    for rel, preds in rows.items():
        ws.predictions.put(KEY, rel, image_stamp(ws.dataset.root / rel), preds)


def factory(path):
    return FakePredictor(path, names=MODEL)


def load(qtbot, session, weights):
    """Rows first, then the model: the screen's requests find them stored."""
    put_rows(session)
    session.model.factory = factory
    session.model.load(weights)
    qtbot.waitUntil(lambda: session.model.state == "ready", timeout=5000)
    session.model.set_class_map(session.model.class_map.with_target(2, "bus_m"))
