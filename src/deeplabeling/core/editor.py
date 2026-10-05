"""The GUI thread's one way to change labels (docs/design/2026-10-04-app-foundation.md#edits).

An applied edit is written by the store, recorded in the history and marks its
image reviewed; the listeners hear which images changed. An edit across many images
(accepting predictions over a queue) is written in chunks by an EditBatch and recorded
as one edit that marks nothing (docs/design/2026-10-05-model-assist.md#accepting).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from .edits import Edit, FileChange, Intent, Refused
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

    def batch(self, description: str) -> EditBatch:
        """An edit across many images, written a chunk at a time, recorded at finish()."""
        return EditBatch(self, description)

    def apply_many(self, intents: Iterable[Intent], description: str) -> Edit | None:
        """Apply intents across many images as one edit that marks nothing."""
        batch = self.batch(description)
        batch.apply(intents)
        return batch.finish()

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


class EditBatch:
    """One edit across many images. Each chunk is written at once, on the owner thread,
    and its images reported; finish() records the whole as one edit and marks nothing.

    If a write fails, every file the batch has written gets its before-bytes back, the
    batch is spent, and nothing is recorded: a failed batch leaves no half.
    """

    def __init__(self, editor: Editor, description: str):
        self._editor, self._description = editor, description
        self._changes: dict[Path, FileChange] = {}      # by label file: first before, last after
        self._images: dict[Path, None] = {}
        self._image_of: dict[Path, Path] = {}           # label file -> its image
        self._spent = False

    def apply(self, intents: Iterable[Intent]) -> None:
        if self._spent:
            raise RuntimeError("this batch is finished or failed")
        store, touched = self._editor.store, []
        try:
            for intent in intents:
                edit = store.apply(intent)
                if edit is None:
                    continue
                for change in edit.changes:
                    self._image_of[change.path] = edit.images[0]
                    first = self._changes.get(change.path)
                    self._changes[change.path] = FileChange(
                        change.path, change.before if first is None else first.before, change.after)
                for image in edit.images:
                    self._images[image] = None
                    touched.append(image)
        except Refused as e:
            self._spent = True
            self._roll_back(e)
        if touched:
            self._editor._labels_changed(tuple(touched))

    def _roll_back(self, cause: Refused) -> None:
        """Put back every file written, one by one: files this batch created go first,
        which frees space on a full disk. What cannot be put back is recorded as an edit,
        so undo can retry it once the cause is gone; it is never dropped."""
        written = self._edit()
        if written is None:
            raise cause
        store, kept = self._editor.store, []
        for change in sorted(written.changes, key=lambda c: c.before is not None):
            try:
                store.restore(Edit((change,), (self._image_of[change.path],), self._description), undo=True)
            except Refused:
                kept.append(change)
        images = tuple(self._images)
        self._editor._labels_changed(images)
        if not kept:
            raise cause
        self._editor.history.push(Edit(tuple(kept), images, self._description))
        self._editor._history_changed()
        raise Refused(f"{cause}; {len(kept)} file(s) could not be put back and stay as written: "
                      "undo puts them back once that is fixed") from cause

    def _edit(self) -> Edit | None:
        if not self._changes:
            return None
        return Edit(tuple(self._changes.values()), tuple(self._images), self._description)

    def finish(self) -> Edit | None:
        """Record what was written as one edit; None when nothing changed."""
        if self._spent:
            raise RuntimeError("this batch is finished or failed")
        self._spent = True
        edit = self._edit()
        if edit is not None:
            self._editor.history.push(edit)
            self._editor._history_changed()
        return edit
