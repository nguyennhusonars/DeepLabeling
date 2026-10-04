"""The queue panel (docs/design/2026-10-04-app-foundation.md#window): a virtualised list
of the queue, whose selection mirrors the session's cursor -- there is no second notion
of the current item. Plan 1c adds the grid."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtWidgets import QAbstractItemView, QLabel, QListView, QVBoxLayout, QWidget

from .session import Session


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


class QueuePanel(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self.title = QLabel()
        self.model = QueueModel(session, self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setFocusPolicy(Qt.NoFocus)         # arrows belong to the window's actions
        self.view.clicked.connect(lambda index: session.go_to(index.data(Qt.UserRole)))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.title)
        layout.addWidget(self.view, 1)
        for signal in (session.queueReset, session.queueGrew, session.queueDone, session.closed):
            signal.connect(self._retitle)
        # Follow cursor moves only. Following every batch scrolled the view as each one
        # arrived, re-laying out every row so far: 5 s of a 9 s launch on pvn-vehicle.
        session.cursorChanged.connect(self._follow)
        self._retitle()
        self._follow()

    def _retitle(self) -> None:
        queue = self._session.queue
        if queue is None:
            self.title.setText("Queue")
        else:
            building = "" if queue.complete else " · building…"
            self.title.setText(f"Queue · {len(queue):,}{building}")

    def _follow(self) -> None:
        queue = self._session.queue
        row = queue.position() if queue is not None else None
        if row is None or row >= self.model.rowCount():
            self.view.clearSelection()
            return
        self.view.setCurrentIndex(self.model.index(row))     # which also scrolls to it
