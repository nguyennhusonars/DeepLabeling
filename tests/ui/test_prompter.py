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


def test_the_class_map_and_threshold_dialogs_answer_none_when_cancelled(qtbot):
    from deeplabeling.core.classmap import ClassMap
    from deeplabeling.ui.class_map_dialog import ClassMapDialog

    parent = QWidget()
    qtbot.addWidget(parent)
    prompter = QtPrompter(parent)
    answer_with_cancel()
    assert prompter.edit_class_map(ClassMap.seeded(("car",), ("car",)), ("car",)) is None
    answer_with_cancel()
    assert prompter.ask_threshold(0.25) is None
    qtbot.waitUntil(lambda: not parent.findChildren(ClassMapDialog))


def test_the_progress_dialog_is_modal_visible_and_cancels(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QProgressDialog

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(600, 400)
    parent.show()
    progress = QtPrompter(parent).progress("Undoing accept", 10)
    dialog = parent.findChild(QProgressDialog)
    qtbot.waitUntil(dialog.isVisible)
    assert dialog.windowModality() == Qt.ApplicationModal and dialog.labelText() == "Undoing accept"
    progress.set(4)
    assert dialog.value() == 4 and not progress.cancelled()
    dialog.cancel()
    assert progress.cancelled()
    progress.close()
    qtbot.waitUntil(lambda: not parent.findChildren(QProgressDialog))


def test_the_queue_accept_is_confirmed_with_yes_and_declined_otherwise(qtbot):
    from PySide6.QtWidgets import QMessageBox

    parent = QWidget()
    qtbot.addWidget(parent)
    prompter = QtPrompter(parent)
    def press_yes():
        box = QApplication.activeModalWidget()
        if box is None:
            QTimer.singleShot(10, press_yes)                 # not shown yet
        else:
            box.button(QMessageBox.Yes).click()

    QTimer.singleShot(0, press_yes)
    assert prompter.confirm_queue_accept("Accept 1 box on 1 image?") is True
    answer_with_cancel()
    assert prompter.confirm_queue_accept("Accept 1 box on 1 image?") is False


def test_esc_on_the_progress_dialog_cancels_it(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QProgressDialog

    parent = QWidget()
    qtbot.addWidget(parent)
    progress = QtPrompter(parent).progress("Accepting", 10)
    dialog = parent.findChild(QProgressDialog)
    qtbot.waitUntil(dialog.isVisible)
    qtbot.keyClick(dialog, Qt.Key_Escape)
    assert progress.cancelled()
    progress.close()



def test_the_reassign_is_confirmed_with_yes_and_declined_otherwise(qtbot):
    from PySide6.QtWidgets import QMessageBox

    parent = QWidget()
    qtbot.addWidget(parent)
    prompter = QtPrompter(parent)

    def press(button):
        box = QApplication.activeModalWidget()
        if box is None:
            QTimer.singleShot(10, lambda: press(button))     # not shown yet
        else:
            box.button(button).click()

    QTimer.singleShot(0, lambda: press(QMessageBox.Yes))
    assert prompter.confirm_reassign("Reassign 1 car box on 1 image to bus_m?") is True
    QTimer.singleShot(0, lambda: press(QMessageBox.No))
    assert prompter.confirm_reassign("Reassign 1 car box on 1 image to bus_m?") is False
