"""Reassigning a class across the queue: looked at, asked, then written a chunk at a time
as one edit (docs/design/2026-10-07-bulk-and-stats.md#bulk-reassign)."""

import pytest

from deeplabeling.core.findings import Findings
from deeplabeling.core.queue import ImageFilter, NameContains
from deeplabeling.ui import chunked
from deeplabeling.ui.reassign import reassign_queue
from fixtures import FakePrompter, assert_only_changed, open_session, read_exact

WRITTEN = {"camA/labels/0001.txt", "weird/labels/имя пробел.txt", "bad/labels/corrupt.txt",
           "bad/labels/ok.txt", "crlf/labels/c.txt", "seg/labels/poly1.txt", "seg/labels/mixed.txt"}
QUESTION = ("Reassign 10 person boxes on 7 images to bus_l?\n\n"
            "Skipped: 2 images whose label file cannot be edited.\n\n"
            "It is one edit: one undo takes it all back. Nothing is marked reviewed.")


@pytest.fixture
def prompter():
    return FakePrompter(reassign=(0, 3))


@pytest.fixture
def session(qtbot, ds, prompter, monkeypatch):
    monkeypatch.setattr(chunked, "CHUNK", 2)
    s = open_session(qtbot, ds.yaml, prompter)
    yield s
    s.close()


def reassigned(qtbot, session):
    with qtbot.waitSignal(session.status, timeout=5000) as said:
        reassign_queue(session)
        qtbot.waitUntil(lambda: session.running is None and said.signal_triggered, timeout=5000)
    return said.args[0]


def test_it_asks_with_counts_writes_one_edit_and_marks_nothing(qtbot, session, prompter, ds):
    before = ds.snapshot()
    assert reassigned(qtbot, session) == ("reassigned 10 person boxes on 7 images to bus_l; "
                                          "skipped 2 images whose label file cannot be edited")
    assert ("reassign question", QUESTION) in prompter.asked
    assert_only_changed(before, ds.snapshot(), WRITTEN)
    assert len(session.workspace.review.keys()) == 0
    session.undo()                                          # one undo takes it all back
    qtbot.waitUntil(lambda: session.running is None, timeout=5000)
    assert ds.snapshot() == before


def test_the_from_list_offers_the_ids_the_yaml_does_not_name(qtbot, session, prompter, ds):
    qtbot.waitUntil(lambda: session.unnamed_ids == (-1, 99), timeout=5000)
    prompter.reassign = (99, 1)
    assert reassigned(qtbot, session) == "reassigned 1 #99? box on 1 image to car"
    assert ("reassign", ("person", "car", "bus_m", "bus_l"), (-1, 99)) in prompter.asked
    assert read_exact(ds.lbl("bad/ok")).splitlines()[1] == "1 0.5 0.5 0.1 0.1"


def test_a_queue_without_the_class_writes_nothing_and_says_so(qtbot, session, prompter, ds):
    session.set_queue(ImageFilter(conditions=(NameContains("camB"),)))
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    prompter.reassign = (3, 1)
    before = ds.snapshot()
    assert reassigned(qtbot, session) == "no bus_l boxes in this queue"
    assert ds.snapshot() == before


def test_answering_no_writes_nothing(qtbot, session, prompter, ds):
    prompter.accept_reassign = False
    before = ds.snapshot()
    assert reassigned(qtbot, session) == "reassign cancelled: nothing was written"
    assert ds.snapshot() == before


def test_cancelling_the_write_keeps_the_chunks_written_as_one_edit(qtbot, session, prompter, ds):
    prompter.cancel_at = {"Reassigning 10 person boxes on 7 images": 2}
    before = ds.snapshot()
    assert reassigned(qtbot, session) == "reassign stopped: 2 boxes on 2 images kept, as one edit"
    assert_only_changed(before, ds.snapshot(), {"camA/labels/0001.txt", "weird/labels/имя пробел.txt"})
    session.undo()
    qtbot.waitUntil(lambda: session.running is None, timeout=5000)
    assert ds.snapshot() == before


def test_a_queue_still_waiting_is_refused(qtbot, session, ds):
    session.set_queue(Findings())                           # no model: it waits
    before = ds.snapshot()
    with qtbot.waitSignal(session.status) as said:
        reassign_queue(session)
    assert said.args == ["the queue waits for a model"] and ds.snapshot() == before
