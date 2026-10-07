"""The reassign dialog: From and To (docs/design/2026-10-07-bulk-and-stats.md#the-dialog)."""

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QDialog

from deeplabeling.ui.reassign_dialog import ReassignDialog

NAMES = ("person", "car", "bus_m", "bus_l")


def dialog(qtbot, ids=(-1, 99)):
    d = ReassignDialog(NAMES, ids)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(d.isVisible)
    return d


def items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def test_from_lists_the_classes_then_the_ids_the_yaml_does_not_name(qtbot):
    d = dialog(qtbot)
    assert items(d.source) == ["person", "car", "bus_m", "bus_l", "#-1?", "#99?"]
    assert items(d.target) == list(NAMES)


def test_ok_takes_from_and_to(qtbot):
    d = dialog(qtbot)
    d.source.setCurrentText("#99?")
    d.target.setCurrentText("car")
    d.accept()
    assert d.result() == QDialog.Accepted and d.chosen == (99, 1)


def test_a_class_onto_itself_is_refused_and_the_dialog_stays_open(qtbot):
    d = dialog(qtbot)
    d.source.setCurrentText("car")
    d.target.setCurrentText("car")
    d.accept()
    assert d.isVisible() and d.result() != QDialog.Accepted
    assert d.error.isVisible() and d.error.text() == "From and To are the same class"


def test_its_rows_are_visible_and_do_not_overlap(qtbot):
    d = dialog(qtbot)
    rects = []
    for w in (d.source, d.target):
        rect = QRect(w.mapTo(d, QPoint(0, 0)), w.size())
        assert w.isVisible() and w.width() >= 80 and d.rect().contains(rect)
        assert not any(rect.intersects(r) for r in rects)
        rects.append(rect)
