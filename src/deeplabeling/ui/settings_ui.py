"""Global settings, saving, and binding widgets to settings
(docs/design/2026-10-04-app-foundation.md#state-and-settings)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction

from ..core.settings import JsonFile, Setting, Settings, define
from ..core.state import state_dir


def _is_width(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _is_source(v) -> bool:
    return (isinstance(v, dict) and isinstance(v.get("source"), str)
            and (v.get("labels") is None or isinstance(v.get("labels"), str)))


#: {"source": yaml or image folder, "labels": label folder or None}
LAST_SOURCE = define("app.last_source", "global", None, lambda v: v is None or _is_source(v))
RECENT = define("app.recent", "global", [], lambda v: isinstance(v, list) and all(map(_is_source, v)))
WINDOW_GEOMETRY = define("window.geometry", "global", "", lambda v: isinstance(v, str))
WINDOW_STATE = define("window.state", "global", "", lambda v: isinstance(v, str))
SHOW_LABELS = define("view.labels", "global", True, lambda v: isinstance(v, bool))
SHOW_CAPTIONS = define("view.captions", "global", True, lambda v: isinstance(v, bool))
SHOW_PREDICTIONS = define("view.predictions", "global", True, lambda v: isinstance(v, bool))
SHOW_CROSSHAIR = define("view.crosshair", "global", False, lambda v: isinstance(v, bool))
SHOW_GRID = define("view.queue_grid", "global", False, lambda v: isinstance(v, bool))
#: The queue panel's width in each view: the grid widens it, the list takes its own back.
QUEUE_LIST_WIDTH = define("window.queue_list_width", "global", 280, _is_width)
QUEUE_GRID_WIDTH = define("window.queue_grid_width", "global", 560, _is_width)

RECENT_MAX = 8


def global_settings() -> tuple[JsonFile, Settings]:
    file = JsonFile(state_dir() / "settings.json")
    return file, Settings(file, "global")


def remember_source(settings: Settings, source: str, labels: str | None) -> None:
    """Record an opened dataset as the last one and at the top of the recent list."""
    entry = {"source": source, "labels": labels}
    settings.set(LAST_SOURCE, entry)
    settings.set(RECENT, ([entry] + [e for e in settings.get(RECENT) if e != entry])[:RECENT_MAX])


class Saver(QObject):
    """Saves a moment after the last change (atomic writes, debounced), or at once on flush."""

    def __init__(self, save: Callable[[], None], delay_ms: int = 2000, parent=None):
        super().__init__(parent)
        self._save = save
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(save)

    @property
    def pending(self) -> bool:
        return self._timer.isActive()

    def schedule(self) -> None:
        self._timer.start()

    def flush(self) -> None:
        self._timer.stop()
        self._save()


def bind_toggle(action: QAction, settings: Settings, setting: Setting,
                changed: Callable[[bool], None]) -> None:
    """The one way a checkable control meets a setting: seeded from the value the logic
    reads, and every change written back (CLAUDE.md landmine 7)."""
    action.setCheckable(True)
    action.setChecked(settings.get(setting))

    def on_toggled(value: bool) -> None:
        settings.set(setting, bool(value))
        changed(bool(value))

    action.toggled.connect(on_toggled)
