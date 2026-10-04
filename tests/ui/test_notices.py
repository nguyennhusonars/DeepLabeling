from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from deeplabeling.ui.notices import MAX_ROWS, NoticeStrip


@pytest.fixture
def strip(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    s = NoticeStrip()
    layout.addWidget(s)
    layout.addWidget(QWidget(), 1)
    host.resize(600, 300)
    host.show()
    qtbot.waitUntil(host.isVisible)
    yield s                 # the generator frame keeps `host`, the strip's parent, alive


def test_a_notice_is_visible_with_its_text(qtbot, strip):
    assert not strip.isVisible()
    strip.add("error", "camA/images/0001.jpg: this image already has a label file")
    qtbot.waitUntil(strip.isVisible)
    [row] = strip.rows
    assert row.label.isVisible() and row.label.text().endswith("already has a label file")
    assert row.geometry().height() > 0 and strip.rect().contains(row.geometry())


def test_newest_first_and_only_so_many(strip):
    for i in range(MAX_ROWS + 2):
        strip.add("info", f"n{i}")
    assert strip.texts() == [f"n{i}" for i in range(MAX_ROWS + 1, 1, -1)]


def test_a_keyed_notice_replaces_its_predecessor_and_empty_text_removes_it(strip):
    strip.add("warning", "12 boxes have ids ≥ 4", key="out-of-range")
    strip.add("warning", "3 boxes have ids ≥ 4", key="out-of-range")
    assert strip.texts() == ["3 boxes have ids ≥ 4"]
    strip.add("warning", "", key="out-of-range")
    assert strip.texts() == [] and not strip.isVisible()


def test_a_successful_edit_clears_that_images_refusals_only(strip):
    a, b = Path("/d/a.jpg"), Path("/d/b.jpg")
    strip.add("error", "a refused", image=a)
    strip.add("error", "b refused", image=b)
    strip.add("warning", "standing", image=a, key="k")
    strip.clear_image([a])
    assert strip.texts() == ["standing", "b refused"]


def test_dismissing_removes_and_an_empty_strip_hides(qtbot, strip):
    strip.add("error", "refused")
    qtbot.mouseClick(strip.rows[0].close_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: not strip.isVisible())
    assert strip.rows == []


def test_a_dismissed_row_is_freed(qtbot, strip):
    import gc
    import weakref

    strip.add("error", "refused")
    row = weakref.ref(strip.rows[0])
    qtbot.mouseClick(strip.rows[0].close_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: not strip.rows)
    qtbot.wait(20)                                  # deleteLater runs
    gc.collect()
    assert row() is None


def test_a_standing_notice_is_never_pushed_out(strip):
    strip.add("warning", "ids the yaml does not name", key="out-of-range")
    for i in range(MAX_ROWS + 1):
        strip.add("error", f"refused {i}")
    assert "ids the yaml does not name" in strip.texts()
