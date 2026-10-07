"""The main window: layout A (docs/design/2026-10-04-app-foundation.md#window).

The state bar spans the top; the queue is docked left and the inspector right; the
notice strip sits above the canvas. Everything shown comes from the Session.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget

from ..core.assist import shown_predictions
from ..core.queue import Seen
from ..core.workspace import CLASS_COLORS
from . import grid_actions
from .boxes import box_views, prediction_views
from .canvas import Canvas
from .classes import DEFAULT_HOTKEYS, class_with_hotkey
from .editing import Editing
from .findview import spotlight
from .inspector import Inspector
from .keymap import HelpDialog, build_actions
from .model import RECENT_MODELS
from .notices import NoticeStrip
from .queue_accept import accept_queue
from .queue_panel import QueuePanel
from .reassign import reassign_queue
from .session import Session
from .settings_ui import (QUEUE_GRID_WIDTH, QUEUE_LIST_WIDTH, RECENT, SHOW_CAPTIONS, SHOW_CROSSHAIR, SHOW_GRID,
                          SHOW_PREDICTIONS,
                          SHOW_LABELS, WINDOW_GEOMETRY, WINDOW_STATE, bind_toggle)
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
        self.editing = Editing(session, self.canvas, prompter, self)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.notices)
        layout.addWidget(self.canvas, 1)
        self.setCentralWidget(central)
        self.queue_panel = QueuePanel(session)
        self.queue_dock = self._dock("Queue", "queue", self.queue_panel, Qt.LeftDockWidgetArea)
        self.inspector = Inspector(session, self.editing)
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
            "down": lambda: session.move(self.queue_panel.columns()),
            "up": lambda: session.move(-self.queue_panel.columns()),
            "mark_page": self.queue_panel.mark_page,
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
            **{f"class_{key}": self._either(lambda items, k=key: self._tiles_class(items, k),
                                            lambda k=key: self.editing.class_key(k)) for key in DEFAULT_HOTKEYS},
            "pick_class": self._either(self._tiles_pick_class, self.editing.pick_class),
            "delete": self._either(lambda items: grid_actions.delete(session, items), self.editing.delete),
            "select_next": lambda: self.editing.select_step(1),
            "select_previous": lambda: self.editing.select_step(-1),
            "select_all": self.editing.select_all,
            "escape": self.editing.escape,
            "copy": self.editing.copy,
            "paste": self.editing.paste,
            "accept_missing": self.editing.accept_missing,
            "take_model_class": self._either(lambda items: grid_actions.take_model_class(session, items),
                                             self.editing.take_model_class),
            "take_model_box": self._either(lambda items: grid_actions.take_model_box(session, items),
                                           self.editing.take_model_box),
            "dismiss": self._either(lambda items: grid_actions.dismiss(session, items), session.dismiss_current),
        })
        layers = self.state_bar.layers.menu()
        for key, setting in (("toggle_labels", SHOW_LABELS), ("toggle_captions", SHOW_CAPTIONS),
                             ("toggle_predictions", SHOW_PREDICTIONS), ("toggle_crosshair", SHOW_CROSSHAIR)):
            bind_toggle(self.actions[key], session.settings, setting, self._layers_changed)
            layers.addAction(self.actions[key])
        bind_toggle(self.actions["toggle_grid"], session.settings, SHOW_GRID, self._grid_changed)
        self.queue_panel.grid_button.setDefaultAction(self.actions["toggle_grid"])
        # Working on the full frame lets the selected tiles go: a key then acts on what it shows.
        for signal in (self.canvas.picked, self.canvas.drawn, self.canvas.moved, self.canvas.resized,
                       self.canvas.predictionPicked, self.inspector.boxes.itemClicked):
            signal.connect(lambda *_: self.queue_panel.keep_only_current())
        self.panels_menu = layers.addMenu("Panels")     # a closed dock comes back from here
        self.panels_menu.addAction(self.queue_dock.toggleViewAction())
        self.panels_menu.addAction(self.inspector_dock.toggleViewAction())
        self._layers_changed()
        self.state_bar.dataset.menu().aboutToShow.connect(self._fill_dataset_menu)
        self.state_bar.model.menu().aboutToShow.connect(self._fill_model_menu)
        self.state_bar.queue.clicked.connect(self.edit_queue)
        self.state_bar.queue.menu().aboutToShow.connect(self._fill_queue_menu)
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
        session.model.changed.connect(self._predictions_changed)
        session.model.changed.connect(self._queue_state_changed)
        session.queueDone.connect(self._queue_state_changed)
        session.model.ready.connect(self._image_predicted)
        self.canvas.predictionPicked.connect(self.editing.accept_prediction)
        self._restore_layout()
        self._show_grid(self.actions["toggle_grid"].isChecked())
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
            queue = session.queue
            if queue is not None and queue.waiting:
                message = ("Waiting for the model…" if session.model.state == "loading"
                           else "This queue needs a model: load one.")
            elif queue is not None and not queue.complete:
                message = "Building the queue…"
            else:
                message = "No images in this queue."
            self.canvas.set_image(None, message)
        else:
            path = item.entry.path
            image, why = session.images.get(path), session.images.error(path)
            if why is not None:
                self._shown = None
                self.canvas.set_image(None, f"Cannot decode {item.entry.rel}: {why}")
                self.notices.add("error", f"{item.entry.rel}: the image cannot be decoded ({why}); "
                                 "its labels are not edited", image=path, key=f"decode:{item.entry.rel}")
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
        highlight = session.queue.source.highlight(labels, ws.dataset, self._seen(item))
        self.editing.show(labels)
        lit = None if item.finding is None else spotlight(
            item.finding, ws.dataset, self.canvas.image_size, ws.root_settings.get(CLASS_COLORS), session.model.names)
        self.canvas.set_spotlight(*(lit or (None,)), redraw=False)        # set_boxes draws it
        self.canvas.set_boxes(box_views(labels, ws.dataset, self.canvas.image_size,
                                        ws.root_settings.get(CLASS_COLORS), highlight),
                              selected=self.editing.selection.indices(labels),
                              predictions=self._prediction_views(item))

    def _seen(self, item) -> Seen:
        """What the queue's conditions highlight from besides the labels."""
        model = self.session.model
        return Seen(size=self.canvas.image_size, predictions=model.predictions(item.entry),
                    class_map=model.class_map)

    def _prediction_views(self, item):
        """The predictions for the item on screen, as the canvas draws them; Editing keeps
        the same list, so what is accepted is what is drawn. Those the queue matched are
        emphasised, and drawn even below the display threshold: they are what it found."""
        session, ws, model = self.session, self.session.workspace, self.session.model
        shown, seen = model.shown(item.entry), self._seen(item)
        marked: list = []
        if session.queue is not None and seen.predictions is not None:
            indices = session.queue.source.highlight_predictions(session.labels(item.entry), ws.dataset, seen)
            marked = [seen.predictions[k] for k in sorted(indices)]
        if marked:
            shown = list(shown or [])
            drawn = [s.pred for s in shown]
            extras = [p for p in marked if p not in drawn]
            if extras:
                # Judged as everything the canvas draws is: missing only if no label covers it
                # and it speaks for its place, so A never stacks it on a label.
                judged = {s.pred: s for s in shown_predictions(drawn + extras, session.labels(item.entry),
                                                                model.class_map, ws.dataset, 0.0)}
                shown += [judged[p] for p in extras]
        emphasised = frozenset(i for i, s in enumerate(shown or []) if s.pred in marked)
        self.editing.show_predictions(item.entry.path, shown)
        return prediction_views(shown or [], ws.dataset, self.canvas.image_size,
                                ws.root_settings.get(CLASS_COLORS), model.names, emphasised)

    def _predictions_changed(self) -> None:
        """The model, its threshold or its class map changed: redraw the predictions alone."""
        item = self.session.current()
        if item is not None and self.canvas.image_size is not None and self._shown == item.entry.path:
            self.canvas.set_predictions(self._prediction_views(item))
        self._update_status()

    def _queue_state_changed(self) -> None:
        """With nothing on screen, the canvas says why: waiting, building, or empty."""
        if self.session.current() is None:
            self.show_current()

    def _image_predicted(self, path) -> None:
        item = self.session.current()
        if item is not None and item.entry.path == path:
            self._predictions_changed()

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
        labels = self.actions["toggle_labels"].isChecked()
        if not labels:
            self.editing.selection.clear()          # hidden boxes are not acted on
        self.canvas.set_layers(labels=labels, captions=self.actions["toggle_captions"].isChecked(),
                               predictions=self.actions["toggle_predictions"].isChecked())
        self.canvas.set_crosshair(self.actions["toggle_crosshair"].isChecked())
        self.session.saver.schedule()
        self.state_bar.refresh()

    def _grid_changed(self, on: bool) -> None:
        """G: keep the width the panel had for the view it leaves, then show the other
        view at its own width."""
        self._remember_queue_width(not on)
        self._show_grid(on)
        self.session.saver.schedule()

    def _show_grid(self, on: bool) -> None:
        self.queue_panel.set_grid(on)
        self.actions["mark_page"].setEnabled(on)
        width = self.session.settings.get(QUEUE_GRID_WIDTH if on else QUEUE_LIST_WIDTH)
        self.resizeDocks([self.queue_dock], [width], Qt.Horizontal)
        if self.isVisible():                        # now, so a second G at once reads this width;
            self.layout().activate()                # before the first show, the show lays it out

    def _remember_queue_width(self, grid: bool) -> None:
        """Keep the panel's width for a view -- only while the panel is beside the canvas,
        where its width is what the user set; along the top or bottom it is the window's."""
        dock = self.queue_dock
        beside = self.dockWidgetArea(dock) in (Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea)
        if dock.isVisible() and not dock.isFloating() and beside:
            self.session.settings.set(QUEUE_GRID_WIDTH if grid else QUEUE_LIST_WIDTH, dock.width())

    def _update_status(self) -> None:
        session, item = self.session, self.session.current()
        if item is None or session.workspace is None:
            self.status_text.setText("")
            return
        parts = [item.entry.rel]
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

    def _fill_model_menu(self) -> None:
        menu, model, ws = self.state_bar.model.menu(), self.session.model, self.session.workspace
        menu.clear()
        menu.addAction("Load a model…", self.load_model)
        recent = self.session.settings.get(RECENT_MODELS)
        if recent:
            menu.addSeparator()
        for path in map(Path, recent):
            menu.addAction(f"{path.name} — {path.parent}", lambda p=path: model.load(p))
        menu.addSeparator()
        menu.addAction("Threshold…", self.ask_threshold).setEnabled(ws is not None)
        menu.addAction("Class map…", self.edit_class_map).setEnabled(ws is not None and model.state == "ready")
        menu.addSeparator()
        queue = self.session.queue
        whole = model.state == "ready" and queue is not None and queue.complete
        if model.passing:
            menu.addAction("Cancel inferring", model.cancel_pass)
        else:
            menu.addAction("Infer this queue", model.infer_queue).setEnabled(whole)
        menu.addAction("Accept missing boxes in this queue…", self.accept_queue).setEnabled(whole)

    def accept_queue(self) -> None:
        accept_queue(self.session)

    def _fill_queue_menu(self) -> None:
        menu, queue = self.state_bar.queue.menu(), self.session.queue
        menu.clear()
        menu.addAction("Edit queue…", self.edit_queue).setEnabled(queue is not None)
        built = queue is not None and queue.complete
        menu.addAction("Reassign a class in this queue…", self.reassign_queue).setEnabled(built)

    def reassign_queue(self) -> None:
        reassign_queue(self.session)

    def load_model(self) -> None:
        path = self.prompter.choose_weights()
        if path:
            self.session.model.load(path)

    def ask_threshold(self) -> None:
        value = self.prompter.ask_threshold(self.session.model.conf)
        if value is not None:
            self.session.model.set_conf(value)

    def edit_class_map(self) -> None:
        model = self.session.model
        cmap = self.prompter.edit_class_map(model.class_map, self.session.workspace.dataset.names)
        if cmap is not None:
            model.set_class_map(cmap)

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

    def _either(self, on_tiles, otherwise):
        """A key's action: on the tiles selected in a grid of crops
        (docs/design/2026-10-06-find-bad.md#the-grid), unless only the current one is; otherwise
        its own."""
        def run():
            items, current = self.queue_panel.selected_findings(), self.session.current()
            # One tile that is not the current item -- the current one Ctrl-clicked away -- is
            # still the tiles' to act on: the frame shows a finding no longer selected.
            if len(items) > 1 or (items and current is not None and items[0].key != current.key):
                on_tiles(items)
            else:
                otherwise()
        return run

    def _tiles_pick_class(self, items) -> None:
        infos = self.editing.classes()
        chosen = self.prompter.pick_class(infos) if infos else None
        if chosen is not None:
            grid_actions.set_class(self.session, items, chosen.cls_id, chosen.name)

    def _tiles_class(self, items, key: str) -> None:
        info = class_with_hotkey(self.editing.classes(), key)
        if info is None:
            self.editing.class_key(key)             # which says no class has it
        else:
            grid_actions.set_class(self.session, items, info.cls_id, info.name)

    def edit_queue(self) -> None:
        if self.session.queue is None:
            return
        current = self.session.queue.source
        chosen = self.prompter.edit_queue(self.session.workspace.dataset, current, self.session.model.conf)
        if chosen is not None:                      # the same filter again is a refresh
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
        self._remember_queue_width(self.queue_panel.grid)
        settings.set(WINDOW_GEOMETRY, bytes(self.saveGeometry().toBase64()).decode())
        settings.set(WINDOW_STATE, bytes(self.saveState().toBase64()).decode())
        self.session.close()
        self.session.model.shutdown()               # a model loaded with no dataset open, too
        self.session.saver.flush()
        super().closeEvent(event)
