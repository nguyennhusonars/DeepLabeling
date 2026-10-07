"""Reassign a class in this queue… (docs/design/2026-10-07-bulk-and-stats.md#bulk-reassign).

It asks From and To, looks at every image of the queue a chunk at a time behind a progress
dialog, and asks first with the counts. Then it writes a chunk at a time on the GUI thread's
write path, as one edit that marks nothing, as accepting across a queue does
(`src/deeplabeling/ui/chunked.py::write_as_one_edit`).
"""

from __future__ import annotations

from ..core.reassign import Reassign, plan_reassign
from . import chunked
from .reassign_dialog import class_label

PLAN_BATCH = 500        #: images looked at per event-loop turn: their label files, read


def _count(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def _skipped(plan: Reassign) -> str:
    return f"{plan.read_only:,} read-only" if plan.read_only else ""


def reassign_question(plan: Reassign, source: str, target: str) -> str:
    text = (f"Reassign {_count(plan.boxes, source + ' box', source + ' boxes')} on "
            f"{_count(len(plan.intents), 'image', 'images')} to {target}?\n\n")
    if plan.read_only:
        text += f"Skipped: {_skipped(plan)}.\n\n"
    return text + "One edit: one undo takes it back. Nothing is marked reviewed."


def reassign_queue(session) -> None:
    """Ask, look, confirm and write; each step says how it ended in the status bar."""
    ws, queue = session.workspace, session.queue
    if ws is None or queue is None or session._busy():
        return
    if not ws.dataset.names:
        session.status.emit("this dataset names no classes")
        return
    why = session.queue_not_whole()
    if why:
        session.status.emit(why)
        return
    names = ws.dataset.names
    chosen = session.prompter.ask_reassign(names, session.unnamed_ids)
    if chosen is None:
        return
    source, target = chosen
    source_name, target_name = class_label(source, names), class_label(target, names)
    description = f"reassign {source_name} to {target_name}"
    entries = session.queue_images()
    plan, looked = Reassign((), 0, 0), 0

    def step(progress) -> bool:                     # reads only: the label files
        nonlocal plan, looked
        plan += plan_reassign(entries[looked:looked + PLAN_BATCH], ws.store.get, source, target, description)
        looked += PLAN_BATCH
        progress.set(min(looked, len(entries)))
        return looked < len(entries)

    def end(progress, cancelled, error) -> None:
        skipped = f"; skipped {_skipped(plan)}" if plan.read_only else ""
        if error is not None and session.workspace is ws:
            session.notice.emit("error", f"the queue could not be read: {error}", None)
        elif cancelled or session.workspace is not ws:
            session.status.emit("reassign cancelled: nothing written")
        elif not plan.intents:
            session.status.emit(f"no {source_name} boxes in this queue{skipped}")
        elif not session.prompter.confirm_reassign(reassign_question(plan, source_name, target_name)):
            session.status.emit("reassign cancelled: nothing written")
        else:
            # A stray id repaired: once written, the warning about it is counted again.
            after = session.recount_unnamed if not 0 <= source < len(names) else None
            _write(session, plan, description, source_name, target_name, skipped, after)

    session.run_chunked(f"Looking at {len(entries):,} images", len(entries), step, end)


def _write(session, plan: Reassign, description: str, source: str, target: str, skipped: str, after=None) -> None:
    def said(written, cancelled) -> str:
        boxes = sum(len(intent.ops) for intent in written)
        if cancelled and not written:
            return "reassign cancelled: nothing written"
        if cancelled:
            return (f"reassign stopped: {_count(boxes, 'box', 'boxes')} on "
                    f"{_count(len(written), 'image', 'images')} kept (one edit)")
        return (f"reassigned {_count(boxes, source + ' box', source + ' boxes')} on "
                f"{_count(len(written), 'image', 'images')} to {target}{skipped}")

    chunked.write_as_one_edit(
        session, plan.intents, description,
        f"Reassigning {_count(plan.boxes, source + ' box', source + ' boxes')} on "
        f"{_count(len(plan.intents), 'image', 'images')}", said,
        failed="the reassign failed part-way", undone="nothing was reassigned", after=after)
