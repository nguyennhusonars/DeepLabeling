"""A long write on the GUI thread, a chunk per event-loop turn, behind a modal progress
dialog (docs/design/2026-10-05-model-assist.md#accepting).

Every label file is written on the GUI thread's one write path (CLAUDE.md landmine 2). A
write across a whole queue done at once would freeze the window (about 2 ms a file), so it
goes a chunk at a time: the window keeps painting between chunks, the modal dialog keeps
anything else from editing, and its Cancel stops the run between two chunks.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

from ..core.edits import Refused

CHUNK = 50      #: files written per event-loop turn: about 0.1 s


class Chunked(QObject):
    """Calls `step` once per event-loop turn while it returns True; then `end(cancelled,
    error)` once: cancelled from the dialog or by stop(), or stopped by a Refused."""

    def __init__(self, progress, step: Callable[[], bool],
                 end: Callable[[bool, Refused | None], None], parent=None):
        super().__init__(parent)
        self._progress, self._step, self._end = progress, step, end
        self._over = False
        QTimer.singleShot(0, self._next)

    def _next(self) -> None:
        if self._over:
            return
        if self._progress.cancelled():
            self._finish(cancelled=True)
            return
        try:
            more = self._step()
        except Refused as e:
            self._finish(error=e)
            return
        if more:
            QTimer.singleShot(0, self._next)
        else:
            self._finish()

    def stop(self) -> None:
        """Stop now, between two chunks, as a cancel does."""
        if not self._over:
            self._finish(cancelled=True)

    def _finish(self, *, cancelled: bool = False, error: Refused | None = None) -> None:
        self._over = True
        self._progress.close()
        self._end(cancelled, error)
