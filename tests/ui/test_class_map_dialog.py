"""The class-map editor (docs/design/2026-10-05-model-assist.md#the-class-map)."""

from PySide6.QtCore import QPoint, QRect

from deeplabeling.core.classmap import ClassMap
from deeplabeling.ui.class_map_dialog import NOT_MAPPED, ClassMapDialog

NAMES = ("person", "car", "bus_m", "bus_l")
MODEL = ("car", "truck", "human")


def dialog(qtbot, cmap=None):
    d = ClassMapDialog(cmap or ClassMap.seeded(MODEL, NAMES), NAMES)
    qtbot.addWidget(d)
    return d


def test_one_row_per_model_class_showing_what_it_maps_to(qtbot):
    assert dialog(qtbot).rows() == [("car", "car"), ("truck", NOT_MAPPED), ("human", NOT_MAPPED)]


def test_a_choice_becomes_the_map_and_is_marked_as_chosen(qtbot):
    d = dialog(qtbot)
    d.choose("human", "person")
    d.choose("car", NOT_MAPPED)
    cmap = d.class_map()
    assert cmap.targets == (None, None, "person") and cmap.chosen == (True, False, True)


def test_a_row_left_alone_stays_as_it_was(qtbot):
    d = dialog(qtbot)
    d.choose("human", "person")
    d.choose("human", NOT_MAPPED)                   # back to where it was
    assert d.class_map() == ClassMap.seeded(MODEL, NAMES)


def test_seeding_again_forgets_the_choices(qtbot):
    d = dialog(qtbot, ClassMap.seeded(MODEL, NAMES).with_target(0, None).with_target(2, "person"))
    assert d.rows()[0] == ("car", NOT_MAPPED)
    d.seed_button.click()
    assert d.rows() == [("car", "car"), ("truck", NOT_MAPPED), ("human", NOT_MAPPED)]
    assert d.class_map() == ClassMap.seeded(MODEL, NAMES)


def test_every_row_is_visible_and_none_overlaps(qtbot):
    d = dialog(qtbot)
    d.show()
    qtbot.waitUntil(d.isVisible)
    rects = []
    for label, combo in d.row_widgets():
        for w in (label, combo):
            rect = QRect(w.mapTo(d, QPoint(0, 0)), w.size())
            assert w.isVisible() and w.width() >= w.sizeHint().width() and d.rect().contains(rect)
            assert not any(rect.intersects(r) for r in rects)
            rects.append(rect)


def test_eighty_classes_scroll_inside_a_dialog_that_fits_the_screen(qtbot):
    names = tuple(f"class {i}" for i in range(80))
    d = ClassMapDialog(ClassMap.seeded(names, NAMES), NAMES)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(d.isVisible)
    assert d.height() <= 700 and len(d.rows()) == 80
