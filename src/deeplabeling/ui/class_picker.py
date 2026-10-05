"""The class picker (key C): type to filter the classes, Enter to choose. It reaches the
classes past the tenth, which have no digit key."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from .classes import ClassInfo
from .inspector import swatch


class ClassPicker(QDialog):
    def __init__(self, infos: Sequence[ClassInfo], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose a class")
        self._infos = list(infos)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Type to filter")
        self.list = QListWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.filter)
        layout.addWidget(self.list)
        self.filter.textChanged.connect(self._fill)
        self.filter.returnPressed.connect(self._choose)
        self.list.itemActivated.connect(self._choose)
        self.filter.installEventFilter(self)        # Up and Down move through the list
        self._fill("")
        self.resize(320, 360)

    def _fill(self, text: str) -> None:
        self.list.clear()
        for info in self._infos:
            if text.lower() in info.name.lower():
                item = QListWidgetItem(swatch(info.color), f"{info.hotkey or ' '}   {info.name}")
                item.setData(Qt.UserRole, info.cls_id)
                self.list.addItem(item)
        self.list.setCurrentRow(0)

    def chosen(self) -> ClassInfo | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return next(info for info in self._infos if info.cls_id == item.data(Qt.UserRole))

    def _choose(self, *_) -> None:
        if self.chosen() is not None:
            self.accept()

    def eventFilter(self, watched, event) -> bool:
        if (watched is self.filter and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Up, Qt.Key_Down)):
            step = 1 if event.key() == Qt.Key_Down else -1
            row = self.list.currentRow() + step
            if 0 <= row < self.list.count():
                self.list.setCurrentRow(row)
            return True
        return super().eventFilter(watched, event)
