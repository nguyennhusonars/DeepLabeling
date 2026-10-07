"""The Statistics dialog: computed on a worker, shown as tables and charts
(docs/design/2026-10-07-bulk-and-stats.md#the-dialog)."""

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from deeplabeling.core.queue import ImageFilter, NameContains
from deeplabeling.ui.stats_dialog import StatsDialog
from fixtures import FakePrompter, open_session


@pytest.fixture
def prompter(tmp_path):
    return FakePrompter(save_path=tmp_path / "charts.png")


@pytest.fixture
def session(qtbot, ds, prompter):
    s = open_session(qtbot, ds.yaml, prompter)
    yield s
    s.close()


@pytest.fixture
def dialog(qtbot, session, prompter):
    d = StatsDialog(session, prompter)
    qtbot.addWidget(d)
    d.resize(900, 700)
    d.show()
    qtbot.waitUntil(lambda: d.stats is not None, timeout=10000)
    return d


def cells(table):
    return [[table.item(r, c).text() if table.item(r, c) else "" for c in range(table.columnCount())]
            for r in range(table.rowCount())]


def colours(widget):
    image = widget.grab().toImage()
    return {QColor(image.pixel(x, y)).name() for x in range(0, image.width(), 3) for y in range(0, image.height(), 3)}


def near(found, wanted, tol=24):
    w = QColor(wanted)
    return any(abs(c.red() - w.red()) + abs(c.green() - w.green()) + abs(c.blue() - w.blue()) < tol
               for c in map(QColor, found))


def test_it_names_the_queue_and_fills_its_tables(qtbot, dialog):
    assert dialog.windowTitle() == "Statistics — all images"
    assert dialog.status.text().startswith("15 images · computed ")
    assert cells(dialog.tables["Classes"])[0] == ["person", "4", "4", "0", "8", "5", "1"]
    assert cells(dialog.tables["Label files"])[1] == ["val", "5", "5", "0", "0", "0", "0", "4"]


def test_copy_puts_the_shown_table_on_the_clipboard_as_tsv(qtbot, dialog):
    dialog.tabs.setCurrentIndex(dialog.tabs.indexOf(dialog.tables["Boxes per image"]))
    dialog.copy()
    assert QApplication.clipboard().text().startswith("boxes\timages\n0\t3\n1\t6\n")


def test_the_charts_are_drawn(qtbot, dialog):
    dialog.tabs.setCurrentWidget(dialog.charts)
    qtbot.wait(50)
    found = colours(dialog.canvas)
    assert near(found, "#1f77b4") and near(found, "#ff7f0e")      # train and val bars
    assert near(found, "#440154")                                   # the heatmap's empty cells (viridis)


def test_one_class_narrows_the_sizes_and_the_centres(qtbot, dialog):
    dialog.tabs.setCurrentWidget(dialog.charts)
    dialog.chart_class.setCurrentText("bus_m")
    assert dialog.drawn_class == 2


def test_save_charts_writes_a_png(qtbot, dialog, prompter):
    dialog.save_charts()
    assert prompter.save_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_while_it_reads_it_says_how_far_and_closing_cancels(qtbot, session, prompter, monkeypatch):
    import deeplabeling.ui.stats_dialog as module

    gate = __import__("threading").Event()
    real = module.stats_of

    def slow(entries, labels_of, size_of, cancelled, *, progress):
        progress(3, 15)
        gate.wait(5)
        return real(entries, labels_of, size_of, cancelled, progress=progress)

    monkeypatch.setattr(module, "stats_of", slow)
    d = StatsDialog(session, prompter)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(lambda: d.status.text() == "reading 3 / 15", timeout=5000)
    d.close()
    gate.set()
    qtbot.waitUntil(lambda: d._job is None, timeout=5000)
    assert d.stats is None


def test_an_empty_queue_says_no_images_and_draws_no_charts(qtbot, session, prompter):
    session.set_queue(ImageFilter(conditions=(NameContains("nothing like this"),)))
    qtbot.waitUntil(lambda: session.queue.complete, timeout=5000)
    d = StatsDialog(session, prompter)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(lambda: d.stats is not None, timeout=5000)
    assert d.status.text() == "no images" and d.canvas is None


def test_recompute_reads_again(qtbot, dialog, ds):
    ds.lbl("camA/0002").write_text("1 0.5 0.5 0.1 0.1\n")              # the negative gains a car
    first = dialog.stats
    dialog.recompute()
    qtbot.waitUntil(lambda: dialog.stats is not None and dialog.stats is not first, timeout=10000)
    assert cells(dialog.tables["Classes"])[1][1] == "2"


def test_its_parts_are_visible_inside_it(qtbot, dialog):
    rects = []
    for w in (dialog.status, dialog.tabs, dialog.copy_button, dialog.recompute_button, dialog.save_button):
        rect = QRect(w.mapTo(dialog, QPoint(0, 0)), w.size())
        assert w.isVisible() and dialog.rect().contains(rect) and w.width() > 0
        assert not any(rect.intersects(r) for r in rects)
        rects.append(rect)


def test_the_size_axis_starts_below_one_box_so_every_bar_shows(qtbot, dialog):
    dialog.tabs.setCurrentWidget(dialog.charts)
    sizes = dialog.canvas.figure.axes[1]
    assert sizes.get_yscale() == "log" and sizes.get_ylim()[0] < 1



def test_the_charts_are_drawn_when_their_tab_is_shown_not_when_the_numbers_come(qtbot, dialog):
    assert dialog.canvas is None                            # the tables show; matplotlib waits
    dialog.tabs.setCurrentWidget(dialog.charts)
    assert dialog.canvas is not None and dialog.drawn_class is None
    first = dialog.stats
    dialog.recompute()
    qtbot.waitUntil(lambda: dialog.stats is not first and dialog.stats is not None, timeout=10000)
    assert dialog.drawn_for is dialog.stats                 # its tab on show: redrawn for the new numbers
