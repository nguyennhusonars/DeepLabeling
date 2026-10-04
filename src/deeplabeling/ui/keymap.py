"""The one registry of actions and their keys (docs/design/2026-10-04-app-foundation.md#window).

The help dialog is generated from it, so the help cannot drift from the keys. Shortcuts
are window-wide; Qt keeps them quiet while a text field has focus. Plan 1c adds the
editing actions here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QDialog, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


@dataclass(frozen=True)
class ActionSpec:
    id: str
    text: str
    keys: tuple[str, ...]
    checkable: bool = False         #: bound to a setting by its owner, not to a handler


ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec("next", "Next item", ("Right", "Down")),
    ActionSpec("previous", "Previous item", ("Left", "Up")),
    ActionSpec("done_next", "Done & next: mark reviewed, go to the next item", ("Space",)),
    ActionSpec("toggle_reviewed", "Toggle reviewed", ("K",)),
    ActionSpec("mark_negative", "Mark negative (an image with no label file and no boxes)", ("N",)),
    ActionSpec("undo", "Undo", ("Ctrl+Z",)),
    ActionSpec("redo", "Redo", ("Ctrl+Shift+Z", "Ctrl+Y")),
    ActionSpec("fit", "Fit the image to the view", ("F",)),
    ActionSpec("zoom_in", "Zoom in", ("+", "=")),
    ActionSpec("zoom_out", "Zoom out", ("-",)),
    ActionSpec("toggle_labels", "Labels", ("L",), checkable=True),
    ActionSpec("toggle_captions", "Captions", ("T",), checkable=True),
    ActionSpec("go_to", "Go to an item by number or name", ("Ctrl+G",)),
    ActionSpec("help", "Shortcut help", ("?",)),
)


def build_actions(window: QWidget, handlers: Mapping[str, Callable[[], None]]) -> dict[str, QAction]:
    """One QAction per spec, added to `window`. Every non-checkable spec needs a handler."""
    actions = {}
    for spec in ACTIONS:
        action = QAction(spec.text, window)
        action.setShortcuts([QKeySequence(key) for key in spec.keys])
        action.setShortcutContext(Qt.WindowShortcut)
        if not spec.checkable:
            handler = handlers[spec.id]
            action.triggered.connect(lambda checked=False, h=handler: h())
        window.addAction(action)
        actions[spec.id] = action
    return actions


def help_rows() -> list[tuple[str, str]]:
    """(keys, what they do) for every action, in registry order."""
    return [(", ".join(QKeySequence(k).toString(QKeySequence.NativeText) for k in spec.keys),
             spec.text + (" (on / off)" if spec.checkable else "")) for spec in ACTIONS]


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shortcuts")
        rows = help_rows()
        self.table = QTableWidget(len(rows), 2)
        self.table.setHorizontalHeaderLabels(["Keys", "Action"])
        for i, (keys, text) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(keys))
            self.table.setItem(i, 1, QTableWidgetItem(text))
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        self.resize(560, 420)
