"""The queue editor: splits and conditions for slice 1's one source, ImageFilter
(docs/design/2026-10-04-app-foundation.md#queue), with slice 3's box size, overlap and
model rows (docs/design/2026-10-06-filters.md#the-queue-editor), and slice 4's second
source, Findings, whose scope is those rows (docs/design/2026-10-06-find-bad.md#the-queue-editor).
It is seeded from the
queue in force, so it never shows a filter the queue is not using (CLAUDE.md landmine 7).
A value it cannot use is refused when OK is pressed, by row and field, and the dialog stays
open with what was typed: never swapped, never clamped."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.dataset import Dataset
from ..core.findings import FindSettings, Findings
from ..core.queue import (
    UNITS,
    Boxes,
    HasClass,
    ImageFilter,
    LabelStateIs,
    ModelDisagrees,
    NameContains,
    Overlap,
    Reviewed,
)

CLASS_MODES = ("any class", "has", "lacks")
LABEL_MODES = ("any", "missing", "negative", "boxes")
REVIEW_MODES = ("any", "reviewed", "not reviewed")
OVERLAP_MODES = {"off": None, "different classes": "different", "same class": "same", "any class": "any"}
MODEL_MODES = {"off": None, "unseen labels": "unseen", "unlabelled predictions": "unlabelled", "either": "either"}
SOURCES = ("Images", "Findings")


def _row(*widgets) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        layout.addWidget(w)
    return row


def _edit(text: str = "") -> QLineEdit:
    edit = QLineEdit(text)
    edit.setMinimumWidth(48)
    return edit


def _text(value) -> str:
    """A number as typed back: exactly the value saved, without a trailing ".0"."""
    if value is None:
        return ""
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text


def _number(edit: QLineEdit, name: str, *, blank: bool = False) -> float | None:
    """The number typed, None for a blank where a blank is an open end, else ValueError."""
    text = edit.text().strip()
    if not text and blank:
        return None
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise ValueError(f"{name}: “{text}” is not a number")
    return value


class QueueEditor(QDialog):
    def __init__(self, dataset: Dataset, current: ImageFilter | Findings, parent=None, *, conf: float = 0.25):
        super().__init__(parent)
        self.setWindowTitle("Queue")
        self.source_kind = QComboBox()
        self.source_kind.addItems(SOURCES)
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
        self.size_w_lo, self.size_w_hi, self.size_h_lo, self.size_h_hi = (_edit() for _ in range(4))
        self.size_unit = QComboBox()
        self.size_unit.addItems(UNITS)
        self.overlap_mode = QComboBox()
        self.overlap_mode.addItems(OVERLAP_MODES)
        self.overlap_lo, self.overlap_hi = _edit("0.5"), _edit("1")
        self.model_mode = QComboBox()
        self.model_mode.addItems(MODEL_MODES)
        self.model_iou, self.model_lo, self.model_hi = _edit("0.5"), _edit(_text(conf)), _edit("1")
        self.error = QLabel()
        self.error.setStyleSheet("color: #e05252;")
        self.error.setWordWrap(True)
        self.error.hide()
        self.chosen: ImageFilter | Findings | None = None      #: what OK took
        self.find_rows = self._find_rows()
        form = QFormLayout()
        form.addRow("Source", self.source_kind)
        form.addRow("Splits", split_row)
        form.addRow("Classes", self.class_mode)
        form.addRow("", self.classes)
        form.addRow("Box size", _row(QLabel("W"), self.size_w_lo, QLabel("–"), self.size_w_hi,
                                     QLabel("H"), self.size_h_lo, QLabel("–"), self.size_h_hi, self.size_unit))
        form.addRow("Label file", self.label_mode)
        form.addRow("Reviewed", self.review_mode)
        form.addRow("Name contains", self.name)
        form.addRow("Overlap", _row(self.overlap_mode, QLabel("IoU"), self.overlap_lo,
                                               QLabel("–"), self.overlap_hi))
        form.addRow("Model", self.model_mode)
        form.addRow("", _row(QLabel("IoU"), self.model_iou, QLabel("conf"), self.model_lo,
                             QLabel("–"), self.model_hi))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.find_rows)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self.source_kind.currentTextChanged.connect(lambda kind: self.find_rows.setVisible(kind == "Findings"))
        if isinstance(current, Findings):
            self.source_kind.setCurrentText("Findings")
            self._seed(current.scope)
            self._seed_settings(current.settings)
        else:
            self._seed(current)
            self._seed_settings(FindSettings())
        self.find_rows.setVisible(self.source_kind.currentText() == "Findings")

    def _find_rows(self) -> QWidget:
        """Find Bad's settings: shown for a Findings queue, whose scope is the rows above."""
        self.find_floor, self.find_iou, self.find_ceiling = _edit(), _edit(), _edit()
        self.find_band_lo, self.find_band_hi, self.find_cutoff = _edit(), _edit(), _edit()
        self.find_band_hi.setPlaceholderText("= IoU")
        self.find_wrong, self.find_not_object, self.find_weak = (
            QCheckBox("wrong class"), QCheckBox("not an object"), QCheckBox("weakly seen"))
        rows = QWidget()
        form = QFormLayout(rows)
        form.setContentsMargins(0, 0, 0, 0)
        # Short labels; each field's tooltip is the name a refusal uses.
        for edit, tip in ((self.find_floor, "confidence floor"), (self.find_iou, "matching IoU"),
                          (self.find_ceiling, "wrong-class ceiling"), (self.find_band_lo, "not-an-object band"),
                          (self.find_band_hi, "not-an-object band; blank: the matching IoU"),
                          (self.find_cutoff, "weak cutoff")):
            edit.setToolTip(tip)
        form.addRow("Find Bad", _row(QLabel("conf ≥"), self.find_floor, QLabel("IoU"), self.find_iou))
        form.addRow("", _row(self.find_wrong, QLabel("conf ≤"), self.find_ceiling))
        form.addRow("", _row(self.find_not_object, QLabel("IoU"), self.find_band_lo,
                             QLabel("–"), self.find_band_hi))
        form.addRow("", _row(self.find_weak, QLabel("conf <"), self.find_cutoff))
        return rows

    def _seed_settings(self, settings: FindSettings) -> None:
        for edit, value in ((self.find_floor, settings.floor), (self.find_iou, settings.match_iou),
                            (self.find_ceiling, settings.ceiling), (self.find_band_lo, settings.band[0]),
                            (self.find_band_hi, settings.band[1]), (self.find_cutoff, settings.cutoff)):
            edit.setText(_text(value))
        self.find_wrong.setChecked(settings.wrong_class)
        self.find_not_object.setChecked(settings.not_object)
        self.find_weak.setChecked(settings.weak)

    def _seed(self, current: ImageFilter) -> None:
        for name, box in self.splits.items():
            box.setChecked(not current.splits or name in current.splits)
        for condition in current.conditions:
            if isinstance(condition, (HasClass, Boxes)):
                present = condition.present if isinstance(condition, HasClass) else True
                self.class_mode.setCurrentText(("has" if condition.names else "any class") if present else "lacks")
                for i in range(self.classes.count()):
                    item = self.classes.item(i)
                    item.setCheckState(Qt.Checked if item.text() in condition.names else Qt.Unchecked)
            if isinstance(condition, Boxes):
                for edit, value in zip((self.size_w_lo, self.size_w_hi, self.size_h_lo, self.size_h_hi),
                                       (*condition.w, *condition.h)):
                    edit.setText(_text(value))
                self.size_unit.setCurrentText(condition.unit)
            elif isinstance(condition, Overlap):
                self.overlap_mode.setCurrentText(next(k for k, v in OVERLAP_MODES.items() if v == condition.scope))
                self.overlap_lo.setText(_text(condition.lo))
                self.overlap_hi.setText(_text(condition.hi))
            elif isinstance(condition, ModelDisagrees):
                self.model_mode.setCurrentText(next(k for k, v in MODEL_MODES.items() if v == condition.direction))
                self.model_iou.setText(_text(condition.match_iou))
                self.model_lo.setText(_text(condition.conf[0]))
                self.model_hi.setText(_text(condition.conf[1]))
            elif isinstance(condition, LabelStateIs):
                self.label_mode.setCurrentText(condition.state)
            elif isinstance(condition, Reviewed):
                self.review_mode.setCurrentText("reviewed" if condition.value else "not reviewed")
            elif isinstance(condition, NameContains):
                self.name.setText(condition.text)

    def accept(self) -> None:
        """OK: take the queue the rows describe, or say why not and stay open."""
        try:
            self.chosen = self.source()
        except ValueError as e:
            self.error.setText(str(e))
            self.error.show()
            return
        self.error.hide()
        super().accept()

    def source(self) -> ImageFilter | Findings:
        """The queue the dialog describes: its image filter, or the findings in it."""
        if self.source_kind.currentText() == "Images":
            return self.filter()
        return Findings(self.filter(), self.settings())

    def settings(self) -> FindSettings:
        """Find Bad's settings; ValueError naming the field when they cannot be used."""
        try:
            settings = FindSettings(
                _number(self.find_floor, "confidence floor"), _number(self.find_iou, "matching IoU"),
                self.find_wrong.isChecked(), _number(self.find_ceiling, "wrong-class ceiling"),
                self.find_not_object.isChecked(),
                (_number(self.find_band_lo, "not-an-object band"),
                 _number(self.find_band_hi, "not-an-object band", blank=True)),
                self.find_weak.isChecked(), _number(self.find_cutoff, "weak cutoff"))
        except ValueError as e:
            raise ValueError(f"Find Bad — {e}") from e
        if not settings.kinds:
            raise ValueError("Find Bad — choose at least one kind of finding")
        return settings

    def filter(self) -> ImageFilter:
        """The queue the dialog describes. All splits checked means every split. ValueError,
        naming the row and the field, when a row cannot be used."""
        checked = tuple(name for name, box in self.splits.items() if box.isChecked())
        if self.splits and not checked:
            raise ValueError("Splits — choose at least one")        # never quietly "every split"
        splits = () if len(checked) == len(self.splits) else checked
        conditions = []
        names = tuple(self.classes.item(i).text() for i in range(self.classes.count())
                      if self.classes.item(i).checkState() == Qt.Checked)
        mode = self.class_mode.currentText()
        if mode != "any class" and not names:
            raise ValueError("Classes — choose a class, or any class")    # never quietly dropped
        size = self._size()
        if size is not None:
            if mode == "lacks":
                raise ValueError("Box size — needs Classes: has, or any class")
            conditions.append(self._made("Box size", Boxes, names if mode == "has" else (), *size))
        elif mode != "any class" and names:
            conditions.append(HasClass(names, present=mode == "has"))
        if self.label_mode.currentText() != "any":
            conditions.append(LabelStateIs(self.label_mode.currentText()))
        if self.review_mode.currentText() != "any":
            conditions.append(Reviewed(self.review_mode.currentText() == "reviewed"))
        if self.name.text().strip():
            conditions.append(NameContains(self.name.text().strip()))
        scope = OVERLAP_MODES[self.overlap_mode.currentText()]
        if scope is not None:
            conditions.append(self._made("Overlap", lambda: Overlap(
                scope, _number(self.overlap_lo, "IoU"), _number(self.overlap_hi, "IoU"))))
        direction = MODEL_MODES[self.model_mode.currentText()]
        if direction is not None:
            conditions.append(self._made("Model", lambda: ModelDisagrees(
                direction, _number(self.model_iou, "matching IoU"),
                (_number(self.model_lo, "confidence"), _number(self.model_hi, "confidence")))))
        return ImageFilter(splits, tuple(conditions))

    def _size(self):
        """(w, h, unit) when any size end is typed, else None. ValueError for junk."""
        try:
            ends = [_number(e, name, blank=True) for e, name in ((self.size_w_lo, "width"), (self.size_w_hi, "width"),
                                                                 (self.size_h_lo, "height"), (self.size_h_hi, "height"))]
        except ValueError as e:
            raise ValueError(f"Box size — {e}") from e
        if all(end is None for end in ends):
            return None
        return (ends[0], ends[1]), (ends[2], ends[3]), self.size_unit.currentText()

    @staticmethod
    def _made(row: str, make, *args):
        """A condition, or ValueError naming the row it came from."""
        try:
            return make(*args)
        except ValueError as e:
            raise ValueError(f"{row} — {e}") from e
