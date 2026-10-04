import pytest
from PySide6.QtCore import QPoint, QRect

from deeplabeling.ui.session import Session
from deeplabeling.ui.state_bar import StateBar
from fixtures import FakePrompter


def shown(qtbot, widget, width=900):
    qtbot.addWidget(widget)
    widget.resize(width, 40)
    widget.show()
    qtbot.waitUntil(widget.isVisible)
    return widget


def chips(bar):
    return (bar.dataset, bar.queue, bar.layers, bar.reviewed)


def test_the_chips_say_what_is_in_force(qtbot, session):
    bar = shown(qtbot, StateBar(session), 1400)
    assert bar.dataset.full_text == "ds · data.yaml · train + val · 15 images"
    assert bar.queue.full_text == "Queue: all images · 15 · 15 left"
    assert bar.reviewed.full_text == "Reviewed 0 / 15"
    assert bar.layers.full_text == "Layers: none"
    session.done_and_next()
    assert bar.reviewed.full_text == "Reviewed 1 / 15"
    assert bar.queue.full_text == "Queue: all images · 15 · 14 left"


def test_without_a_dataset_the_chip_invites_one(qtbot):
    bar = shown(qtbot, StateBar(Session(FakePrompter())))
    assert bar.dataset.full_text == "No dataset · open one"


def test_a_narrow_bar_elides_but_shows_every_chip(qtbot, session):
    bar = shown(qtbot, StateBar(session), 420)
    for chip in chips(bar):
        rect = QRect(chip.mapTo(bar, QPoint(0, 0)), chip.size())
        assert chip.isVisible() and chip.width() >= 40 and bar.rect().contains(rect)
        assert chip.toolTip() == chip.full_text
    assert bar.dataset.text().endswith("…")


def test_a_growing_queue_refreshes_the_bar_at_most_once_per_interval(qtbot, session, monkeypatch):
    bar = shown(qtbot, StateBar(session), 1400)
    refreshes = []
    monkeypatch.setattr(bar, "refresh", lambda: refreshes.append(1))
    bar._soon.timeout.disconnect()
    bar._soon.timeout.connect(bar.refresh)
    for _ in range(20):
        session.queueGrew.emit()
    assert refreshes == []
    qtbot.waitUntil(lambda: refreshes == [1], timeout=2000)
