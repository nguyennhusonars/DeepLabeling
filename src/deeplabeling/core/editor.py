"""The GUI thread's one way to change labels (docs/design/2026-10-04-app-foundation.md#edits).

An applied edit is written by the store, recorded in the history and marks its
image reviewed; the listeners hear which images changed. An edit across many images
(accepting predictions over a queue) is written in chunks by an EditBatch and recorded
as one edit that marks nothing (docs/design/2026-10-05-model-assist.md#accepting).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from .edits import Conflict, Edit, FileChange, Intent, PartlyRestored, Refused
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

    def restoring(self, *, undo: bool) -> Restoring | None:
        """The last edit (or the last undone), to undo (or redo) a chunk at a time."""
        edit = self.history.peek_undo() if undo else self.history.peek_redo()
        return None if edit is None else Restoring(self, edit, undo)

    def undo(self) -> Edit | None:
        try:
            edit = self.history.undo()
        except PartlyRestored as e:
            self._labels_changed(e.images)          # files that stayed restored: the views follow
            raise
        finally:
            self._history_changed()     # a refused undo still dropped an edit
        if edit is not None:
            self._labels_changed(edit.images)
        return edit

    def redo(self) -> Edit | None:
        try:
            edit = self.history.redo()
        except PartlyRestored as e:
            self._labels_changed(e.images)          # files that stayed restored: the views follow
            raise
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
                try:
                    edit = store.apply(intent)
                except Refused as e:                # which of thousands of files said no
                    raise Refused(f"{store.dataset.entry(intent.image).rel}: {e}") from e
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
        raise Refused(f"{cause}; {len(kept)} file(s) stay as written — undo them once that is fixed") from cause

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


class Restoring:
    """Undo (or redo) of one edit a chunk of files at a time, for an edit too big to write
    at once without freezing the window (docs/design/2026-10-05-model-assist.md#accepting).

    Every file is checked before any is written, as LabelStore.restore does: an edit any
    file of which has changed since is refused whole, and dropped. Then the files are
    written a chunk at a time, each on its own, so a refusal stops at the file it names.
    Stopped part-way -- cancelled, or a write refused -- what was written becomes an edit
    of its own on the other list and the rest stays where it was: both stay undoable, and
    nothing is lost.
    """

    def __init__(self, editor: Editor, edit: Edit, undo: bool):
        self._editor, self.edit, self.undo = editor, edit, undo
        self._changes = list(edit.changes)
        self.checked = self.written = 0
        self.dropped = False            #: a file changed since: what was not written is gone from the history
        self._images: dict[Path, list[Path]] = {}       # label file -> its images in the edit
        for image in edit.images:
            self._images.setdefault(editor.store.dataset.entry(image).label_path, []).append(image)

    @property
    def total(self) -> int:
        return len(self._changes)

    def _verb(self) -> str:
        return "undo" if self.undo else "redo"

    def check(self, n: int) -> None:
        """Check the next `n` files. A file changed since: the edit is dropped, Refused."""
        chunk = self._changes[self.checked:self.checked + n]
        try:
            self._editor.store.check(chunk, undo=self.undo)
        except Conflict as e:
            self._editor.history.drop(self.edit, undo=self.undo)
            self._editor._history_changed()
            self.dropped = True
            raise Refused(f"cannot {self._verb()} “{self.edit.description}”: {e} — dropped from the history") from e
        self.checked += len(chunk)

    def write(self, n: int) -> tuple[Path, ...]:
        """Write the next `n` files, every one checked; the images they belong to. A
        refusal stops at the file it names: stop() then keeps what was written."""
        assert self.checked == self.total, "every file is checked first"
        images: list[Path] = []
        try:
            for change in self._changes[self.written:self.written + n]:
                mine = tuple(self._images.get(change.path, ()))
                self._editor.store.restore(Edit((change,), mine, self.edit.description), undo=self.undo)
                self.written += 1
                images.extend(mine)
        except Conflict as e:
            # Changed between its check and its write: as in the check, what is left cannot be
            # restored. What was written becomes an edit of its own; the rest is dropped.
            done = self.written
            history = self._editor.history
            if done:
                self.stop()                         # the rest is left where the edit was
                history.drop(history.peek_undo() if self.undo else history.peek_redo(), undo=self.undo)
            else:
                self._editor.history.drop(self.edit, undo=self.undo)
            self._editor._history_changed()
            self.dropped = True
            past = "undone" if self.undo else "redone"
            raise Refused(f"cannot {self._verb()} “{self.edit.description}”: {e} — {done:,} of {self.total:,} files "
                          f"{past}; the rest dropped from the history") from e
        finally:
            if images:
                self._editor._labels_changed(tuple(images))
        return tuple(images)

    def finish(self) -> None:
        """Every file written: the edit moves to the other list."""
        assert self.written == self.total
        self._editor.history.move(self.edit, undo=self.undo)
        self._editor._history_changed()

    def stop(self) -> None:
        """Stop part-way: what was written goes to the other list, the rest stays."""
        if not self.written:
            return
        if self.written == self.total:
            self.finish()
            return
        done, rest = self._changes[:self.written], self._changes[self.written:]
        self._editor.history.split(self.edit, undo=self.undo, done=self._part(done), rest=self._part(rest))
        self._editor._history_changed()

    def _part(self, changes: list[FileChange]) -> Edit:
        paths = {change.path for change in changes}
        images = tuple(i for i in self.edit.images if self._editor.store.dataset.entry(i).label_path in paths)
        return Edit(tuple(changes), images, self.edit.description)
