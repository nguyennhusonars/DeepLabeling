"""The inspector (docs/design/2026-10-04-app-foundation.md#window): the current image, its
classes and its boxes. Clicking a class reclassifies the selection, or makes it the active
class (marked ✎); the box list shows the one selection and sets it."""

from __future__ import annotations

import time
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.store import LabelState
from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .session import Session

#: After the active class's name in the palette.
ACTIVE_MARK = "✎"


def swatch(color: str) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class Inspector(QWidget):
    def __init__(self, session: Session, editing, parent=None):
        super().__init__(parent)
        self._session, self._editing = session, editing
        self._syncing = False                       # the box list is being set, not clicked
        self._labels = None                         # what the box list shows; its rows mean these
        self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label = (
            QLabel() for _ in range(5))
        for label in self._fields():
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form = QFormLayout()
        form.addRow("Image", self.path_label)
        form.addRow("Size", self.size_label)
        form.addRow("Labels", self.state_label)
        form.addRow("Unparsable lines", self.unparsed_label)
        form.addRow("Reviewed", self.reviewed_label)
        self.classes = QListWidget()
        self.boxes = QListWidget()
        for widget in (self.classes, self.boxes):
            widget.setFocusPolicy(Qt.NoFocus)
        self.classes.setSelectionMode(QAbstractItemView.NoSelection)    # ✎ marks the active class
        self.boxes.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(form)
        layout.addWidget(QLabel("Classes"))
        layout.addWidget(self.classes, 1)
        layout.addWidget(QLabel("Boxes"))
        layout.addWidget(self.boxes, 1)
        for signal in (session.cursorChanged, session.reviewChanged, session.opened, session.closed):
            signal.connect(self.refresh)
        session.labelsChanged.connect(self._labels_event)
        session.images.ready.connect(self._image_event)
        session.images.failed.connect(lambda path, why: self._image_event(path))
        self.classes.itemClicked.connect(self._class_clicked)
        self.boxes.itemSelectionChanged.connect(self._boxes_clicked)
        editing.selection.changed.connect(self._show_selection)
        editing.activeChanged.connect(self.refresh)
        self.refresh()

    def _fields(self) -> tuple[QLabel, ...]:
        # *_label names: a field called `size` would shadow QWidget.size()
        return (self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label)

    def _labels_event(self, images) -> None:
        item = self._session.current()
        if item is not None and item.entry.path in images:
            self.refresh()                          # another image's change is not shown here

    def _image_event(self, path) -> None:
        item = self._session.current()
        if item is not None and item.entry.path == path:
            self.refresh()

    def _class_clicked(self, row: QListWidgetItem) -> None:
        info = next(i for i in self._editing.classes() if i.cls_id == row.data(Qt.UserRole))
        self._editing.choose_class(info)

    def _boxes_clicked(self) -> None:
        if not self._syncing:
            self._editing.pick([row.data(Qt.UserRole) for row in self.boxes.selectedItems()], self._labels)
            self._show_selection()                  # a refused pick (labels hidden) un-highlights

    def _show_selection(self) -> None:
        selected = set(self._editing.selection.indices(self._labels)) if self._labels is not None else set()
        self._syncing = True
        try:
            first = None
            for i in range(self.boxes.count()):
                row = self.boxes.item(i)
                row.setSelected(row.data(Qt.UserRole) in selected)
                if first is None and row.isSelected():
                    first = row
            if first is not None:
                self.boxes.scrollToItem(first)
        finally:
            self._syncing = False

    def refresh(self) -> None:
        session, item = self._session, self._session.current()
        self._syncing = True
        try:
            self._fill(session, item)
        finally:
            self._syncing = False
        self._show_selection()

    def _fill(self, session, item) -> None:
        self.classes.clear()
        self.boxes.clear()
        self._labels = None
        if session.workspace is None or item is None:
            for label in self._fields():
                label.setText("—")
            return
        ws, entry = session.workspace, item.entry
        labels = session.labels(entry)
        image, why = session.images.get(entry.path), session.images.error(entry.path)
        self.path_label.setText(entry.rel)
        self.size_label.setText(f"cannot decode: {why}" if why else
                          f"{image.width()} × {image.height()}" if image is not None else "decoding…")
        self.state_label.setText(self._state_text(labels))
        self.unparsed_label.setText(str(labels.unparsed))
        marked = ws.review.marked_at(entry.rel)
        self.reviewed_label.setText(time.strftime("%Y-%m-%d %H:%M", time.localtime(marked)) if marked else "not yet")
        colors = ws.root_settings.get(CLASS_COLORS)
        counts = Counter(line.cls_id for _, line in labels.boxes)
        active = self._editing.active_class()
        for info in self._editing.classes():
            text = f"{info.hotkey or ' '}   {info.name}   {counts.get(info.cls_id, 0)}"
            row = QListWidgetItem(swatch(info.color), text + (f"   {ACTIVE_MARK}" if info == active else ""))
            row.setData(Qt.UserRole, info.cls_id)
            self.classes.addItem(row)
        if image is not None:
            self._labels = labels
            for view in box_views(labels, ws.dataset, (image.width(), image.height()), colors):
                x1, y1, x2, y2 = view.rect
                row = QListWidgetItem(swatch(view.color), f"{view.caption}   {round(x2 - x1)} × {round(y2 - y1)} px")
                row.setData(Qt.UserRole, view.index)
                self.boxes.addItem(row)

    @staticmethod
    def _state_text(labels) -> str:
        if labels.state is LabelState.ERROR:
            return labels.error
        if labels.state is LabelState.SHARED:
            return f"read-only: {labels.error}"
        if labels.raw is None:
            return "no label file"
        if labels.negative:
            return "negative sample (no boxes)"
        n = len(labels.boxes)
        return f"{n} box" if n == 1 else f"{n} boxes"
