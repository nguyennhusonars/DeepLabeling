"""The reassign dialog (docs/design/2026-10-07-bulk-and-stats.md#the-dialog): From and To.
From lists the yaml's classes, then the class ids the labels hold that it does not name; To
lists the yaml's classes. A class onto itself is refused, and the dialog stays open."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout


def class_label(cls_id: int, names) -> str:
    """A class as the app writes it: its name, or `#99?` for an id the yaml does not name."""
    return names[cls_id] if 0 <= cls_id < len(names) else f"#{cls_id}?"


class ReassignDialog(QDialog):
    def __init__(self, names, unnamed_ids=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reassign a class in this queue")
        self.source, self.target = QComboBox(), QComboBox()
        for cls_id in [*range(len(names)), *unnamed_ids]:
            self.source.addItem(class_label(cls_id, names), cls_id)
        for cls_id, name in enumerate(names):
            self.target.addItem(name, cls_id)
        for combo in (self.source, self.target):
            combo.setMinimumWidth(160)
        self.error = QLabel()
        self.error.setStyleSheet("color: #e05252;")
        self.error.hide()
        self.chosen: tuple[int, int] | None = None     #: (from, to), what OK took
        form = QFormLayout()
        form.addRow("From", self.source)
        form.addRow("To", self.target)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def accept(self) -> None:
        source, target = self.source.currentData(), self.target.currentData()
        if source == target:
            self.error.setText("From and To are the same class")
            self.error.show()
            return
        self.chosen = (source, target)
        super().accept()
