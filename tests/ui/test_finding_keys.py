"""Fixing and dismissing findings from the full frame
(docs/design/2026-10-06-find-bad.md#keys)."""

import pytest
from PySide6.QtCore import Qt

import deeplabeling.ui.model as model_module
from deeplabeling.core.dismissals import Dismissals
from deeplabeling.core.findings import FindSettings, Findings
from drive import start
from finding_rows import FOUND, PERSON, P, factory, load, put_rows
from fixtures import CAMA_0001, read_exact

BUS_M = "2 0.750000 0.750000 0.150000 0.150000\n"


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    load(qtbot, w.session, weights)
    yield w
    w.close()


def findings(qtbot, window, rows=None):
    if rows:
        put_rows(window.session, rows)
    window.session.set_queue(Findings())
    qtbot.waitUntil(lambda: window.session.queue.complete and window.canvas.image_size is not None, timeout=5000)


def on(qtbot, window, key):
    window.session.go_to(key)
    qtbot.waitUntil(lambda: window._shown == window.session.current().entry.path, timeout=5000)


def test_a_finding_arrives_with_its_label_selected(qtbot, window):
    findings(qtbot, window)
    assert window.session.current().key == FOUND[1]          # the image the cursor was on: camA/0001
    assert window.editing.selected() == [1]
    on(qtbot, window, FOUND[0])
    assert window.editing.selected() == [0]


def test_m_takes_the_model_s_class_and_moves_on(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[0])
    qtbot.keyClick(window, Qt.Key_M)                         # sub/0005's bus_m: the model says car
    assert read_exact(ds.lbl("camA/sub/0005")) == "1 0.750000 0.750000 0.150000 0.150000\n"
    assert window.session.current().key == FOUND[1]
    assert window.session.finding_state(window.session.queue.items[0]) == "fixed"


def test_b_takes_the_model_s_box_keeping_the_class(qtbot, window, ds):
    findings(qtbot, window, {"camA/images/0001.jpg": [P(1, (0.26, 0.25, 0.1, 0.1), 0.95), P(1, PERSON, 0.9)]})
    on(qtbot, window, FOUND[1])
    qtbot.keyClick(window, Qt.Key_B)
    assert read_exact(ds.lbl("camA/0001")).splitlines()[1] == "1 0.260000 0.250000 0.100000 0.100000"
    assert window.session.current().key == FOUND[0]          # 0.95 at camA/0001 now sorts first


def test_a_key_that_cannot_apply_says_why_and_changes_nothing(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[2])                              # camB/0001: not an object, no model box
    for key, why in ((Qt.Key_M, "the model has no class for it"), (Qt.Key_B, "this finding has no model box")):
        with qtbot.waitSignal(window.session.status) as said:
            qtbot.keyClick(window, key)
        assert said.args == [why]
    assert read_exact(ds.lbl("camB/0001")) == BUS_M and window.session.current().key == FOUND[2]


def test_d_dismisses_moves_on_and_d_again_takes_it_back(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[0])
    qtbot.keyClick(window, Qt.Key_D)
    first = window.session.queue.items[0]
    assert window.session.finding_state(first) == "dismissed" and window.session.current().key == FOUND[1]
    on(qtbot, window, FOUND[0])
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_D)
    assert said.args == ["the dismissal is taken back"] and window.session.finding_state(first) == ""
    assert window.session.current().key == FOUND[0]
    qtbot.keyClick(window, Qt.Key_D)
    path = window.session.workspace.dismissals.path
    window.close()
    assert Dismissals(path, ds.root).has("camA/images/sub/0005.jpg", BUS_M.strip(), "wrong class")


def test_deleting_a_finding_s_label_moves_on(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[1])
    qtbot.keyClick(window, Qt.Key_Delete)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001.splitlines(keepends=True)[0]
    assert window.session.current().key == FOUND[2]


def test_m_finds_the_finding_s_line_after_a_line_above_it_is_deleted(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[1])                              # camA/0001's car, line 1
    window.editing.pick([0], window.session.labels(window.session.current().entry))
    qtbot.keyClick(window, Qt.Key_Delete)                    # the person: the car is line 0 now
    assert window.session.current().key == FOUND[1]          # not the finding's line: no moving on
    qtbot.keyClick(window, Qt.Key_M)
    assert read_exact(ds.lbl("camA/0001")) == "0 0.250000 0.250000 0.100000 0.100000\n"



def test_m_on_a_label_that_already_has_the_model_s_class_says_so(qtbot, window):
    window.session.set_queue(Findings(settings=FindSettings(weak=True)))
    qtbot.waitUntil(lambda: window.session.queue.complete and window.canvas.image_size is not None, timeout=5000)
    on(qtbot, window, "weird/images/имя пробел.jpg#0#weakly seen")         # the person, seen at 0.5
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_M)
    assert said.args == ["the label already has the model's class: D dismisses the finding"]


def test_b_on_a_label_that_has_the_model_s_box_already_says_so(qtbot, window, ds):
    findings(qtbot, window)
    on(qtbot, window, FOUND[1])                              # camA/0001's car: the model's person is on it exactly
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_B)
    assert said.args == ["the label has the model's box already: D dismisses the finding"]
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 and window.session.current().key == FOUND[1]
