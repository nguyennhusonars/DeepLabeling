"""Background jobs (docs/design/2026-10-04-app-foundation.md#architecture).

A job gets immutable inputs, reports through queued signals, never writes a file and
never touches a widget. The GUI thread never waits on one (CLAUDE.md landmine 3).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

#: fn(emit, cancelled) -> result. `emit` sends a batch to the GUI thread; `cancelled`
#: says whether to stop early.
JobFn = Callable[[Callable[[object], None], Callable[[], bool]], object]


class JobSignals(QObject):
    batch = Signal(object)
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()


class Job(QRunnable):
    """Runs one function on a pool thread. It is created on the GUI thread, so its
    signals reach GUI-thread receivers through queued connections."""

    def __init__(self, fn: JobFn):
        super().__init__()
        self.setAutoDelete(False)       # Jobs keeps the Python object alive instead
        self.signals = JobSignals()
        self._fn = fn
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:
        try:
            result = self._fn(self.signals.batch.emit, self._cancel.is_set)
        except Exception as e:                      # a worker that raises stops alone
            if not self.cancelled:
                self.signals.failed.emit(f"{type(e).__name__}: {e}")
        else:
            if not self.cancelled:
                self.signals.done.emit(result)
        finally:
            self.signals.finished.emit()


class Jobs:
    """A pool of worker threads that keeps every job alive until it finishes."""

    def __init__(self, threads: int):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(threads)
        self._live: set[Job] = set()

    def start(self, fn: JobFn, *, batch: Callable[[object], None] | None = None,
              done: Callable[[object], None] | None = None,
              failed: Callable[[str], None] | None = None) -> Job:
        job = Job(fn)
        if batch is not None:
            job.signals.batch.connect(batch)
        if done is not None:
            job.signals.done.connect(done)
        if failed is not None:
            job.signals.failed.connect(failed)
        job.signals.finished.connect(lambda j=job: self._live.discard(j))
        self._live.add(job)
        self.pool.start(job)
        return job

    def cancel_all(self) -> None:
        for job in list(self._live):
            job.cancel()

    def wait(self, msecs: int = -1) -> bool:
        """Block until the pool is idle. For shutdown and tests, never for the GUI."""
        return self.pool.waitForDone(msecs)
