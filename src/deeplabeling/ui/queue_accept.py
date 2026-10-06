"""Accept missing boxes in this queue… (docs/design/2026-10-05-model-assist.md#accepting).

It looks at every image a chunk at a time, behind a progress dialog, and asks first. Then it
writes a chunk at a time on the GUI thread's write path, as one edit that marks nothing. A cancel
keeps the chunks already written, as one edit; a write that fails puts every file back.
"""

from __future__ import annotations

from ..core.assist import QueueAccept, plan_queue_accept
from ..core.predstore import image_stamp
from . import chunked

DESCRIPTION = "accept missing boxes in this queue"
PLAN_BATCH = 500        #: images looked at per event-loop turn: label files and store rows, read


def _count(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def _skipped(plan: QueueAccept) -> list[str]:
    return [text for n, text in (
        (plan.uninferred, _count(plan.uninferred, "image", "images") + " not inferred yet"),
        (plan.negative, _count(plan.negative, "negative sample", "negative samples")
         + " (an empty label file is someone's decision)"),
        (plan.read_only, _count(plan.read_only, "image", "images") + " whose label file cannot be edited"),
        (plan.unmapped, _count(plan.unmapped, "prediction", "predictions") + " of a class the map leaves out"),
    ) if n]


def queue_accept_question(plan: QueueAccept) -> str:
    text = f"Accept {_count(plan.boxes, 'box', 'boxes')} on {_count(len(plan.intents), 'image', 'images')}?\n\n"
    skipped = _skipped(plan)
    if skipped:
        text += "Skipped: " + "; ".join(skipped) + ".\n\n"
    return text + "It is one edit: one undo takes it all back. Nothing is marked reviewed."


def accept_queue(session) -> None:
    """Look, confirm and write; each step says how it ended in the status bar."""
    model, ws, queue = session.model, session.workspace, session.queue
    if ws is None or session._busy():
        return
    if model.state != "ready":
        session.status.emit("the model is still loading" if model.state == "loading" else "no model is loaded")
        return
    if queue is None or not queue.complete:
        session.status.emit("the queue is still being built")
        return
    entries = [item.entry for item in queue.items]
    key, preds, cmap, conf = model.key, ws.predictions, model.class_map, model.conf
    plan, looked = QueueAccept((), 0, 0, 0, 0, 0), 0

    def preds_of(entry):
        try:
            return preds.get(key, entry.rel, image_stamp(entry.path))
        except OSError:
            return None

    def step(progress) -> bool:                     # reads only: label files and the store
        nonlocal plan, looked
        part = plan_queue_accept(entries[looked:looked + PLAN_BATCH], ws.store.get, preds_of,
                                 cmap, ws.dataset, conf)
        plan = QueueAccept(plan.intents + part.intents, *(a + b for a, b in zip(
            (plan.boxes, plan.uninferred, plan.unmapped, plan.read_only, plan.negative),
            (part.boxes, part.uninferred, part.unmapped, part.read_only, part.negative))))
        looked += PLAN_BATCH
        progress.set(min(looked, len(entries)))
        return looked < len(entries)

    def end(progress, cancelled, error) -> None:
        if cancelled or error is not None or session.workspace is not ws:
            session.status.emit("accept cancelled: nothing was written")
        elif not plan.intents:
            session.status.emit("; ".join(["no missing boxes to accept in this queue"]
                                          + [s.replace(" not inferred yet", " are not inferred yet")
                                             for s in _skipped(plan)]))
        elif session.prompter.confirm_queue_accept(queue_accept_question(plan)):
            _write(session, plan)

    session.run_chunked(f"Looking at {len(entries):,} images", len(entries), step, end)


def _write(session, plan: QueueAccept) -> None:
    batch = session.workspace.editor.batch(DESCRIPTION)
    intents, written = plan.intents, 0

    def step(progress) -> bool:
        nonlocal written
        chunk = intents[written:written + chunked.CHUNK]
        batch.apply(chunk)                          # Refused: every file already put back
        written += len(chunk)
        progress.set(written)
        return written < len(intents)

    def end(progress, cancelled, error) -> None:
        if error is not None:
            session.notice.emit("error", f"nothing was accepted: {error}", None)
            return
        batch.finish()
        boxes = sum(len(intent.ops) for intent in intents[:written])
        what = f"{_count(boxes, 'box', 'boxes')} on {_count(written, 'image', 'images')}"
        session.status.emit(f"accept stopped: {what} kept, as one edit" if cancelled else f"accepted {what}")

    session.run_chunked(f"Accepting {_count(plan.boxes, 'box', 'boxes')} on {_count(len(intents), 'image', 'images')}",
                        len(intents), step, end)
