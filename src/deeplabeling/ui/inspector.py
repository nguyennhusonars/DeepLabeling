"""The inspector (docs/design/2026-10-04-app-foundation.md#window): the current image, its
classes and its boxes. Read-only in plan 1b; plan 1c makes the palette and the box list
act on the selection."""

from __future__ import annotations

import time
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QFormLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..core.store import LabelState
from ..core.workspace import CLASS_COLORS, CLASS_HOTKEYS
from .boxes import box_views
from .classes import class_infos
from .session import Session


def swatch(color: str) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class Inspector(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(form)
        layout.addWidget(QLabel("Classes"))
        layout.addWidget(self.classes, 1)
        layout.addWidget(QLabel("Boxes"))
        layout.addWidget(self.boxes, 1)
        for signal in (session.cursorChanged, session.reviewChanged, session.opened, session.closed):
            signal.connect(self.refresh)
        session.labelsChanged.connect(lambda images: self.refresh())
        session.images.ready.connect(self._image_event)
        session.images.failed.connect(lambda path, why: self._image_event(path))
        self.refresh()

    def _fields(self) -> tuple[QLabel, ...]:
        # *_label names: a field called `size` would shadow QWidget.size()
        return (self.path_label, self.size_label, self.state_label, self.unparsed_label, self.reviewed_label)

    def _image_event(self, path) -> None:
        item = self._session.current()
        if item is not None and item.entry.path == path:
            self.refresh()

    def refresh(self) -> None:
        session, item = self._session, self._session.current()
        self.classes.clear()
        self.boxes.clear()
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
        for info in class_infos(ws.dataset, colors, ws.root_settings.get(CLASS_HOTKEYS)):
            row = QListWidgetItem(swatch(info.color), f"{info.hotkey or ' '}   {info.name}   {counts.get(info.cls_id, 0)}")
            self.classes.addItem(row)
        if image is not None:
            for view in box_views(labels, ws.dataset, (image.width(), image.height()), colors):
                x1, y1, x2, y2 = view.rect
                self.boxes.addItem(QListWidgetItem(swatch(view.color),
                                                   f"{view.caption}   {round(x2 - x1)} × {round(y2 - y1)} px"))

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
