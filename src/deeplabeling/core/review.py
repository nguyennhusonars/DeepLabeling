"""Which images have been reviewed (docs/design/2026-10-04-app-foundation.md#review-marks).

Keyed by ImageEntry.rel and saved atomically as {"version": 1, "root": ...,
"marks": {rel: unix time}}. What marks an image -- an edit, done & next, mark
page, never mere viewing -- is the caller's rule; this is only the record.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path

from .atomic import write_atomic
from .state import set_aside

SCHEMA_VERSION = 1


class ReviewMarks:
    def __init__(self, path: Path, root: Path):
        self.path = Path(path)
        self.root = Path(root)
        self.marks: dict[str, int] = {}
        self.dirty = False
        self.warning = ""
        self.writable = True
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_bytes())
            stored = data["marks"]
            if not isinstance(stored, dict):
                raise TypeError("marks is not an object")
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.warning, self.writable = set_aside(self.path, e)
            return
        bad = 0
        for key, when in stored.items():
            try:
                self.marks[str(key)] = int(when)
            except (TypeError, ValueError):
                bad += 1
        if bad:
            self.warning = f"{bad} review mark(s) in {self.path.name} could not be read and were skipped"

    def is_marked(self, rel: str) -> bool:
        return rel in self.marks

    def marked_at(self, rel: str) -> int | None:
        return self.marks.get(rel)

    def count(self) -> int:
        return len(self.marks)

    def keys(self) -> frozenset[str]:
        """A snapshot, safe to hand to a worker thread."""
        return frozenset(self.marks)

    def mark(self, rel: str, when: int | None = None) -> bool:
        """Mark one image; False when it already was (its time is kept)."""
        if rel in self.marks:
            return False
        self.marks[rel] = int(time.time() if when is None else when)
        self.dirty = True
        return True

    def mark_many(self, rels: Iterable[str]) -> int:
        return sum(1 for rel in rels if self.mark(rel))

    def unmark(self, rel: str) -> bool:
        if rel not in self.marks:
            return False
        del self.marks[rel]
        self.dirty = True
        return True

    def toggle(self, rel: str) -> bool:
        """Flip one image; returns its new state."""
        if self.unmark(rel):
            return False
        self.mark(rel)
        return True

    def save(self) -> bool:
        if not self.dirty or not self.writable:
            return False
        payload = {"version": SCHEMA_VERSION, "root": str(self.root), "marks": self.marks}
        write_atomic(self.path, json.dumps(payload, indent=1, sort_keys=True).encode())
        self.dirty = False
        return True
