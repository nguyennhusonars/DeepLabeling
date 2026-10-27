"""What a finding shows: its row, the inspector's line, and the spotlight
(docs/design/2026-10-06-find-bad.md#window)."""

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage

import deeplabeling.ui.model as model_module
from deeplabeling.core.findings import Finding, Findings
from deeplabeling.ui.boxes import PredictionView
from deeplabeling.ui.canvas import Canvas
from deeplabeling.ui.findview import finding_text
from deeplabeling.ui.queue_panel import tile_text
from drive import start
from finding_rows import FOUND, factory, load

CAR = (0.25, 0.25, 0.1, 0.1)


@pytest.mark.parametrize("finding, text", [
    (Finding(1, "", "wrong class", 0.82, 1, CAR, 0, CAR, 0.82), "wrong class: car → person 0.82"),
    (Finding(1, "", "not an object", 0.97, 2, CAR), "not an object: bus_m (nearest 0.03)"),
    (Finding(1, "", "not an object", 0.8, 2, CAR, None, CAR, 0.6, model_raw=3), "not an object: bus_m (nearest 0.20)"),
    (Finding(1, "", "weakly seen", 0.59, 1, CAR, 1, CAR, 0.41), "weakly seen: car 0.41"),
    (Finding(1, "", "wrong class", 0.9, 9, CAR, 0, CAR, 0.9), "wrong class: #9? → person 0.90"),
])
def test_a_finding_reads_as_words(ds, finding, text):
    from deeplabeling.core.dataset import Dataset

    assert finding_text(finding, Dataset.open(ds.yaml)) == text


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    load(qtbot, w.session, weights)
    w.session.set_queue(Findings())
    qtbot.waitUntil(lambda: w.session.queue.complete and w.canvas.image_size is not None, timeout=5000)
    yield w
    w.close()


def test_rows_name_the_finding_and_say_when_it_is_fixed_or_dismissed(qtbot, window):
    session = window.session
    rows = [session.describe_item(item) for item in session.queue.items]
    assert rows == ["· camA/images/sub/0005.jpg  —  wrong class: bus_m → car 0.95",
                    "· camA/images/0001.jpg  —  wrong class: car → person 0.80",
                    "· camB/images/0001.jpg  —  not an object: bus_m (nearest 0.00)"]
    session.go_to(FOUND[0])
    session.dismiss_current()
    assert session.describe_item(session.queue.items[0]).endswith("car 0.95 · dismissed")


def test_a_tile_names_the_label_the_model_s_call_and_its_state(qtbot, window):
    session = window.session
    first, item, nothing = session.queue.items
    assert tile_text(session, item) == "car → person 0.80"
    assert tile_text(session, nothing) == "bus_m → nothing 1.00"
    session.mark_reviewed([item.key])
    assert tile_text(session, item) == "✓ car → person 0.80"
    session.go_to(first.key)
    session.dismiss_current()
    assert tile_text(session, first) == "bus_m → car 0.95 · dismissed"


def test_the_inspector_has_a_finding_line(qtbot, window):
    assert window.inspector.finding_label.text() == "wrong class · 0.80 · the model: person 0.80"
    window.session.set_queue(window.session.queue.source.scope)          # an image queue
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    assert window.inspector.finding_label.text() == "—"


def test_the_full_frame_dims_around_the_finding_and_draws_the_model_s_box(qtbot, window):
    canvas = window.canvas
    rect, view = canvas.spotlight                              # camA/0001's car: (13, 10)-(19, 14) of 64 x 48
    assert rect == (9, 6, 23, 18) and view.caption == "person 0.80"
    window.session.set_queue(window.session.queue.source.scope)
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    assert canvas.spotlight is None


def test_a_spotlight_is_drawn_dimmed_outside_and_plain_inside(qtbot):
    canvas = Canvas()
    qtbot.addWidget(canvas)
    canvas.resize(400, 300)
    canvas.show()
    image = QImage(200, 100, QImage.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    canvas.set_image(image)
    view = PredictionView(-1, (60, 30, 100, 60), "#00ff00", "car 0.90", False)
    canvas.set_spotlight((50, 20, 110, 70), view)
    canvas.set_boxes([])
    shot = canvas.viewport().grab().toImage()

    def grey(x, y):
        return QColor(shot.pixel(canvas.mapFromScene(QPointF(x, y)))).red()

    assert grey(80, 45) > 180 and grey(20, 50) < 140             # inside plain, outside dimmed
    assert QColor(shot.pixel(canvas.mapFromScene(QPointF(80, 30)))).green() > 150    # the model's box


def test_the_status_bar_names_the_image_not_the_finding_key(qtbot, window):
    assert window.status_text.text().startswith("camA/images/0001.jpg · 64×48 · 2/3")


def test_an_edit_beside_the_finding_redraws_once_and_keeps_the_spotlight(qtbot, window, monkeypatch):
    session, editing = window.session, window.editing
    editing.pick([0], session.labels(session.current().entry))              # the person, not the finding
    lit, redraws, redraw = window.canvas.spotlight, [], window.canvas._redraw
    monkeypatch.setattr(window.canvas, "_redraw", lambda: (redraws.append(1), redraw()))
    editing.choose_class(next(i for i in editing.classes() if i.name == "bus_m"))
    assert len(redraws) == 1 and window.canvas.spotlight == lit


def test_the_queue_editor_opens_a_findings_queue_and_is_offered_it_back(qtbot, window):
    session = window.session
    session.set_queue(session.queue.source.scope)
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    window.prompter.queue = Findings()
    window.edit_queue()
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    assert [item.key for item in session.queue.items] == FOUND
    window.edit_queue()
    assert window.prompter.asked[-1][1] == Findings()


@pytest.mark.parametrize("finding, text", [
    (Finding(1, "", "wrong class", 0.82, 1, CAR, 0, CAR, 0.82), "car → person 0.82"),
    (Finding(1, "", "not an object", 0.97, 2, CAR), "bus_m → nothing 0.97"),
    (Finding(1, "", "weakly seen", 0.59, 1, CAR, 1, CAR, 0.41), "car → car 0.41"),
])
def test_a_tile_caption_is_short(ds, finding, text):
    from deeplabeling.core.dataset import Dataset
    from deeplabeling.ui.findview import finding_caption

    assert finding_caption(finding, Dataset.open(ds.yaml)) == text


def test_paging_to_a_finding_on_another_image_draws_the_canvas_once(qtbot, window, monkeypatch):
    nxt = window.session.queue.items[2]                                # camB/0001: not the image on screen
    qtbot.waitUntil(lambda: window.session.images.get(nxt.entry.path) is not None, timeout=5000)
    redraws, redraw = [], window.canvas._redraw
    monkeypatch.setattr(window.canvas, "_redraw", lambda: (redraws.append(1), redraw()))
    window.session.go_to(nxt.key)
    assert window._shown == nxt.entry.path and window.canvas.spotlight is not None and len(redraws) == 1
    assert len(window.canvas.handle_items()) == 8                      # its label arrived selected, and drawn so


def test_a_blurry_box_reads_as_words(ds):
    from deeplabeling.core.dataset import Dataset
    from deeplabeling.core.findings import BlurFinding
    from deeplabeling.ui.findview import finding_caption, finding_detail

    f = BlurFinding(line=0, text="0 0.5 0.5 0.2 0.2", kind="blurry", score=0.004, label_cls=0,
                    label_box=(0.5, 0.5, 0.2, 0.2), z=-3.42, group="16–31 px")
    dataset = Dataset.open(ds.yaml)
    assert finding_text(f, dataset) == "blurry: person, 0.4% of 16–31 px"
    assert finding_caption(f, dataset) == "person 0.4%"
    assert finding_detail(f, dataset, ()) == "blurry · 0.4% of person 16–31 px · z −3.4"
