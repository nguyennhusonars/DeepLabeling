import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, SetBox, SetClass, materialize
from deeplabeling.core.store import LabelStore
from deeplabeling.ui import actions
from deeplabeling.ui.selection import Selection
from fixtures import CAMA_0001

BOX = (0.5, 0.5, 0.2, 0.2)


@pytest.fixture
def store(ds):
    return LabelStore(Dataset.open(ds.yaml))


def written(store, intent) -> str:
    """The file an intent would leave, computed without writing it."""
    labels = store.get(intent.image)
    return materialize(labels.raw, intent.ops, class_ok=store.dataset.known).decode()


def test_add_box(ds):
    intent = actions.add_box(ds.img("camA/0003.jpg"), 2, BOX)
    assert intent.ops == (AddBox(2, BOX),) and intent.description == "draw a box"


def test_reclassify_skips_boxes_already_of_that_class(store, ds):
    img = ds.img("camA/0001.jpg")
    labels = store.get(img)
    intent = actions.reclassify(img, labels, [0, 1], 1)
    assert [type(op) for op in intent.ops] == [SetClass] and intent.description == "reclassify 1 box"
    assert written(store, intent) == "1" + CAMA_0001[1:]
    assert actions.reclassify(img, labels, [1], 1) is None


def test_delete(store, ds):
    img = ds.img("camA/0001.jpg")
    labels = store.get(img)
    intent = actions.delete(img, labels, [1, 0])
    assert written(store, intent) == "" and intent.description == "delete 2 boxes"
    assert actions.delete(img, labels, []) is None


def test_lines_that_are_not_boxes_are_ignored(store, ds):
    img = ds.img("bad/ok.jpg")
    labels = store.get(img)                       # GAUNTLET: line 4 is not a box
    assert actions.delete(img, labels, [4]) is None
    assert len(actions.delete(img, labels, [4, 0]).ops) == 1


def test_move_keeps_the_size_and_stays_inside_the_image(store, ds):
    img = ds.img("camA/0001.jpg")
    labels = store.get(img)
    intent = actions.move(img, labels, [0], 0.6, 0.0)
    assert intent.ops[0].bbox == pytest.approx((0.9, 0.5, 0.2, 0.3))
    assert isinstance(intent.ops[0], SetBox) and intent.description == "move 1 box"
    assert actions.move(img, labels, [0], 0, 0) is None


def test_resize(store, ds):
    img = ds.img("bad/ok.jpg")
    labels = store.get(img)
    intent = actions.resize(img, labels, 0, (0.4, 0.4, 0.2, 0.2))
    assert written(store, intent).startswith("1 0.400000 0.400000 0.200000 0.200000\n")
    assert actions.resize(img, labels, 4, BOX) is None


def test_copy_writes_label_lines_and_leaves_polygons_out(store, ds):
    mixed = store.get(ds.img("seg/mixed.jpg"))               # a box, then a polygon
    assert actions.copy_text(mixed, [0, 1]) == "0 0.500000 0.500000 0.200000 0.200000\n"
    assert actions.copy_text(store.get(ds.img("seg/poly1.jpg")), [0, 1]) == ""


def test_a_copy_pastes_back_as_the_same_lines(store, ds):
    text = actions.copy_text(store.get(ds.img("camA/0001.jpg")), [0, 1])
    intent = actions.paste(ds.img("camA/0003.jpg"), text, store.dataset.known)
    assert written(store, intent) == CAMA_0001 and intent.description == "paste 2 boxes"


def test_paste_clamps_and_skips_what_is_not_a_box_of_a_known_class(store, ds):
    text = "0 0.95 0.5 0.2 0.2\n9 0.5 0.5 0.1 0.1\n-1 0.5 0.5 0.1 0.1\nhello\n1 2.0 2.0 0.1 0.1\n"
    intent = actions.paste(ds.img("camA/0003.jpg"), text, store.dataset.known)
    assert len(intent.ops) == 1 and intent.ops[0].bbox == pytest.approx((0.925, 0.5, 0.15, 0.2))
    assert actions.paste(ds.img("camA/0003.jpg"), "nothing here", store.dataset.known) is None


def test_a_selection_finds_its_boxes_after_lines_move(qtbot, store, ds):
    img = ds.img("camA/0001.jpg")
    selection = Selection()
    selection.select(store.get(img), [1])
    ds.lbl("camA/0001").write_bytes(b"2 0.1 0.1 0.05 0.05\n" + CAMA_0001.encode())   # a line above
    assert selection.indices(store.get(img)) == [2]


def test_a_selected_box_that_is_gone_drops_out(qtbot, store, ds):
    img = ds.img("camA/0001.jpg")
    selection = Selection()
    selection.select(store.get(img), [0, 1])
    ds.lbl("camA/0001").write_bytes(CAMA_0001.splitlines(keepends=True)[1].encode())
    assert selection.indices(store.get(img)) == [0]


def test_another_image_has_nothing_selected(qtbot, store, ds):
    selection = Selection()
    selection.select(store.get(ds.img("camA/0001.jpg")), [0])
    assert selection.indices(store.get(ds.img("camB/0001.jpg"))) == []


def test_only_lines_that_are_boxes_can_be_selected(qtbot, store, ds):
    selection = Selection()
    selection.select(store.get(ds.img("bad/ok.jpg")), [4, 7])
    assert len(selection) == 0


def test_changed_fires_only_when_the_selection_changes(qtbot, store, ds):
    labels = store.get(ds.img("camA/0001.jpg"))
    selection, seen = Selection(), []
    selection.changed.connect(lambda: seen.append(1))
    selection.select(labels, [0])
    selection.select(labels, [0])
    selection.clear()
    selection.clear()
    assert seen == [1, 1]


def test_boxes_moved_together_stop_together_at_the_edge(store, ds):
    img = ds.img("camA/0001.jpg")                           # person cx 0.5 w 0.2; car cx 0.25 w 0.1
    intent = actions.move(img, store.get(img), [0, 1], 0.6, 0.0)
    assert [op.bbox[0] for op in intent.ops] == pytest.approx([0.9, 0.65])


def test_pasted_classes_follow_their_names_into_another_class_list():
    text = "0 0.5 0.5 0.2 0.3\n1 0.25 0.25 0.1 0.1\n2 0.7 0.7 0.1 0.1\nhello\n"
    remapped, lost = actions.remap_classes(text, ("person", "car", "bus_m"), ("car", "truck", "person"))
    assert remapped == "2 0.500000 0.500000 0.200000 0.300000\n0 0.250000 0.250000 0.100000 0.100000\n"
    assert lost == 1                                        # bus_m has no place in the new list
