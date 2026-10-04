import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.store import LabelStore
from deeplabeling.ui.boxes import box_views
from deeplabeling.ui.classes import PALETTE, UNKNOWN, class_infos, text_color

SIZE = (100, 50)


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


def views(dataset, ds, name, **kw):
    labels = LabelStore(dataset).get(ds.img(name))
    return {v.index: v for v in box_views(labels, dataset, SIZE, kw.pop("colors", {}), **kw)}


def test_captions_name_the_class_and_count_stacked_boxes(dataset, ds):
    v = views(dataset, ds, "bad/ok.jpg")
    assert {i: v[i].caption for i in v} == {
        0: "car x4", 1: "#99? x2", 2: "#-1? x2", 3: "person",
        5: "person x4", 6: "person x4", 10: "person x4"}


def test_an_id_outside_the_names_is_grey_and_unknown(dataset, ds):
    v = views(dataset, ds, "bad/ok.jpg")
    assert not v[1].known and v[1].color == UNKNOWN
    assert v[0].known and v[0].color == PALETTE[1]


def test_boxes_are_in_image_pixels(dataset, ds):
    assert views(dataset, ds, "bad/ok.jpg")[0].rect == pytest.approx((40, 20, 60, 30))


def test_a_polygon_keeps_its_points(dataset, ds):
    v = views(dataset, ds, "seg/poly1.jpg")
    points = [c for point in v[0].polygon for c in point]
    assert points == pytest.approx([10, 5, 20, 5, 20, 10, 10, 10])
    assert v[0].rect == pytest.approx((10, 5, 20, 10))


def test_colour_overrides_and_highlight(dataset, ds):
    v = views(dataset, ds, "bad/ok.jpg", colors={"car": "#123456"}, highlight=frozenset({3}))
    assert v[0].color == "#123456"
    assert v[3].highlighted and not v[0].highlighted


def test_without_names_captions_are_ids(ds):
    folder = Dataset.open(ds.root / "camA/images")
    labels = LabelStore(folder).get(ds.img("camA/0001.jpg"))
    assert [v.caption for v in box_views(labels, folder, SIZE, {})] == ["0", "1"]


def test_class_infos_give_default_and_chosen_hotkeys(dataset):
    infos = class_infos(dataset, {"bus_l": "#000000"}, {"car": "q"})
    assert [(i.name, i.hotkey) for i in infos] == [("person", "1"), ("car", "q"), ("bus_m", "3"), ("bus_l", "4")]
    assert infos[3].color == "#000000"


def test_text_colour_contrasts():
    assert text_color("#000075") == "#ffffff" and text_color("#fffac8") == "#000000"
