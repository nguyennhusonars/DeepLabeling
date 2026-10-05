"""Entry point: `python -m deeplabeling [DATASET] [--labels LABEL_DIR]`.

Every launch path reaches Session.open (docs/design/2026-10-04-app-foundation.md#state-and-settings):
a yaml, an image folder with an optional label folder, the last dataset when no argument
is given, or the open dialog when there is no last dataset or it is gone.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.model import threads_running
from .ui.prompter import QtPrompter
from .ui.session import Session
from .ui.settings_ui import LAST_SOURCE


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="deeplabeling",
                                     description="Label and clean YOLO datasets.")
    parser.add_argument("dataset", nargs="?", help="a dataset yaml, or a folder of images")
    parser.add_argument("--labels", help="the label folder, for an image folder whose path "
                                         "has no 'images' folder in it")
    return parser.parse_args(argv)


def launch(argv: list[str], prompter=None) -> MainWindow:
    """Build the window and open what the arguments, or the last session, say."""
    args = parse_args(argv)
    prompter = prompter if prompter is not None else QtPrompter()
    session = Session(prompter)
    window = MainWindow(session, prompter)
    if isinstance(prompter, QtPrompter):
        prompter.parent = window
    if args.dataset:
        session.open(args.dataset, args.labels)
    else:
        last = session.settings.get(LAST_SOURCE)
        if last is not None and Path(last["source"]).exists():
            session.open(last["source"], last["labels"])
        else:
            QTimer.singleShot(0, window.open_yaml)
    return window


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = launch(sys.argv[1:] if argv is None else argv)
    window.show()
    code = app.exec()
    if threads_running():
        # A model thread still loading or predicting after closing waited SHUTDOWN_MS: the
        # settings are saved, and destroying the thread would abort the process.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
