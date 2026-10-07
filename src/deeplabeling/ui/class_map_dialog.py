"""The class-map editor (docs/design/2026-10-05-model-assist.md#the-class-map): one row per
model class, each mapped to a dataset class or to nothing, and a button that seeds by name
again. Only a row the user changes becomes their choice; the rest stay seeded."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..core.classmap import ClassMap

NOT_MAPPED = "not mapped"
MAX_HEIGHT = 640


class ClassMapDialog(QDialog):
    def __init__(self, cmap: ClassMap, dataset_names: Sequence[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Class map")
        self._base, self._names = cmap, tuple(dataset_names)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        self._rows: list[tuple[QLabel, QComboBox]] = []
        for name in cmap.model_names:
            label, combo = QLabel(name), QComboBox()
            combo.addItems([NOT_MAPPED, *self._names])
            form.addRow(label, combo)
            self._rows.append((label, combo))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        self.seed_button = QPushButton("Seed by name again")
        self.seed_button.clicked.connect(self._seed)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Model class → the dataset class it is accepted as"))
        layout.addWidget(scroll)
        layout.addWidget(self.seed_button)
        layout.addWidget(buttons)
        self._show(cmap)
        hint = form_widget.sizeHint()
        self.resize(max(hint.width() + 60, 360), min(hint.height() + 140, MAX_HEIGHT))

    def _show(self, cmap: ClassMap) -> None:
        for (_, combo), target in zip(self._rows, cmap.targets):
            combo.setCurrentText(target if target in self._names else NOT_MAPPED)

    def _seed(self) -> None:
        self._base = ClassMap.seeded(self._base.model_names, self._names)
        self._show(self._base)

    def rows(self) -> list[tuple[str, str]]:
        return [(label.text(), combo.currentText()) for label, combo in self._rows]

    def row_widgets(self) -> list[tuple[QLabel, QComboBox]]:
        return list(self._rows)

    def choose(self, model_name: str, target: str) -> None:
        self._rows[self._base.model_names.index(model_name)][1].setCurrentText(target)

    def class_map(self) -> ClassMap:
        """The map as shown: the rows that differ from where they started are choices."""
        cmap = self._base
        for i, (_, combo) in enumerate(self._rows):
            target = None if combo.currentText() == NOT_MAPPED else combo.currentText()
            if target != cmap.targets[i]:
                cmap = cmap.with_target(i, target)
        return cmap
