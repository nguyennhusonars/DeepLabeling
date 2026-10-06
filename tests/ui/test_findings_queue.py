"""A Find Bad queue in the session (docs/design/2026-10-06-find-bad.md#the-queue)."""

import pytest

from deeplabeling.core.edits import Intent, SetClass
from deeplabeling.core.findings import Findings
from deeplabeling.core.queue import Scanned
from finding_rows import FOUND, KEY, P, load, put_rows
from fixtures import open_session


@pytest.fixture
def weights(tmp_path):
    path = tmp_path / "best.pt"
    path.write_bytes(b"weights")
    return path


@pytest.fixture
def session(qtbot, ds, weights):
    s = open_session(qtbot, ds.yaml)
    load(qtbot, s, weights)
    yield s
    s.close()


def found(qtbot, session, source=Findings()):
    session.set_queue(source)
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    return [item.key for item in session.queue.items]


def test_a_findings_queue_lists_them_in_order_and_counts_them_by_kind(qtbot, session):
    assert found(qtbot, session) == FOUND
    assert session.progress_text() == " · 2 wrong class · 1 not an object · 9 not inferred"


def test_while_it_scans_the_chip_says_how_far(qtbot, session):
    found(qtbot, session)
    queue = session.queue
    queue.complete = False
    session._grew(queue, Scanned(5, 15))
    assert session.progress_text() == " · scanning 5 / 15"


def test_a_dismissed_finding_is_left_out_of_the_next_scan(qtbot, session):
    session.workspace.dismissals.dismiss("camA/images/0001.jpg", "1 0.250000 0.250000 0.100000 0.100000",
                                         "wrong class")
    assert found(qtbot, session) == [FOUND[0], FOUND[2]]


def test_review_marks_and_left_go_by_image(qtbot, session):
    found(qtbot, session)
    session.go_to(FOUND[1])
    rows = []
    session.itemsChanged.connect(lambda keys: rows.append(list(keys)))
    session.done_and_next()
    assert session.workspace.review.is_marked("camA/images/0001.jpg")
    assert rows[-1] == [FOUND[1]] and session.left() == 2
    assert session.describe_item(session.queue.items[1]).startswith("✓ ")


def test_an_edit_that_fixes_a_finding_shows_it_fixed(qtbot, session, ds):
    found(qtbot, session)
    item = session.queue.items[1]                     # the car the model calls a person
    from fixtures import wait_decoded

    wait_decoded(qtbot, session, item.entry.path)
    session.apply(Intent(item.entry.path, (SetClass(item.focus, 0),), "take the model's class"))
    assert session.queue.stale == {FOUND[1]}


def test_findings_of_an_image_inferred_later_join_in_their_place(qtbot, session, ds):
    found(qtbot, session)
    put_rows(session, {"camB/images/rot.jpg": [P(0, (0.75, 0.75, 0.15, 0.15), 0.85)]})   # a bus_m called a car
    with qtbot.waitSignal(session.itemInserted):
        session.model.ready.emit(ds.root / "camB/images/rot.jpg")
    assert [item.key for item in session.queue.items] == [
        FOUND[0], "camB/images/rot.jpg#0#wrong class", FOUND[1], FOUND[2]]
    assert session.progress_text().endswith(" · 8 not inferred")


def test_a_rebuild_keeps_the_finding_the_cursor_is_on(qtbot, session):
    found(qtbot, session)
    session.go_to(FOUND[1])
    session.model.set_class_map(session.model.class_map.with_target(3, "car"))    # rebuilds
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    assert session.current().key == FOUND[1]


def test_a_findings_queue_and_its_place_survive_a_relaunch(qtbot, ds, weights, monkeypatch):
    import deeplabeling.ui.model as model_module
    from drive import start
    from finding_rows import factory

    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    window = start(qtbot, [str(ds.yaml)])
    load(qtbot, window.session, weights)
    found(qtbot, window.session)
    window.session.go_to(FOUND[2])
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert again.session.queue.source == Findings()
    qtbot.waitUntil(lambda: again.session.queue.complete and len(again.session.queue) == 3, timeout=5000)
    assert again.session.current().key == FOUND[2]
    again.close()


def test_without_a_model_it_waits_says_so_and_builds_when_one_is_loaded(qtbot, ds, weights):
    s = open_session(qtbot, ds.yaml)
    s.set_queue(Findings())
    assert s.queue.waiting and len(s.queue) == 0 and s.progress_text() == " · needs a model"
    load(qtbot, s, weights)
    qtbot.waitUntil(lambda: not s.queue.waiting and s.queue.complete, timeout=5000)
    assert [item.key for item in s.queue.items] == FOUND
    s.close()
