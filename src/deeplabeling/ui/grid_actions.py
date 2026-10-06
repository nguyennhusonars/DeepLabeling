"""Several findings at once, from the grid (docs/design/2026-10-06-find-bad.md#the-grid).

Every selected finding takes the key, as one edit that marks nothing reviewed: a crop is
not the image. A finding the key cannot apply to -- its label file read-only, its line
changed since, no model class or box -- is skipped, and the status bar counts it.
"""

from __future__ import annotations

from collections import Counter

from ..core.edits import DeleteLine, Intent, SetBox, SetClass
from ..core.labelio import locate_line
from .actions import clamp_box


def _count(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def _act(session, items, describe, op_for) -> None:
    """Apply `op_for(item)` -- an op, or None and why not -- to every finding that can take it."""
    ops, skipped = {}, Counter()
    for item in items:
        labels, f = session.labels(item.entry), item.focus
        if not labels.editable:
            skipped["its label file cannot be edited"] += 1
            continue
        if locate_line(labels.lines, f.cls_id, f.bbox, f.index) is None:
            skipped["its label changed since"] += 1
            continue
        op, why = op_for(item)
        if op is None:
            skipped[why] += 1
            continue
        ops.setdefault(item.entry.path, []).append(op)
    n = sum(len(o) for o in ops.values())
    if n:
        description = describe(n)
        if session.apply_many([Intent(image, tuple(o), description) for image, o in ops.items()],
                              description) is None:
            return                                  # refused: a notice says why
        text = f"{description}, as one edit"
    else:
        text = "nothing changed"
    if skipped:
        text += "; skipped " + ", ".join(f"{k} ({why})" for why, k in skipped.items())
    session.status.emit(text)


def take_model_class(session, items) -> None:
    def op(item):
        f = item.finding
        if f.model_cls is None or f.kind == "not an object":
            return None, "the model has no class for it"
        if f.model_cls == item.focus.cls_id:
            return None, "it already has the model's class"
        return SetClass(item.focus, f.model_cls), ""
    _act(session, items, lambda n: f"took the model's class on {_count(n, 'finding', 'findings')}", op)


def take_model_box(session, items) -> None:
    def op(item):
        box = item.finding.model_box and clamp_box(item.finding.model_box)
        return (None, "it has no model box") if box is None else (SetBox(item.focus, box), "")
    _act(session, items, lambda n: f"took the model's box on {_count(n, 'finding', 'findings')}", op)


def delete(session, items) -> None:
    _act(session, items, lambda n: f"deleted {n:,} finding's label" if n == 1 else f"deleted {n:,} findings' labels",
         lambda item: (DeleteLine(item.focus), ""))


def set_class(session, items, cls_id: int, name: str) -> None:
    def op(item):
        if item.focus.cls_id == cls_id:
            return None, f"it is a {name} already"
        return SetClass(item.focus, cls_id), ""
    _act(session, items, lambda n: f"set {_count(n, 'finding', 'findings')} to {name}", op)


def dismiss(session, items) -> None:
    """D: dismiss every selected finding -- or, when all are dismissed, take them all back."""
    dismissals = session.workspace.dismissals
    shown = [(item.entry.rel, item.finding.text, item.finding.kind) for item in items]
    back = all(dismissals.has(*d) for d in shown)
    changed = [d for d in shown if dismissals.has(*d) == back]
    for d in changed:
        dismissals.toggle(*d)
    session.saver.schedule()
    session.itemsChanged.emit([item.key for item in items])
    n = len(changed)
    session.status.emit(f"{_count(n, 'dismissal', 'dismissals')} taken back" if back
                        else f"dismissed {_count(n, 'finding', 'findings')}")
