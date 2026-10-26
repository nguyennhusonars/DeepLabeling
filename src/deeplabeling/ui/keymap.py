"""The one registry of actions and their keys (docs/design/2026-10-04-app-foundation.md#window).

The help dialog is generated from it, so the help cannot drift from the keys. Shortcuts
are window-wide; Qt keeps them quiet while a text field has focus.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QDialog, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from .classes import DEFAULT_HOTKEYS


@dataclass(frozen=True)
class ActionSpec:
    id: str
    text: str
    keys: tuple[str, ...]
    checkable: bool = False         #: bound to a setting by its owner, not to a handler


ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec("next", "Next", ("Right",)),
    ActionSpec("previous", "Previous", ("Left",)),
    ActionSpec("down", "Next — in the grid, the row below", ("Down",)),
    ActionSpec("up", "Previous — in the grid, the row above", ("Up",)),
    ActionSpec("done_next", "✓ Reviewed, then next", ("Space",)),
    ActionSpec("toggle_reviewed", "✓ Reviewed on / off", ("K",)),
    ActionSpec("mark_negative", "Negative: nothing to label (an empty file)", ("N",)),
    *(ActionSpec(f"class_{key}", f"Class {key} — the selection, or the class drawn",
                 (key,)) for key in DEFAULT_HOTKEYS),
    ActionSpec("pick_class", "Pick a class by name", ("C",)),
    ActionSpec("delete", "Delete the selection", ("Delete", "Backspace")),
    ActionSpec("select_next", "Select the next box", ("Tab",)),
    ActionSpec("select_previous", "Select the previous box", ("Shift+Tab",)),
    ActionSpec("select_all", "Select all boxes", ("Ctrl+A",)),
    ActionSpec("escape", "Cancel drawing / clear the selection", ("Esc",)),
    ActionSpec("copy", "Copy boxes", ("Ctrl+C",)),
    ActionSpec("paste", "Paste boxes", ("Ctrl+V",)),
    ActionSpec("undo", "↶ Undo", ("Ctrl+Z",)),
    ActionSpec("redo", "↷ Redo", ("Ctrl+Shift+Z", "Ctrl+Y")),
    ActionSpec("fit", "Fit to the view", ("F",)),
    ActionSpec("zoom_in", "Zoom in", ("+", "=")),
    ActionSpec("zoom_out", "Zoom out", ("-",)),
    ActionSpec("toggle_labels", "Labels", ("L",), checkable=True),
    ActionSpec("toggle_captions", "Captions", ("T",), checkable=True),
    ActionSpec("toggle_crosshair", "Crosshair", (), checkable=True),
    ActionSpec("toggle_grid", "Grid", ("G",), checkable=True),
    ActionSpec("mark_page", "✓ Mark the tiles in view reviewed (grid)", ()),
    ActionSpec("go_to", "Go to… a number or a name", ("Ctrl+G",)),
    ActionSpec("help", "Shortcuts", ("?",)),
    ActionSpec("toggle_predictions", "Predictions", ("P",), checkable=True),
    ActionSpec("accept_missing", "✚ Accept this image's missing predictions", ("A",)),
    ActionSpec("take_model_class", "Find Bad: take the model's class", ("M",)),
    ActionSpec("take_model_box", "Find Bad: take the model's box", ("B",)),
    ActionSpec("dismiss", "Find Bad: dismiss / undismiss", ("D",)),
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
    """(keys, what they do) for every action, in registry order; the class keys as one row."""
    rows = []
    for spec in ACTIONS:
        if spec.id.startswith("class_"):
            if spec.id == f"class_{DEFAULT_HOTKEYS[0]}":
                rows.append((f"{DEFAULT_HOTKEYS[0]} – {DEFAULT_HOTKEYS[-1]}",
                             f"Class 1–{len(DEFAULT_HOTKEYS)} — the selection, or the class drawn"))
            continue
        rows.append((", ".join(QKeySequence(k).toString(QKeySequence.NativeText) for k in spec.keys),
                     spec.text + (" (on / off)" if spec.checkable else "")))
    return rows


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
