"""An edit across many images is undone and redone a chunk at a time, behind a progress
dialog that can cancel (docs/design/2026-10-05-model-assist.md#accepting)."""

import pytest
from PySide6.QtCore import QTimer

from deeplabeling.core import store as store_module
from deeplabeling.core.edits import AddBox, Intent
from deeplabeling.ui import chunked
from fixtures import FakePrompter, assert_only_changed, open_session, wait_decoded

BOX = (0.5, 0.5, 0.2, 0.2)
IMAGES = ("camA/0001.jpg", "camA/0003.jpg", "camA/0004.JPG", "camB/0001.jpg", "weird/имя пробел.jpg")


@pytest.fixture
def small_chunks(monkeypatch):
    monkeypatch.setattr(chunked, "CHUNK", 2)                 # 5 files: three chunks


@pytest.fixture
def prompter():
    return FakePrompter()


@pytest.fixture
def session(qtbot, ds, prompter, small_chunks):
    s = open_session(qtbot, ds.yaml, prompter)
    yield s
    s.close()


@pytest.fixture
def accepted(session, ds):
    before = ds.snapshot()
    session.workspace.editor.apply_many([Intent(ds.img(n), (AddBox(1, BOX),), "accept") for n in IMAGES],
                                        "accept missing boxes")
    return before, ds.snapshot()


def finished(session):
    return session.running is None


def test_a_big_edit_is_undone_and_redone_in_chunks_while_the_window_keeps_turning(qtbot, session, prompter,
                                                                                ds, accepted):
    before, after = accepted
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(0)
    session.undo()
    assert session.running is not None                      # not done at once
    qtbot.waitUntil(lambda: finished(session))
    timer.stop()
    assert_only_changed(before, ds.snapshot(), set())
    progress = prompter.progresses[-1]
    assert progress.title == "Undoing accept missing boxes" and progress.total == 10
    assert progress.values == sorted(progress.values) and progress.values[-1] == 10 and progress.closed
    assert len(ticks) >= 3                                   # the event loop ran between chunks
    with qtbot.waitSignal(session.status) as said:
        session.redo()
        qtbot.waitUntil(lambda: finished(session))
    assert said.args == ["↷ accept missing boxes: 5 files"]
    assert_only_changed(after, ds.snapshot(), set())


def test_a_cancelled_undo_keeps_what_it_wrote_as_an_edit_of_its_own(qtbot, session, prompter, ds, accepted):
    before, after = accepted
    prompter.cancel_at = 7                                  # 5 checked, then 2 written
    with qtbot.waitSignal(session.status, timeout=5000) as said:
        session.undo()
        qtbot.waitUntil(lambda: finished(session))
    assert said.args == ["undo stopped at 2 of 5 files; undo again for the rest"]
    assert_only_changed(after, ds.snapshot(), {"camA/labels/0001.txt", "camA/labels/0003.txt"})
    history = session.workspace.history
    assert len(history.peek_undo().changes) == 3 and len(history.peek_redo().changes) == 2
    prompter.cancel_at = None
    session.undo()
    qtbot.waitUntil(lambda: finished(session))
    assert_only_changed(before, ds.snapshot(), set())


def test_a_write_failing_part_way_says_so_and_keeps_the_rest_for_a_retry(qtbot, session, ds, accepted,
                                                                        monkeypatch):
    before, after = accepted
    real, calls = store_module.write_atomic, []

    def failing(path, data):
        calls.append(path)
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(store_module, "write_atomic", failing)
    with qtbot.waitSignal(session.notice, timeout=5000) as said:
        session.undo()
        qtbot.waitUntil(lambda: finished(session))
    assert "No space left on device" in said.args[1]
    assert said.args[1].endswith("3 of 5 files undone; undo again for the rest")
    monkeypatch.setattr(store_module, "write_atomic", real)
    session.undo()
    qtbot.waitUntil(lambda: finished(session))
    assert_only_changed(before, ds.snapshot(), set())


def test_nothing_else_edits_while_it_runs(qtbot, session, ds, accepted):
    wait_decoded(qtbot, session, session.current().entry.path)
    session.undo()
    with qtbot.waitSignal(session.status) as said:
        assert session.apply(Intent(ds.img("camA/0002.jpg"), (AddBox(0, BOX),), "draw")) is None
    assert said.args == ["wait — undoing accept missing boxes"]
    with qtbot.waitSignal(session.status) as said:
        session.undo()                                      # a second undo, pressed meanwhile
    assert said.args == ["wait — undoing accept missing boxes"]
    qtbot.waitUntil(lambda: finished(session))
    assert session.workspace.history.can_redo and not session.workspace.history.can_undo


def test_closing_the_dataset_stops_it_before_its_next_chunk(qtbot, session, prompter, ds, accepted):
    _, after = accepted
    session.undo()
    session.close()                                          # before the first chunk ran
    assert finished(session) and prompter.progresses[-1].closed
    qtbot.wait(50)
    assert_only_changed(after, ds.snapshot(), set())         # no chunk ran after the close


def test_a_small_edit_is_undone_at_once(qtbot, session, ds, small_chunks):
    wait_decoded(qtbot, session, ds.img("camA/0001.jpg"))
    before = ds.snapshot()
    session.apply(Intent(ds.img("camA/0001.jpg"), (AddBox(1, BOX),), "draw"))
    session.undo()
    assert finished(session)
    assert_only_changed(before, ds.snapshot(), set())
