"""Findings as a queue source (docs/design/2026-10-06-find-bad.md#the-queue)."""

import pytest

from deeplabeling.core.classmap import ClassMap
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import LineRef
from deeplabeling.core.findings import Findings, FindSettings
from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import PredictionStore, image_stamp
from deeplabeling.core.queue import BuildContext, ImageFilter, ModelSnapshot, Queue, source_from_json
from deeplabeling.core.store import LabelStore

KEY = "fake:best.pt"
MODEL = ("car", "person", "bus", "truck")
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
EXPECTED = ["camA/images/sub/0005.jpg#0#wrong class", "camA/images/0001.jpg#1#wrong class",
            "camB/images/0001.jpg#0#not an object"]


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


@pytest.fixture
def store(dataset, tmp_path):
    s = PredictionStore(tmp_path / "predictions.sqlite")
    for rel, preds in ROWS.items():
        s.put(KEY, rel, image_stamp(dataset.root / rel), preds)
    yield s
    s.close()


@pytest.fixture
def make_ctx(dataset, store):
    cmap = ClassMap.seeded(MODEL, dataset.names).with_target(2, "bus_m")
    labels = LabelStore(dataset)
    return lambda **kw: BuildContext(dataset, labels, frozenset(), model=ModelSnapshot(KEY, store, cmap), **kw)


def built(source, ctx, **kw):
    batches = []
    assert source.build(ctx, batches.append, **kw)
    return [item for batch in batches for item in batch]


def test_findings_come_ordered_by_kind_then_score(make_ctx):
    ctx = make_ctx()
    items = built(Findings(), ctx)
    assert [item.key for item in items] == EXPECTED
    car = items[1]
    assert car.focus == LineRef(1, 1, CAR) and car.finding.kind == "wrong class" and car.finding.model_cls == 0
    assert ctx.unsettled == {"not inferred": 9}


def test_weakly_seen_findings_come_last_when_asked_for(make_ctx):
    items = built(Findings(settings=FindSettings(weak=True)), make_ctx())
    assert [item.key for item in items] == EXPECTED + ["weird/images/имя пробел.jpg#0#weakly seen"]


def test_a_dismissed_finding_is_left_out(make_ctx):
    dismissed = frozenset({("camA/images/0001.jpg", "1 0.250000 0.250000 0.100000 0.100000", "wrong class")})
    assert [item.key for item in built(Findings(), make_ctx(dismissed=dismissed))] == [EXPECTED[0], EXPECTED[2]]


def test_the_scope_chooses_the_images(make_ctx):
    ctx = make_ctx()
    assert built(Findings(scope=ImageFilter(splits=("val",))), ctx) == []
    assert ctx.unsettled == {"not inferred": 5}


def test_without_a_model_nothing_is_found_and_it_is_said(dataset):
    ctx = BuildContext(dataset, LabelStore(dataset), frozenset())
    assert built(Findings(), ctx) == [] and ctx.unsettled == {"no model": 15}


def test_the_scan_says_how_far_it_is(make_ctx):
    said = []
    built(Findings(), make_ctx(), progress=lambda n, total: said.append((n, total)))
    assert said[-1] == (15, 15)


def test_a_finding_queue_holds_its_items_in_their_order_and_rechecks_them(make_ctx, dataset, ds):
    ctx = make_ctx()
    queue = Queue(Findings())
    queue.extend(built(Findings(), ctx))
    assert [item.key for item in queue.items] == EXPECTED
    ds.lbl("camA/0001").write_text("0 0.500000 0.500000 0.200000 0.300000\n0 0.250000 0.250000 0.100000 0.100000\n")
    queue.recheck(dataset.entry(dataset.root / "camA/images/0001.jpg"), make_ctx())  # the car is a person now
    assert queue.stale == {EXPECTED[1]}


@pytest.mark.parametrize("source, text", [
    (Findings(), "findings: wrong class, not an object (conf ≥ 0.40)"),
    (Findings(ImageFilter(splits=("val",)), FindSettings(weak=True, floor=0.5)),
     "findings: wrong class, not an object, weakly seen (conf ≥ 0.50) of all images in val"),
])
def test_a_findings_queue_reads_as_words_and_survives_its_json(source, text, dataset):
    assert source.describe(dataset) == text and source.needs_model
    assert source_from_json(source.to_json()) == source
    assert source_from_json(ImageFilter(splits=("val",)).to_json()) == ImageFilter(splits=("val",))
