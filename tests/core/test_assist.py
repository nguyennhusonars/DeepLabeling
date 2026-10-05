"""What an accept adds (docs/design/2026-10-05-model-assist.md#accepting)."""

import pytest

from deeplabeling.core.assist import Shown, accept_image, accept_one, plan_queue_accept, shown_predictions
from deeplabeling.core.classmap import ClassMap
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, materialize
from deeplabeling.core.inference import Prediction
from deeplabeling.core.store import LabelStore
from fixtures import CAMA_0001

MODEL = ("car", "truck", "human")                           # car → car, human: unmapped here
PERSON_BOX = (0.5, 0.5, 0.2, 0.3)                           # camA/0001 line 0 (person)


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)                            # person, car, bus_m, bus_l


@pytest.fixture
def store(dataset):
    return LabelStore(dataset)


@pytest.fixture
def cmap(dataset):
    return ClassMap.seeded(MODEL, dataset.names)            # car → car; truck, human unmapped


def p(cls, box, conf):
    return Prediction(cls, box, conf)


def test_a_prediction_a_label_overlaps_is_not_missing_whatever_its_class(store, cmap, dataset, ds):
    labels = store.get(ds.img("camA/0001.jpg"))
    shown = shown_predictions([p(0, (0.51, 0.5, 0.2, 0.3), 0.9), p(0, (0.8, 0.8, 0.1, 0.1), 0.8)],
                              labels, cmap, dataset, conf=0.25)
    assert [(s.cls, s.missing) for s in shown] == [(1, False), (1, True)]


def test_the_threshold_applies_before_anything_else(store, cmap, dataset, ds):
    labels = store.get(ds.img("camA/0003.jpg"))
    assert shown_predictions([p(0, (0.8, 0.8, 0.1, 0.1), 0.2)], labels, cmap, dataset, conf=0.25) == []


def test_of_overlapping_predictions_the_most_confident_speaks_for_the_place(store, cmap, dataset, ds):
    labels = store.get(ds.img("camA/0003.jpg"))
    car, truck = p(0, (0.5, 0.5, 0.2, 0.2), 0.8), p(1, (0.505, 0.5, 0.2, 0.2), 0.35)
    shown = shown_predictions([truck, car], labels, cmap, dataset, conf=0.25)
    assert [(s.pred, s.missing) for s in shown] == [(car, True), (truck, False)]


def test_a_stronger_unmapped_prediction_keeps_a_weaker_mapped_one_out(store, cmap, dataset, ds):
    labels = store.get(ds.img("camA/0003.jpg"))
    human, car = p(2, (0.5, 0.5, 0.2, 0.2), 0.9), p(0, (0.5, 0.5, 0.2, 0.2), 0.5)
    intent, unmapped = accept_image(ds.img("camA/0003.jpg"),
                                    shown_predictions([human, car], labels, cmap, dataset, conf=0.25))
    assert intent is None and unmapped == 1


def test_accepting_an_image_adds_its_missing_mapped_predictions_as_one_edit(store, cmap, dataset, ds):
    image = ds.img("camA/0001.jpg")
    labels = store.get(image)
    shown = shown_predictions([p(0, PERSON_BOX, 0.9), p(0, (0.8, 0.8, 0.1, 0.1), 0.8),
                               p(2, (0.1, 0.9, 0.1, 0.1), 0.7)], labels, cmap, dataset, conf=0.25)
    intent, unmapped = accept_image(image, shown)
    assert intent.ops == (AddBox(1, (0.8, 0.8, 0.1, 0.1)),) and unmapped == 1
    assert intent.description == "accept 1 prediction"
    after = materialize(labels.raw, intent.ops, class_ok=dataset.known).decode()
    assert after == CAMA_0001 + "1 0.800000 0.800000 0.100000 0.100000\n"


def test_accepting_one_takes_even_a_covered_prediction_but_never_an_unmapped_one(store, cmap, dataset, ds):
    image = ds.img("camA/0001.jpg")
    covered = Shown(p(0, PERSON_BOX, 0.9), 1, False)
    assert accept_one(image, covered).ops == (AddBox(1, PERSON_BOX),)
    assert accept_one(image, Shown(p(2, PERSON_BOX, 0.9), None, True)) is None


def test_a_queue_accept_is_planned_from_what_is_inferred(store, cmap, dataset, ds):
    entries = [dataset.entry(ds.img(rel)) for rel in ("camA/0001.jpg", "camA/0003.jpg", "camA/0004.JPG",
                                                      "camB/twin.jpg")]
    found = {"camA/images/0001.jpg": [p(0, PERSON_BOX, 0.9)],              # covered: nothing to add
             "camA/images/0003.jpg": [p(0, (0.5, 0.5, 0.2, 0.2), 0.8), p(2, (0.1, 0.1, 0.1, 0.1), 0.9)],
             "camB/images/twin.jpg": [p(0, (0.5, 0.5, 0.3, 0.3), 0.8)]}     # its label file is shared
    plan = plan_queue_accept(entries, store.get, lambda e: found.get(e.rel), cmap, dataset, conf=0.25)
    assert [i.image for i in plan.intents] == [ds.img("camA/0003.jpg")]
    assert (plan.boxes, plan.uninferred, plan.unmapped, plan.read_only) == (1, 1, 1, 1)


def test_a_queue_accept_plan_stops_when_cancelled(store, cmap, dataset, ds):
    entries = list(dataset.images)
    plan = plan_queue_accept(entries, store.get, lambda e: [], cmap, dataset, conf=0.25,
                             cancelled=lambda: True)
    assert plan is None
