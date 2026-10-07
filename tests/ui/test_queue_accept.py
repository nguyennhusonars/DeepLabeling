"""Accepting the missing predictions across a queue: planned on a job, confirmed, then
written a chunk at a time as one edit (docs/design/2026-10-05-model-assist.md#accepting)."""

import pytest

from deeplabeling.core import store as store_module
from deeplabeling.core.assist import QueueAccept
from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import image_stamp
from deeplabeling.ui import chunked, queue_accept
from deeplabeling.ui.queue_accept import accept_queue, queue_accept_question
from fixtures import CAMA_0001, FakePredictor, FakePrompter, assert_only_changed, open_session, read_exact

CAR = Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9)              # the model's car: the dataset's car (1)
HUMAN = Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)            # unmapped
CAR_LINE = "1 0.800000 0.800000 0.100000 0.100000\n"
ROWS = {"camA/images/0001.jpg": [CAR, HUMAN], "camA/images/0002.jpg": [CAR],      # 0002: a negative
        "camA/images/0003.jpg": [CAR], "camA/images/0004.JPG": [CAR], "camB/images/0001.jpg": [CAR],
        "camB/images/twin.jpg": [CAR],                                              # shares its file
        "weird/images/имя пробел.jpg": [CAR]}
WRITTEN = {"camA/labels/0001.txt", "camA/labels/0003.txt", "camA/labels/0004.txt",
           "camB/labels/0001.txt", "weird/labels/имя пробел.txt"}


@pytest.fixture
def prompter():
    return FakePrompter()


@pytest.fixture
def session(qtbot, ds, prompter, tmp_path, monkeypatch):
    """The dataset open, ROWS in the store, and the fake model that found them loaded."""
    monkeypatch.setattr(chunked, "CHUNK", 2)
    s = open_session(qtbot, ds.yaml, prompter)
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    for rel, preds in ROWS.items():
        entry = s.workspace.dataset.entry(ds.root / rel)
        s.workspace.predictions.put("fake:best.pt", rel, image_stamp(entry.path), preds)
    s.model.factory = FakePredictor
    s.model.load(weights)
    qtbot.waitUntil(lambda: s.model.state == "ready", timeout=5000)
    yield s
    s.close()


def accepted(qtbot, session):
    with qtbot.waitSignal(session.status, timeout=5000) as said:
        accept_queue(session)
        qtbot.waitUntil(lambda: session.running is None and said.signal_triggered, timeout=5000)
    return said.args[0]


def test_the_question_says_what_it_adds_and_what_it_skips():
    plan = QueueAccept(intents=(None,) * 567, boxes=1234, uninferred=89, unmapped=40, read_only=3, negative=12)
    assert queue_accept_question(plan) == (
        "Accept 1,234 boxes on 567 images?\n\n"
        "Skipped: 89 not inferred; 12 negative samples (kept empty); 3 not editable; "
        "40 unmapped predictions.\n\n"
        "One edit: one undo takes it back. Nothing is marked reviewed.")
    one = QueueAccept(intents=(None,), boxes=1, uninferred=0, unmapped=0, read_only=0, negative=0)
    assert queue_accept_question(one) == ("Accept 1 box on 1 image?\n\n"
                                          "One edit: one undo takes it back. Nothing is marked reviewed.")


def test_the_queue_accept_writes_one_edit_that_marks_nothing_and_undoes_whole(qtbot, session, prompter, ds):
    before = ds.snapshot()
    assert accepted(qtbot, session) == "✚ accepted 5 boxes on 5 images"
    [(_, text)] = [a for a in prompter.asked if a[0] == "queue accept"]
    assert text.startswith("Accept 5 boxes on 5 images?\n\nSkipped: 8 not inferred; 1 negative sample")
    assert [p.title for p in prompter.progresses] == ["Looking at 15 images", "Accepting 5 boxes on 5 images"]
    assert_only_changed(before, ds.snapshot(), WRITTEN)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 + CAR_LINE
    assert read_exact(ds.lbl("camA/0003")) == CAR_LINE
    assert session.workspace.history.depth == 1 and session.workspace.review.count() == 0
    session.undo()                                          # 5 files > CHUNK: in chunks too
    qtbot.waitUntil(lambda: session.running is None)
    assert_only_changed(before, ds.snapshot(), set())


def test_declined_nothing_is_written(qtbot, session, prompter, ds):
    prompter.accept_queue = False
    before = ds.snapshot()
    accept_queue(session)
    qtbot.waitUntil(lambda: any(a[0] == "queue accept" for a in prompter.asked))
    qtbot.wait(50)
    assert_only_changed(before, ds.snapshot(), set()) and session.workspace.history.depth == 0


def test_nothing_missing_says_so_without_asking(qtbot, session, prompter):
    session.model.set_conf(0.95)                            # above every prediction
    assert accepted(qtbot, session) == (
        "nothing missing to accept; 8 not inferred; 1 negative sample (kept empty); 1 not editable")
    assert not any(a[0] == "queue accept" for a in prompter.asked)


def test_a_cancel_while_writing_keeps_the_chunks_written_as_one_edit(qtbot, session, prompter, ds):
    before = ds.snapshot()
    prompter.cancel_at = {"Accepting 5 boxes on 5 images": 2}
    assert accepted(qtbot, session) == "accept stopped: 2 boxes on 2 images kept (one edit)"
    assert_only_changed(before, ds.snapshot(), {"camA/labels/0001.txt", "camA/labels/0003.txt"})
    assert session.workspace.history.depth == 1
    session.undo()
    assert_only_changed(before, ds.snapshot(), set())       # 2 files: undone at once


def test_a_cancel_while_looking_writes_nothing(qtbot, session, prompter, ds, monkeypatch):
    monkeypatch.setattr(queue_accept, "PLAN_BATCH", 1)
    prompter.cancel_at = 3
    before = ds.snapshot()
    assert accepted(qtbot, session) == "accept cancelled: nothing written"
    assert not any(a[0] == "queue accept" for a in prompter.asked)
    assert_only_changed(before, ds.snapshot(), set())


def test_a_write_failing_part_way_puts_every_file_back_and_says_why(qtbot, session, ds, monkeypatch):
    before = ds.snapshot()
    real, calls = store_module.write_atomic, []

    def failing(path, data):
        calls.append(path)
        if len(calls) == 3:
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", failing)
    with qtbot.waitSignal(session.notice, timeout=5000) as said:
        accept_queue(session)
    qtbot.waitUntil(lambda: session.running is None)
    assert said.args[1].startswith("nothing was accepted: camA/images/0004.JPG: could not write") and "No space left" in said.args[1]
    monkeypatch.setattr(store_module, "write_atomic", real)
    assert_only_changed(before, ds.snapshot(), set())
    assert session.workspace.history.depth == 0


def test_without_a_model_or_a_whole_queue_it_says_why(qtbot, session):
    session.model.unload()
    with qtbot.waitSignal(session.status) as said:
        accept_queue(session)
    assert said.args == ["no model loaded"]


def test_an_unexpected_error_while_looking_ends_the_run_and_says_so(qtbot, session, prompter, monkeypatch):
    import sqlite3

    def broken(*args):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(session.workspace.predictions, "get", broken)
    with qtbot.waitSignal(session.notice, timeout=5000) as said:
        accept_queue(session)
    assert said.args[1] == "the queue could not be read: DatabaseError: database disk image is malformed"
    assert session.running is None and prompter.progresses[-1].closed


def test_files_that_cannot_be_put_back_are_said_to_stay_written(qtbot, session, ds, monkeypatch):
    real, calls = store_module.write_atomic, []

    def failing(path, data):
        calls.append(path)
        if len(calls) >= 3:                                  # the disk fills, and stays full
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", failing)
    with qtbot.waitSignal(session.notice, timeout=5000) as said:
        accept_queue(session)
    qtbot.waitUntil(lambda: session.running is None)
    assert said.args[1].startswith("the accept failed part-way: camA/images/0004.JPG: could not write")
    assert "stay as written" in said.args[1]
    assert session.workspace.history.depth == 1               # undo puts them back once there is room



def test_a_queue_whose_build_failed_is_not_accepted_across(qtbot, session, ds):
    session.queue.fail("could not read the store")
    before = ds.snapshot()
    with qtbot.waitSignal(session.status) as said:
        accept_queue(session)
    assert said.args == ["the queue's build failed — rebuild it first"] and ds.snapshot() == before
