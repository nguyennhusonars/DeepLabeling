"""The GUI thread's hold on one open dataset: the workspace, its queue, the jobs that
feed them, and every action that changes labels or review marks
(docs/design/2026-10-04-app-foundation.md).

Widgets read from the session and call its methods; they never reach into the core's
store, editor or files. Dialogs go through a Prompter, so tests answer them without a
modal event loop. The session is created, and opens datasets, on the GUI thread, which
therefore owns the LabelStore's write path (spec: Notes for plan 1b).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.crops import crop_rect
from ..core.dataset import DatasetError, ImageEntry
from ..core.edits import CreateEmpty, Edit, Intent, Refused
from ..core.findings import KINDS, Findings
from ..core.queue import BuildContext, ImageFilter, ModelSnapshot, Queue, QueueItem, Scanned, source_from_json
from ..core.state import Locked
from ..core.store import ImageLabels, LabelState
from ..core.taxonomy import count_out_of_range
from ..core.workspace import CLASS_COLORS, CLASS_HOTKEYS, QUEUE_CURSOR, QUEUE_SOURCE, OpenCancelled, Workspace
from . import chunked
from .chunked import Chunked
from .classes import assign_classes
from .findview import finding_text
from .images import THUMB_BYTES, Crop, ImageCache, decode_thumb, decode_tile
from .model import ModelSession
from .settings_ui import Saver, global_settings, remember_source
from .workers import Jobs

#: The key of the standing notice about ids the yaml does not name.
OUT_OF_RANGE = "out-of-range"
#: How often the image on screen has its label file re-checked for outside changes.
WATCH_MS = 1500
_UNREAD = object()      #: crop_of's size, when the caller has not read it


#: What a build could not settle, as the queue chip says it.
UNSETTLED = {
    "could not be sized": lambda n: f"{n:,} unsized" ,
    "not inferred": lambda n: f"{n:,} not inferred",
    "labels unreadable": lambda n: f"{n:,} unreadable",
}


class Prompter(Protocol):
    """The dialogs the session needs. The window's prompter adds the ones it needs."""

    def confirm_taxonomy(self, last_source: str, last_names: list[str],
                         source: str, names: tuple[str, ...]) -> bool: ...

    def error(self, title: str, text: str) -> None: ...

    def progress(self, title: str, total: int): ...

    def confirm_queue_accept(self, text: str) -> bool: ...

    def ask_reassign(self, names, unnamed_ids) -> tuple[int, int] | None: ...

    def confirm_reassign(self, text: str) -> bool: ...


class Session(QObject):
    opened = Signal()
    closed = Signal()
    labelsChanged = Signal(object)      # tuple[Path, ...]: images whose label file changed
    historyChanged = Signal()
    written = Signal()                  # an edit, undo or redo wrote label files (an outside change is not)
    reviewChanged = Signal()
    queueReset = Signal()               # a new queue replaced the old one
    queueGrew = Signal()                # items were appended to the queue
    queueDone = Signal()                # the queue finished building
    itemsChanged = Signal(object)       # list[str]: keys whose badge or tick may differ
    cursorChanged = Signal()
    itemInserted = Signal(int)          # a row joined the queue after its build
    notice = Signal(str, str, object)   # level, text, image Path or None
    standing = Signal(str, str)         # key, text: a notice that stays; "" removes it
    status = Signal(str)                # a passing message for the status bar
    _reloaded = Signal(object)          # emitted from any thread, delivered queued

    def __init__(self, prompter: Prompter, parent=None):
        super().__init__(parent)
        self.prompter = prompter
        self.settings_file, self.settings = global_settings()
        self.workspace: Workspace | None = None
        self.queue: Queue | None = None
        self.io = Jobs(2)
        self.images = ImageCache(Jobs(2), parent=self)
        self.thumbs = ImageCache(Jobs(2), THUMB_BYTES, decode=decode_thumb, parent=self)
        self.crops = ImageCache(Jobs(2), THUMB_BYTES, decode=decode_tile, parent=self, key=Crop.of)
        self.saver = Saver(self._save, parent=self)
        self._build = None
        self._by_rel: dict[str, ImageEntry] = {}
        self.unnamed_ids: tuple[int, ...] = ()      #: class ids the labels hold that the yaml does not name
        self._follow: ImageEntry | QueueItem | None = None  # where a rebuilding queue must land
        self._seen: tuple | None = None             # (image, raw, state) last reported on screen
        self._keys: frozenset[str] | None = None    # review marks, snapshotted until they change
        self._reloaded.connect(lambda image: self.labelsChanged.emit((image,)))
        self.labelsChanged.connect(self._recheck)
        # The store notices an outside edit when its file is next read; reading the one on
        # screen now and then (a stat, unless it changed) makes it appear without a click.
        self._watch = QTimer(self)
        self._watch.setInterval(WATCH_MS)
        self._watch.timeout.connect(self.check_current)
        self._watch.start()
        self.running: Chunked | None = None         # a long write under way (ui/chunked.py)
        self._running_title = ""
        self._arrived: set[Path] = set()           # predictions that came while a model queue built
        self._closing = False                       # the model goes with the dataset: nothing to rebuild
        self.model = ModelSession(self, self)
        self.model.changed.connect(self._model_changed)
        self.model.ready.connect(self._predicted)

    # -- opening and closing -----------------------------------------------

    def open(self, source, labels=None) -> bool:
        """Open a dataset, closing the current one first (a root opens once). If the new
        one cannot be opened, the previous one is reopened."""
        previous = self.current_source()
        self.close()
        if self._open(source, labels, quiet=False):
            return True
        if previous is not None:
            self._open(*previous, quiet=True)
        return False

    def current_source(self) -> tuple[str, str | None] | None:
        if self.workspace is None:
            return None
        dataset = self.workspace.dataset
        return str(dataset.source), str(dataset.labels) if dataset.labels else None

    def _open(self, source, labels, *, quiet: bool) -> bool:
        try:
            ws = Workspace.open(source, labels, confirm_taxonomy=self.prompter.confirm_taxonomy,
                                on_labels_changed=self._wrote,
                                on_history_changed=self.historyChanged.emit,
                                on_reload=self._reloaded.emit)
        except OpenCancelled:
            return False
        except (DatasetError, Locked, OSError) as e:
            if not quiet:
                self.prompter.error("Cannot open the dataset", str(e))
            return False
        self.workspace = ws
        self._by_rel = {e.rel: e for e in ws.dataset.images}
        self._follow = self._seen = self._keys = None
        root = ws.root_settings
        colors, hotkeys = assign_classes(ws.dataset.names, root.get(CLASS_COLORS), root.get(CLASS_HOTKEYS))
        root.set(CLASS_COLORS, colors)
        root.set(CLASS_HOTKEYS, hotkeys)
        remember_source(self.settings, *self.current_source())
        self.saver.schedule()
        self.opened.emit()
        for warning in ws.warnings:
            self.notice.emit("warning", warning, None)
        if ws.dataset.missing:
            listed = ", ".join(str(p) for p in ws.dataset.missing)
            self.notice.emit("warning", f"listed in {ws.dataset.source.name} but missing: {listed}", None)
        self._count_out_of_range()
        self._restore_queue()
        return True

    def _wrote(self, images) -> None:
        """The editor wrote these images' label files."""
        self.labelsChanged.emit(images)
        self.written.emit()

    def close(self) -> None:
        ws = self.workspace
        if ws is None:
            return
        if self.running is not None:
            self.running.stop()                     # between two chunks: nothing half-written
        self.io.cancel_all()
        self._closing = True
        try:
            self.model.release()                    # before the store it writes to closes
        finally:
            self._closing = False
        self.images.clear()
        self.thumbs.clear()
        self.crops.clear()
        self.io.wait(2000)
        self.workspace, self.queue, self._build, self._by_rel = None, None, None, {}
        self._follow = self._seen = self._keys = None
        self.unnamed_ids = ()
        try:
            ws.close()
        except OSError as e:
            self.prompter.error("Could not save the review marks", str(e))
        self._save()
        self.closed.emit()
        self.standing.emit(OUT_OF_RANGE, "")

    def _save(self) -> None:
        try:
            if self.workspace is not None:
                self.workspace.save()
            self.settings_file.save()
        except OSError as e:
            self.notice.emit("error", f"could not save settings: {e}", None)

    def _require(self) -> Workspace:
        if self.workspace is None:
            raise RuntimeError("no dataset is open")
        return self.workspace

    # -- the queue -----------------------------------------------------------

    def _restore_queue(self) -> None:
        opening = self._require().opening_settings
        try:
            stored = opening.get(QUEUE_SOURCE)
            source = source_from_json(stored) if stored else ImageFilter()
        except ValueError:
            source = ImageFilter()
        cursor = opening.get(QUEUE_CURSOR)
        # An image's key is its rel, which may hold a "#"; a finding's is rel#line#kind.
        entry = (self._by_rel.get(cursor) or self._by_rel.get(cursor.rsplit("#", 2)[0])) if cursor else None
        self.set_queue(source, follow=QueueItem(cursor, entry) if entry is not None else None)

    def set_queue(self, source, follow: ImageEntry | QueueItem | None = None) -> None:
        """Rebuild the queue from `source` (images, or findings), keeping the cursor on its
        item if it is still in."""
        ws = self._require()
        if self._build is not None:
            self._build.cancel()
        if follow is None:
            # A rebuild that has not yet reached the user's place still owes it: follow
            # that, not the item the unfinished queue happens to show.
            follow = self._follow or self.current()
        self._follow = follow
        queue = self.queue = Queue(source, follow=follow)
        queue.built_with = self._model_identity()
        queue.waiting = source.needs_model and queue.built_with is None    # built when a model is ready
        self._arrived = set()
        ws.opening_settings.set(QUEUE_SOURCE, source.to_json())
        self.saver.schedule()
        self.queueReset.emit()
        self.cursorChanged.emit()
        if queue.waiting:
            if self.model.state != "loading":
                self.notice.emit("warning", "this queue needs a model — load one", None)
            return
        ctx = self.context()
        self._build = self.io.start(
            lambda emit, cancelled: source.build(ctx, emit, cancelled,
                                                 progress=lambda done, total: emit(Scanned(done, total))),
            batch=lambda items: self._grew(queue, items),
            done=lambda finished: self._built(queue, finished, left_out=ctx.left_out),
            failed=lambda why: self._build_failed(queue, why, ctx.left_out))

    def _model_identity(self):
        """What a model queue's build depends on: the model and its class map."""
        model = self.model
        return (model.key, model.class_map) if model.state == "ready" else None

    def _model_changed(self) -> None:
        """A model queue is rebuilt when the model or its class map changes, and built
        once a model it waited for is ready; a threshold change leaves it as it is."""
        queue = self.queue
        if (not self._closing and queue is not None and self.workspace is not None and queue.source.needs_model
                and self._model_identity() != queue.built_with):
            self.set_queue(queue.source)

    def _predicted(self, path) -> None:
        """Predictions arrived for an image: a model queue re-tests it, and an image it
        left out as not inferred joins it, in dataset order, if it now matches."""
        queue, ws = self.queue, self.workspace
        if queue is None or ws is None or not queue.source.needs_model:
            return
        try:
            entry = ws.dataset.entry(path)
        except KeyError:
            return
        if queue.has_image(entry.rel):
            self._recheck((path,))
            return
        if not queue.complete:
            if not queue.waiting:
                self._arrived.add(path)             # settled when the build has said what it left out
            return
        waiting = queue.left_out.get("not inferred")
        if not waiting or entry.rel not in waiting:
            return
        waiting.discard(entry.rel)
        empty = queue.cursor is None
        for item in queue.source.items_for(entry, self.context()):     # an image, or its findings
            row = queue.insert(item)
            if row is not None:
                self.itemInserted.emit(row)
        if empty and queue.cursor is not None:
            self._cursor_moved()                    # the first item of an empty queue: shown
        self.queueGrew.emit()

    def context(self) -> BuildContext:
        """The inputs of a build or a recheck. The review marks are snapshotted once and
        reused until they change: an import underneath the app reports thousands of
        changed files, and a fresh snapshot each time froze the GUI for seconds."""
        ws, model = self._require(), self.model
        if self._keys is None:
            self._keys = ws.review.keys()
        snapshot = (ModelSnapshot(model.key, ws.predictions, model.class_map)
                    if model.state == "ready" and model.class_map is not None else None)
        return BuildContext(ws.dataset, ws.store, self._keys, sizes=ws.sizes, model=snapshot,
                            dismissed=ws.dismissals.snapshot())

    def _grew(self, queue: Queue, items: list[QueueItem]) -> None:
        if queue is not self.queue:
            return                                  # a cancelled build's last batch
        if isinstance(items, Scanned):
            queue.scanned = items
            self.queueGrew.emit()
            return
        before = queue.cursor
        queue.extend(items)
        if self._follow is not None and not queue.following:
            self._follow = None                     # the user's place has arrived
        self.queueGrew.emit()
        if queue.cursor != before:
            self._cursor_moved()

    def _build_failed(self, queue: Queue, why: str, left_out=None) -> None:
        self.notice.emit("error", f"the queue could not be built: {why}", None)
        self._built(queue, True, failed=why, left_out=left_out)

    def _built(self, queue: Queue, finished: bool, failed: str | None = None, left_out=None) -> None:
        if queue is not self.queue or not finished:
            return
        if left_out:
            queue.left_out = {what: set(rels) for what, rels in left_out.items()}
        before = queue.cursor
        if failed is None:
            queue.finish()
        else:
            queue.fail(failed)
        self._follow = None                         # finish() settled the place
        self.queueDone.emit()
        if queue.cursor != before:
            self._cursor_moved()
        arrived, self._arrived = self._arrived, set()
        for path in arrived:
            self._predicted(path)

    def current(self) -> QueueItem | None:
        return self.queue.current() if self.queue is not None else None

    def move(self, delta: int) -> bool:
        if self.queue is not None and len(self.queue):
            self._follow = None                     # the user chose a place
        if self.queue is None or not self.queue.move(delta):
            if self.queue is not None and len(self.queue):
                self.status.emit("end of the queue" if delta > 0 else "start of the queue")
            return False
        self._cursor_moved()
        return True

    def go_to(self, key: str) -> bool:
        if self.queue is None or not self.queue.go_to(key):
            return False
        self._follow = None                         # the user chose a place
        self._cursor_moved()
        return True

    def go_to_text(self, text: str) -> bool:
        """Go to an item by its 1-based number, or the first whose path contains the text."""
        if self.queue is None or not text.strip():
            return False
        text = text.strip()
        if text.isdigit() and 1 <= int(text) <= len(self.queue):
            return self.go_to(self.queue.items[int(text) - 1].key)
        match = next((it.key for it in self.queue.items if text.lower() in it.key.lower()), None)
        if match is None:
            self.status.emit(f"no item matches “{text}”")
            return False
        return self.go_to(match)

    def _cursor_moved(self) -> None:
        item = self.current()
        if item is not None and self.workspace is not None:
            if self._follow is None:                # never save a place the rebuild passes through
                self.workspace.opening_settings.set(QUEUE_CURSOR, item.key)
                self.saver.schedule()
            self.workspace.store.pin(item.entry.path)
            labels = self.workspace.store.get(item.entry.path)
            self._seen = (item.entry.path, labels.raw, labels.state, labels.writable)
            i, items = self.queue.position(), self.queue.items
            # want, not keep: an arrow held down passes images whose decodes, still waiting,
            # are cancelled -- otherwise the image on screen waits behind every one skipped.
            self.images.want([items[j].entry.path for j in (i, i + 1, i + 2, i - 1)
                              if 0 <= j < len(items)])
        self.cursorChanged.emit()

    def check_current(self) -> None:
        """Re-read the current image's label file, and report any change as labelsChanged.

        The store reports a reload only when it replaces a cached copy; a file that was
        missing (never cached) and now exists is caught here, against what was last shown.
        """
        item = self.current()
        if item is None or self.workspace is None:
            return
        labels = self.workspace.store.get(item.entry.path)      # may report a reload itself
        seen = (item.entry.path, labels.raw, labels.state, labels.writable)
        if self._seen is not None and self._seen[0] == seen[0] and self._seen != seen:
            self._seen = seen
            self.labelsChanged.emit((item.entry.path,))
        self._seen = seen

    def progress_text(self) -> str:
        """How the queue's build stands, for the chip and the panel: "" once built."""
        queue = self.queue
        if queue is None:
            return ""
        if queue.waiting:
            return " · waiting for the model" if self.model.state == "loading" else " · needs a model"
        if queue.failed is not None:
            return " · build failed"
        if not queue.complete:
            if queue.scanned is not None:
                return f" · scanning {queue.scanned.done:,} / {queue.scanned.total:,}"
            return " · building…"
        text = ""
        if isinstance(queue.source, Findings):
            counts = Counter(item.finding.kind for item in queue.items)
            text = "".join(f" · {counts[kind]:,} {kind}" for kind in KINDS if counts[kind])
        return text + "".join(f" · {UNSETTLED[what](len(rels))}" for what, rels in sorted(queue.left_out.items())
                              if rels and what in UNSETTLED)

    def left(self) -> int:
        if self.queue is None or self.workspace is None:
            return 0
        return self.queue.left(self.workspace.review.is_marked)

    # -- what the panels show ------------------------------------------------

    def labels(self, entry: ImageEntry) -> ImageLabels:
        return self._require().store.get(entry.path)

    def badge(self, item: QueueItem, labels: ImageLabels | None = None) -> str:
        if item.finding is not None:
            state = self.finding_state(item)
            return finding_text(item.finding, self._require().dataset) + (f" · {state}" if state else "")
        labels = self.labels(item.entry) if labels is None else labels
        if labels.state is LabelState.ERROR:
            text = "unreadable"
        elif labels.state is LabelState.SHARED:
            text = "read-only (shared)"             # an edit here would be refused: say so
        elif labels.raw is None:
            text = "missing"
        elif labels.negative:
            text = "negative"
        else:
            n = len(labels.boxes)
            text = f"{n} box" if n == 1 else f"{n} boxes"
        if not labels.writable and labels.state is not LabelState.SHARED:   # shared says read-only already
            text = f"read-only · {text}"
        if self.queue is not None and item.key in self.queue.stale:
            text += " · no longer matches"
        return text

    def finding_state(self, item: QueueItem) -> str:
        """"dismissed", "fixed" (it no longer holds), or "" for a finding still open."""
        f = item.finding
        if f is None:
            return ""
        if self._require().dismissals.has(item.entry.rel, f.text, f.kind):
            return "dismissed"
        return "fixed" if self.queue is not None and item.key in self.queue.stale else ""

    def dismiss_current(self) -> None:
        """D: dismiss the finding on screen and move on, or take its dismissal back."""
        item = self.current()
        if item is None or item.finding is None:
            return
        f = item.finding
        dismissed = self._require().dismissals.toggle(item.entry.rel, f.text, f.kind)
        self.saver.schedule()
        self.itemsChanged.emit([item.key])
        if dismissed:
            self.status.emit(f"dismissed: {f.kind}")
            self.move(1)
        else:
            self.status.emit("undismissed")

    def queue_not_whole(self) -> str:
        """Why the queue cannot stand for its images yet -- waiting for a model, building,
        or its build failed part-way -- or "" when it is whole."""
        queue = self.queue
        if queue is None:
            return "no queue"
        if queue.waiting:
            return "the queue waits for a model"
        if queue.failed is not None:
            return "the queue's build failed — rebuild it first"
        if not queue.complete:
            return "the queue is still building"
        return ""

    def recount_unnamed(self) -> None:
        """Count the class ids the yaml does not name again: after a reassign repaired some."""
        self._count_out_of_range()

    def queue_images(self) -> list[ImageEntry]:
        """The queue's images, each once, in queue order: a findings queue has an item per
        finding, several to an image (docs/design/2026-10-07-bulk-and-stats.md#the-queues-images)."""
        if self.queue is None:
            return []
        return list({item.entry.rel: item.entry for item in self.queue.items}.values())

    def crop_of(self, item: QueueItem, size=_UNREAD) -> Crop | None:
        """The crop a finding's tile shows; None for an image item, or when the image's
        header cannot be read -- its crop could not be decoded either. `size`: the image's,
        when the caller has read it already (None: it cannot be read)."""
        f = item.finding
        if f is None:
            return None
        if size is _UNREAD:
            size = self._require().sizes.get(item.entry.path)
        rect = None if size is None else crop_rect(f.label_box, f.model_box, *size)
        return None if rect is None else Crop(item.entry.path, rect)

    def describe_item(self, item: QueueItem) -> str:
        tick = "✓" if self._require().review.is_marked(item.entry.rel) else "·"
        return f"{tick} {item.entry.rel}  —  {self.badge(item)}"

    def reviewed_counts(self) -> tuple[int, int]:
        """Marks among THIS dataset's images: yamls sharing a root list different folders."""
        ws = self._require()
        marks = ws.review.marks
        return sum(1 for e in ws.dataset.images if e.rel in marks), len(ws.dataset.images)

    # -- review marks --------------------------------------------------------

    def done_and_next(self) -> None:
        item = self.current()
        if item is None:
            return
        if self._require().review.mark(item.entry.rel):
            self._review_changed([item.entry.rel])
        self.move(1)

    def toggle_reviewed(self) -> None:
        item = self.current()
        if item is None:
            return
        self._require().review.toggle(item.entry.rel)
        self._review_changed([item.entry.rel])

    def mark_reviewed(self, keys, left: int = 0) -> int:
        """Mark these images reviewed (the grid's mark page); how many were not already.
        `left` counts the tiles mark page passed over, for the message."""
        ws = self.workspace
        if ws is None:
            return 0
        rels = dict.fromkeys(self.queue.items[self.queue.index_of(key)].entry.rel for key in keys
                             if self.queue is not None and key in self.queue)
        newly = [rel for rel in rels if ws.review.mark(rel)]
        if newly:
            self._review_changed(newly)
            said = f"✓ {len(newly)} image{'' if len(newly) == 1 else 's'} reviewed"
        else:
            said = "all reviewed already"
        if left:
            said += (f"; {left} not shown yet, left unmarked")
        self.status.emit(said)
        return len(newly)

    def _review_changed(self, rels: list[str]) -> None:
        """These images' marks changed: every item they stand behind is redrawn."""
        self._keys = None                           # the marks snapshot is out of date
        self.saver.schedule()
        self.reviewChanged.emit()
        queue = self.queue
        self.itemsChanged.emit([key for rel in rels for key in queue.keys_of(rel)] if queue is not None else rels)

    # -- edits -----------------------------------------------------------------

    def apply(self, intent: Intent) -> Edit | None:
        """Every label change goes through here; a refusal becomes a notice."""
        ws = self._require()
        if self._busy():
            return None
        rel = ws.dataset.entry(intent.image).rel
        why = self.images.error(intent.image)
        if why is not None:
            self.notice.emit("error", f"{rel}: cannot decode ({why}) — not edited", intent.image)
            return None
        if self.images.get(intent.image) is None:
            # Until it is decoded, whether it CAN be decoded is unknown -- and "could not
            # read" must never become "no boxes" (legacy defect #2).
            self.notice.emit("error", f"{rel}: still loading — not edited yet", intent.image)
            return None
        try:
            edit = ws.editor.apply(intent)
        except Refused as e:
            self.notice.emit("error", f"{rel}: {e}", intent.image)
            return None
        if edit is not None:
            self._review_changed([rel])
        return edit

    def apply_many(self, intents: list[Intent], description: str) -> Edit | None:
        """Changes to many images as one edit that marks nothing: a grid action on
        several findings. None when refused, which a notice says."""
        ws = self._require()
        if self._busy():
            return None
        try:
            return ws.editor.apply_many(intents, description)
        except Refused as e:
            self.notice.emit("error", f"{description}: {e}", None)
            return None

    def mark_negative(self) -> None:
        item = self.current()
        if item is not None:
            self.apply(Intent(item.entry.path, (CreateEmpty(),), "mark negative"))

    def undo(self) -> None:
        self._step(undo=True)

    def redo(self) -> None:
        self._step(undo=False)

    def _busy(self) -> bool:
        """While a long write runs, nothing else edits; a key that would says so."""
        if self.running is None:
            return False
        self.status.emit(f"wait — {self._running_title[0].lower()}{self._running_title[1:]}")
        return True

    def run_chunked(self, title: str, total: int, step, end) -> None:
        """Run `step` a chunk per event-loop turn behind a progress dialog (ui/chunked.py)."""
        progress = self.prompter.progress(title, total)

        def ended(cancelled, error):
            self.running = None
            end(progress, cancelled, error)

        self._running_title = title
        self.running = Chunked(progress, lambda: step(progress), ended, self)

    def _step(self, *, undo: bool) -> None:
        ws = self.workspace
        if self._busy():
            return
        edit = None if ws is None else ws.history.peek_undo() if undo else ws.history.peek_redo()
        if edit is None:
            self.status.emit("nothing to undo" if undo else "nothing to redo")
            return
        image = edit.images[0]
        rel = ws.dataset.entry(image).rel
        current = self.current()
        if (self.queue is not None and self.queue.has_image(rel)
                and (current is None or current.entry.rel != rel)):
            self.go_to(self.queue.keys_of(rel)[0])  # the change happens in view
        if len(edit.changes) > chunked.CHUNK:
            self._restore_in_chunks(edit, undo)
            return
        try:
            (ws.editor.undo if undo else ws.editor.redo)()
        except Refused as e:
            self.notice.emit("error", str(e), image)
            return
        self.status.emit(f"{'↶' if undo else '↷'} {edit.description}: {rel}")

    def _restore_in_chunks(self, edit: Edit, undo: bool) -> None:
        """Undo (or redo) an edit across many images: every file checked, then written, a
        chunk at a time. Stopped part-way, what was written stays an edit of its own."""
        restoring = self._require().editor.restoring(undo=undo)
        verb, past = ("undo", "undone") if undo else ("redo", "redone")

        def step(progress) -> bool:
            if restoring.checked < restoring.total:
                restoring.check(chunked.CHUNK)
            else:
                restoring.write(chunked.CHUNK)
            progress.set(restoring.checked + restoring.written)
            return restoring.written < restoring.total

        def end(progress, cancelled, error) -> None:
            n, w = restoring.total, restoring.written
            if error is None and not cancelled:
                restoring.finish()
                self.status.emit(f"{'↶' if undo else '↷'} {edit.description}: {n:,} files")
            elif error is not None and restoring.dropped:
                self.notice.emit("error", str(error), None)     # a file changed since: it says what was dropped
            elif error is not None and restoring.checked < n:   # a file could not be read: nothing written
                self.notice.emit("error", f"cannot {verb} “{edit.description}”: {error} — {verb} again", None)
            elif error is not None:
                restoring.stop()
                self.notice.emit("error", f"cannot {verb} “{edit.description}”: {error} — {w:,} of {n:,} files {past}; "
                                 f"{verb} again for the rest", None)
            else:
                restoring.stop()
                self.status.emit(f"{verb} stopped at {w:,} of {n:,} files; {verb} again for the rest"
                                 if w else f"{verb} stopped: nothing written")

        self.run_chunked(f"{'Undoing' if undo else 'Redoing'} {edit.description}", 2 * restoring.total, step, end)

    def _recheck(self, images) -> None:
        if self.workspace is None:
            return
        item = self.current()
        if item is not None and item.entry.path in images:
            labels = self.workspace.store.get(item.entry.path)
            self._seen = (item.entry.path, labels.raw, labels.state, labels.writable)
        if self.queue is None:
            return
        ctx, keys = None, []
        for image in images:
            try:
                entry = self.workspace.dataset.entry(image)
            except KeyError:
                continue
            if not self.queue.has_image(entry.rel):
                continue
            ctx = ctx or self.context()
            self.queue.recheck(entry, ctx)
            keys.extend(self.queue.keys_of(entry.rel))
        if keys:
            self.itemsChanged.emit(keys)

    # -- the taxonomy guard ----------------------------------------------------

    def _count_out_of_range(self) -> None:
        ws = self._require()
        dataset, store = ws.dataset, ws.store

        def found(result) -> None:
            if self.workspace is ws and result is not None:
                self.unnamed_ids = result.ids
                self.standing.emit(OUT_OF_RANGE, result.message(dataset))

        self.io.start(lambda emit, cancelled: count_out_of_range(dataset, store, cancelled),
                      done=found,
                      failed=lambda why: self.notice.emit("error", f"checking class ids failed: {why}", None))
