"""The real dialogs behind the Prompter the session and window use. Tests answer the same
calls with tests/fixtures.py's FakePrompter, so no test waits on a modal loop."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox, QProgressDialog

from ..core.classmap import ClassMap
from ..core.dataset import Dataset
from ..core.findings import Findings
from ..core.inference import FLOOR
from ..core.queue import ImageFilter
from .class_map_dialog import ClassMapDialog
from .class_picker import ClassPicker
from .classes import ClassInfo
from .queue_editor import QueueEditor
from .reassign_dialog import ReassignDialog


def _names(names) -> str:
    names = list(names)
    return ", ".join(names[:6]) + (", …" if len(names) > 6 else "")


def taxonomy_question(last_source: str, last_names, source: str, names) -> str:
    return (f"These label files were last opened with {Path(last_source).name} "
            f"({len(last_names)} classes: {_names(last_names)}).\n\n"
            f"You are opening them with {Path(source).name} "
            f"({len(names)} classes: {_names(names)}).\n\n"
            "A label file's ids mean one class list. Under the wrong one every name shown is "
            "wrong, and every edit writes wrong ids. Open with the new class list?")


class Progress:
    """A modal progress dialog with a Cancel button. The window keeps painting behind it,
    and nothing else in the app can be clicked while it shows."""

    def __init__(self, dialog: QProgressDialog):
        self._dialog = dialog
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        dialog.show()

    def set(self, value: int) -> None:
        self._dialog.setValue(value)

    def cancelled(self) -> bool:
        return self._dialog.wasCanceled() or not self._dialog.isVisible()     # Esc hides it

    def close(self) -> None:
        self._dialog.close()
        self._dialog.deleteLater()


class QtPrompter:
    def __init__(self, parent=None):
        self.parent = parent

    def confirm_taxonomy(self, last_source, last_names, source, names) -> bool:
        answer = QMessageBox.question(self.parent, "A different class list",
                                      taxonomy_question(last_source, last_names, source, names),
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes

    def error(self, title: str, text: str) -> None:
        QMessageBox.warning(self.parent, title, text)

    def choose_yaml(self) -> str | None:
        path, _ = QFileDialog.getOpenFileName(self.parent, "Open a dataset yaml", "",
                                              "Dataset yaml (*.yaml *.yml)")
        return path or None

    def choose_folder(self, title: str) -> str | None:
        return QFileDialog.getExistingDirectory(self.parent, title) or None

    def edit_queue(self, dataset: Dataset, current: ImageFilter | Findings,
                   conf: float = 0.25) -> ImageFilter | Findings | None:
        dialog = QueueEditor(dataset, current, self.parent, conf=conf)
        try:
            return dialog.chosen if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()                    # a child of the window until deleted

    def ask_text(self, title: str, label: str) -> str | None:
        text, ok = QInputDialog.getText(self.parent, title, label)
        return text if ok else None

    def pick_class(self, infos: list[ClassInfo]) -> ClassInfo | None:
        dialog = ClassPicker(infos, self.parent)
        try:
            return dialog.chosen() if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()

    def choose_weights(self) -> str | None:
        path, _ = QFileDialog.getOpenFileName(self.parent, "Load a model", "",
                                              "Model weights (*.pt);;All files (*)")
        return path or None

    def ask_threshold(self, current: float) -> float | None:
        value, ok = QInputDialog.getDouble(self.parent, "Confidence threshold",
                                           "Show and accept predictions at or above:",
                                           current, FLOOR, 1.0, 2)
        return value if ok else None

    def edit_class_map(self, cmap: ClassMap, dataset_names) -> ClassMap | None:
        dialog = ClassMapDialog(cmap, dataset_names, self.parent)
        try:
            return dialog.class_map() if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()

    def progress(self, title: str, total: int) -> Progress:
        return Progress(QProgressDialog(title, "Cancel", 0, total, self.parent))

    def ask_reassign(self, names, unnamed_ids) -> tuple[int, int] | None:
        dialog = ReassignDialog(names, unnamed_ids, self.parent)
        try:
            return dialog.chosen if dialog.exec() == QDialog.Accepted else None
        finally:
            dialog.deleteLater()

    def confirm_reassign(self, text: str) -> bool:
        answer = QMessageBox.question(self.parent, "Reassign a class in this queue", text,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes

    def confirm_queue_accept(self, text: str) -> bool:
        answer = QMessageBox.question(self.parent, "Accept missing boxes in this queue", text,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes
