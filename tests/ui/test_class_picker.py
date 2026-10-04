from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from deeplabeling.ui.class_picker import ClassPicker
from deeplabeling.ui.classes import ClassInfo

INFOS = [ClassInfo(0, "person", "#e6194b", "1"), ClassInfo(1, "car", "#3cb44b", "2"),
         ClassInfo(2, "bus_m", "#4363d8", "3"), ClassInfo(3, "bus_l", "#f58231", "4")]


def picker(qtbot):
    dialog = ClassPicker(INFOS)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.list.isVisible)
    return dialog


def shown(dialog):
    return [dialog.list.item(i).text().split()[-1] for i in range(dialog.list.count())]


def test_typing_filters_and_enter_chooses_the_highlighted_class(qtbot):
    dialog = picker(qtbot)
    qtbot.keyClicks(dialog.filter, "BUS")
    assert shown(dialog) == ["bus_m", "bus_l"] and dialog.list.height() > 0
    qtbot.keyClick(dialog.filter, Qt.Key_Down)
    qtbot.keyClick(dialog.filter, Qt.Key_Return)
    assert dialog.result() == QDialog.Accepted and dialog.chosen() == INFOS[3]


def test_enter_with_no_match_chooses_nothing(qtbot):
    dialog = picker(qtbot)
    qtbot.keyClicks(dialog.filter, "tram")
    qtbot.keyClick(dialog.filter, Qt.Key_Return)
    assert shown(dialog) == [] and dialog.isVisible() and dialog.chosen() is None
