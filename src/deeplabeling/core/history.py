"""Undo and redo across every image (docs/design/2026-10-04-app-foundation.md#history)."""

from __future__ import annotations

from collections import deque

from .edits import Conflict, Edit, Refused
from .store import LabelStore


class History:
    """One global list of Edits, capped in bytes; the oldest are dropped first.

    Undo and redo go through `LabelStore.restore`. When a file no longer holds what
    the edit left, it raises Conflict: that edit can never succeed, so it is dropped
    and the edits before it stay undoable. Any other refusal -- a full disk, a read
    error -- keeps the edit, since it holds the only copy of the bytes it replaced.
    """

    def __init__(self, store: LabelStore, *, cap_bytes: int = 64 * 2**20):
        self._store = store
        self._cap = cap_bytes
        self._undo: deque[Edit] = deque()
        self._redo: list[Edit] = []
        self._bytes = 0

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def depth(self) -> int:
        return len(self._undo)

    def peek_undo(self) -> Edit | None:
        """The edit `undo` would revert, so the UI can move to its image first."""
        return self._undo[-1] if self._undo else None

    def peek_redo(self) -> Edit | None:
        return self._redo[-1] if self._redo else None

    def push(self, edit: Edit) -> None:
        self._bytes -= sum(e.nbytes for e in self._redo)
        self._redo.clear()
        self._undo.append(edit)
        self._bytes += edit.nbytes
        while self._bytes > self._cap and len(self._undo) > 1:
            self._bytes -= self._undo.popleft().nbytes

    def undo(self) -> Edit | None:
        if not self._undo:
            return None
        edit = self._undo[-1]
        try:
            self._store.restore(edit, undo=True)
        except Conflict as e:
            self._undo.pop()
            self._bytes -= edit.nbytes
            raise Refused(f"cannot undo “{edit.description}”: {e}. "
                          "It has been dropped from the history.") from e
        except Refused as e:
            raise Refused(f"cannot undo “{edit.description}”: {e}. "
                          "It is still in the history; try again.") from e
        self._redo.append(self._undo.pop())
        return edit

    def redo(self) -> Edit | None:
        if not self._redo:
            return None
        edit = self._redo[-1]
        try:
            self._store.restore(edit, undo=False)
        except Conflict as e:
            self._redo.pop()
            self._bytes -= edit.nbytes
            raise Refused(f"cannot redo “{edit.description}”: {e}. "
                          "It has been dropped from the history.") from e
        except Refused as e:
            raise Refused(f"cannot redo “{edit.description}”: {e}. "
                          "It is still in the history; try again.") from e
        self._undo.append(self._redo.pop())
        return edit
