"""The queue chip's menu: what acts on the queue's images
(docs/design/2026-10-07-bulk-and-stats.md#the-queue-chip)."""

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QToolButton

from drive import start
from fixtures import FakePrompter, read_exact


@pytest.fixture
def prompter():
    return FakePrompter(reassign=(99, 1))


@pytest.fixture
def window(qtbot, ds, prompter):
    w = start(qtbot, [str(ds.yaml)], prompter)
    yield w
    w.close()


def menu(window) -> dict:
    m = window.state_bar.queue.menu()
    m.aboutToShow.emit()
    return {a.text(): a for a in m.actions() if not a.isSeparator()}


def test_the_chip_offers_the_queue_s_actions(qtbot, window):
    assert list(menu(window)) == ["Edit queue…", "Reassign a class in this queue…", "Statistics of this queue…"]
    assert all(action.isEnabled() for action in menu(window).values())


def test_reassign_runs_from_the_menu(qtbot, window, prompter, ds):
    qtbot.waitUntil(lambda: window.session.unnamed_ids == (-1, 99), timeout=5000)
    with qtbot.waitSignal(window.session.status, timeout=5000) as said:
        menu(window)["Reassign a class in this queue…"].trigger()
        qtbot.waitUntil(lambda: window.session.running is None and said.signal_triggered, timeout=5000)
    assert said.args == ["reassigned 1 #99? box on 1 image to car"]
    assert read_exact(ds.lbl("bad/ok")).splitlines()[1] == "1 0.5 0.5 0.1 0.1"


def test_a_click_on_the_chip_still_opens_the_queue_editor(qtbot, window, prompter):
    chip = window.state_bar.queue
    qtbot.mouseClick(chip, Qt.LeftButton, pos=QPoint(10, chip.height() // 2))
    assert prompter.asked[-1][0] == "queue"
    menu(window)["Edit queue…"].trigger()
    assert prompter.asked[-1][0] == "queue"


def test_the_chip_shows_its_arrow_inside_the_bar(qtbot, window):
    chip = window.state_bar.queue
    assert chip.popupMode() == QToolButton.MenuButtonPopup
    rect = QRect(chip.mapTo(window.state_bar, QPoint(0, 0)), chip.size())
    assert chip.isVisible() and window.state_bar.rect().contains(rect) and chip.width() > 100


def test_reassign_is_offered_only_once_the_queue_is_built(qtbot, window):
    window.session.queue.complete = False
    assert not menu(window)["Reassign a class in this queue…"].isEnabled()



def test_reassign_is_not_offered_on_a_queue_whose_build_failed(qtbot, window):
    window.session.queue.fail("could not read the store")
    assert not menu(window)["Reassign a class in this queue…"].isEnabled()



def test_statistics_open_from_the_menu_and_close_with_the_dataset(qtbot, window):
    menu(window)["Statistics of this queue…"].trigger()
    dialog = window.statistics
    qtbot.waitUntil(lambda: dialog.isVisible() and dialog.stats is not None, timeout=10000)
    assert dialog.windowTitle() == "Statistics — all images"
    window.session.close()
    assert not dialog.isVisible()


def test_a_second_statistics_window_replaces_the_first(qtbot, window):
    from deeplabeling.ui.stats_dialog import StatsDialog

    menu(window)["Statistics of this queue…"].trigger()
    menu(window)["Statistics of this queue…"].trigger()
    qtbot.waitUntil(lambda: len(window.findChildren(StatsDialog)) == 1, timeout=5000)


def test_statistics_are_not_offered_on_a_queue_whose_build_failed(qtbot, window):
    window.session.queue.fail("could not read the store")
    assert not menu(window)["Statistics of this queue…"].isEnabled()
