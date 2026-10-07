"""Several findings at once, from the grid: selected tiles take a key together, as one
edit that marks nothing (docs/design/2026-10-06-find-bad.md#the-grid)."""

import pytest
from PySide6.QtCore import Qt

import deeplabeling.ui.model as model_module
from deeplabeling.core.dismissals import Dismissals
from deeplabeling.core.edits import Intent, SetClass
from deeplabeling.core.findings import Findings
from drive import start
from finding_rows import FOUND_TWO, TWO, P, factory, load, put_rows
from fixtures import CAMA_0001, CAMB_0001, read_exact

PERSON2 = (0.51, 0.5, 0.2, 0.3)     #: the model's box for camA/0001's person, a little to the right
TWIN = {"camB/images/twin.jpg": [P(0, (0.5, 0.5, 0.1, 0.1), 0.9)]}     # its person, a car: its file is shared


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    load(qtbot, w.session, weights)
    put_rows(w.session, {**TWO, **TWIN})
    w.session.set_queue(Findings())
    qtbot.waitUntil(lambda: w.session.queue.complete, timeout=5000)
    w.queue_panel.set_grid(True)
    w.resize(1400, 900)
    qtbot.wait(50)
    yield w
    w.close()


def click(qtbot, window, key, modifier=Qt.NoModifier):
    panel = window.queue_panel
    rect = panel.view.visualRect(panel.model.index(window.session.queue.index_of(key)))
    qtbot.mouseClick(panel.view.viewport(), Qt.LeftButton, modifier, rect.center())


def select(qtbot, window, keys):
    click(qtbot, window, keys[0])
    for key in keys[1:]:
        click(qtbot, window, key, Qt.ControlModifier)
    assert [item.key for item in window.queue_panel.selected_findings()] == keys


def states(session, keys):
    return [session.finding_state(session.queue.items[session.queue.index_of(key)]) for key in keys]


def said(qtbot, window, key):
    with qtbot.waitSignal(window.session.status) as signal:
        qtbot.keyClick(window, key)
    return signal.args[0]


def test_ctrl_click_selects_several_tiles_and_a_plain_click_one(qtbot, window):
    select(qtbot, window, FOUND_TWO[:3])
    assert window.session.current().key == FOUND_TWO[2]
    click(qtbot, window, FOUND_TWO[0])
    assert [item.key for item in window.queue_panel.selected_findings()] == FOUND_TWO[:1]


def test_m_on_several_tiles_is_one_edit_that_marks_nothing(qtbot, window, ds):
    select(qtbot, window, FOUND_TWO[:3])
    assert said(qtbot, window, Qt.Key_M) == "took the model's class on 3 findings"
    assert read_exact(ds.lbl("camA/sub/0005")) == "1 0.750000 0.750000 0.150000 0.150000\n"
    assert read_exact(ds.lbl("camA/0001")) == "1 0.500000 0.500000 0.200000 0.300000\n0 0.250000 0.250000 0.100000 0.100000\n"
    session = window.session
    assert len(session.workspace.review.keys()) == 0                     # a crop is not the image
    assert states(session, FOUND_TWO[:3]) == ["fixed"] * 3
    session.undo()                                                       # one undo takes it all back
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 and read_exact(ds.lbl("camA/sub/0005")) == CAMB_0001


def test_a_tile_the_key_cannot_apply_to_is_skipped_and_counted(qtbot, window, ds):
    select(qtbot, window, [FOUND_TWO[0], FOUND_TWO[3]])                 # camB/0001: not an object
    assert said(qtbot, window, Qt.Key_M) == ("took the model's class on 1 finding; "
                                             "skipped 1 (no model class)")
    assert read_exact(ds.lbl("camB/0001")) == CAMB_0001


def test_a_shared_label_file_is_skipped_and_the_rest_is_one_edit(qtbot, window, ds):
    twin = "camB/images/twin.jpg#0#wrong class"
    select(qtbot, window, [FOUND_TWO[0], twin])
    assert said(qtbot, window, Qt.Key_Delete) == ("deleted 1 finding's label; "
                                                  "skipped 1 (read-only)")
    assert read_exact(ds.lbl("camA/sub/0005")) == "" and read_exact(ds.lbl("camB/twin")).startswith("0 ")


def test_a_class_key_on_several_tiles_sets_each_label_s_class(qtbot, window, ds):
    select(qtbot, window, FOUND_TWO[1:3])
    assert said(qtbot, window, Qt.Key_3) == "set 2 findings to bus_m"
    assert read_exact(ds.lbl("camA/0001")) == "2 0.500000 0.500000 0.200000 0.300000\n2 0.250000 0.250000 0.100000 0.100000\n"


def test_b_on_several_tiles_takes_each_model_box(qtbot, window, ds):
    put_rows(window.session, {"camA/images/0001.jpg": [P(1, (0.26, 0.25, 0.1, 0.1), 0.8), P(0, PERSON2, 0.9)]})
    window.session.set_queue(Findings())
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    select(qtbot, window, FOUND_TWO[1:3])
    assert said(qtbot, window, Qt.Key_B) == "took the model's box on 2 findings"
    assert read_exact(ds.lbl("camA/0001")) == "0 0.510000 0.500000 0.200000 0.300000\n1 0.260000 0.250000 0.100000 0.100000\n"



def test_d_on_several_tiles_dismisses_them_together_and_d_again_takes_them_back(qtbot, window, ds):
    select(qtbot, window, FOUND_TWO[:2])
    assert said(qtbot, window, Qt.Key_D) == "dismissed 2 findings"
    session = window.session
    assert states(session, FOUND_TWO[:2]) == ["dismissed"] * 2
    assert said(qtbot, window, Qt.Key_D) == "2 dismissals taken back"
    assert states(session, FOUND_TWO[:2]) == [""] * 2
    qtbot.keyClick(window, Qt.Key_D)
    path = session.workspace.dismissals.path
    window.close()
    saved = Dismissals(path, ds.root)
    assert saved.has("camA/images/sub/0005.jpg", CAMB_0001.strip(), "wrong class")
    assert saved.has("camA/images/0001.jpg", CAMA_0001.splitlines()[0], "wrong class")


def test_a_finding_whose_line_changed_since_is_skipped(qtbot, window, ds):
    session = window.session
    item = session.queue.items[session.queue.index_of(FOUND_TWO[1])]           # camA/0001's person
    session.workspace.editor.apply(Intent(item.entry.path, (SetClass(item.focus, 1),), "fixed elsewhere"))
    select(qtbot, window, FOUND_TWO[:2])
    assert said(qtbot, window, Qt.Key_Delete) == ("deleted 1 finding's label; "
                                                  "skipped 1 (changed since)")
    assert read_exact(ds.lbl("camA/sub/0005")) == ""
    assert read_exact(ds.lbl("camA/0001")).startswith("1 0.500000 0.500000")


def test_a_key_after_a_tile_is_deselected_acts_on_the_selected_tile(qtbot, window, ds):
    click(qtbot, window, FOUND_TWO[1])
    click(qtbot, window, FOUND_TWO[0], Qt.ControlModifier)
    click(qtbot, window, FOUND_TWO[0], Qt.ControlModifier)               # deselected, but still current
    assert window.session.current().key == FOUND_TWO[0]
    assert [item.key for item in window.queue_panel.selected_findings()] == [FOUND_TWO[1]]
    qtbot.keyClick(window, Qt.Key_M)
    assert read_exact(ds.lbl("camA/sub/0005")) == CAMB_0001               # the deselected tile: untouched
    assert read_exact(ds.lbl("camA/0001")).startswith("1 0.500000 0.500000")


def test_a_box_picked_on_the_canvas_is_what_a_key_acts_on(qtbot, window, ds):
    select(qtbot, window, [FOUND_TWO[0], FOUND_TWO[1]])                  # current: camA/0001
    qtbot.waitUntil(lambda: window.canvas.image_size is not None, timeout=5000)
    window.canvas.picked.emit([1])                                       # the car, picked on the canvas
    assert [item.key for item in window.queue_panel.selected_findings()] == [FOUND_TWO[1]]
    qtbot.keyClick(window, Qt.Key_Delete)
    assert read_exact(ds.lbl("camA/sub/0005")) == CAMB_0001
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001.splitlines(keepends=True)[0]


def test_switching_to_the_list_and_back_keeps_only_the_current_tile(qtbot, window):
    select(qtbot, window, FOUND_TWO[:2])
    window.queue_panel.set_grid(False)
    window.queue_panel.set_grid(True)
    assert [item.key for item in window.queue_panel.selected_findings()] == [FOUND_TWO[1]]


def test_b_skips_a_polygon_and_the_rest_is_one_edit(qtbot, window, ds):
    put_rows(window.session, {"seg/images/poly1.jpg": [P(0, (0.15, 0.15, 0.1, 0.1), 0.9)],     # the polygon: a car
                              "camA/images/sub/0005.jpg": [P(0, (0.76, 0.75, 0.15, 0.15), 0.95)]})
    window.session.set_queue(Findings())
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    select(qtbot, window, [FOUND_TWO[0], "seg/images/poly1.jpg#0#wrong class"])
    assert said(qtbot, window, Qt.Key_B) == ("took the model's box on 1 finding; "
                                             "skipped 1 (a polygon)")
    assert read_exact(ds.lbl("camA/sub/0005")) == "2 0.760000 0.750000 0.150000 0.150000\n"


def test_b_on_a_label_that_has_the_model_s_box_already_is_skipped_and_said(qtbot, window, ds):
    select(qtbot, window, FOUND_TWO[1:3])                                # the model's boxes are the labels'
    assert said(qtbot, window, Qt.Key_B) == "nothing changed; skipped 2 (already the model's box)"
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_the_class_picker_on_several_tiles_sets_each_label_s_class(qtbot, window, ds):
    select(qtbot, window, FOUND_TWO[1:3])
    window.prompter.class_name = "bus_m"
    with qtbot.waitSignal(window.session.status) as signal:
        window.actions["pick_class"].trigger()
    assert signal.args == ["set 2 findings to bus_m"]
    assert read_exact(ds.lbl("camA/0001")) == "2 0.500000 0.500000 0.200000 0.300000\n2 0.250000 0.250000 0.100000 0.100000\n"
