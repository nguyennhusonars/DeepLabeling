"""A Blurry queue in the window (docs/design/2026-10-27-blurry.md#window): crop tiles, the
spotlight, the rows, and the keys."""

import pytest
from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor

from deeplabeling.core.blurry import Blurry, BlurSettings
from deeplabeling.core.crops import crop_rect
from deeplabeling.ui.queue_panel import tile_text, tile_thumb_rect
from drive import start
from fixtures import build_blur_dataset, read_exact


@pytest.fixture
def window(qtbot, tmp_path):
    blur = build_blur_dataset(tmp_path / "b")
    w = start(qtbot, [str(blur.yaml)])
    w.session.set_queue(Blurry(settings=BlurSettings(share=0.1)))
    qtbot.waitUntil(lambda: w.session.queue.complete, timeout=10000)
    w.session.go_to(w.session.queue.items[0].key)          # the queue follows the image it was on
    w.resize(1200, 800)
    qtbot.wait(50)
    w.blur = blur
    yield w
    w.close()


def test_the_row_and_the_inspector_say_how_blurry(window):
    item = window.session.current()
    assert window.session.describe_item(item).endswith(("blurry: head, 0.0% of 32–63 px",
                                                        "blurry: human, 0.0% of 16–31 px"))
    assert window.inspector.finding_label.text().startswith("blurry · 0.0% of ")


def test_a_blurry_queue_shows_crop_tiles(qtbot, window):
    session, panel = window.session, window.queue_panel
    panel.set_grid(True)
    item = session.queue.items[0]
    crop = session.crop_of(item)
    assert crop is not None and crop.rect == crop_rect(item.finding.label_box, None, 160, 120)
    qtbot.waitUntil(lambda: session.crops.get(crop) is not None, timeout=5000)
    qtbot.wait(20)
    assert session.thumbs.get(item.entry.path) is None                     # the crop, not the frame
    x0, y0, x1, y1 = crop.rect
    target = tile_thumb_rect(panel.view.visualRect(panel.model.index(0)), QSize(x1 - x0, y1 - y0))
    shot = panel.view.viewport().grab().toImage()
    greys = {QColor(shot.pixel(target.center().x() + dx, target.center().y() + dy)).lightness()
             for dx in range(-8, 9, 4) for dy in range(-8, 9, 4)}
    assert target.width() > 60 and len(greys) > 5                          # texture drawn, not a flat frame
    assert tile_text(session, item).endswith(f"{session.workspace.dataset.names[item.focus.cls_id]} 0.0%")


def test_the_spotlight_dims_outside_a_blurry_box(qtbot, window):
    canvas, item = window.canvas, window.session.current()
    qtbot.waitUntil(lambda: canvas.spotlight is not None, timeout=5000)
    rect, view = canvas.spotlight
    assert rect == crop_rect(item.finding.label_box, None, 160, 120) and view is None
    shot = canvas.viewport().grab().toImage()

    def light(x, y):
        return QColor(shot.pixel(canvas.mapFromScene(QPointF(x, y)))).lightness()

    outside = (155, 5) if rect[0] < 100 else (5, 115)
    assert light(*outside) < 100                                           # the 128 grey, dimmed


def shown(qtbot, window):
    qtbot.waitUntil(lambda: window._shown == window.session.current().entry.path, timeout=5000)
    qtbot.waitUntil(lambda: window.session.images.get(window.session.current().entry.path) is not None,
                    timeout=5000)


def said(qtbot, window, key):
    with qtbot.waitSignal(window.session.status) as signal:
        qtbot.keyClick(window, key)
    return signal.args[0]


def labels_text(window):
    return {item.entry.rel: read_exact(item.entry.label_path) for item in window.session.queue.items}


@pytest.mark.parametrize("key", [Qt.Key_M, Qt.Key_B])
def test_m_and_b_say_they_are_not_for_blurry_boxes(qtbot, window, key):
    shown(qtbot, window)
    before = labels_text(window)
    assert said(qtbot, window, key) == "not for blurry boxes"
    assert labels_text(window) == before


def test_d_dismisses_and_moves_on(qtbot, window):
    shown(qtbot, window)
    first = window.session.current()
    qtbot.keyClick(window, Qt.Key_D)
    assert window.session.finding_state(first) == "dismissed" and window.session.current().key != first.key


def test_a_delete_in_the_full_frame_leaves_the_box_fixed(qtbot, window):
    shown(qtbot, window)
    first = window.session.current()
    qtbot.keyClick(window, Qt.Key_Delete)                                  # the box arrives selected
    qtbot.waitUntil(lambda: window.session.finding_state(first) == "fixed", timeout=5000)
    assert first.finding.text not in read_exact(first.entry.label_path)


def select(qtbot, window, rows):
    panel = window.queue_panel
    for n, row in enumerate(rows):
        rect = panel.view.visualRect(panel.model.index(row))
        qtbot.mouseClick(panel.view.viewport(), Qt.LeftButton, Qt.ControlModifier if n else Qt.NoModifier,
                         rect.center())
    assert len(panel.selected_findings()) == len(rows)


def test_several_tiles_m_says_why_and_delete_is_one_edit(qtbot, window):
    window.queue_panel.set_grid(True)
    qtbot.wait(50)
    select(qtbot, window, [0, 2])
    before = labels_text(window)
    assert said(qtbot, window, Qt.Key_M) == "nothing changed; skipped 2 (not for blurry boxes)"
    assert said(qtbot, window, Qt.Key_Delete).startswith("deleted 2 findings' labels")
    assert labels_text(window) != before
    window.session.undo()                                                  # one undo takes both back
    assert labels_text(window) == before
