"""The model, for the session (docs/design/2026-10-05-model-assist.md#the-inference-thread).

One QThread owns the predictor from loading to closing: an ultralytics model is not safe to
share across threads, and its CUDA context stays on the thread that made it. The GUI thread
never calls it and never waits on it (CLAUDE.md landmine 3). It asks for the image on screen
and its neighbours; each new cursor position replaces the list, so a fast page through the
queue leaves no backlog. Answers go into the prediction store, which the GUI reads.
"""

from __future__ import annotations

import collections
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from ..core.assist import Shown, shown_predictions
from ..core.classmap import ClassMap, load_class_map, save_class_map
from ..core.dataset import ImageEntry
from ..core.inference import FLOOR, Failure, ModelError, Prediction, UltralyticsPredictor
from ..core.predstore import PredictionStore, Stamp, image_stamp
from ..core.settings import define, is_str_list, is_str_or_none

#: The weights last used, for each opening (yaml or folder): loaded again when it opens.
MODEL_PATH = define("model.path", "opening", None, is_str_or_none)
#: Weights files used lately, newest first.
RECENT_MODELS = define("models.recent", "global", [], is_str_list)
#: The confidence a prediction needs to be shown or accepted, for each root.
PRED_CONF = define("model.conf", "root", 0.25,
                   lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and FLOOR <= v <= 1)

RECENT_MAX = 8
SHUTDOWN_MS = 2000      #: the longest closing waits for a prediction in hand
NEIGHBOURS = (1, 2, -1)  #: queue offsets predicted after the image on screen, as images are kept

Wanted = tuple[str, Path, Stamp]   #: (dataset-relative path, file, stamp)

#: Threads let go of while a prediction was still in hand: kept until they finish, since Qt
#: aborts the process when a running QThread is destroyed.
_FINISHING: set = set()


class _Worker(QThread):
    """The thread that owns the predictor. Control jobs (load, unload, stop) go first, then
    the images wanted on screen, in order."""

    loaded = Signal(object, object, object)   # path, key, names
    loadFailed = Signal(object, str)          # path, why
    ready = Signal(object)                    # image path: its row is in the store
    failed = Signal(object, str)              # image path, why

    def __init__(self):
        super().__init__()                            # no parent: it may outlive its session
        self._cond = threading.Condition()
        self._control: collections.deque = collections.deque()
        self._screen: list[Wanted] = []
        self._store: PredictionStore | None = None
        self._predictor = None

    # -- asked from the GUI thread ----------------------------------------------------

    def load(self, factory: Callable, path: Path) -> None:
        self._put(("load", factory, path))

    def unload(self) -> None:
        self.want(None, [])
        self._put(("unload",))

    def stop(self) -> None:
        self.want(None, [])
        self._put(("stop",))

    def want(self, store: PredictionStore | None, items: list[Wanted]) -> None:
        """Replace the images wanted on screen: the first is the one shown."""
        with self._cond:
            self._store, self._screen = store, list(items)
            self._cond.notify()

    def _put(self, job) -> None:
        with self._cond:
            self._control.append(job)
            self._cond.notify()

    # -- on the thread ---------------------------------------------------------------------

    def run(self) -> None:
        while True:
            with self._cond:
                while not self._control and not (self._screen and self._predictor is not None):
                    self._cond.wait()
                if self._control:
                    job, item, store = self._control.popleft(), None, None
                else:
                    job, item, store = None, self._screen.pop(0), self._store
            if job is not None:
                if job[0] == "stop":
                    self._close()
                    return
                if job[0] == "unload":
                    self._close()
                else:
                    self._load(*job[1:])
            elif store is not None:
                self._predict(store, *item)

    def _close(self) -> None:
        if self._predictor is not None:
            self._predictor.close()
            self._predictor = None

    def _load(self, factory, path: Path) -> None:
        self._close()
        try:
            predictor = factory(path)
        except ModelError as e:
            self.loadFailed.emit(path, str(e))
            return
        except Exception as e:                        # whatever a factory raises: say it
            self.loadFailed.emit(path, f"{Path(path).name} could not be loaded: {e}")
            return
        self._predictor = predictor
        self.loaded.emit(path, predictor.key, predictor.names)

    def _predict(self, store: PredictionStore, rel: str, path: Path, stamp: Stamp) -> None:
        key = self._predictor.key
        if store.get(key, rel, stamp) is not None:
            return                                    # asked again while it was in hand
        [found] = self._predictor.predict([path])
        if isinstance(found, Failure):
            self.failed.emit(path, found.why)
            return
        store.put(key, rel, stamp, found)
        self.ready.emit(path)


class ModelSession(QObject):
    """The loaded model as the GUI sees it: its state, its class map and threshold for the
    open root, and the predictions for an image, read from the store."""

    changed = Signal()                  # the state, the model, the threshold or the map
    ready = Signal(object)              # image path: predictions for it are in the store
    failed = Signal(object, str)        # image path, why

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.factory: Callable = UltralyticsPredictor
        self.state = "none"             # none, loading, ready or failed
        self.path: Path | None = None
        self.key: str | None = None
        self.names: tuple[str, ...] = ()
        self.error = ""
        self.class_map: ClassMap | None = None
        self._failures: dict[Path, str] = {}
        self._worker: _Worker | None = None        # runs while a model is loaded or loading
        session.cursorChanged.connect(self.want_screen)
        session.opened.connect(self._opened)

    # -- the model ----------------------------------------------------------------------

    def load(self, path) -> None:
        """Load a weights file on the thread; `changed` says when it is ready or failed."""
        self.state, self.path, self.key, self.names, self.error = "loading", Path(path), None, (), ""
        self.class_map, self._failures = None, {}
        if self._worker is None:
            self._worker = self._start_worker()
        self._worker.want(None, [])
        self._worker.load(self.factory, Path(path))
        self.changed.emit()

    def unload(self) -> None:
        """Let the model go: its thread stops, waiting at most SHUTDOWN_MS."""
        self._stop_worker()
        self._forget()

    def _start_worker(self) -> _Worker:
        worker = _Worker()
        worker.loaded.connect(self._loaded)
        worker.loadFailed.connect(self._load_failed)
        worker.ready.connect(self._ready)
        worker.failed.connect(self._failed)
        worker.start()
        return worker

    def _stop_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is None:
            return
        for signal, slot in ((worker.loaded, self._loaded), (worker.loadFailed, self._load_failed),
                             (worker.ready, self._ready), (worker.failed, self._failed)):
            signal.disconnect(slot)                   # a late answer is for a dataset now gone
        worker.stop()
        if not worker.wait(SHUTDOWN_MS):
            _FINISHING.add(worker)
        for done in [w for w in _FINISHING if w.isFinished()]:
            _FINISHING.discard(done)

    def _forget(self) -> None:
        self.state, self.path, self.key, self.names, self.error = "none", None, None, (), ""
        self.class_map, self._failures = None, {}
        self.changed.emit()

    def _loaded(self, path, key, names) -> None:
        if path != self.path or self.state != "loading":
            return                                    # superseded by another load or unload
        self.state, self.key, self.names = "ready", key, tuple(names)
        ws = self.session.workspace
        if ws is not None:
            self.class_map = load_class_map(ws.root_settings, self.names, ws.dataset.names)
            ws.opening_settings.set(MODEL_PATH, str(path))
        settings = self.session.settings
        recent = [str(path)] + [p for p in settings.get(RECENT_MODELS) if p != str(path)]
        settings.set(RECENT_MODELS, recent[:RECENT_MAX])
        self.session.saver.schedule()
        self.changed.emit()
        self.want_screen()

    def _load_failed(self, path, why: str) -> None:
        if path != self.path:
            return
        self.state, self.error = "failed", why
        self.session.notice.emit("error", why, None)
        self.changed.emit()

    # -- for the open dataset ---------------------------------------------------------

    def _opened(self) -> None:
        stored = self.session.workspace.opening_settings.get(MODEL_PATH)
        if stored and Path(stored).is_file():
            self.load(stored)
        elif self.key is not None:
            self.class_map = load_class_map(self.session.workspace.root_settings, self.names,
                                            self.session.workspace.dataset.names)
            self.changed.emit()

    def release(self) -> None:
        """The dataset closes: nothing more is asked of its store, and the model goes, so
        that the next dataset loads its own."""
        if self._worker is not None or self.state != "none":
            self.unload()

    def shutdown(self) -> None:
        """The app quits: as release, the thread waited for at most SHUTDOWN_MS."""
        self.release()

    @property
    def conf(self) -> float:
        ws = self.session.workspace
        return ws.root_settings.get(PRED_CONF) if ws is not None else PRED_CONF.default

    def set_conf(self, value: float) -> None:
        """The threshold for this root; nothing below the floor is offered (ValueError)."""
        self.session.workspace.root_settings.set(PRED_CONF, float(value))
        self.session.saver.schedule()
        self.changed.emit()

    def set_class_map(self, cmap: ClassMap) -> None:
        self.class_map = cmap
        save_class_map(self.session.workspace.root_settings, cmap)
        self.session.saver.schedule()
        self.changed.emit()

    # -- predictions --------------------------------------------------------------------------

    def predictions(self, entry: ImageEntry) -> list[Prediction] | None:
        """What the model found on this image at the floor; None when it has not looked
        (or no model is loaded)."""
        ws = self.session.workspace
        if self.state != "ready" or ws is None:
            return None
        try:
            stamp = image_stamp(entry.path)
        except OSError:
            return None
        return ws.predictions.get(self.key, entry.rel, stamp)

    def shown(self, entry: ImageEntry) -> list[Shown] | None:
        """The predictions as shown: above the threshold, translated, missing or not."""
        preds = self.predictions(entry)
        if preds is None:
            return None
        ws = self.session.workspace
        return shown_predictions(preds, self.session.labels(entry), self.class_map, ws.dataset, self.conf)

    def failure(self, entry: ImageEntry) -> str | None:
        return self._failures.get(entry.path)

    def want_screen(self) -> None:
        """Ask for the image on screen, then its neighbours, of those not yet in the store."""
        session, ws = self.session, self.session.workspace
        queue = session.queue
        if (self.state != "ready" or self._worker is None or ws is None or queue is None
                or queue.position() is None):
            return
        i, items = queue.position(), queue.items
        wanted = []
        for j in (i, *(i + d for d in NEIGHBOURS)):
            if not 0 <= j < len(items):
                continue
            entry = items[j].entry
            if entry.path in self._failures:
                continue
            try:
                stamp = image_stamp(entry.path)
            except OSError:
                continue
            if ws.predictions.get(self.key, entry.rel, stamp) is None:
                wanted.append((entry.rel, entry.path, stamp))
        self._worker.want(ws.predictions, wanted)

    def _ready(self, path) -> None:
        self.ready.emit(path)

    def _failed(self, path, why: str) -> None:
        self._failures[path] = why
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self.session.notice.emit("error", f"{item.key}: the model could not predict ({why})", path)
        self.failed.emit(path, why)
