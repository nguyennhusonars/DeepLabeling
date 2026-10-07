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


def test_a_very_long_notice_leaves_the_canvas_its_room(qtbot, ds):
    from drive import start

    w = start(qtbot, [str(ds.yaml)])
    w.resize(1024, 640)
    qtbot.waitUntil(lambda: w.canvas.height() > 300, timeout=5000)
    before = w.canvas.height()
    text = "a very long reason " * 320                     # about 6,000 characters
    w.notices.add("error", text)
    qtbot.wait(50)
    assert w.canvas.height() >= before - 170                # shortened: a few lines, not a page
    row = w.notices.rows[0]
    assert row.toolTip() == text and text in w.notices.texts()
    w.close()


def test_a_notice_said_again_comes_back_to_the_top(strip):
    strip.add("error", "first")
    strip.add("error", "second")
    strip.add("error", "first")
    assert strip.texts() == ["first", "second"]


def test_each_level_shows_its_icon_before_the_text(strip):
    for level in ("info", "warning", "error"):
        strip.add(level, f"a {level}")
    assert [row.label.text() for row in strip.rows] == ["✖ a error", "⚠ a warning", "ℹ a info"]
    assert strip.texts() == ["a error", "a warning", "a info"]     # what was said, without the icon
