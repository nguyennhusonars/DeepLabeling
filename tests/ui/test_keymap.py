import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QWidget

from deeplabeling.ui.keymap import ACTIONS, HelpDialog, build_actions, help_rows


def test_action_ids_are_unique_and_no_key_is_bound_twice():
    ids = [spec.id for spec in ACTIONS]
    keys = [QKeySequence(k).toString() for spec in ACTIONS for k in spec.keys]
    assert len(ids) == len(set(ids)) and len(keys) == len(set(keys))


def test_a_shortcut_runs_its_handler(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    hits = []
    handlers = {spec.id: (lambda i=spec.id: hits.append(i)) for spec in ACTIONS if not spec.checkable}
    actions = build_actions(host, handlers)
    with qtbot.waitActive(host):        # window shortcuts need the active window
        host.show()
        host.activateWindow()
    qtbot.keyClick(host, Qt.Key_K)
    qtbot.keyClick(host, Qt.Key_Space)
    qtbot.keyClick(host, Qt.Key_Z, Qt.ControlModifier)
    assert hits == ["toggle_reviewed", "done_next", "undo"]
    assert actions["toggle_labels"].shortcut() == QKeySequence("L")


def test_every_handler_is_required():
    with pytest.raises(KeyError):
        build_actions(QWidget(), {})


def test_the_help_lists_every_action(qtbot):
    dialog = HelpDialog()
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == len(ACTIONS) == len(help_rows())
    assert dialog.table.item(2, 1).text().startswith("Done & next")
