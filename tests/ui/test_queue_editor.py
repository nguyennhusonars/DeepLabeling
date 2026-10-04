import pytest
from PySide6.QtCore import Qt

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.queue import HasClass, ImageFilter, LabelStateIs, NameContains, Reviewed
from deeplabeling.ui.queue_editor import QueueEditor


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


def editor(qtbot, dataset, current):
    dialog = QueueEditor(dataset, current)
    qtbot.addWidget(dialog)
    return dialog


@pytest.mark.parametrize("current", [
    ImageFilter(),
    ImageFilter(("val",), (HasClass(("car", "bus_l")), LabelStateIs("boxes"),
                           Reviewed(False), NameContains("cam"))),
    ImageFilter(conditions=(HasClass(("person",), present=False), LabelStateIs("missing"))),
])
def test_the_editor_is_seeded_from_the_queue_in_force(qtbot, dataset, current):
    assert editor(qtbot, dataset, current).filter() == current


def test_choosing_has_without_a_class_adds_no_condition(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.class_mode.setCurrentText("has")
    assert dialog.filter() == ImageFilter()


def test_the_widgets_build_the_filter(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.splits["train"].setChecked(False)
    dialog.class_mode.setCurrentText("lacks")
    dialog.classes.item(1).setCheckState(Qt.Checked)
    dialog.review_mode.setCurrentText("not reviewed")
    dialog.name.setText("  seg ")
    assert dialog.filter() == ImageFilter(("val",), (HasClass(("car",), present=False),
                                                     Reviewed(False), NameContains("seg")))
