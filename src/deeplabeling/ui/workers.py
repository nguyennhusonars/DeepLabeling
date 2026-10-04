"""Background jobs (docs/design/2026-10-04-app-foundation.md#architecture).

A job gets immutable inputs, reports through queued signals, never writes a file and
never touches a widget. The GUI thread never waits on one (CLAUDE.md landmine 3).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

#: fn(emit, cancelled) -> result. `emit` sends a batch to the GUI thread; `cancelled`
#: says whether to stop early.
JobFn = Callable[[Callable[[object], None], Callable[[], bool]], object]


class JobSignals(QObject):
    batch = Signal(object)
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _Relay(QObject):
    """Forwards one job's signals to its caller's callbacks, on the GUI thread.

    Its slots are methods on purpose: PySide6 6.6 never releases a lambda, partial or
    closure connected to a signal, even after the sender is gone, so a lambda slot keeps
    whatever it captures -- a whole workspace -- for good. A method slot goes with its
    receiver, and the callbacks themselves are dropped as soon as the job finishes.
    """

    def __init__(self, batch, done, failed, finished):
        super().__init__()
        self._batch, self._done, self._failed, self._finished = batch, done, failed, finished

    @Slot(object)
    def on_batch(self, items) -> None:
        if self._batch is not None:
            self._batch(items)

    @Slot(object)
    def on_done(self, result) -> None:
        if self._done is not None:
            self._done(result)

    @Slot(str)
    def on_failed(self, why: str) -> None:
        if self._failed is not None:
            self._failed(why)

    @Slot()
    def on_finished(self) -> None:
        finished = self._finished
        self._batch = self._done = self._failed = self._finished = None
        if finished is not None:
            finished()


class Handle:
    """What a caller keeps of a running job: its signals, and a way to cancel it."""

    def __init__(self, signals: JobSignals, cancel: threading.Event, relay: _Relay):
        self.signals = signals
        self._cancel = cancel
        self._relay = relay

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


class Job(QRunnable):
    """Runs one function on a pool thread, then is deleted by the pool. Its signals object
    is created on the GUI thread, so it reaches GUI-thread receivers through queued
    connections."""

    def __init__(self, fn: JobFn, signals: JobSignals, cancel: threading.Event):
        super().__init__()
        # With autoDelete off, PySide6's pool keeps every job -- and whatever its closures
        # capture, a whole workspace included -- for the life of the pool.
        self.setAutoDelete(True)
        self._fn, self._signals, self._cancel = fn, signals, cancel

    def run(self) -> None:
        signals, cancel = self._signals, self._cancel
        try:
            result = self._fn(signals.batch.emit, cancel.is_set)
        except Exception as e:                      # a worker that raises stops alone
            if not cancel.is_set():
                signals.failed.emit(f"{type(e).__name__}: {e}")
        else:
            if not cancel.is_set():
                signals.done.emit(result)
        finally:
            self._fn = self._signals = None         # drop the closures now
            signals.finished.emit()


class Jobs:
    """A pool of worker threads. A job's handle is kept until the job finishes; then its
    callbacks are dropped, so a finished job keeps nothing alive."""

    def __init__(self, threads: int):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(threads)
        self._live: dict[int, Handle] = {}
        self._next = 0

    def start(self, fn: JobFn, *, batch: Callable[[object], None] | None = None,
              done: Callable[[object], None] | None = None,
              failed: Callable[[str], None] | None = None) -> Handle:
        signals, cancel = JobSignals(), threading.Event()
        key, self._next = self._next, self._next + 1
        relay = _Relay(batch, done, failed, lambda: self._live.pop(key, None))
        signals.batch.connect(relay.on_batch)
        signals.done.connect(relay.on_done)
        signals.failed.connect(relay.on_failed)
        signals.finished.connect(relay.on_finished)
        handle = Handle(signals, cancel, relay)
        self._live[key] = handle
        self.pool.start(Job(fn, signals, cancel))
        return handle

    def cancel_all(self) -> None:
        for handle in list(self._live.values()):
            handle.cancel()

    def wait(self, msecs: int = -1) -> bool:
        """Block until the pool is idle. For shutdown and tests, never for the GUI."""
        return self.pool.waitForDone(msecs)
