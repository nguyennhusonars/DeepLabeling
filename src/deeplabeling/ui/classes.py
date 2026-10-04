"""Class colours and hotkeys, keyed by class name so every yaml of a root shares them
(docs/design/2026-10-04-app-foundation.md#dataset)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..core.dataset import Dataset

#: Distinct colours, handed out in order; no greys, which mean "unknown class".
PALETTE = (
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6",
    "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324", "#fffac8", "#800000",
    "#aaffc3", "#808000", "#ffd8b1", "#000075", "#ffe119", "#a9a9f5",
)
#: A class id the dataset's names do not cover.
UNKNOWN = "#9e9e9e"
#: The hotkeys there are; a class past the tenth is chosen with the class picker.
DEFAULT_HOTKEYS = "1234567890"


@dataclass(frozen=True)
class ClassInfo:
    cls_id: int
    name: str
    color: str
    hotkey: str     #: "" when the class has none


def assign_classes(names: Sequence[str], colors: dict[str, str],
                   hotkeys: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """A colour and a hotkey for every class name, keeping what is stored by name.

    The yamls of one root differ in class ids but share names (car is id 3 in one and 5
    in another), so a class keeps its colour and key by name. A name seen for the first
    time takes the first colour and the first digit no other class of THIS list uses;
    when two names of one list hold the same stored key, the first keeps it and the
    other is given a free one. Returns new maps; the arguments are not changed.
    """
    colors, hotkeys = dict(colors), dict(hotkeys)
    used = {colors[n] for n in names if n in colors}
    free_colors = [c for c in PALETTE if c not in used]
    for i, name in enumerate(names):
        if name not in colors:
            colors[name] = free_colors.pop(0) if free_colors else PALETTE[i % len(PALETTE)]
    taken: set[str] = set()
    waiting = []
    for name in names:
        key = hotkeys.get(name, "")
        if key and key not in taken:
            taken.add(key)
        else:
            waiting.append(name)
    free_keys = [k for k in DEFAULT_HOTKEYS if k not in taken]
    for name in waiting:
        hotkeys[name] = free_keys.pop(0) if free_keys else ""
    return colors, hotkeys


def class_color(cls_id: int, name: str, overrides: dict[str, str]) -> str:
    """The colour of a class: the one stored for its name, else the palette's for its id."""
    return overrides.get(name) or PALETTE[cls_id % len(PALETTE)]


def class_infos(dataset: Dataset, colors: dict[str, str], hotkeys: dict[str, str]) -> list[ClassInfo]:
    """Every class of the dataset, with the colour and hotkey stored for its name. A
    dataset without names (a folder with no classes.txt) shows bare ids, so it offers
    the ids 0-9 on the digit keys."""
    if not dataset.names:
        return [ClassInfo(i, str(i), class_color(i, str(i), colors), key)
                for i, key in enumerate(DEFAULT_HOTKEYS)]
    return [ClassInfo(cls_id, name, class_color(cls_id, name, colors), hotkeys.get(name, ""))
            for cls_id, name in enumerate(dataset.names)]


def class_with_hotkey(infos: Sequence[ClassInfo], key: str) -> ClassInfo | None:
    return next((info for info in infos if info.hotkey == key), None)


def text_color(background: str) -> str:
    """Black or white, whichever reads better on `background` (#rrggbb)."""
    r, g, b = (int(background[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#ffffff"
