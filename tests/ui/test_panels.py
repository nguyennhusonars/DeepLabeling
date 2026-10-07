"""The queue panel and the inspector, shown and read back."""

import pytest
from PySide6.QtCore import Qt

from deeplabeling.ui.canvas import Canvas
from deeplabeling.ui.editing import Editing
from deeplabeling.ui.inspector import Inspector
from deeplabeling.ui.queue_panel import QueuePanel
from fixtures import FakePrompter


@pytest.fixture
def panel(qtbot, session):
    p = QueuePanel(session)
    qtbot.addWidget(p)
    p.resize(360, 500)
    p.show()
    qtbot.waitUntil(p.isVisible)
    return p


@pytest.fixture
def inspector(qtbot, session):
    canvas = Canvas()
    qtbot.addWidget(canvas)
    i = Inspector(session, Editing(session, canvas, FakePrompter()))
    qtbot.addWidget(i)
    i.resize(320, 600)
    i.show()
    qtbot.waitUntil(i.isVisible)
    return i


def row_text(panel, row):
    return panel.model.index(row).data(Qt.DisplayRole)


def test_the_panel_lists_the_queue_with_badges(panel):
    assert panel.model.rowCount() == 15 and panel.title.text() == "Queue · 15"
    assert row_text(panel, 0) == "· camA/images/0001.jpg  —  2 boxes"
    assert row_text(panel, 2) == "· camA/images/0003.jpg  —  missing"
    rect = panel.view.visualRect(panel.model.index(0))
    assert rect.height() > 0 and panel.view.viewport().rect().contains(rect.center())


def test_the_selection_follows_the_cursor(panel, session):
    session.move(3)
    assert panel.view.currentIndex().row() == 3


def test_clicking_a_row_moves_the_cursor(qtbot, panel, session):
    rect = panel.view.visualRect(panel.model.index(4))
    qtbot.mouseClick(panel.view.viewport(), Qt.LeftButton, pos=rect.center())
    assert session.current().key == "camA/images/sub/0005.jpg"


def test_a_reviewed_row_shows_its_tick(panel, session):
    session.done_and_next()
    assert row_text(panel, 0).startswith("✓ camA/images/0001.jpg")


def test_the_inspector_describes_the_current_image(qtbot, inspector, session):
    qtbot.waitUntil(lambda: inspector.size_label.text() == "64 × 48")
    assert inspector.path_label.text() == "camA/images/0001.jpg"
    assert inspector.state_label.text() == "2 boxes" and inspector.reviewed_label.text() == "not yet"
    assert [inspector.classes.item(i).text() for i in range(4)] == [
        "1   person   1   ✎", "2   car   1", "3   bus_m   0", "4   bus_l   0"]
    qtbot.waitUntil(lambda: inspector.boxes.count() == 2)
    assert inspector.boxes.item(0).text() == "person   13 × 14 px"


def test_the_inspector_follows_the_cursor_and_marks(qtbot, inspector, session):
    session.go_to("camA/images/0003.jpg")
    assert inspector.state_label.text() == "no label file"
    session.toggle_reviewed()
    assert inspector.reviewed_label.text() != "not yet"


def test_the_inspector_says_when_an_image_cannot_be_decoded(qtbot, inspector, session):
    session.go_to("bad/images/corrupt.jpg")
    qtbot.waitUntil(lambda: inspector.size_label.text().startswith("cannot decode"))


def test_new_rows_do_not_scroll_the_list(panel, session, monkeypatch):
    calls = []
    monkeypatch.setattr(panel.view, "scrollTo", lambda *a: calls.append(a))
    for _ in range(5):
        session.queueGrew.emit()           # a building queue grows; the cursor stays
    assert calls == []
    session.move(1)
    assert len(calls) == 1


def test_the_inspector_says_a_shared_label_file_is_read_only(qtbot, inspector, session):
    session.go_to("camB/images/twin.jpg")
    assert inspector.state_label.text() == "🔒 shared with another image: not edited"


def test_the_inspector_ignores_changes_to_other_images(qtbot, inspector, session, monkeypatch):
    calls = []
    monkeypatch.setattr(inspector, "refresh", lambda: calls.append(1))
    session.labelsChanged.emit((session.workspace.dataset.images[5].path,))
    assert calls == []
    session.labelsChanged.emit((session.current().entry.path,))
    assert calls == [1]


def test_dragging_across_rows_moves_the_cursor_with_the_highlight(panel, session):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    def send(kind, point, buttons):
        event = QMouseEvent(kind, QPointF(point), panel.view.viewport().mapToGlobal(QPointF(point)),
                            Qt.LeftButton, buttons, Qt.NoModifier)
        QApplication.sendEvent(panel.view.viewport(), event)

    a = panel.view.visualRect(panel.model.index(1)).center()
    b = panel.view.visualRect(panel.model.index(5)).center()
    send(QEvent.MouseButtonPress, a, Qt.LeftButton)
    send(QEvent.MouseMove, b, Qt.LeftButton)
    send(QEvent.MouseButtonRelease, b, Qt.NoButton)
    assert panel.view.currentIndex().row() == 5
    assert session.current().key == session.queue.items[5].key


def test_clicking_a_class_with_nothing_selected_makes_it_the_active_class(qtbot, inspector):
    row = inspector.classes.item(2)
    qtbot.mouseClick(inspector.classes.viewport(), Qt.LeftButton,
                     pos=inspector.classes.visualItemRect(row).center())
    assert inspector.classes.item(2).text() == "3   bus_m   0   ✎"
    assert inspector.classes.item(0).text() == "1   person   1"


def test_the_inspector_says_what_the_model_found(qtbot, inspector, session, tmp_path):
    import threading

    from deeplabeling.core.inference import Prediction
    from fixtures import FakePredictor

    assert inspector.predictions_label.text() == "no model"
    loading, predicting = threading.Event(), threading.Event()
    found = {"0001.jpg": [Prediction(0, (0.8, 0.8, 0.1, 0.1), 0.9),           # car, missing
                          Prediction(0, (0.5, 0.5, 0.2, 0.3), 0.85),          # on the person
                          Prediction(2, (0.1, 0.9, 0.1, 0.1), 0.7)]}          # human: unmapped
    session.model.factory = lambda p: (loading.wait(5), FakePredictor(p, found=found, gate=predicting))[1]
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    session.model.load(weights)
    assert inspector.predictions_label.text() == "loading"
    loading.set()
    qtbot.waitUntil(lambda: inspector.predictions_label.text() == "not inferred yet")
    predicting.set()
    qtbot.waitUntil(lambda: inspector.predictions_label.text() == "3 (1 missing)")
    session.go_to("camA/images/0002.jpg")
    qtbot.waitUntil(lambda: inspector.predictions_label.text() == "none found")


def test_the_inspector_says_when_the_model_could_not_predict(qtbot, inspector, session, tmp_path):
    from fixtures import FakePredictor

    session.model.factory = lambda p: FakePredictor(p, fail={"0001.jpg"})
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    session.model.load(weights)
    qtbot.waitUntil(lambda: inspector.predictions_label.text() == "failed: 0001.jpg: CUDA out of memory")
