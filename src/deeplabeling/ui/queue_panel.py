"""The queue panel (docs/design/2026-10-04-app-foundation.md#window): the queue as a
virtualised list, or as a grid of thumbnails with their label boxes drawn on them. One
view shows both, so there is one selection, and it mirrors the session's cursor -- there
is no second notion of the current item."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.queue import QueueItem
from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .images import THUMB_PX
from .session import Session

TILE = QSize(176, 150)                      #: one grid cell
THUMB_AREA = QRect(8, 6, THUMB_PX, 120)     #: where a cell's thumbnail goes, within it
TILE_BG, TILE_TEXT, TILE_CURRENT = "#3a3a3a", "#e0e0e0", "#4a90d9"
WANT_MS = 30                                #: thumbnails are wanted this long after a scroll
REFOLLOW_MS = 120                           #: a resize is settled when none came for this long


def tile_thumb_rect(cell: QRect, thumb: QSize) -> QRect:
    """Where a thumbnail of size `thumb` is drawn in a grid cell: fitted to the
    thumbnail area, its aspect kept, centred."""
    area = THUMB_AREA.translated(cell.topLeft())
    rect = QRect(QPoint(0, 0), thumb.scaled(area.size(), Qt.KeepAspectRatio))
    rect.moveCenter(area.center())
    return rect


def tile_text(session: Session, item: QueueItem, labels=None) -> str:
    """A tile's caption: the reviewed tick, the file name and the badge."""
    tick = "✓ " if session.workspace.review.is_marked(item.key) else ""
    return f"{tick}{Path(item.key).name} · {session.badge(item, labels)}"


class QueueModel(QAbstractListModel):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self._rows = 0
        session.queueReset.connect(self._reset)
        session.closed.connect(self._reset)
        session.queueGrew.connect(self._grew)
        session.itemsChanged.connect(self._changed)
        self._reset()                               # a queue may already be built

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self._rows

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        queue = self._session.queue
        if not index.isValid() or queue is None or index.row() >= len(queue):
            return None
        item = queue.items[index.row()]
        if role == Qt.DisplayRole:
            return self._session.describe_item(item)
        if role == Qt.ToolTipRole:
            return str(item.entry.path)
        if role == Qt.UserRole:
            return item.key
        return None

    def _reset(self) -> None:
        self.beginResetModel()
        queue = self._session.queue
        self._rows = len(queue) if queue is not None else 0
        self.endResetModel()

    def _grew(self) -> None:
        n = len(self._session.queue)
        if n > self._rows:
            self.beginInsertRows(QModelIndex(), self._rows, n - 1)
            self._rows = n
            self.endInsertRows()

    def _changed(self, keys) -> None:
        queue = self._session.queue
        if queue is None:
            return
        for key in keys:
            row = queue.index_of(key)
            if row is not None and row < self._rows:
                index = self.index(row)
                self.dataChanged.emit(index, index)


class TileDelegate(QStyledItemDelegate):
    """Paints one grid tile: the thumbnail, its label boxes in their class colours, and
    the caption. Labels are read as the tile is painted, so it never shows old boxes."""

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session

    def sizeHint(self, option, index) -> QSize:
        return TILE

    def paint(self, painter, option, index) -> None:
        session = self._session
        queue = session.queue
        if queue is None or session.workspace is None or index.row() >= len(queue):
            return
        item, cell = queue.items[index.row()], option.rect
        labels = session.labels(item.entry)        # once a paint: the caption and the boxes
        painter.save()
        painter.fillRect(cell.adjusted(2, 2, -2, -2), QColor(TILE_BG))
        if option.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor(TILE_CURRENT), 3))
            painter.drawRect(cell.adjusted(3, 3, -4, -4))
        painter.setPen(QColor(TILE_TEXT))
        thumb = session.thumbs.get(item.entry.path)
        if thumb is None:
            why = session.thumbs.error(item.entry.path)
            painter.drawText(THUMB_AREA.translated(cell.topLeft()), Qt.AlignCenter,
                             "cannot decode" if why else "…")
        else:
            target = tile_thumb_rect(cell, thumb.size())
            painter.drawImage(target, thumb)
            self._draw_boxes(painter, labels, target)
        caption = QRect(cell.x() + 8, cell.y() + THUMB_AREA.bottom() + 4, cell.width() - 16,
                        cell.height() - THUMB_AREA.bottom() - 8)
        painter.setPen(QColor(TILE_TEXT))
        painter.drawText(caption, Qt.AlignLeft | Qt.AlignVCenter,
                         option.fontMetrics.elidedText(tile_text(session, item, labels), Qt.ElideMiddle,
                                                       caption.width()))
        painter.restore()

    def _draw_boxes(self, painter, labels, target: QRect) -> None:
        session, ws = self._session, self._session.workspace
        highlight = session.queue.source.highlight(labels, ws.dataset)
        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setClipRect(target)             # a box past the image's edge stays in its tile
        for view in box_views(labels, ws.dataset, (target.width(), target.height()),
                              ws.root_settings.get(CLASS_COLORS), highlight):
            pen = QPen(QColor(view.color), 2 if view.highlighted else 1)
            if not view.known:
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            if view.polygon:
                painter.drawPolygon(QPolygonF([QPointF(target.x() + x, target.y() + y)
                                               for x, y in view.polygon]))
            else:
                x1, y1, x2, y2 = view.rect
                painter.drawRect(QRectF(target.x() + x1, target.y() + y1, x2 - x1, y2 - y1))
        painter.restore()


class QueuePanel(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self.grid = False
        self.title = QLabel()
        self.mark_button = QToolButton()
        self.mark_button.setText("Mark page")
        self.mark_button.setToolTip("Mark every tile in view reviewed")
        self.mark_button.setFocusPolicy(Qt.NoFocus)
        self.mark_button.clicked.connect(self.mark_page)
        self.mark_button.hide()
        self.grid_button = QToolButton()           # the window gives it the G action
        self.grid_button.setFocusPolicy(Qt.NoFocus)
        self.model = QueueModel(session, self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setFocusPolicy(Qt.NoFocus)         # arrows belong to the window's actions
        self._rows = self.view.itemDelegate()
        self._tiles = TileDelegate(session, self.view)
        # The view's current row drives the cursor, however the mouse got there (a drag
        # across rows moves it without a click); following the cursor does not count.
        self._following = False
        self.view.selectionModel().currentChanged.connect(self._picked)
        header = QHBoxLayout()
        header.addWidget(self.title, 1)
        header.addWidget(self.mark_button)
        header.addWidget(self.grid_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(header)
        layout.addWidget(self.view, 1)
        for signal in (session.queueReset, session.queueGrew, session.queueDone, session.closed):
            signal.connect(self._retitle)
        # Follow cursor moves only. Following every batch scrolled the view as each one
        # arrived, re-laying out every row so far: 5 s of a 9 s launch on pvn-vehicle.
        session.cursorChanged.connect(self._follow)
        # Thumbnails are decoded only for the tiles in view: wanted a moment after the
        # view moves, and a scroll cancels those that left it.
        self._want = QTimer(self)
        self._want.setSingleShot(True)
        self._want.setInterval(WANT_MS)
        self._want.timeout.connect(self._want_thumbs)
        # A resized grid re-flows into other columns, and a narrowed list can gain a
        # horizontal scrollbar over its bottom row: either way the same scroll offset then
        # hides the current item, so once the size settles it is brought back.
        self._refollow = QTimer(self)
        self._refollow.setSingleShot(True)
        self._refollow.setInterval(REFOLLOW_MS)    # a drag of the dock's edge: once, at its end
        self._refollow.timeout.connect(self._relayout)
        self.view.verticalScrollBar().valueChanged.connect(self._want_soon)
        session.queueReset.connect(self._want_soon)
        session.queueGrew.connect(self._want_soon)
        session.thumbs.ready.connect(self._thumb_arrived)
        session.thumbs.failed.connect(self._thumb_arrived)
        self._retitle()
        self._follow()

    # -- list or grid -------------------------------------------------------------------

    def set_grid(self, on: bool) -> None:
        """Show the queue as a grid of thumbnails, or as a list. One view does both."""
        self.grid = on
        view = self.view
        view.setFlow(QListView.LeftToRight if on else QListView.TopToBottom)
        view.setWrapping(on)
        view.setResizeMode(QListView.Adjust if on else QListView.Fixed)
        view.setGridSize(TILE if on else QSize())
        view.setItemDelegate(self._tiles if on else self._rows)
        self.mark_button.setVisible(on)
        self._relayout()
        self._want_soon()

    def _relayout(self) -> None:
        # Lay the view out now: scrolling to the cursor before then would scroll by the
        # old geometry, leaving the current item out of sight.
        self.view.doItemsLayout()
        self._follow()

    def columns(self) -> int:
        """Tiles per grid row; 1 in the list."""
        if not self.grid:
            return 1
        # Qt wraps a row when a tile would reach the viewport's last pixel.
        return max(1, (self.view.viewport().width() - 1) // TILE.width())

    def _visible_rows(self, partial: bool) -> list[int]:
        area = self.view.viewport().rect()
        first = self.view.indexAt(QPoint(1, 1))
        rows = []
        for row in range(first.row() if first.isValid() else 0, self.model.rowCount()):
            rect = self.view.visualRect(self.model.index(row))
            if rect.top() > area.bottom():
                break                               # rows run in reading order
            if area.intersects(rect) if partial else area.contains(rect):
                rows.append(row)
        return rows

    def visible_keys(self, partial: bool = False) -> list[str]:
        """The items wholly in view, or (partial) at least partly in view."""
        queue = self._session.queue
        if queue is None:
            return []
        return [queue.items[row].key for row in self._visible_rows(partial) if row < len(queue)]

    def mark_page(self) -> None:
        """Mark every tile wholly in view reviewed: what was seen, nothing more."""
        session = self._session
        if not self.grid or session.workspace is None or session.queue is None:
            return
        whole = self.visible_keys()
        if not whole:
            session.status.emit("no tile is wholly in view")
            return
        # A tile still loading, or one that cannot be decoded, shows no picture: unseen.
        items = session.queue.items
        shown = [key for key in whole if session.thumbs.get(items[session.queue.index_of(key)].entry.path)]
        if not shown:
            session.status.emit("no tile in view shows its picture yet; nothing was marked")
            return
        session.mark_reviewed(shown, left=len(whole) - len(shown))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refollow.start()
        self._want_soon()

    def _want_soon(self, *_) -> None:
        if self.grid:
            self._want.start()

    def _want_thumbs(self) -> None:
        queue = self._session.queue
        if self.grid and queue is not None:
            self._session.thumbs.want([queue.items[row].entry.path
                                       for row in self._visible_rows(partial=True) if row < len(queue)])

    def _thumb_arrived(self, path, *_) -> None:
        """Repaint the one tile whose thumbnail came, if it is in the queue."""
        session = self._session
        if not self.grid or session.workspace is None or session.queue is None:
            return
        try:
            row = session.queue.index_of(session.workspace.dataset.entry(path).rel)
        except KeyError:
            return
        if row is not None and row < self.model.rowCount():
            self.view.update(self.model.index(row))

    # -- the title and the cursor ----------------------------------------------------------

    def _retitle(self) -> None:
        queue = self._session.queue
        if queue is None:
            self.title.setText("Queue")
        else:
            self.title.setText(f"Queue · {len(queue):,}{self._session.progress_text()}")

    def _follow(self) -> None:
        queue = self._session.queue
        row = queue.position() if queue is not None else None
        if row is None or row >= self.model.rowCount():
            self.view.clearSelection()
            return
        self._following = True
        try:
            index = self.model.index(row)
            if self.view.currentIndex() == index:
                self.view.scrollTo(index)           # a new layout: the same item, elsewhere
            else:
                self.view.setCurrentIndex(index)    # which also scrolls to it
        finally:
            self._following = False

    def _picked(self, current, previous) -> None:
        if self._following or not current.isValid():
            return
        key = current.data(Qt.UserRole)
        item = self._session.current()
        if item is None or item.key != key:
            self._session.go_to(key)
