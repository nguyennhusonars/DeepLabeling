"""Editing in the assembled window: the mouse on the canvas and the editing keys, read back
from the label files and from what is on screen (CLAUDE.md landmines 1 and 4)."""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QGuiApplication

from deeplabeling.core.labelio import parse_label_bytes
from deeplabeling.core.workspace import ACTIVE_CLASS
from deeplabeling.ui.settings_ui import SHOW_CROSSHAIR
from drive import click, drag, mouse, start, vp
from fixtures import CAMA_0001, FakePrompter, read_exact

# camA/0001.jpg is 64 x 48: person (line 0) spans x 25.6-38.4, y 16.8-31.2; car (line 1)
# spans x 12.8-19.2, y 9.6-14.4.
PERSON, CAR = (32, 24), (16, 12)


@pytest.fixture
def window(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)])
    yield w
    w.close()


def go(qtbot, window, key):
    window.session.go_to(key)
    path = window.session.current().entry.path
    qtbot.waitUntil(lambda: window._shown == path)


def lines(path):
    return [(line.cls_id, line.bbox) for line in parse_label_bytes(path.read_bytes())]


def selected(window):
    return window.editing.selection.indices(window.session.labels(window.session.current().entry))


def test_a_drawn_box_is_written_in_the_active_class_and_selected(qtbot, window, ds):
    go(qtbot, window, "camA/images/0003.jpg")
    drag(window.canvas, (10, 10), (30, 40))
    [(cls_id, bbox)] = lines(ds.lbl("camA/0003"))
    assert cls_id == 0 and bbox == pytest.approx((20 / 64, 25 / 48, 20 / 64, 30 / 48), abs=0.01)
    assert selected(window) == [0] and len(window.canvas.handle_items()) == 8
    qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert not ds.lbl("camA/0003").exists()


def test_a_digit_with_nothing_selected_sets_the_active_class_for_this_opening(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_2)
    assert window.editing.active_class().name == "car"
    assert window.session.workspace.opening_settings.get(ACTIVE_CLASS) == "car"
    go(qtbot, window, "camA/images/0003.jpg")
    drag(window.canvas, (10, 10), (30, 40))
    assert lines(ds.lbl("camA/0003"))[0][0] == 1
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert again.editing.active_class().name == "car"
    again.close()


def test_a_click_selects_and_a_digit_reclassifies_the_selection(qtbot, window, ds):
    click(window.canvas, PERSON)
    assert selected(window) == [0]
    qtbot.keyClick(window, Qt.Key_3)
    assert read_exact(ds.lbl("camA/0001")) == "2" + CAMA_0001[1:]
    assert selected(window) == [0] and window.editing.active_class().name == "person"


def test_a_digit_no_class_has_changes_nothing(qtbot, window, ds):
    click(window.canvas, PERSON)
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_9)
    assert said.args == ["no class has the key 9"]
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_the_class_picker_chooses_a_class_without_a_digit(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)], FakePrompter(class_name="bus_l"))
    qtbot.keyClick(w, Qt.Key_C)
    assert w.editing.active_class().name == "bus_l"
    assert ("class", ("person", "car", "bus_m", "bus_l")) in w.prompter.asked
    w.close()


def test_ctrl_a_then_delete_empties_the_file_and_keeps_it(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_A, Qt.ControlModifier)
    assert selected(window) == [0, 1]
    qtbot.keyClick(window, Qt.Key_Delete)
    assert ds.lbl("camA/0001").read_bytes() == b""      # a negative sample, never a deletion
    assert selected(window) == []


def test_backspace_deletes_too(qtbot, window, ds):
    click(window.canvas, CAR)
    qtbot.keyClick(window, Qt.Key_Backspace)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001.splitlines(keepends=True)[0]


def test_tab_and_shift_tab_step_through_the_boxes(qtbot, window):
    seen = []
    for key, modifier in ((Qt.Key_Tab, Qt.NoModifier), (Qt.Key_Tab, Qt.NoModifier),
                          (Qt.Key_Tab, Qt.NoModifier), (Qt.Key_Backtab, Qt.ShiftModifier)):
        qtbot.keyClick(window, key, modifier)
        seen.append(selected(window))
    assert seen == [[0], [1], [0], [1]]


def test_esc_cancels_a_drag_first_and_then_clears_the_selection(qtbot, window, ds):
    click(window.canvas, PERSON)
    drag(window.canvas, (50, 40), (60, 45), release=False)
    qtbot.keyClick(window, Qt.Key_Escape)
    mouse(window.canvas, QEvent.MouseButtonRelease, vp(window.canvas, 60, 45))
    assert selected(window) == [0] and read_exact(ds.lbl("camA/0001")) == CAMA_0001
    qtbot.keyClick(window, Qt.Key_Escape)
    assert selected(window) == [] and window.canvas.handle_items() == []


def test_dragging_a_selected_box_moves_it_in_the_file(qtbot, window, ds):
    click(window.canvas, PERSON)
    drag(window.canvas, PERSON, (PERSON[0] + 10, PERSON[1]))
    assert lines(ds.lbl("camA/0001"))[0][1] == pytest.approx((0.5 + 10 / 64, 0.5, 0.2, 0.3), abs=0.01)
    assert read_exact(ds.lbl("camA/0001")).endswith(CAMA_0001.splitlines(keepends=True)[1])
    assert selected(window) == [0]


def test_dragging_a_handle_resizes_the_box_in_the_file(qtbot, window, ds):
    click(window.canvas, PERSON)
    drag(window.canvas, (38.4, 31.2), (44.8, 36))
    assert lines(ds.lbl("camA/0001"))[0][1] == pytest.approx((0.55, 0.55, 0.3, 0.4), abs=0.01)
    assert selected(window) == [0]


def test_moving_a_polygon_is_refused_where_it_can_be_seen(qtbot, window, ds):
    go(qtbot, window, "seg/images/poly1.jpg")
    before = read_exact(ds.lbl("seg/poly1"))
    click(window.canvas, (9.6, 7.2))
    assert selected(window) == [0]
    drag(window.canvas, (9.6, 7.2), (20, 15))
    assert read_exact(ds.lbl("seg/poly1")) == before
    qtbot.waitUntil(window.notices.isVisible)
    assert any("polygon cannot be moved" in t for t in window.notices.texts())


def test_copy_and_paste_carry_boxes_to_another_image_as_one_edit(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClick(window, Qt.Key_C, Qt.ControlModifier)
    assert QGuiApplication.clipboard().text() == CAMA_0001
    go(qtbot, window, "camA/images/0003.jpg")
    qtbot.keyClick(window, Qt.Key_V, Qt.ControlModifier)
    assert read_exact(ds.lbl("camA/0003")) == CAMA_0001
    assert selected(window) == [0, 1]
    qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert not ds.lbl("camA/0003").exists()


def test_hiding_the_labels_clears_the_selection(qtbot, window, ds):
    click(window.canvas, PERSON)
    qtbot.keyClick(window, Qt.Key_L)
    assert selected(window) == []
    qtbot.keyClick(window, Qt.Key_Delete)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_the_crosshair_is_a_layer_that_persists(qtbot, window, ds):
    window.actions["toggle_crosshair"].trigger()
    assert window.canvas.show_crosshair and window.session.settings.get(SHOW_CROSSHAIR) is True
    assert window.state_bar.layers.full_text == "Layers: labels, captions, crosshair"
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert again.canvas.show_crosshair
    again.close()


def test_the_box_being_drawn_shows_the_active_class_colour(qtbot, window):
    go(qtbot, window, "camA/images/0003.jpg")
    qtbot.keyClick(window, Qt.Key_2)                            # car
    drag(window.canvas, (10, 10), (30, 40), release=False)
    want = QColor(window.editing.active_class().color)
    shot = window.canvas.viewport().grab().toImage()
    edge = vp(window.canvas, 30, 25)                            # the preview's right edge
    near = [QColor(shot.pixel(edge.x() + dx, edge.y() + dy)) for dx in range(-2, 3) for dy in range(-2, 3)]
    assert any(abs(c.red() - want.red()) + abs(c.green() - want.green()) + abs(c.blue() - want.blue()) < 40
               for c in near)
    window.canvas.cancel_drag()


def click_row(qtbot, listview, row, modifier=Qt.NoModifier):
    item = listview.item(row)
    qtbot.mouseClick(listview.viewport(), Qt.LeftButton, modifier, listview.visualItemRect(item).center())


def test_clicking_a_class_in_the_inspector_reclassifies_the_selection(qtbot, window, ds):
    click(window.canvas, PERSON)
    click_row(qtbot, window.inspector.classes, 3)                # bus_l
    assert read_exact(ds.lbl("camA/0001")) == "3" + CAMA_0001[1:]
    assert window.editing.active_class().name == "person"


def test_the_box_list_and_the_canvas_show_one_selection(qtbot, window):
    boxes = window.inspector.boxes
    qtbot.waitUntil(lambda: boxes.count() == 2)
    click(window.canvas, CAR)
    assert [boxes.item(i).isSelected() for i in range(2)] == [False, True]
    assert boxes.viewport().rect().contains(boxes.visualItemRect(boxes.item(1)))
    click_row(qtbot, boxes, 0)
    assert selected(window) == [0] and len(window.canvas.handle_items()) == 8
    click_row(qtbot, boxes, 1, Qt.ControlModifier)
    assert selected(window) == [0, 1] and window.canvas.handle_items() == []


def test_the_box_list_keeps_the_selection_through_an_edit(qtbot, window):
    boxes = window.inspector.boxes
    click(window.canvas, PERSON)
    qtbot.keyClick(window, Qt.Key_2)                             # reclassify: the list is rebuilt
    qtbot.waitUntil(lambda: boxes.count() == 2)
    assert [boxes.item(i).isSelected() for i in range(2)] == [True, False]


def test_every_kind_of_edit_undoes_back_to_the_bytes_it_started_from(qtbot, window, ds):
    before = ds.snapshot()
    go(qtbot, window, "camA/images/0003.jpg")
    drag(window.canvas, (5, 5), (20, 20))                       # draw a person
    qtbot.keyClick(window, Qt.Key_2)                            # it is a car
    drag(window.canvas, (12, 12), (22, 17))                     # move it by (10, 5)
    drag(window.canvas, (30, 25), (35, 32))                     # its bottom-right handle
    [(cls_id, bbox)] = lines(ds.lbl("camA/0003"))
    assert cls_id == 1 and bbox == pytest.approx((25 / 64, 21 / 48, 20 / 64, 22 / 48), abs=0.01)
    qtbot.keyClick(window, Qt.Key_C, Qt.ControlModifier)
    go(qtbot, window, "camA/images/0001.jpg")
    qtbot.keyClick(window, Qt.Key_V, Qt.ControlModifier)        # pasted, and selected
    assert len(lines(ds.lbl("camA/0001"))) == 3 and selected(window) == [2]
    qtbot.keyClick(window, Qt.Key_Delete)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001
    assert window.session.workspace.history.depth == 6
    for _ in range(6):
        qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert ds.snapshot() == before
    assert window.session.current().key == "camA/images/0003.jpg"   # undo went to its image


INSERTED = "2 0.100000 0.100000 0.050000 0.050000\n"


def write_unseen(window, ds, text):
    """Another program rewrites the label file, and the app has not looked since: its
    watch, which re-reads the file on screen every 1.5 s, is stopped."""
    window.session._watch.stop()
    ds.lbl("camA/0001").write_bytes(text.encode())


def test_a_handle_drag_resizes_the_box_it_showed_after_an_unseen_outside_write(qtbot, window, ds):
    click(window.canvas, PERSON)
    write_unseen(window, ds, INSERTED + CAMA_0001)          # the person is now line 1
    drag(window.canvas, (38.4, 31.2), (44.8, 36))
    assert read_exact(ds.lbl("camA/0001")).startswith(INSERTED)
    assert lines(ds.lbl("camA/0001"))[1][1] == pytest.approx((0.55, 0.55, 0.3, 0.4), abs=0.01)


def test_a_click_selects_the_box_it_showed_after_an_unseen_outside_write(qtbot, window, ds):
    write_unseen(window, ds, INSERTED + CAMA_0001)
    click(window.canvas, CAR)
    qtbot.keyClick(window, Qt.Key_Delete)
    assert read_exact(ds.lbl("camA/0001")) == INSERTED + CAMA_0001.splitlines(keepends=True)[0]


def test_a_box_list_click_selects_the_box_it_listed_after_an_unseen_outside_write(qtbot, window, ds):
    boxes = window.inspector.boxes
    qtbot.waitUntil(lambda: boxes.count() == 2)
    write_unseen(window, ds, INSERTED + CAMA_0001)
    click_row(qtbot, boxes, 1)                               # car, as listed
    qtbot.keyClick(window, Qt.Key_Delete)
    assert read_exact(ds.lbl("camA/0001")) == INSERTED + CAMA_0001.splitlines(keepends=True)[0]


def test_with_the_labels_hidden_no_key_or_list_click_touches_a_box(qtbot, window, ds):
    boxes = window.inspector.boxes
    qtbot.waitUntil(lambda: boxes.count() == 2)
    qtbot.keyClick(window, Qt.Key_L)
    qtbot.keyClick(window, Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClick(window, Qt.Key_Delete)
    qtbot.keyClick(window, Qt.Key_Tab)
    qtbot.keyClick(window, Qt.Key_2)                         # sets the active class instead
    click_row(qtbot, boxes, 0)
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 and selected(window) == []
    assert window.editing.active_class().name == "car" and not boxes.item(0).isSelected()


def test_undo_on_the_image_on_screen_keeps_the_selection(qtbot, window, ds):
    drag(window.canvas, (50, 40), (60, 46))                 # a new box, selected
    click(window.canvas, PERSON)
    qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)    # the drawn box goes; the person stays
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 and selected(window) == [0]


def test_an_edit_redraws_the_canvas_once(qtbot, window, monkeypatch):
    click(window.canvas, PERSON)
    redraws, redraw = [], window.canvas._redraw
    monkeypatch.setattr(window.canvas, "_redraw", lambda: (redraws.append(1), redraw()))
    qtbot.keyClick(window, Qt.Key_3)
    assert len(redraws) == 1 and selected(window) == [0]
    assert len(window.canvas.handle_items()) == 8


def test_copying_polygons_says_they_were_left_out(qtbot, window):
    go(qtbot, window, "seg/images/mixed.jpg")
    qtbot.keyClick(window, Qt.Key_A, Qt.ControlModifier)
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_C, Qt.ControlModifier)
    assert said.args == ["copied 1 box; 1 polygon is not copied: a paste would make it a box"]


def test_a_paste_says_what_it_skipped(qtbot, window, ds):
    QGuiApplication.clipboard().setText("0 0.5 0.5 0.2 0.2\n9 0.5 0.5 0.1 0.1\nnot a box\n")
    go(qtbot, window, "camA/images/0003.jpg")
    with qtbot.waitSignal(window.session.status) as said:
        qtbot.keyClick(window, Qt.Key_V, Qt.ControlModifier)
    assert said.args == ["pasted 1 box; 2 lines were not boxes of this dataset's classes"]
    assert len(lines(ds.lbl("camA/0003"))) == 1


def test_a_paste_under_another_class_list_keeps_each_box_its_class_name(qtbot, window, ds):
    import yaml

    qtbot.keyClick(window, Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClick(window, Qt.Key_C, Qt.ControlModifier)    # person (id 0), car (id 1)
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data["names"] = ["car", "truck", "person"]
    other = ds.root / "other.yaml"
    other.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with qtbot.waitSignal(window.session.queueDone, timeout=5000):
        assert window.session.open(other)
    go(qtbot, window, "camA/images/0003.jpg")
    qtbot.keyClick(window, Qt.Key_V, Qt.ControlModifier)
    assert [cls for cls, _ in lines(ds.lbl("camA/0003"))] == [2, 0]   # person, car by name
