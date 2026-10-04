"""The GUI thread's one way to change labels (docs/design/2026-10-04-app-foundation.md#edits).

An applied edit is written by the store, recorded in the history and marks its
image reviewed; the listeners hear which images changed.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .edits import Edit, Intent
from .history import History
from .review import ReviewMarks
from .store import LabelStore


class Editor:
    def __init__(self, store: LabelStore, history: History, review: ReviewMarks, *,
                 on_labels_changed: Callable[[tuple[Path, ...]], None] | None = None,
                 on_history_changed: Callable[[], None] | None = None):
        self.store = store
        self.history = history
        self.review = review
        self._labels_changed = on_labels_changed or (lambda images: None)
        self._history_changed = on_history_changed or (lambda: None)

    def apply(self, intent: Intent) -> Edit | None:
        """Write, record and mark. On Refused nothing has changed."""
        edit = self.store.apply(intent)
        if edit is None:
            return None
        self.history.push(edit)
        self.review.mark(self.store.dataset.entry(intent.image).rel)
        self._labels_changed(edit.images)
        self._history_changed()
        return edit

    def undo(self) -> Edit | None:
        try:
            edit = self.history.undo()
        finally:
            self._history_changed()     # a refused undo still dropped an edit
        if edit is not None:
            self._labels_changed(edit.images)
        return edit

    def redo(self) -> Edit | None:
        try:
            edit = self.history.redo()
        finally:
            self._history_changed()
        if edit is not None:
            self._labels_changed(edit.images)
        return edit
