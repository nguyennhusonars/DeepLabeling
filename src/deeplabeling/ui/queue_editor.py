"""The queue editor: splits and conditions for slice 1's one source, ImageFilter
(docs/design/2026-10-04-app-foundation.md#queue). It is seeded from the queue in
force, so it never shows a filter the queue is not using (CLAUDE.md landmine 7)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.dataset import Dataset
from ..core.queue import HasClass, ImageFilter, LabelStateIs, NameContains, Reviewed

CLASS_MODES = ("any class", "has", "lacks")
LABEL_MODES = ("any", "missing", "negative", "boxes")
REVIEW_MODES = ("any", "reviewed", "not reviewed")


class QueueEditor(QDialog):
    def __init__(self, dataset: Dataset, current: ImageFilter, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Queue")
        self.splits = {name: QCheckBox(name) for name in dataset.splits}
        split_row = QWidget()
        row = QHBoxLayout(split_row)
        row.setContentsMargins(0, 0, 0, 0)
        for box in self.splits.values():
            row.addWidget(box)
        self.class_mode = QComboBox()
        self.class_mode.addItems(CLASS_MODES)
        self.classes = QListWidget()
        for name in dataset.names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.classes.addItem(item)
        self.label_mode = QComboBox()
        self.label_mode.addItems(LABEL_MODES)
        self.review_mode = QComboBox()
        self.review_mode.addItems(REVIEW_MODES)
        self.name = QLineEdit()
        form = QFormLayout()
        form.addRow("Splits", split_row)
        form.addRow("Classes", self.class_mode)
        form.addRow("", self.classes)
        form.addRow("Label file", self.label_mode)
        form.addRow("Reviewed", self.review_mode)
        form.addRow("Name contains", self.name)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._seed(current)

    def _seed(self, current: ImageFilter) -> None:
        for name, box in self.splits.items():
            box.setChecked(not current.splits or name in current.splits)
        for condition in current.conditions:
            if isinstance(condition, HasClass):
                self.class_mode.setCurrentText("has" if condition.present else "lacks")
                for i in range(self.classes.count()):
                    item = self.classes.item(i)
                    item.setCheckState(Qt.Checked if item.text() in condition.names else Qt.Unchecked)
            elif isinstance(condition, LabelStateIs):
                self.label_mode.setCurrentText(condition.state)
            elif isinstance(condition, Reviewed):
                self.review_mode.setCurrentText("reviewed" if condition.value else "not reviewed")
            elif isinstance(condition, NameContains):
                self.name.setText(condition.text)

    def filter(self) -> ImageFilter:
        """The queue the dialog describes. All splits checked means every split."""
        checked = tuple(name for name, box in self.splits.items() if box.isChecked())
        splits = () if len(checked) == len(self.splits) else checked
        conditions = []
        names = tuple(self.classes.item(i).text() for i in range(self.classes.count())
                      if self.classes.item(i).checkState() == Qt.Checked)
        if self.class_mode.currentText() != "any class" and names:
            conditions.append(HasClass(names, present=self.class_mode.currentText() == "has"))
        if self.label_mode.currentText() != "any":
            conditions.append(LabelStateIs(self.label_mode.currentText()))
        if self.review_mode.currentText() != "any":
            conditions.append(Reviewed(self.review_mode.currentText() == "reviewed"))
        if self.name.text().strip():
            conditions.append(NameContains(self.name.text().strip()))
        return ImageFilter(splits, tuple(conditions))
