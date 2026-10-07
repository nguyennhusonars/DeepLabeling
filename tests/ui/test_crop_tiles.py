"""A findings queue's grid: each tile the finding's crop, its label and the model's box
drawn on it (docs/design/2026-10-06-find-bad.md#the-grid)."""

from collections import Counter

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor

import deeplabeling.ui.model as model_module
from deeplabeling.core.findings import Findings
from deeplabeling.core.workspace import CLASS_COLORS
from deeplabeling.ui.classes import class_color
from deeplabeling.ui.images import Crop
from deeplabeling.ui.queue_panel import tile_thumb_rect
from drive import start
from finding_rows import PERSON, P, factory, load, put_rows

NEAR = (0.27, 0.25, 0.1, 0.1)       #: the model's box for camA/0001's car: IoU 0.67, 1.28 px to the right
ROWS = {"camA/images/0001.jpg": [P(1, NEAR, 0.8), P(1, PERSON, 0.9)],
        "bad/images/corrupt.jpg": [P(0, (0.4, 0.4, 0.2, 0.2), 0.9)]}       # its person: a car, says the model


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    load(qtbot, w.session, weights)
    put_rows(w.session, ROWS)
    w.session.set_queue(Findings())
    qtbot.waitUntil(lambda: w.session.queue.complete, timeout=5000)
    w.queue_panel.set_grid(True)
    w.resize(1200, 800)
    qtbot.wait(50)
    yield w
    w.close()


def row_of(session, key):
    return session.queue.index_of(key)


def tile(panel, row):
    return panel.view.visualRect(panel.model.index(row))


def shot(panel):
    return panel.view.viewport().grab().toImage()


def column(image, x, y1, y2):
    return [QColor(image.pixel(x + dx, y)) for dx in (-1, 0, 1) for y in range(y1, y2)]


def test_a_finding_tile_is_its_crop_with_the_label_and_the_model_s_box(qtbot, window):
    session, panel = window.session, window.queue_panel
    key = "camA/images/0001.jpg#1#wrong class"
    crop = Crop(session.queue.items[row_of(session, key)].entry.path, (9, 6, 24, 18))
    assert session.crop_of(session.queue.items[row_of(session, key)]) == crop
    qtbot.waitUntil(lambda: session.crops.get(crop) is not None, timeout=5000)
    qtbot.wait(20)
    target = tile_thumb_rect(tile(panel, row_of(session, key)), QSize(150, 120))     # 15 x 12 px, ten times
    image = shot(panel)
    car = QColor(class_color(1, "car", session.workspace.root_settings.get(CLASS_COLORS)))
    # The label (x 12.8-19.2 px) runs from 38 to 102 in the tile; the model's box from 51 to 115.
    assert any(abs(c.red() - car.red()) < 40 and abs(c.green() - car.green()) < 40 and abs(c.blue() - car.blue()) < 40
               for c in column(image, target.x() + 38, target.y() + 40, target.y() + 80))
    assert any(c.red() > 200 and c.green() < 80 and 40 < c.blue() < 120               # the person's #e6194b
               for c in column(image, target.x() + 115, target.y() + 40, target.y() + 80))
    assert session.thumbs.get(crop.path) is None                                       # the crop, not the frame


def test_a_tile_whose_image_cannot_be_decoded_says_so(qtbot, window):
    session, panel = window.session, window.queue_panel
    row = row_of(session, "bad/images/corrupt.jpg#0#wrong class")
    assert row is not None and session.crop_of(session.queue.items[row]) is None
    session.go_to(session.queue.items[row].key)
    qtbot.wait(50)
    cell = tile(panel, row)
    image = shot(panel)
    light = sum(QColor(image.pixel(x, y)).lightness() > 170
                for x in range(cell.left() + 40, cell.right() - 40) for y in range(cell.top() + 50, cell.top() + 80))
    assert light > 20                                       # "cannot decode" is written where the crop goes


def test_mark_page_is_not_offered_on_crops(qtbot, window):
    panel = window.queue_panel
    assert not panel.mark_button.isVisible()
    with qtbot.waitSignal(window.session.status) as said:
        panel.mark_page()
    assert said.args == ["crop tiles are not whole images: nothing marked"]
    assert len(window.session.workspace.review.keys()) == 0
    window.session.set_queue(window.session.queue.source.scope)
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    assert panel.mark_button.isVisible()


def test_a_crop_tile_reads_its_image_size_once_and_a_crop_repaints_only_its_tiles(qtbot, window, monkeypatch):
    session, panel = window.session, window.queue_panel
    key = "camA/images/0001.jpg#1#wrong class"
    row = row_of(session, key)
    crop = session.crop_of(session.queue.items[row])
    qtbot.waitUntil(lambda: session.crops.get(crop) is not None, timeout=5000)
    sizes, get = [], session.workspace.sizes.get
    monkeypatch.setattr(session.workspace.sizes, "get", lambda path: (sizes.append(path), get(path))[1])
    panel.view.viewport().repaint()
    tiles = Counter(item.entry.path for item in session.queue.items)
    assert sizes and all(n <= tiles[path] for path, n in Counter(sizes).items())   # once a tile, at most
    updates, update = [], panel.view.update
    monkeypatch.setattr(panel.view, "update", lambda index: (updates.append(index.row()), update(index)))
    session.crops.ready.emit(crop)
    assert updates == [row]


def test_a_fixed_tile_shows_the_labels_as_they_are_now(qtbot, window):
    from deeplabeling.core.edits import DeleteLine, Intent

    session, panel = window.session, window.queue_panel
    key = "camA/images/0001.jpg#1#wrong class"
    item = session.queue.items[row_of(session, key)]
    qtbot.waitUntil(lambda: session.crops.get(session.crop_of(item)) is not None, timeout=5000)
    session.workspace.editor.apply(Intent(item.entry.path, (DeleteLine(item.focus),), "delete the car"))
    assert session.finding_state(item) == "fixed"
    target = tile_thumb_rect(tile(panel, row_of(session, key)), QSize(150, 120))
    car = QColor(class_color(1, "car", session.workspace.root_settings.get(CLASS_COLORS)))
    image = shot(panel)
    assert not any(abs(c.red() - car.red()) < 40 and abs(c.green() - car.green()) < 40 and abs(c.blue() - car.blue()) < 40
                   for c in column(image, target.x() + 38, target.y() + 40, target.y() + 80))   # the car is gone
    assert any(c.red() > 200 and c.green() < 80 and 40 < c.blue() < 120                           # the model's box stays
               for c in column(image, target.x() + 115, target.y() + 40, target.y() + 80))


def test_a_tile_whose_header_reads_but_whose_pixels_do_not_says_so(qtbot, ds, tmp_path, monkeypatch):
    import io

    from PIL import Image

    png = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 50, 50)).save(png, "PNG")
    broken = bytearray(png.getvalue())
    at = broken.index(b"IDAT")
    broken[at + 8:at + 20] = b"\0" * 12                                 # the pixels, garbled
    (ds.root / "camA/images/broken.png").write_bytes(bytes(broken))
    (ds.root / "camA/labels/broken.txt").write_text("0 0.500000 0.500000 0.200000 0.300000\n")
    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    load(qtbot, w.session, weights)
    put_rows(w.session, {"camA/images/broken.png": [P(0, (0.5, 0.5, 0.2, 0.3), 0.9)]})     # its person: a car
    w.session.set_queue(Findings())
    qtbot.waitUntil(lambda: w.session.queue.complete, timeout=5000)
    w.queue_panel.set_grid(True)
    session, panel = w.session, w.queue_panel
    key = "camA/images/broken.png#0#wrong class"
    session.go_to(key)
    crop = session.crop_of(session.queue.items[row_of(session, key)])
    assert crop is not None                                              # its size is read
    qtbot.waitUntil(lambda: session.crops.error(crop) is not None, timeout=5000)
    qtbot.wait(20)
    cell = tile(panel, row_of(session, key))
    image = shot(panel)
    light = sum(QColor(image.pixel(x, y)).lightness() > 170
                for x in range(cell.left() + 40, cell.right() - 40) for y in range(cell.top() + 50, cell.top() + 80))
    assert light > 20                                                    # "cannot decode", not "…"
    w.close()
