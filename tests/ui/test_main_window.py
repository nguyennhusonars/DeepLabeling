"""The assembled window, driven by keys and read back from what is on screen
(the run-and-verify-ui skill; CLAUDE.md landmine 4)."""

from itertools import combinations

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLineEdit

from deeplabeling.__main__ import launch
from deeplabeling.core.queue import HasClass, ImageFilter
from deeplabeling.ui.settings_ui import SHOW_LABELS
from drive import start
from fixtures import FakePrompter


@pytest.fixture
def window(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)])
    yield w
    w.close()


def on_screen(window, widget) -> QRect:
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


@pytest.mark.parametrize("size", [(1024, 640), (1920, 1080)])
def test_every_part_is_visible_inside_the_window_and_apart(qtbot, window, size):
    window.resize(*size)
    qtbot.waitUntil(lambda: (window.width(), window.height()) == size)
    window.notices.add("error", "a refusal stays here")
    parts = {"state bar": window.state_bar, "notices": window.notices, "canvas": window.canvas,
             "queue": window.queue_panel.view, "inspector": window.inspector}
    rects = {}
    for name, widget in parts.items():
        qtbot.waitUntil(widget.isVisible)
        rect = on_screen(window, widget)
        assert rect.width() > 0 and rect.height() > 0, name
        assert window.rect().contains(rect), name
        rects[name] = rect
    for a, b in combinations(rects, 2):
        assert not rects[a].intersects(rects[b]), (a, b)
    for chip in (window.state_bar.dataset, window.state_bar.queue,
                 window.state_bar.layers, window.state_bar.reviewed):
        assert chip.isVisible() and chip.width() >= 40
        assert window.rect().contains(on_screen(window, chip))


def test_the_canvas_shows_the_current_image_and_its_boxes(window):
    assert window.canvas.image_size == (64, 48)
    shot = window.canvas.viewport().grab().toImage()
    centre = window.canvas.mapFromScene(QPointF(32, 16.8))      # the person box's top edge
    near = [QColor(shot.pixel(centre.x() + dx, centre.y() + dy)) for dx in (-2, 0, 2) for dy in range(-2, 3)]
    assert any(c.red() > 200 and c.green() < 80 and 40 < c.blue() < 120 for c in near)  # #e6194b
    assert [c.text for c in window.canvas.caption_items()] == ["person", "car"]


def test_arrow_keys_page_without_marking(qtbot, window):
    for key in (Qt.Key_Right, Qt.Key_Right, Qt.Key_Down, Qt.Key_Left):
        qtbot.keyClick(window, key)
    assert window.session.current().key == "camA/images/0003.jpg"
    assert window.session.workspace.review.count() == 0
    assert window.status_text.text().startswith("camA/images/0003.jpg · ")


def test_space_marks_and_moves_and_k_toggles(qtbot, window):
    qtbot.keyClick(window, Qt.Key_Space)
    assert window.session.current().key == "camA/images/0002.jpg"
    assert window.state_bar.reviewed.full_text == "✓ 1/15"
    qtbot.keyClick(window, Qt.Key_K)
    assert window.state_bar.reviewed.full_text == "✓ 2/15"


def test_n_marks_a_missing_image_negative_and_ctrl_z_takes_it_back(qtbot, window, ds):
    window.session.go_to("camA/images/0003.jpg")
    qtbot.waitUntil(lambda: window._shown == ds.img("camA/0003.jpg"))     # edits wait for the image
    qtbot.keyClick(window, Qt.Key_N)
    assert ds.lbl("camA/0003").read_bytes() == b""
    assert "↶1" in window.status_text.text()
    qtbot.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    assert not ds.lbl("camA/0003").exists()


def test_a_refusal_appears_in_the_visible_notice_strip(qtbot, window):
    qtbot.keyClick(window, Qt.Key_N)                # camA/0001 already has labels
    qtbot.waitUntil(window.notices.isVisible)
    row = next(r for r in window.notices.rows if "already has a label file" in r.text)
    assert row.label.isVisible() and window.rect().contains(on_screen(window, row.label))


def test_ids_the_yaml_does_not_name_stay_on_screen(qtbot, window):
    qtbot.waitUntil(lambda: any("does not name" in t for t in window.notices.texts()))
    assert window.notices.isVisible()


def test_an_undecodable_image_says_so_on_the_canvas_and_the_strip(qtbot, window):
    window.session.go_to("bad/images/corrupt.jpg")
    qtbot.waitUntil(lambda: window.canvas.message.startswith("Cannot decode bad/images/corrupt.jpg"))
    assert any("cannot decode" in t for t in window.notices.texts())


def test_layers_toggle_from_their_keys_and_persist(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_L)
    assert not window.canvas.show_labels and window.canvas.caption_items() == []
    assert window.session.settings.get(SHOW_LABELS) is False
    assert window.state_bar.layers.full_text == "👁 captions · predictions"
    qtbot.keyClick(window, Qt.Key_T)
    assert window.state_bar.layers.full_text == "👁 predictions"
    window.close()
    again = start(qtbot, [str(ds.yaml)])
    assert not again.actions["toggle_labels"].isChecked() and not again.canvas.show_labels
    again.close()


def test_zoom_keys(qtbot, window):
    scale = window.canvas.transform().m11()
    qtbot.keyClick(window, Qt.Key_Equal)
    assert window.canvas.transform().m11() > scale
    qtbot.keyClick(window, Qt.Key_F)
    assert window.canvas.transform().m11() == pytest.approx(scale)
    qtbot.keyClick(window, Qt.Key_Minus)
    assert window.canvas.transform().m11() < scale


def test_ctrl_g_goes_to_an_item(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)], FakePrompter(text="poly"))
    qtbot.keyClick(w, Qt.Key_G, Qt.ControlModifier)
    assert w.session.current().key == "seg/images/poly1.jpg"
    w.close()


def test_the_queue_chip_edits_the_queue(qtbot, ds):
    chosen = ImageFilter(conditions=(HasClass(("bus_m",)),))
    w = start(qtbot, [str(ds.yaml)], FakePrompter(queue=chosen))
    with qtbot.waitSignal(w.session.queueDone, timeout=5000):
        qtbot.mouseClick(w.state_bar.queue, Qt.LeftButton)
    assert len(w.session.queue) == 3
    assert w.state_bar.queue.full_text.startswith("☰ has a bus_m · 3 left of 3")
    w.close()


def test_the_help_key_shows_every_shortcut(qtbot, window):
    qtbot.keyClick(window, Qt.Key_Question)
    qtbot.waitUntil(lambda: window._help is not None and window._help.isVisible())


def test_no_shortcut_fires_while_a_text_field_has_focus(qtbot, window):
    field = QLineEdit()
    window.statusBar().addWidget(field)
    field.show()
    field.setFocus()
    qtbot.waitUntil(field.hasFocus)
    qtbot.keyClick(field, Qt.Key_K)
    qtbot.keyClick(field, Qt.Key_Space)
    assert window.session.workspace.review.count() == 0 and field.text() == "k "


def test_an_outside_edit_appears_on_the_canvas(qtbot, window, ds):
    assert [c.text for c in window.canvas.caption_items()] == ["person", "car"]
    ds.lbl("camA/0001").write_bytes(b"3 0.5 0.5 0.1 0.1\n")
    qtbot.waitUntil(lambda: [c.text for c in window.canvas.caption_items()] == ["bus_l"], timeout=5000)


def test_rapid_paging_ends_on_the_current_image(qtbot, ds):
    from PIL import Image
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor

    Image.new("RGB", (64, 48), (255, 0, 255)).save(ds.img("weird/имя пробел.jpg"))    # the one magenta frame
    window = launch([str(ds.yaml)], FakePrompter())
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()
    qtbot.waitUntil(lambda: window.canvas.image_size is not None, timeout=5000)
    for _ in range(9):
        qtbot.keyClick(window, Qt.Key_Right)
    current = window.session.current()
    assert current.key == "weird/images/имя пробел.jpg"
    qtbot.waitUntil(lambda: window._shown == current.entry.path)
    qtbot.wait(200)                         # late decodes of skipped images arrive
    shot = window.canvas.viewport().grab().toImage()
    middle = QColor(shot.pixel(window.canvas.mapFromScene(QPointF(32, 24))))
    assert middle.red() > 240 and middle.green() < 15 and middle.blue() > 240     # drawn: the frame itself
    assert window.status_text.text().startswith(current.key)
    window.close()


def test_closing_while_jobs_run_frees_the_root(qtbot, ds):
    w = launch([str(ds.yaml)], FakePrompter())
    qtbot.addWidget(w)
    w.show()
    w.close()                               # the queue build and the id count are running
    assert w.session.workspace is None
    again = start(qtbot, [str(ds.yaml)])    # the lock is free
    again.close()


def test_a_label_file_created_outside_appears_on_the_canvas(qtbot, window, ds):
    window.session.go_to("camA/images/0003.jpg")
    qtbot.waitUntil(lambda: window._shown == ds.img("camA/0003.jpg"))
    assert window.canvas.caption_items() == []
    ds.lbl("camA/0003").write_bytes(b"1 0.5 0.5 0.2 0.2\n")
    qtbot.waitUntil(lambda: [c.text for c in window.canvas.caption_items()] == ["car"], timeout=5000)


def test_the_queue_chip_can_refresh_the_same_queue(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)], FakePrompter(queue=ImageFilter()))    # the queue in force
    with qtbot.waitSignal(w.session.queueReset, timeout=2000):
        qtbot.mouseClick(w.state_bar.queue, Qt.LeftButton)
    w.close()


def test_a_closed_panel_can_be_shown_again(qtbot, window):
    window.queue_dock.close()
    qtbot.waitUntil(lambda: not window.queue_dock.isVisible())
    action = next(a for a in window.panels_menu.actions() if a.text() == "Queue")
    action.trigger()
    qtbot.waitUntil(window.queue_dock.isVisible)
    assert window.state_bar.layers.full_text == "👁 labels · captions · predictions"



def test_a_second_help_press_brings_the_one_help_window_forward(qtbot, ds):
    from deeplabeling.ui.keymap import HelpDialog
    from drive import start

    w = start(qtbot, [str(ds.yaml)])
    w.show_help()
    w.show_help()
    assert len([d for d in w.findChildren(HelpDialog) if d.isVisible()]) == 1
    w.close()


def test_written_is_stamped_only_when_files_are_written(qtbot, ds):
    from deeplabeling.core.edits import AddBox, Intent
    from drive import start

    w = start(qtbot, [str(ds.yaml)])
    s = w.session
    s.workspace.editor.apply(Intent(ds.img("camA/0001.jpg"), (AddBox(1, (0.9, 0.9, 0.05, 0.05)),), "add"))
    assert w._written is not None
    w._written = None
    ds.lbl("camA/0001").write_text("1 0.1 0.1 0.1 0.1\n")     # changed outside: the undo is refused
    s.undo()
    assert w._written is None and "💾" not in w.status_text.text()
    w.close()


def test_arriving_at_an_image_the_model_failed_on_says_so_once(qtbot, ds, tmp_path):
    from drive import start
    from fixtures import FakePredictor

    w = start(qtbot, [str(ds.yaml)])
    s = w.session
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    s.model.factory = lambda path: FakePredictor(path, fail={"0002.jpg"})
    s.model.load(weights)                                    # on 0001: 0002, a neighbour, fails out of sight
    qtbot.waitUntil(lambda: ds.img("camA/0002.jpg") in s.model._failures, timeout=5000)
    s.go_to("camA/images/0002.jpg")
    s.go_to("camA/images/0001.jpg")
    s.go_to("camA/images/0002.jpg")
    said = [t for t in w.notices.texts() if "prediction failed" in t]
    assert said == ["camA/images/0002.jpg: prediction failed — 0002.jpg: CUDA out of memory"]
    w.notices.clear()                                        # dismissed
    s.cursorChanged.emit()                                   # the same image, re-shown (a rebuild)
    assert not [t for t in w.notices.texts() if "prediction failed" in t]
    w.close()
