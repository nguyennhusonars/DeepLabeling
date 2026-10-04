import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.store import LabelStore
from deeplabeling.ui.boxes import box_views
from deeplabeling.ui.classes import PALETTE, UNKNOWN, assign_classes, class_infos, class_with_hotkey, text_color

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


def test_class_infos_read_the_colour_and_key_stored_for_each_name(dataset):
    infos = class_infos(dataset, {"bus_l": "#000000"}, {"car": "7"})
    assert [(i.name, i.hotkey) for i in infos] == [("person", ""), ("car", "7"), ("bus_m", ""), ("bus_l", "")]
    assert infos[3].color == "#000000" and infos[0].color == PALETTE[0]


def test_a_first_class_list_takes_colours_and_digits_in_order():
    colors, keys = assign_classes([f"c{i}" for i in range(12)], {}, {})
    assert [colors[f"c{i}"] for i in range(12)] == list(PALETTE[:12])
    assert [keys[f"c{i}"] for i in range(12)] == list("1234567890") + ["", ""]


def test_a_second_class_list_keeps_shared_names_and_fills_in_new_ones():
    colors, keys = assign_classes(["person", "car", "bus_m", "bus_l"], {}, {})
    colors, keys = assign_classes(["car", "truck", "person"], colors, keys)
    assert (keys["car"], keys["person"], keys["truck"]) == ("2", "1", "3")
    assert colors["truck"] == PALETTE[2]               # first colour unused by THIS list
    assert colors["car"] == PALETTE[1] and colors["person"] == PALETTE[0]


def test_two_names_sharing_a_stored_key_in_one_list_do_not_collide():
    _, keys = assign_classes(["a", "b"], {}, {"a": "5", "b": "5"})
    assert keys == {"a": "5", "b": "1"}


def test_assignment_does_not_change_its_arguments():
    colors, keys = {"a": "#123456"}, {"a": "9"}
    assign_classes(["a", "b"], colors, keys)
    assert colors == {"a": "#123456"} and keys == {"a": "9"}


def test_the_class_with_a_hotkey(dataset):
    infos = class_infos(dataset, {}, {"car": "2", "bus_l": "4"})
    assert class_with_hotkey(infos, "4").name == "bus_l" and class_with_hotkey(infos, "9") is None


def test_text_colour_contrasts():
    assert text_color("#000075") == "#ffffff" and text_color("#fffac8") == "#000000"


def test_a_dataset_without_names_offers_the_bare_ids_0_to_9(ds):
    folder = Dataset.open(ds.root / "camA" / "images")         # no classes.txt beside it
    infos = class_infos(folder, {}, {})
    assert [(i.cls_id, i.name, i.hotkey) for i in infos[:2]] == [(0, "0", "1"), (1, "1", "2")]
    assert len(infos) == 10 and infos[9].hotkey == "0" and infos[3].color == PALETTE[3]
