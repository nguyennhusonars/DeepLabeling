"""Findings looked at and judged fine (docs/design/2026-10-06-find-bad.md#dismissals).

A dismissal is (image, the label line as it is, the finding kind), saved atomically as
{"version": 1, "root": ..., "dismissed": [[rel, line, kind], ...]}. Editing the label
changes its line, so its dismissals no longer match; a new model does not resurface them.
Dismissing is not an edit: undo leaves it alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from .atomic import write_atomic
from .state import set_aside

SCHEMA_VERSION = 1

Dismissal = tuple[str, str, str]        #: (dataset-relative image, label line, kind)


class Dismissals:
    def __init__(self, path: Path, root: Path):
        self.path = Path(path)
        self.root = Path(root)
        self._items: set[Dismissal] = set()
        self._frozen: frozenset[Dismissal] | None = None     #: the last snapshot, until a change
        self.dirty = False
        self.warning = ""
        self.writable = True
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_bytes())
            stored = data["dismissed"]
            if not isinstance(stored, list):
                raise TypeError("dismissed is not a list")
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.warning, self.writable = set_aside(self.path, e)
            return
        bad = 0
        for entry in stored:
            if isinstance(entry, list) and len(entry) == 3 and all(isinstance(v, str) for v in entry):
                self._items.add(tuple(entry))
            else:
                bad += 1
        if bad:
            self.warning = f"{bad} dismissal(s) in {self.path.name} could not be read and were skipped"

    def has(self, rel: str, line: str, kind: str) -> bool:
        return (rel, line, kind) in self._items

    def snapshot(self) -> frozenset[Dismissal]:
        """A copy, safe to hand to a worker thread: made once, and again after a change."""
        if self._frozen is None:
            self._frozen = frozenset(self._items)
        return self._frozen

    def dismiss(self, rel: str, line: str, kind: str) -> bool:
        """False when it already was."""
        if (rel, line, kind) in self._items:
            return False
        self._items.add((rel, line, kind))
        self.dirty, self._frozen = True, None
        return True

    def undismiss(self, rel: str, line: str, kind: str) -> bool:
        if (rel, line, kind) not in self._items:
            return False
        self._items.discard((rel, line, kind))
        self.dirty, self._frozen = True, None
        return True

    def toggle(self, rel: str, line: str, kind: str) -> bool:
        """Flip one; its new state."""
        if self.undismiss(rel, line, kind):
            return False
        self.dismiss(rel, line, kind)
        return True

    def save(self) -> bool:
        if not self.dirty or not self.writable:
            return False
        payload = {"version": SCHEMA_VERSION, "root": str(self.root),
                   "dismissed": [list(d) for d in sorted(self._items)]}
        write_atomic(self.path, json.dumps(payload, indent=1).encode())
        self.dirty = False
        return True
