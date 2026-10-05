"""The real dialogs behind the prompter, answered by a timer instead of a person."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.queue import ImageFilter
from deeplabeling.ui.class_picker import ClassPicker
from deeplabeling.ui.classes import ClassInfo
from deeplabeling.ui.prompter import QtPrompter
from deeplabeling.ui.queue_editor import QueueEditor


def answer_with_cancel():
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())


def test_an_answered_dialog_is_freed(qtbot, ds):
    parent = QWidget()
    qtbot.addWidget(parent)
    prompter = QtPrompter(parent)
    for _ in range(3):
        answer_with_cancel()
        assert prompter.pick_class([ClassInfo(0, "car", "#3cb44b", "1")]) is None
        answer_with_cancel()
        assert prompter.edit_queue(Dataset.open(ds.yaml), ImageFilter()) is None
    qtbot.waitUntil(lambda: not parent.findChildren(ClassPicker) and not parent.findChildren(QueueEditor))
