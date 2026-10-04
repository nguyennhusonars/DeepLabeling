"""The main window: layout A (docs/design/2026-10-04-app-foundation.md#window).

The state bar spans the top; the queue is docked left and the inspector right; the
notice strip sits above the canvas. Everything shown comes from the Session.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget

from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .canvas import Canvas
from .inspector import Inspector
from .keymap import HelpDialog, build_actions
from .notices import NoticeStrip
from .queue_panel import QueuePanel
from .session import Session
from .settings_ui import RECENT, SHOW_CAPTIONS, SHOW_LABELS, WINDOW_GEOMETRY, WINDOW_STATE, bind_toggle
from .state_bar import StateBar

MIN_SIZE = (1024, 640)


class MainWindow(QMainWindow):
    def __init__(self, session: Session, prompter, parent=None):
        super().__init__(parent)
        self.session, self.prompter = session, prompter
        self.setWindowTitle("DeepLabeling")
        self.setMinimumSize(*MIN_SIZE)
        self.resize(1440, 900)
        self.state_bar = StateBar(session)
        self.setMenuWidget(self.state_bar)          # spans the window, above the docks
        self.notices = NoticeStrip()
        self.canvas = Canvas()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.notices)
        layout.addWidget(self.canvas, 1)
        self.setCentralWidget(central)
        self.queue_panel = QueuePanel(session)
        self.queue_dock = self._dock("Queue", "queue", self.queue_panel, Qt.LeftDockWidgetArea)
        self.inspector = Inspector(session)
        self.inspector_dock = self._dock("Inspector", "inspector", self.inspector, Qt.RightDockWidgetArea)
        self.resizeDocks([self.queue_dock, self.inspector_dock], [280, 280], Qt.Horizontal)
        self.status_text = QLabel()
        self.statusBar().addWidget(self.status_text, 1)
        self._shown: Path | None = None
        self._written: float | None = None
        self._help: HelpDialog | None = None
        self.actions = build_actions(self, {
            "next": lambda: session.move(1),
            "previous": lambda: session.move(-1),
            "done_next": session.done_and_next,
            "toggle_reviewed": session.toggle_reviewed,
            "mark_negative": session.mark_negative,
            "undo": session.undo,
            "redo": session.redo,
            "fit": self.canvas.fit,
            "zoom_in": lambda: self.canvas.zoom_by(1.25),
            "zoom_out": lambda: self.canvas.zoom_by(0.8),
            "go_to": self.go_to,
            "help": self.show_help,
        })
        layers = self.state_bar.layers.menu()
        for key, setting in (("toggle_labels", SHOW_LABELS), ("toggle_captions", SHOW_CAPTIONS)):
            bind_toggle(self.actions[key], session.settings, setting, self._layers_changed)
            layers.addAction(self.actions[key])
        self._layers_changed()
        self.state_bar.dataset.menu().aboutToShow.connect(self._fill_dataset_menu)
        self.state_bar.queue.clicked.connect(self.edit_queue)
        session.cursorChanged.connect(self.show_current)
        session.opened.connect(self.show_current)
        session.closed.connect(self._closed)
        session.images.ready.connect(self._image_event)
        session.images.failed.connect(lambda path, why: self._image_event(path))
        session.labelsChanged.connect(self._labels_changed)
        session.historyChanged.connect(self._history_changed)
        session.reviewChanged.connect(self._update_status)
        session.notice.connect(lambda level, text, image: self.notices.add(level, text, image))
        session.standing.connect(lambda key, text: self.notices.add("warning", text, key=key))
        session.status.connect(lambda text: self.statusBar().showMessage(text, 4000))
        self._restore_layout()
        self.show_current()

    def _dock(self, title: str, name: str, widget: QWidget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)                    # saveState needs a name per dock
        dock.setWidget(widget)
        widget.setMinimumWidth(160)
        self.addDockWidget(area, dock)
        return dock

    # -- what is shown ---------------------------------------------------------------

    def show_current(self) -> None:
        session, item = self.session, self.session.current()
        if session.workspace is None:
            self._shown = None
            self.canvas.set_image(None, "No dataset is open: click the dataset chip to open one.")
        elif item is None:
            self._shown = None
            building = session.queue is not None and not session.queue.complete
            self.canvas.set_image(None, "Building the queue…" if building else "No images in this queue.")
        else:
            path = item.entry.path
            image, why = session.images.get(path), session.images.error(path)
            if why is not None:
                self._shown = None
                self.canvas.set_image(None, f"Cannot decode {item.key}: {why}")
                self.notices.add("error", f"{item.key}: the image cannot be decoded ({why}); "
                                 "its labels are not edited", image=path, key=f"decode:{item.key}")
            elif image is None:
                self._shown = None
                self.canvas.set_image(None, "Loading…")
            else:
                if self._shown != path:
                    self.canvas.set_image(image)
                    self._shown = path
                self._show_boxes()
        self._update_status()

    def _show_boxes(self) -> None:
        session, item = self.session, self.session.current()
        if item is None or self.canvas.image_size is None:
            return
        ws = session.workspace
        labels = session.labels(item.entry)
        highlight = session.queue.source.highlight(labels, ws.dataset)
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
                                        ws.root_settings.get(CLASS_COLORS), highlight))

    def _image_event(self, path) -> None:
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self.show_current()

    def _labels_changed(self, images) -> None:
        self.notices.clear_image(images)
        item = self.session.current()
        if item is not None and item.entry.path in set(images):
            self._show_boxes()
        self._update_status()

    def _history_changed(self) -> None:
        self._written = time.time()
        self._update_status()

    def _closed(self) -> None:
        self.notices.clear()
        self.show_current()

    def _layers_changed(self, _=None) -> None:
        self.canvas.set_layers(labels=self.actions["toggle_labels"].isChecked(),
                               captions=self.actions["toggle_captions"].isChecked())
        self.session.saver.schedule()
        self.state_bar.refresh()

    def _update_status(self) -> None:
        session, item = self.session, self.session.current()
        if item is None or session.workspace is None:
            self.status_text.setText("")
            return
        parts = [item.key]
        if self.canvas.image_size is not None and self._shown == item.entry.path:
            parts.append("{} × {}".format(*self.canvas.image_size))
        parts.append(f"item {session.queue.position() + 1:,} / {len(session.queue):,}")
        if self._written is not None:
            parts.append("written " + time.strftime("%H:%M:%S", time.localtime(self._written)))
        parts.append(f"↶ {session.workspace.history.depth}")
        self.status_text.setText(" · ".join(parts))

    # -- what the chips and keys do --------------------------------------------------

    def _fill_dataset_menu(self) -> None:
        menu = self.state_bar.dataset.menu()
        menu.clear()
        menu.addAction("Open dataset yaml…", self.open_yaml)
        menu.addAction("Open image folder…", self.open_folder)
        recent = self.session.settings.get(RECENT)
        if recent:
            menu.addSeparator()
        for entry in recent:
            name = Path(entry["source"])
            menu.addAction(f"{name.name} — {name.parent}",
                           lambda e=entry: self.session.open(e["source"], e["labels"]))

    def open_yaml(self) -> None:
        path = self.prompter.choose_yaml()
        if path:
            self.session.open(path)

    def open_folder(self) -> None:
        folder = self.prompter.choose_folder("Image folder")
        if not folder:
            return
        labels = None
        if "images" not in Path(folder).resolve().parts:
            labels = self.prompter.choose_folder("Label folder for these images")
            if not labels:
                return
        self.session.open(folder, labels)

    def edit_queue(self) -> None:
        if self.session.queue is None:
            return
        current = self.session.queue.source
        chosen = self.prompter.edit_queue(self.session.workspace.dataset, current)
        if chosen is not None and chosen != current:
            self.session.set_queue(chosen)

    def go_to(self) -> None:
        text = self.prompter.ask_text("Go to", "Item number, or part of its path:")
        if text:
            self.session.go_to_text(text)

    def show_help(self) -> None:
        self._help = HelpDialog(self)
        self._help.show()

    # -- the window's own state ----------------------------------------------------------

    def _restore_layout(self) -> None:
        settings = self.session.settings
        geometry, state = settings.get(WINDOW_GEOMETRY), settings.get(WINDOW_STATE)
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
        if state:
            self.restoreState(QByteArray.fromBase64(state.encode()))

    def closeEvent(self, event) -> None:
        settings = self.session.settings
        settings.set(WINDOW_GEOMETRY, bytes(self.saveGeometry().toBase64()).decode())
        settings.set(WINDOW_STATE, bytes(self.saveState().toBase64()).decode())
        self.session.close()
        self.session.saver.flush()
        super().closeEvent(event)
