"""Settings (docs/design/2026-10-04-app-foundation.md#state-and-settings).

Each setting is defined once -- key, scope, default, validator -- and its value is
read only through `Settings.get`, which falls back to the default for a missing or
invalid stored value. A widget seeded from `get` therefore shows the value the
logic uses (CLAUDE.md landmine 7). Values are JSON values.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic import write_atomic
from .state import set_aside

#: global: settings.json. root: a dataset root's dataset.json. opening: one
#: yaml's (or one folder launch's) section of that file.
SCOPES = ("global", "root", "opening")


@dataclass(frozen=True)
class Setting:
    key: str
    scope: str
    default: Any
    valid: Callable[[Any], bool]


REGISTRY: dict[str, Setting] = {}


def define(key: str, scope: str, default: Any, valid: Callable[[Any], bool]) -> Setting:
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    if key in REGISTRY:
        raise ValueError(f"setting {key!r} is defined twice")
    if not valid(default):
        raise ValueError(f"the default of {key!r} is not valid: {default!r}")
    setting = Setting(key, scope, default, valid)
    REGISTRY[key] = setting
    return setting


def is_str_or_none(v) -> bool:
    return v is None or isinstance(v, str)


def is_str_list(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def is_str_map(v) -> bool:
    return isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, str)
                                       for k, x in v.items())


class JsonFile:
    """A JSON object on disk, loaded once and saved atomically.

    A file that cannot be read is moved aside, never overwritten, and `warning`
    says so; its settings then start from their defaults.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict = {}
        self.dirty = False
        self.warning = ""
        self.writable = True
        try:
            data = json.loads(self.path.read_bytes())
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
            self.data = data
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            self.warning, self.writable = set_aside(self.path, e)

    def save(self) -> bool:
        if not self.dirty or not self.writable:
            return False
        write_atomic(self.path, json.dumps(self.data, indent=1, sort_keys=True).encode())
        self.dirty = False
        return True


class Settings:
    """One scope's values, kept in a section of a JsonFile."""

    def __init__(self, file: JsonFile, scope: str, section: tuple[str, ...] = ()):
        self.file = file
        self.scope = scope
        self.section = section

    def get(self, setting: Setting):
        self._check(setting)
        node = self._node(create=False)
        value = node.get(setting.key, setting.default) if node is not None else setting.default
        return copy.deepcopy(value if setting.valid(value) else setting.default)

    def set(self, setting: Setting, value) -> None:
        self._check(setting)
        if not setting.valid(value):
            raise ValueError(f"not a valid value for {setting.key}: {value!r}")
        node = self._node(create=True)
        if setting.key not in node or node[setting.key] != value:
            node[setting.key] = copy.deepcopy(value)
            self.file.dirty = True

    def _check(self, setting: Setting) -> None:
        if setting.scope != self.scope:
            raise ValueError(f"{setting.key} is a {setting.scope} setting, not a {self.scope} one")

    def _node(self, *, create: bool) -> dict | None:
        node = self.file.data
        for name in self.section:
            child = node.get(name)
            if not isinstance(child, dict):
                if not create:
                    return None
                child = node[name] = {}
            node = child
        return node
