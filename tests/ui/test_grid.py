"""The queue as a grid of thumbnails: shown, read back from its pixels, and driven
(the run-and-verify-ui skill)."""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor

from deeplabeling.ui.queue_panel import QueuePanel, tile_text, tile_thumb_rect
from deeplabeling.ui.settings_ui import QUEUE_GRID_WIDTH, QUEUE_LIST_WIDTH, SHOW_GRID
from drive import start


@pytest.fixture
def grid(qtbot, session):
    """A panel two tiles wide, a row and a half of tiles high."""
    p = QueuePanel(session)
    qtbot.addWidget(p)
    p.set_grid(True)
    p.resize(420, 300)
    p.show()
    qtbot.waitUntil(p.isVisible)
    return p


def tile(panel, row):
    return panel.view.visualRect(panel.model.index(row))


def shot(panel):
    return panel.view.viewport().grab().toImage()


def colours_near(image, x, y, radius=2):
    return [QColor(image.pixel(x + dx, y + dy)) for dx in range(-radius, radius + 1)
            for dy in range(-radius, radius + 1)]


def test_a_tile_shows_the_thumbnail_with_its_label_boxes(qtbot, grid):
    thumb = tile_thumb_rect(tile(grid, 0), QSize(64, 48))
    assert thumb.size() == QSize(160, 120)                  # 64 x 48, drawn at the tile's size
    # The frame's green block covers x and y 12-50 %; the person box's top edge runs at
    # y 35 %, x 40-60 %, in #e6194b.
    qtbot.waitUntil(lambda: any(c.green() > 150 and c.red() < 60
                                for c in colours_near(shot(grid), thumb.x() + 50, thumb.y() + 30)))
    edge = colours_near(shot(grid), thumb.x() + 80, thumb.y() + 42)
    assert any(c.red() > 200 and c.green() < 80 and 40 < c.blue() < 120 for c in edge)


def test_a_tile_with_its_thumbnail_shows_its_caption(qtbot, grid, session):
    qtbot.waitUntil(lambda: session.thumbs.get(session.queue.items[0].entry.path) is not None)
    qtbot.wait(20)
    image, cell = shot(grid), tile(grid, 0)
    below = tile_thumb_rect(cell, QSize(64, 48)).bottom() + 6
    light = sum(QColor(image.pixel(x, y)).lightness() > 170
                for x in range(cell.left() + 8, cell.left() + 120) for y in range(below, cell.bottom() - 2))
    assert light > 30                                       # "0001.jpg · 2 boxes" is drawn


def test_a_box_outside_the_image_stays_inside_its_tile(qtbot, grid, session):
    grid.resize(490, 300)                                   # two columns, then empty space
    qtbot.waitUntil(lambda: grid.columns() == 2)
    row = session.queue.index_of("bad/images/ok.jpg")       # its line 3 is centred at x 1.4
    assert row % 2 == 1                                     # the right-hand column
    session.go_to("bad/images/ok.jpg")                      # which brings its tile into view
    qtbot.waitUntil(lambda: session.thumbs.get(session.queue.items[row].entry.path) is not None)
    qtbot.wait(20)
    thumb = tile_thumb_rect(tile(grid, row), QSize(64, 48))
    beyond = thumb.x() + int(1.3 * 160)                     # the box's left edge, past the tile
    assert tile(grid, row).right() < beyond < grid.view.viewport().width()
    image = shot(grid)
    assert not any(c.red() > 200 and c.green() < 80 and 40 < c.blue() < 120
                   for c in colours_near(image, beyond, thumb.y() + 60))


def test_a_tile_names_its_file_its_badge_and_whether_it_is_reviewed(session):
    item = session.queue.items[0]
    assert tile_text(session, item) == "0001.jpg · 2 boxes"
    session.toggle_reviewed()
    assert tile_text(session, item) == "✓ 0001.jpg · 2 boxes"


def test_the_grid_is_laid_out_in_columns_that_follow_the_width(qtbot, grid):
    assert grid.columns() == 2
    assert tile(grid, 1).top() == tile(grid, 0).top() and tile(grid, 2).top() > tile(grid, 0).top()
    grid.resize(620, 300)
    qtbot.waitUntil(lambda: grid.columns() == 3)
    qtbot.waitUntil(lambda: tile(grid, 2).top() == tile(grid, 0).top())


def test_the_grid_mirrors_the_cursor_and_a_click_moves_it(qtbot, grid, session):
    session.move(3)
    assert grid.view.currentIndex().row() == 3
    assert grid.view.viewport().rect().contains(tile(grid, 3))
    qtbot.mouseClick(grid.view.viewport(), Qt.LeftButton, pos=tile(grid, 2).center())
    assert session.current().key == session.queue.items[2].key


def test_switching_view_shows_the_current_item_in_the_new_one(qtbot, session):
    panel = QueuePanel(session)
    qtbot.addWidget(panel)
    panel.resize(420, 300)
    panel.show()
    qtbot.waitUntil(panel.isVisible)
    session.go_to(session.queue.items[-1].key)              # in view in the list, a page down in the grid
    panel.set_grid(True)
    qtbot.wait(20)
    assert panel.view.viewport().rect().contains(tile(panel, len(session.queue) - 1))
    session.go_to(session.queue.items[0].key)
    panel.set_grid(False)
    qtbot.wait(20)
    assert panel.view.viewport().rect().contains(tile(panel, 0))


def test_a_resized_grid_keeps_the_current_tile_in_view(qtbot, grid, session):
    session.go_to(session.queue.items[7].key)
    assert grid.view.viewport().rect().contains(tile(grid, 7))
    grid.resize(620, 300)                                   # two columns become three
    qtbot.waitUntil(lambda: grid.columns() == 3)
    qtbot.waitUntil(lambda: grid.view.viewport().rect().contains(tile(grid, 7)), timeout=1000)


def test_a_narrowed_list_keeps_the_current_row_whole_in_view(qtbot, session):
    """Back from the grid, the window narrows the panel; paths wider than the list bring a
    horizontal scrollbar, which takes the bottom row's space."""
    panel = QueuePanel(session)
    qtbot.addWidget(panel)
    panel.resize(420, 180)
    panel.show()
    qtbot.waitUntil(panel.isVisible)
    session.go_to(session.queue.items[7].key)               # the bottom row in view
    viewport = panel.view.viewport()

    def whole():
        rect = tile(panel, 7)
        return 0 <= rect.top() and rect.bottom() < viewport.height()

    assert whole()
    panel.resize(200, 180)
    qtbot.waitUntil(lambda: panel.view.horizontalScrollBar().isVisible())
    qtbot.waitUntil(whole, timeout=1000)


def test_the_current_tile_is_framed(qtbot, grid, session):
    session.move(1)
    qtbot.wait(10)
    image = shot(grid)
    current, other = tile(grid, 1), tile(grid, 0)
    frame = QColor(image.pixel(current.left() + 2, current.center().y()))
    plain = QColor(image.pixel(other.left() + 2, other.center().y()))
    assert frame != plain and frame.blue() > 150


def test_only_the_tiles_in_view_are_decoded(qtbot, grid, session):
    in_view = grid.visible_keys(partial=True)
    assert 0 < len(in_view) < len(session.queue)
    paths = {item.key: item.entry.path for item in session.queue.items}
    qtbot.waitUntil(lambda: all(session.thumbs.get(paths[k]) is not None
                                or session.thumbs.error(paths[k]) for k in in_view))
    assert session.thumbs.get(session.queue.items[-1].entry.path) is None
    grid.view.scrollToBottom()
    qtbot.waitUntil(lambda: session.thumbs.get(session.queue.items[-1].entry.path) is not None)


def test_mark_page_marks_exactly_the_tiles_fully_in_view(qtbot, grid, session):
    whole, partly = grid.visible_keys(), grid.visible_keys(partial=True)
    assert len(whole) == 2 and len(partly) == 4             # one row whole, one cut by the edge
    paths = {item.key: item.entry.path for item in session.queue.items}
    qtbot.waitUntil(lambda: all(session.thumbs.get(paths[k]) is not None for k in partly))
    grid.mark_page()
    assert session.workspace.review.keys() == frozenset(whole)
    assert grid.title.text() == "Queue · 15"


def test_mark_page_is_offered_only_in_the_grid(qtbot, grid):
    assert grid.mark_button.isVisible() and grid.mark_button.width() > 0
    grid.set_grid(False)
    assert not grid.mark_button.isVisible() and not grid.grid
    grid.mark_page()                                        # the list has no page to mark
    assert len(grid._session.workspace.review.keys()) == 0


def test_the_list_comes_back_as_it_was(qtbot, grid, session):
    session.move(4)
    grid.set_grid(False)
    assert grid.view.currentIndex().row() == 4 and grid.columns() == 1
    rect = tile(grid, 4)
    assert rect.width() > 300 and rect.height() < 40            # a list row again
    assert grid.view.viewport().rect().contains(rect.center())


# -- in the window ------------------------------------------------------------------------


@pytest.fixture
def window(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)])
    yield w
    w.close()


def near(width, want, slack=6):
    return abs(width - want) <= slack


def test_g_shows_the_grid_at_its_width_and_the_list_at_its_own(qtbot, window):
    dock, panel = window.queue_dock, window.queue_panel
    qtbot.waitUntil(lambda: near(dock.width(), 280))
    qtbot.keyClick(window, Qt.Key_G)
    assert panel.grid and panel.mark_button.isVisible() and window.actions["mark_page"].isEnabled()
    qtbot.waitUntil(lambda: near(dock.width(), 560))
    assert window.session.settings.get(SHOW_GRID) is True
    qtbot.keyClick(window, Qt.Key_G)
    assert not panel.grid and not panel.mark_button.isVisible()
    assert not window.actions["mark_page"].isEnabled()
    qtbot.waitUntil(lambda: near(dock.width(), 280))


def test_the_grid_and_its_width_survive_a_relaunch(qtbot, window, ds):
    qtbot.keyClick(window, Qt.Key_G)
    window.resizeDocks([window.queue_dock], [720], Qt.Horizontal)
    qtbot.waitUntil(lambda: near(window.queue_dock.width(), 720))
    window.close()
    assert window.session.settings.get(QUEUE_GRID_WIDTH) == window.queue_dock.width()
    again = start(qtbot, [str(ds.yaml)])
    assert again.queue_panel.grid and again.actions["toggle_grid"].isChecked()
    qtbot.waitUntil(lambda: near(again.queue_dock.width(), 720))
    qtbot.keyClick(again, Qt.Key_G)                         # the list has kept its own width
    qtbot.waitUntil(lambda: near(again.queue_dock.width(), 280))
    again.close()


def test_down_and_up_move_by_a_row_in_the_grid_and_by_one_in_the_list(qtbot, window):
    queue = window.session.queue
    qtbot.keyClick(window, Qt.Key_Down)
    assert queue.position() == 1
    qtbot.keyClick(window, Qt.Key_G)
    qtbot.waitUntil(lambda: window.queue_panel.columns() == 3)
    qtbot.keyClick(window, Qt.Key_Down)
    assert queue.position() == 4
    qtbot.keyClick(window, Qt.Key_Right)
    assert queue.position() == 5
    qtbot.keyClick(window, Qt.Key_Up)
    assert queue.position() == 2
    qtbot.keyClick(window, Qt.Key_Up)                       # no row above: it stays put
    assert queue.position() == 2


def test_the_mark_page_button_marks_the_tiles_in_view(qtbot, window):
    qtbot.keyClick(window, Qt.Key_G)
    qtbot.waitUntil(lambda: near(window.queue_dock.width(), 560))
    in_view = window.queue_panel.visible_keys()
    assert in_view
    session, partly = window.session, in_view
    paths = {item.key: item.entry.path for item in session.queue.items}
    qtbot.waitUntil(lambda: all(session.thumbs.get(paths[k]) is not None or session.thumbs.error(paths[k])
                                for k in partly))
    in_view = [k for k in in_view if session.thumbs.get(paths[k]) is not None]   # pictures shown
    qtbot.mouseClick(window.queue_panel.mark_button, Qt.LeftButton)
    assert window.session.workspace.review.keys() == frozenset(in_view)
    assert window.state_bar.reviewed.full_text == f"✓ {len(in_view)}/15"


def test_the_grid_button_in_the_panel_is_the_g_toggle(qtbot, window):
    button = window.queue_panel.grid_button
    assert button.isVisible() and not button.isChecked()
    qtbot.mouseClick(button, Qt.LeftButton)
    assert window.queue_panel.grid and button.isChecked() and window.actions["toggle_grid"].isChecked()


def test_columns_match_the_layout_at_every_width(qtbot, grid):
    for width in range(330, 740, 2):
        grid.resize(width, 300)
        qtbot.wait(0)
        grid.view.doItemsLayout()
        laid = sum(1 for row in range(6) if tile(grid, row).top() == tile(grid, 0).top())
        assert grid.columns() == laid, (width, grid.view.viewport().width())


def test_a_run_of_resizes_brings_the_cursor_back_once(qtbot, grid, monkeypatch):
    layouts, follow = [], grid._follow
    monkeypatch.setattr(grid, "_follow", lambda: (layouts.append(1), follow()))
    for width in (430, 450, 470, 490, 510):                 # a drag of the dock's edge
        grid.resize(width, 300)
        qtbot.wait(20)
    qtbot.waitUntil(lambda: len(layouts) >= 1)
    qtbot.wait(200)
    assert len(layouts) == 1


def test_mark_page_with_no_tile_wholly_in_view_says_so(qtbot, grid, session):
    grid.resize(150, 300)                                   # narrower than a tile
    qtbot.waitUntil(lambda: grid.visible_keys() == [])
    with qtbot.waitSignal(session.status) as said:
        grid.mark_page()
    assert said.args == ["no tile is wholly in view"] and not session.workspace.review.keys()


def test_mark_page_leaves_the_tiles_not_showing_their_picture(qtbot, grid, session):
    whole = grid.visible_keys()
    path = {item.key: item.entry.path for item in session.queue.items}
    qtbot.waitUntil(lambda: all(session.thumbs.get(path[k]) is not None for k in whole))
    session.thumbs.clear()                                  # as just after a jump: none decoded yet
    with qtbot.waitSignal(session.status) as said:
        grid.mark_page()
    assert said.args == ["no tile in view shows its picture yet; nothing was marked"]
    assert not session.workspace.review.keys()
    session.thumbs.want([path[whole[0]]])                   # one of the two arrives
    qtbot.waitUntil(lambda: session.thumbs.get(path[whole[0]]) is not None)
    with qtbot.waitSignal(session.status) as said:
        grid.mark_page()
    assert session.workspace.review.keys() == frozenset([whole[0]])
    assert said.args == ["marked 1 image reviewed; 1 tile showing no picture was left unmarked"]


def test_a_tile_reads_its_labels_once_and_a_thumbnail_repaints_only_its_tile(qtbot, grid, session, monkeypatch):
    first = session.queue.items[0]
    qtbot.waitUntil(lambda: session.thumbs.get(first.entry.path) is not None)
    reads, read = [], session.labels
    monkeypatch.setattr(session, "labels", lambda entry: (reads.append(entry.rel), read(entry))[1])
    grid.view.viewport().repaint()
    assert reads and len(reads) == len(set(reads))           # one read per tile painted
    updates, update = [], grid.view.update
    monkeypatch.setattr(grid.view, "update", lambda index: (updates.append(index.row()), update(index)))
    session.thumbs.ready.emit(first.entry.path)
    assert updates == [0]


def test_two_quick_g_presses_keep_both_widths(qtbot, window):
    settings = window.session.settings
    qtbot.waitUntil(lambda: near(window.queue_dock.width(), 280))
    qtbot.keyClick(window, Qt.Key_G)
    qtbot.keyClick(window, Qt.Key_G)                        # before the layout catches up
    assert settings.get(QUEUE_GRID_WIDTH) == 560 and near(settings.get(QUEUE_LIST_WIDTH), 280)
    qtbot.waitUntil(lambda: near(window.queue_dock.width(), 280))


def test_a_queue_dock_along_the_bottom_leaves_the_widths_alone(qtbot, window):
    window.addDockWidget(Qt.BottomDockWidgetArea, window.queue_dock)
    qtbot.waitUntil(lambda: window.queue_dock.width() > 1000)
    qtbot.keyClick(window, Qt.Key_G)
    qtbot.keyClick(window, Qt.Key_G)
    settings = window.session.settings
    assert settings.get(QUEUE_LIST_WIDTH) == 280 and settings.get(QUEUE_GRID_WIDTH) == 560
