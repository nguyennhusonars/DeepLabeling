"""The real dialogs behind the Prompter the session and window use. Tests answer the same
calls with tests/fixtures.py's FakePrompter, so no test waits on a modal loop."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from ..core.dataset import Dataset
from ..core.queue import ImageFilter
from .queue_editor import QueueEditor


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

    def edit_queue(self, dataset: Dataset, current: ImageFilter) -> ImageFilter | None:
        dialog = QueueEditor(dataset, current, self.parent)
        return dialog.filter() if dialog.exec() == QDialog.Accepted else None

    def ask_text(self, title: str, label: str) -> str | None:
        text, ok = QInputDialog.getText(self.parent, title, label)
        return text if ok else None
