"""Find Bad's judgement of one image's labels (docs/design/2026-10-06-find-bad.md#findings,
docs/knowledge/matching.md)."""

import pytest
import yaml

from deeplabeling.core.classmap import ClassMap
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.findings import FindSettings, agrees, judge
from deeplabeling.core.inference import Prediction
from deeplabeling.core.store import LabelStore

MODEL = ("car", "person", "bus", "truck")   # car -> car, person -> person, bus -> bus_m (set), truck: unmapped
CAR, PERSON = (0.25, 0.25, 0.1, 0.1), (0.5, 0.5, 0.2, 0.3)     # camA/0001: line 1 a car, line 0 a person


def P(cls, box, conf):
    return Prediction(cls, box, conf)


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)                    # person, car, bus_m, bus_l; groups: bus = bus_m + bus_l


@pytest.fixture
def cmap(dataset):
    return ClassMap.seeded(MODEL, dataset.names).with_target(2, "bus_m")


@pytest.fixture
def labels(dataset):
    store = LabelStore(dataset)
    return lambda rel: store.get(dataset.root / rel)


def kinds(found):
    return [(f.line, f.kind, round(f.score, 3)) for f in found]


def test_a_confident_prediction_of_another_class_makes_a_wrong_class(labels, dataset, cmap):
    found = judge(labels("camA/images/0001.jpg"), [P(1, CAR, 0.8), P(1, PERSON, 0.9)], cmap, dataset, FindSettings())
    assert kinds(found) == [(1, "wrong class", 0.8)]
    [f] = found
    assert (f.model_cls, f.model_box, f.model_conf, f.label_cls) == (0, CAR, 0.8, 1)
    assert f.text == "1 0.250000 0.250000 0.100000 0.100000"


def test_the_most_confident_candidate_decides_not_the_best_overlap(labels, dataset, cmap):
    near = (0.26, 0.25, 0.1, 0.1)                                # IoU 0.82 with the car
    preds = [P(0, CAR, 0.5), P(1, near, 0.9), P(1, PERSON, 0.9)]
    assert kinds(judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings())) == [(1, "wrong class", 0.9)]


def test_an_unmapped_deciding_prediction_is_inconclusive(labels, dataset, cmap):
    preds = [P(3, CAR, 0.9), P(1, CAR, 0.5), P(1, PERSON, 0.9)]  # a truck decides; the person may not overrule it
    assert judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings()) == []


def test_a_ceiling_reports_less_but_never_removes_a_prediction_from_matching(labels, dataset, cmap):
    preds = [P(1, CAR, 0.8), P(1, PERSON, 0.9)]
    assert judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings(ceiling=0.7)) == []


def test_a_label_nothing_overlaps_is_not_an_object_with_its_nearest_box_from_0_1(labels, dataset, cmap):
    far = (0.33, 0.25, 0.1, 0.1)                                 # IoU 0.11 with the car
    found = judge(labels("camA/images/0001.jpg"), [P(1, PERSON, 0.9), P(0, far, 0.9)], cmap, dataset, FindSettings())
    assert kinds(found) == [(1, "not an object", 0.889)]
    assert found[0].model_box == far and found[0].model_cls == 1
    farther = (0.36, 0.25, 0.1, 0.1)                             # does not touch it: no box kept
    [f] = judge(labels("camA/images/0001.jpg"), [P(1, PERSON, 0.9), P(0, farther, 0.9)], cmap, dataset, FindSettings())
    assert f.kind == "not an object" and f.model_box is None and f.model_cls is None


def test_the_band_reports_only_nearest_boxes_inside_it(labels, dataset, cmap):
    far = (0.33, 0.25, 0.1, 0.1)
    preds = [P(1, PERSON, 0.9), P(0, far, 0.9)]
    assert judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings(band=(0.0, 0.1))) == []


def test_below_the_floor_the_model_sees_nothing(labels, dataset, cmap):
    found = judge(labels("camA/images/0001.jpg"), [P(0, CAR, 0.3), P(1, PERSON, 0.9)], cmap, dataset, FindSettings())
    assert kinds(found) == [(1, "not an object", 1.0)]


def test_weakly_seen_is_off_by_default_and_never_changes_the_other_kinds(labels, dataset, cmap):
    preds = [P(0, CAR, 0.45), P(1, PERSON, 0.95)]
    assert judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings()) == []
    assert kinds(judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings(weak=True))) == [
        (1, "weakly seen", 0.55)]


def test_a_class_of_the_same_group_agrees(labels, dataset, cmap, ds):
    ds.lbl("camB/0001").write_text("3 0.750000 0.750000 0.150000 0.150000\n")      # a bus_l
    bus = P(2, (0.75, 0.75, 0.15, 0.15), 0.9)                                     # the model's bus: bus_m
    assert judge(labels("camB/images/0001.jpg"), [bus], cmap, dataset, FindSettings()) == []
    assert agrees(3, 2, dataset) and not agrees(3, 1, dataset)


def test_a_class_is_checkable_through_its_group(labels, dataset, cmap, ds):
    ds.lbl("camB/0001").write_text("3 0.750000 0.750000 0.150000 0.150000\n")      # bus_l: nothing maps to it,
    found = judge(labels("camB/images/0001.jpg"), [], cmap, dataset, FindSettings())  # but bus_m, its group, does
    assert kinds(found) == [(0, "not an object", 1.0)]


def test_without_groups_each_class_stands_alone(labels, cmap, ds):
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    del data["groups"]
    (ds.root / "plain.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    plain = Dataset.open(ds.root / "plain.yaml")
    ds.lbl("camB/0001").write_text("3 0.750000 0.750000 0.150000 0.150000\n")
    store = LabelStore(plain)
    bus = P(2, (0.75, 0.75, 0.15, 0.15), 0.9)
    [f] = judge(store.get(plain.root / "camB/images/0001.jpg"), [bus], cmap, plain, FindSettings())
    assert f.kind == "wrong class"
    assert judge(store.get(plain.root / "camB/images/0001.jpg"), [], cmap, plain, FindSettings()) == []


@pytest.mark.parametrize("kw, why", [
    (dict(floor=0.05), "confidence floor: must be from 0.1 to 1"),
    (dict(match_iou=0.0), "matching IoU: must be above 0 and at most 1"),
    (dict(ceiling=1.5), "wrong-class ceiling: must be from 0 to 1"),
    (dict(band=(0.4, 0.2)), "not-an-object band: 0.4 is above 0.2: put the lower end first"),
    (dict(cutoff=-0.1), "weak cutoff: must be from 0 to 1"),
])
def test_unusable_settings_are_refused_by_name(kw, why):
    with pytest.raises(ValueError, match=why):
        FindSettings(**kw)


def test_settings_survive_their_json():
    s = FindSettings(floor=0.5, match_iou=0.6, ceiling=0.9, band=(0.0, None), weak=True, cutoff=0.7)
    assert FindSettings.from_json(s.to_json()) == s and FindSettings.from_json(FindSettings().to_json()) == FindSettings()
