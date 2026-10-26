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
            "Skipped: 2 not editable.\n\n"
            "One edit, one undo. Nothing is marked reviewed.")


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
                                          "skipped 2 not editable")
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
    assert reassigned(qtbot, session) == "reassign cancelled: nothing written"
    assert ds.snapshot() == before


def test_cancelling_the_write_keeps_the_chunks_written_as_one_edit(qtbot, session, prompter, ds):
    prompter.cancel_at = {"Reassigning 10 person boxes on 7 images": 2}
    before = ds.snapshot()
    assert reassigned(qtbot, session) == "reassign stopped: 2 boxes on 2 images kept (one edit)"
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



def test_a_queue_whose_build_failed_is_refused(qtbot, session, ds):
    session.queue.fail("could not read the store")
    before = ds.snapshot()
    with qtbot.waitSignal(session.status) as said:
        reassign_queue(session)
    assert said.args == ["the queue's build failed — rebuild it first"] and ds.snapshot() == before


def test_a_dataset_that_names_no_classes_is_refused(qtbot, ds, prompter):
    s = open_session(qtbot, ds.root / "camA" / "images", prompter)
    try:
        assert s.workspace.dataset.names == ()
        with qtbot.waitSignal(s.status) as said:
            reassign_queue(s)
        assert said.args == ["this dataset names no classes"]
    finally:
        s.close()


def test_repairing_an_unnamed_id_counts_them_again(qtbot, session, prompter):
    qtbot.waitUntil(lambda: session.unnamed_ids == (-1, 99), timeout=5000)
    prompter.reassign = (99, 1)
    reassigned(qtbot, session)
    qtbot.waitUntil(lambda: session.unnamed_ids == (-1,), timeout=5000)


def test_a_findings_queue_with_two_findings_on_an_image_reassigns_it_once(qtbot, ds, prompter, tmp_path, monkeypatch):
    import deeplabeling.ui.model as model_module
    from finding_rows import FOUND_TWO, TWO, factory, load, put_rows

    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    s = open_session(qtbot, ds.yaml, prompter)
    try:
        weights = tmp_path / "best.pt"
        weights.write_bytes(b"weights")
        load(qtbot, s, weights)
        put_rows(s, TWO)
        s.set_queue(Findings())
        qtbot.waitUntil(lambda: s.queue.complete, timeout=5000)
        assert [i.key for i in s.queue.items][:3] == FOUND_TWO[:3]           # camA/0001 twice
        prompter.reassign = (1, 2)                                         # car -> bus_m
        assert reassigned(qtbot, s) == "reassigned 1 car box on 1 image to bus_m"
        assert read_exact(ds.lbl("camA/0001")).splitlines()[1] == "2 0.250000 0.250000 0.100000 0.100000"
    finally:
        s.close()


def test_a_queue_of_the_class_shows_its_images_no_longer_matching(qtbot, session):
    from deeplabeling.core.queue import HasClass

    session.set_queue(ImageFilter(conditions=(HasClass(("bus_m",)),)))
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    session.prompter.reassign = (2, 1)
    reassigned(qtbot, session)
    assert all(session.badge(item).endswith("· no longer matches") for item in session.queue.items)


def test_cancelled_before_its_first_chunk_it_says_nothing_was_written(qtbot, session, prompter, ds):
    real = prompter.progress

    class Cancelled:
        def set(self, value): pass
        def cancelled(self): return True
        def close(self): pass

    prompter.progress = lambda title, total: Cancelled() if title.startswith("Reassigning") else real(title, total)
    before = ds.snapshot()
    assert reassigned(qtbot, session) == "reassign cancelled: nothing written"
    assert ds.snapshot() == before and session.workspace.history.depth == 0


def test_an_undo_that_cannot_read_a_file_keeps_the_edit_and_says_so(qtbot, session, ds):
    reassigned(qtbot, session)                              # 7 files, more than a chunk: undone in chunks
    ds.lbl("camA/0001").chmod(0o000)
    try:
        with qtbot.waitSignal(session.notice, timeout=5000) as said:
            session.undo()
            qtbot.waitUntil(lambda: session.running is None, timeout=5000)
    finally:
        ds.lbl("camA/0001").chmod(0o644)
    assert said.args[1].endswith("— nothing undone; undo again once fixed")
    assert session.workspace.history.depth == 1


def test_a_finished_long_write_lets_its_runner_go(qtbot, session):
    from deeplabeling.ui.chunked import Chunked

    reassigned(qtbot, session)
    qtbot.waitUntil(lambda: not session.findChildren(Chunked), timeout=5000)
