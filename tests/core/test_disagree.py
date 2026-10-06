"""Where the model and the labels disagree: the Label/Prediction IoU condition
(docs/design/2026-10-06-filters.md#labelprediction-iou, docs/knowledge/matching.md#the-iou-filter)."""

import pytest

from deeplabeling.core.classmap import ClassMap
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import PredictionStore, image_stamp
from deeplabeling.core.queue import (
    BuildContext,
    ImageFilter,
    ModelDisagrees,
    ModelSnapshot,
    Seen,
    condition_from_json,
)
from deeplabeling.core.store import LabelStore

KEY = "fake:best.pt"
MODEL = ("car", "person", "truck")          # car -> car (1), person -> person (0), truck: unmapped


def P(cls, box, conf):
    return Prediction(cls, box, conf)


ROWS = {
    "camA/images/0001.jpg": [P(1, (0.5, 0.5, 0.2, 0.3), 0.9)],      # sees the person; the car is unseen
    "camA/images/0002.jpg": [P(0, (0.8, 0.8, 0.1, 0.1), 0.95)],     # a car on a negative: unlabelled
    "camA/images/0003.jpg": [P(2, (0.5, 0.5, 0.1, 0.1), 0.9)],      # an unmapped truck: never unlabelled
    "camA/images/0004.JPG": [P(0, (0.8, 0.8, 0.1, 0.1), 0.3)],      # a weak car on nothing
    "camA/images/sub/0005.jpg": [],                                  # bus_m: the model cannot see it
    "camB/images/0001.jpg": [],                                      # bus_m, inferred, nothing found
    "camB/images/twin.jpg": [P(1, (0.5, 0.5, 0.1, 0.1), 0.97)],     # sees its person, above 0.9
    "weird/images/имя пробел.jpg": [P(2, (0.5, 0.5, 0.1, 0.1), 0.8)],   # an unmapped truck sees the person
}


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


@pytest.fixture
def cmap(dataset):
    return ClassMap.seeded(MODEL, dataset.names)


@pytest.fixture
def ctx(dataset, cmap, tmp_path):
    store = PredictionStore(tmp_path / "predictions.sqlite")
    for rel, preds in ROWS.items():
        store.put(KEY, rel, image_stamp(dataset.root / rel), preds)
    yield BuildContext(dataset, LabelStore(dataset), frozenset(), model=ModelSnapshot(KEY, store, cmap))
    store.close()


def keys(condition, ctx):
    batches = []
    assert ImageFilter(conditions=(condition,)).build(ctx, batches.append)
    return [item.key for batch in batches for item in batch]


def test_a_label_no_prediction_overlaps_is_unseen(ctx):
    assert keys(ModelDisagrees("unseen"), ctx) == ["camA/images/0001.jpg"]


def test_an_upper_bound_never_removes_a_prediction_from_matching(ctx):
    # twin's person is seen at 0.97; an upper bound of 0.9 must not make it unseen.
    assert keys(ModelDisagrees("unseen", conf=(0.25, 0.9)), ctx) == ["camA/images/0001.jpg"]


def test_a_mapped_prediction_no_label_overlaps_was_labelled_by_nobody(ctx):
    assert keys(ModelDisagrees("unlabelled"), ctx) == ["camA/images/0002.jpg", "camA/images/0004.JPG"]
    assert keys(ModelDisagrees("unlabelled", conf=(0.5, 1.0)), ctx) == ["camA/images/0002.jpg"]


def test_either_direction(ctx):
    assert keys(ModelDisagrees("either"), ctx) == [
        "camA/images/0001.jpg", "camA/images/0002.jpg", "camA/images/0004.JPG"]


def test_images_never_inferred_are_counted_and_those_inferred_empty_are_evaluated(ctx):
    keys(ModelDisagrees("unseen"), ctx)
    assert ctx.unsettled == {"not inferred": 7}


def test_without_a_model_nothing_matches_and_it_is_said(dataset):
    ctx = BuildContext(dataset, LabelStore(dataset), frozenset())
    assert keys(ModelDisagrees("unseen"), ctx) == [] and ctx.unsettled == {"no model": 15}


def test_the_highlights_are_the_unseen_labels_and_the_unlabelled_predictions(ctx, dataset, cmap):
    for rel, condition, lines, preds in (
            ("camA/images/0001.jpg", ModelDisagrees("unseen"), {1}, set()),
            ("camA/images/0002.jpg", ModelDisagrees("unlabelled"), set(), {0}),
            ("camA/images/0001.jpg", ModelDisagrees("unlabelled"), set(), set())):
        labels = ctx.labels(dataset.entry(dataset.root / rel))
        seen = Seen(predictions=ROWS[rel], class_map=cmap)
        assert condition.highlight(labels, dataset, seen) == lines
        assert condition.highlight_predictions(labels, dataset, seen) == preds
        assert condition.highlight(labels, dataset) == frozenset()          # no predictions known
    assert ImageFilter(conditions=(ModelDisagrees("unlabelled"),)).highlight_predictions(
        ctx.labels(dataset.entry(dataset.root / "camA/images/0002.jpg")), dataset,
        Seen(predictions=ROWS["camA/images/0002.jpg"], class_map=cmap)) == {0}


@pytest.mark.parametrize("condition, text", [
    (ModelDisagrees("unseen"), "labels the model does not see (IoU 0.50, conf ≥ 0.25)"),
    (ModelDisagrees("unlabelled", 0.6, (0.5, 0.9)), "predictions nobody labelled (IoU 0.60, conf 0.50–0.90)"),
    (ModelDisagrees("either"), "labels and predictions that disagree (IoU 0.50, conf 0.25–1.00)"),
])
def test_a_model_condition_reads_as_words_and_survives_its_json(condition, text, dataset):
    assert condition.describe(dataset) == text
    assert condition_from_json(condition.to_json()) == condition
    assert ImageFilter(conditions=(condition,)).needs_model


@pytest.mark.parametrize("kw, why", [
    (dict(direction="sideways"), "unknown direction 'sideways'"),
    (dict(match_iou=0.0), "matching IoU: must be above 0 and at most 1"),
    (dict(conf=(0.05, 1.0)), "confidence: the lower end cannot be below 0.1"),
    (dict(conf=(0.9, 0.5)), "confidence: 0.9 is above 0.5: put the lower end first"),
])
def test_an_unusable_model_condition_is_refused(kw, why):
    with pytest.raises(ValueError, match=why):
        ModelDisagrees(**kw)
