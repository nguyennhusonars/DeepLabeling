"""The one owner of every image's labels in memory
(docs/design/2026-10-04-app-foundation.md#label-document-model).

`get` may be called from any thread. `apply` and `restore` write files and run
only on the thread that created the store: the GUI thread.
"""

from __future__ import annotations

import enum
import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .atomic import write_atomic
from .dataset import Dataset, ImageEntry
from .edits import Conflict, Edit, FileChange, Intent, LineRef, Refused, materialize
from .labelio import LabelLine, parse_label_bytes

#: (inode, mtime_ns, size). An atomic replace changes the inode, and a class
#: change keeps the size, so all three are compared.
Stamp = tuple[int, int, int]

_SHARED = "another image uses the same label file, so it is not edited here"


class LabelState(enum.Enum):
    MISSING = "missing"     #: no label file: not labelled yet
    OK = "ok"
    SHARED = "shared"       #: another image resolves to the same file; read-only
    ERROR = "error"         #: the file cannot be read; read-only


@dataclass(frozen=True)
class ImageLabels:
    image: Path
    label_path: Path
    state: LabelState
    raw: bytes | None = None
    lines: tuple[LabelLine, ...] = ()
    stamp: Stamp | None = None
    error: str = ""

    @property
    def editable(self) -> bool:
        return self.state in (LabelState.MISSING, LabelState.OK)

    @property
    def boxes(self) -> tuple[tuple[int, LabelLine], ...]:
        """(line index, line) for every parsed line."""
        return tuple((i, line) for i, line in enumerate(self.lines) if line.parsed)

    @property
    def unparsed(self) -> int:
        return sum(1 for line in self.lines if not line.parsed)

    @property
    def negative(self) -> bool:
        """A label file with no box in it: a negative sample."""
        return self.raw is not None and not self.boxes

    def ref(self, index: int) -> LineRef:
        return LineRef.of(self.lines, index)


def _cost(snap: ImageLabels) -> int:
    """Roughly the bytes a cached snapshot holds."""
    return 400 + len(snap.raw or b"") + 200 * len(snap.lines)


def _error(entry: ImageEntry, e: OSError) -> ImageLabels:
    return ImageLabels(entry.path, entry.label_path, LabelState.ERROR,
                       error=f"cannot read {entry.label_path.name}: {e.strerror or e}")


def _read_or_none(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise Refused(f"cannot read {path.name}: {e.strerror or e}") from e


class LabelStore:
    def __init__(self, dataset: Dataset, *, cache_bytes: int = 256 * 2**20,
                 on_reload: Callable[[Path], None] | None = None):
        self.dataset = dataset
        self._limit = cache_bytes
        self._on_reload = on_reload or (lambda image: None)
        self._lock = threading.Lock()
        self._cache: OrderedDict[Path, ImageLabels] = OrderedDict()
        self._costs: dict[Path, int] = {}
        self._total = 0
        self._pinned: Path | None = None
        self._owner = threading.get_ident()

    # -- reading, from any thread ------------------------------------------

    def get(self, image) -> ImageLabels:
        """The image's labels as its file is now.

        Every call stats the file; a changed stamp means a reload, and replacing a
        cached copy is reported to `on_reload`, on the calling thread.
        """
        return self._load(self.dataset.entry(image), notify=True)

    def pin(self, image) -> None:
        """Keep this image cached whatever the budget: the image on screen."""
        with self._lock:
            self._pinned = Path(image) if image is not None else None

    @property
    def cached_bytes(self) -> int:
        return self._total

    @property
    def cached_count(self) -> int:
        return len(self._cache)

    def is_cached(self, image) -> bool:
        with self._lock:
            return Path(image) in self._cache

    def _load(self, entry: ImageEntry, *, notify: bool) -> ImageLabels:
        shared = entry.label_path in self.dataset.shared_labels
        try:
            st = os.stat(entry.label_path)
        except FileNotFoundError:
            dropped = self._drop(entry.path)
            if notify and dropped is not None:
                self._on_reload(entry.path)
            return ImageLabels(entry.path, entry.label_path,
                               LabelState.SHARED if shared else LabelState.MISSING,
                               error=_SHARED if shared else "")
        except OSError as e:
            return _error(entry, e)
        # The stamp is taken BEFORE the bytes are read: a change in between leaves
        # a stamp older than the bytes, so the next call reloads again -- safe --
        # instead of trusting stale bytes under a new stamp.
        stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
        with self._lock:
            cached = self._cache.get(entry.path)
            if cached is not None and cached.stamp == stamp:
                self._cache.move_to_end(entry.path)
                return cached
        try:
            raw = entry.label_path.read_bytes()
        except OSError as e:
            return _error(entry, e)
        snap = ImageLabels(entry.path, entry.label_path,
                           LabelState.SHARED if shared else LabelState.OK,
                           raw, parse_label_bytes(raw), stamp, _SHARED if shared else "")
        self._remember(snap)
        if notify and cached is not None and cached.raw != raw:
            self._on_reload(entry.path)
        return snap

    def _remember(self, snap: ImageLabels) -> None:
        cost = _cost(snap)
        with self._lock:
            if snap.image in self._cache:
                del self._cache[snap.image]
                self._total -= self._costs.pop(snap.image)
            self._cache[snap.image] = snap
            self._costs[snap.image] = cost
            self._total += cost
            # Evict oldest first, and only while over budget: walking the whole
            # cache on every insert made a full dataset pass quadratic.
            while self._total > self._limit:
                victim = next((k for k in self._cache if k not in (self._pinned, snap.image)), None)
                if victim is None:
                    break
                del self._cache[victim]
                self._total -= self._costs.pop(victim)

    def _drop(self, image: Path) -> ImageLabels | None:
        with self._lock:
            snap = self._cache.pop(image, None)
            if snap is not None:
                self._total -= self._costs.pop(image)
            return snap

    # -- writing, on the owner thread --------------------------------------

    def apply(self, intent: Intent) -> Edit | None:
        """Write `intent` to the image's label file. None when it changes nothing."""
        self._check_thread()
        snap = self.get(intent.image)
        if not snap.editable:
            raise Refused(snap.error or f"{snap.label_path.name} cannot be edited")
        after = materialize(snap.raw, intent.ops, class_ok=self.dataset.known)
        if after == snap.raw:
            return None
        self._write(snap.label_path, after)
        self._load(self.dataset.entry(intent.image), notify=False)
        return Edit((FileChange(snap.label_path, snap.raw, after),), (snap.image,),
                    intent.description)

    def restore(self, edit: Edit, *, undo: bool) -> None:
        """Put every file of `edit` back as it was before it (undo) or after it (redo).

        Every file is checked first. If any no longer holds what `edit` left (undo)
        or found (redo), something else changed it: Conflict, and nothing at all is
        written. A failed read or write raises plain Refused, which may be retried.
        A file absent on the target side is deleted: only ever a file this edit
        created, and only while it still holds exactly what the edit wrote.
        """
        self._check_thread()
        self.check(edit.changes, undo=undo)
        for change in edit.changes:
            target = change.before if undo else change.after
            if target is None:
                try:
                    change.path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as e:
                    raise Refused(f"could not remove {change.path.name}: {e.strerror or e}") from e
            else:
                self._write(change.path, target)
        for image in edit.images:
            self._load(self.dataset.entry(image), notify=False)

    def check(self, changes, *, undo: bool) -> None:
        """Conflict if any file no longer holds what its change left (undo) or found
        (redo). Reads only."""
        for change in changes:
            expected = change.after if undo else change.before
            if _read_or_none(change.path) != expected:
                raise Conflict(f"{change.path.name} has changed since, so it is left as it is")

    def _write(self, path: Path, data: bytes) -> None:
        try:
            write_atomic(path, data)
        except OSError as e:
            raise Refused(f"could not write {path.name}: {e.strerror or e}; "
                          "the file is unchanged") from e

    def _check_thread(self) -> None:
        if threading.get_ident() != self._owner:
            raise RuntimeError("label files are written only on the thread that created the store")
