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
PASS_BATCH = 8          #: images a pass asks the model for at once, decoded in parallel
PASS_WALK = 500         #: images a pass step looks at, at most: a resumed pass over 45k inferred took 0.16 s

Wanted = tuple[str, Path, Stamp]   #: (dataset-relative path, file, stamp)

#: Threads let go of while a prediction was still in hand: kept until they finish, since Qt
#: aborts the process when a running QThread is destroyed.
_FINISHING: set = set()


def threads_running() -> bool:
    """Whether a thread let go of is still running. The process must then end without
    destroying it (os._exit), or Qt aborts it."""
    for done in [w for w in _FINISHING if w.isFinished()]:
        _FINISHING.discard(done)
    return bool(_FINISHING)


class _Worker(QThread):
    """The thread that owns the predictor. Control jobs (load, unload, stop) go first, then
    the images wanted on screen, in order, then a batch of the dataset pass."""

    loaded = Signal(object, object, object)   # path, key, names
    loadFailed = Signal(object, str)          # path, why
    ready = Signal(object)                    # image path: its row is in the store
    failed = Signal(object, str)              # image path, why
    passProgress = Signal(int, int)           # queue images walked, of how many
    passEnded = Signal(int, int, bool)        # inferred, failed, cancelled

    def __init__(self):
        super().__init__()                            # no parent: it may outlive its session
        self._cond = threading.Condition()
        self._control: collections.deque = collections.deque()
        self._screen: list[Wanted] = []
        self._store: PredictionStore | None = None
        self._predictor = None
        self._known: dict[str, Stamp] | None = None    # the store's rows for this model, once a pass asks
        self._pass: collections.deque = collections.deque()
        self._pass_store: PredictionStore | None = None
        self._passing = self._pass_cancelled = False
        self._walked = self._total = self._inferred = self._failed = 0

    # -- asked from the GUI thread ----------------------------------------------------

    def load(self, factory: Callable, path: Path) -> None:
        with self._cond:
            self._pass.clear()                        # a pass is the old model's: it ends here
            self._passing = False
        self._put(("load", factory, path))

    def unload(self) -> None:
        self.want(None, [])
        self._put(("unload",))

    def start_pass(self, store: PredictionStore, items: list[tuple[str, Path]]) -> None:
        """Infer these (dataset-relative path, file) in order, those the store has no row
        for, after whatever the screen wants."""
        with self._cond:
            self._pass_store, self._pass = store, collections.deque(items)
            self._passing, self._pass_cancelled = True, False
            self._walked, self._total, self._inferred, self._failed = 0, len(items), 0, 0
            self._cond.notify()

    def cancel_pass(self) -> None:
        """Stop after the batch in hand; what it inferred is kept. passEnded says so."""
        with self._cond:
            if self._passing:
                self._pass.clear()
                self._pass_cancelled = True
                self._cond.notify()

    def stop(self) -> None:
        """Stop after the job in hand: a load queued but not started is dropped."""
        self.want(None, [])
        with self._cond:
            self._pass.clear()
            self._passing = False
            self._control.clear()
            self._control.append(("stop",))
            self._cond.notify()

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
                while not self._control and not ((self._screen or self._passing) and self._predictor is not None):
                    self._cond.wait()
                if self._control:
                    job, item, store = self._control.popleft(), None, None
                elif self._screen:
                    job, item, store = None, self._screen.pop(0), self._store
                else:
                    job, item, store = ("pass",), None, None
            if job is not None:
                if job[0] == "stop":
                    self._close()
                    return
                if job[0] == "pass":
                    self._pass_step()
                elif job[0] == "unload":
                    self._close()
                else:
                    self._load(*job[1:])
            elif store is not None:
                try:
                    self._predict(store, *item)
                except Exception as e:                # whatever the model raises: that image fails
                    self.failed.emit(item[1], str(e))

    def _close(self) -> None:
        self._known = None
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
            self.loadFailed.emit(path, f"{Path(path).name} failed to load: {e}")
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
        try:
            store.put(key, rel, stamp, found)
        except Exception as e:                        # the disk full, the store broken
            self.failed.emit(path, f"predictions not stored: {e}")
            return
        if self._known is not None:
            self._known[rel] = stamp                  # a pass under way skips it
        self.ready.emit(path)

    def _pass_step(self) -> None:
        """One batch of the pass: up to PASS_BATCH images the store has no row for, asked
        at once and written in one transaction, so a cancel keeps every batch done."""
        store, key = self._pass_store, self._predictor.key
        if self._known is None:
            self._known = store.inferred(key)
        todo, looked = [], 0
        while len(todo) < PASS_BATCH and looked < PASS_WALK:
            with self._cond:
                if not self._pass or (self._screen and looked):
                    break                           # the image on screen goes ahead of the walk
                rel, path = self._pass.popleft()
            looked += 1
            self._walked += 1
            try:
                stamp = image_stamp(path)
            except OSError as e:
                self._failed += 1
                self.failed.emit(path, f"unreadable: {e.strerror or e}")
                continue
            if self._known.get(rel) != stamp:
                todo.append((rel, path, stamp))
        if todo:
            try:
                answers = self._predictor.predict([path for _, path, _ in todo])
            except Exception as e:                    # whatever the model raises: the batch fails
                answers = [Failure(str(e))] * len(todo)
            rows = [(rel, stamp, found) for (rel, _, stamp), found in zip(todo, answers)
                    if not isinstance(found, Failure)]
            try:
                store.put_many(key, rows)
            except Exception as e:                    # the disk full, the store broken
                answers = [Failure(f"predictions not stored: {e}")] * len(todo)
            for (rel, path, stamp), found in zip(todo, answers):
                if isinstance(found, Failure):
                    self._failed += 1
                    self.failed.emit(path, found.why)
                else:
                    self._inferred += 1
                    self._known[rel] = stamp
                    self.ready.emit(path)
        self.passProgress.emit(self._walked, self._total)
        with self._cond:
            if self._pass or not self._passing:
                return
            self._passing = False
            ended = (self._inferred, self._failed, self._pass_cancelled)
        self.passEnded.emit(*ended)


class ModelSession(QObject):
    """The loaded model as the GUI sees it: its state, its class map and threshold for the
    open root, and the predictions for an image, read from the store."""

    changed = Signal()                  # the state, the model, the threshold or the map
    ready = Signal(object)              # image path: predictions for it are in the store
    failed = Signal(object, str)        # image path, why
    progress = Signal()                 # the dataset pass moved on

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.factory: Callable = UltralyticsPredictor
        self.state = "none"             # none, loading, ready or failed
        self.path: Path | None = None
        self._on_screen: Path | None = None     # the image want_screen last saw on screen
        self.key: str | None = None
        self.names: tuple[str, ...] = ()
        self.error = ""
        self.class_map: ClassMap | None = None
        self._failures: dict[Path, str] = {}
        self._known: set[str] = set()               # images the store has a row for, by rel
        self.passing = False
        self.pass_walked = self.pass_total = 0
        self._worker: _Worker | None = None        # runs while a model is loaded or loading
        session.cursorChanged.connect(self.want_screen)
        session.opened.connect(self._opened)

    # -- the model ----------------------------------------------------------------------

    def load(self, path) -> None:
        """Load a weights file on the thread; `changed` says when it is ready or failed."""
        if self.passing:
            self.session.notice.emit("info", "inferring stopped: another model loaded", None)
        self.state, self.path, self.key, self.names, self.error = "loading", Path(path), None, (), ""
        self.class_map, self._failures, self.passing = None, {}, False
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
        worker.passProgress.connect(self._pass_progress)
        worker.passEnded.connect(self._pass_ended)
        worker.start()
        return worker

    def _stop_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is None:
            return
        for signal, slot in ((worker.loaded, self._loaded), (worker.loadFailed, self._load_failed),
                             (worker.ready, self._ready), (worker.failed, self._failed),
                             (worker.passProgress, self._pass_progress), (worker.passEnded, self._pass_ended)):
            signal.disconnect(slot)                   # a late answer is for a dataset now gone
        worker.stop()
        if not worker.wait(SHUTDOWN_MS):
            _FINISHING.add(worker)
        for done in [w for w in _FINISHING if w.isFinished()]:
            _FINISHING.discard(done)

    def _forget(self) -> None:
        self.state, self.path, self.key, self.names, self.error = "none", None, None, (), ""
        self.class_map, self._failures, self._known = None, {}, set()
        self.passing = False
        self.changed.emit()

    def _loaded(self, path, key, names) -> None:
        if path != self.path or self.state != "loading":
            return                                    # superseded by another load or unload
        self.state, self.key, self.names = "ready", key, tuple(names)
        ws = self.session.workspace
        if ws is not None:
            self.class_map = load_class_map(ws.root_settings, self.names, ws.dataset.names)
            ws.opening_settings.set(MODEL_PATH, str(path))
            self._known = set(ws.predictions.inferred(key))
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
        elif self.key is not None:                  # loaded before this dataset opened: it is this one's now
            ws = self.session.workspace
            self.class_map = load_class_map(ws.root_settings, self.names, ws.dataset.names)
            ws.opening_settings.set(MODEL_PATH, str(self.path))
            self._known = set(ws.predictions.inferred(self.key))
            self.session.saver.schedule()
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
        save_class_map(self.session.workspace.root_settings, cmap, self.session.workspace.dataset.names)
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
        arrived, before = items[i].entry.path, self._on_screen   # re-shown, not arrived: said already
        wanted = []
        for j in (i, *(i + d for d in NEIGHBOURS)):
            if not 0 <= j < len(items):
                continue
            entry = items[j].entry
            if entry.path in self._failures:
                if j == i and entry.path != before:  # failed out of sight: said on arrival
                    session.notice.emit("error", f"{entry.rel}: prediction failed — {self._failures[entry.path]}", entry.path)
                continue
            try:
                stamp = image_stamp(entry.path)
            except OSError:
                continue
            if ws.predictions.get(self.key, entry.rel, stamp) is None:
                wanted.append((entry.rel, entry.path, stamp))
        self._on_screen = arrived
        self._worker.want(ws.predictions, wanted)

    # -- the dataset pass ---------------------------------------------------------------------

    def infer_queue(self) -> None:
        """Infer the queue's images, in queue order, that the store has no row for."""
        session, ws = self.session, self.session.workspace
        queue = session.queue
        if self.state != "ready" or ws is None or queue is None or not queue.complete or self.passing:
            return
        # A model queue also needs the images it left out as not inferred: inferred, they
        # can join it (docs/design/2026-10-06-filters.md#building-and-keeping-current).
        waiting = queue.left_out.get("not inferred", set())
        items = [(e.rel, e.path) for e in ws.dataset.images if queue.has_image(e.rel) or e.rel in waiting]
        self.passing, self.pass_walked, self.pass_total = True, 0, len(items)
        self._worker.start_pass(ws.predictions, items)
        self.changed.emit()

    def cancel_pass(self) -> None:
        if self.passing and self._worker is not None:
            self._worker.cancel_pass()

    def inferred_count(self) -> tuple[int, int] | None:
        """How many of the queue's images the store has a row for, of how many. A model
        queue's images left out as not inferred count too: a pass is what they wait for."""
        queue = self.session.queue
        if queue is None:
            return None
        waiting = len(queue.left_out.get("not inferred", ()))
        images = {item.entry.rel for item in queue.items}       # a findings queue: several to an image
        return sum(1 for rel in images if rel in self._known), len(images) + waiting

    def _pass_progress(self, walked: int, total: int) -> None:
        self.pass_walked, self.pass_total = walked, total
        self.progress.emit()

    def _pass_ended(self, inferred: int, failed: int, cancelled: bool) -> None:
        if not self.passing:
            return                                    # queued before a switch: a pass of a dataset gone
        self.passing = False
        said = f"{inferred:,} inferred, {failed:,} failed"
        self.session.notice.emit("info", f"inferring stopped: {said}" if cancelled
                                 else f"{'⚠' if failed else '✓'} {said}", None)
        self.changed.emit()

    def _current(self, path):
        """The open dataset's entry for an answer's image, or None for a stale answer: the
        thread answers in order, so one queued before a switch comes while the next model
        loads, or names an image of a dataset since closed."""
        ws = self.session.workspace
        if ws is None or self.state != "ready":
            return None
        try:
            return ws.dataset.entry(path)
        except KeyError:
            return None

    def _ready(self, path) -> None:
        entry = self._current(path)
        if entry is None:
            return
        self._known.add(entry.rel)
        self._failures.pop(path, None)                # stored since: no longer failed
        self.ready.emit(path)

    def _failed(self, path, why: str) -> None:
        if self._current(path) is None:
            return
        self._failures[path] = why
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self.session.notice.emit("error", f"{item.entry.rel}: prediction failed — {why}", path)
        self.failed.emit(path, why)
