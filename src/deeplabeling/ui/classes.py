"""Class colours and hotkeys, keyed by class name so every yaml of a root shares them
(docs/design/2026-10-04-app-foundation.md#dataset)."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.dataset import Dataset

#: Distinct colours for class ids, in id order; no greys, which mean "unknown class".
PALETTE = (
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6",
    "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324", "#fffac8", "#800000",
    "#aaffc3", "#808000", "#ffd8b1", "#000075", "#ffe119", "#a9a9f5",
)
#: A class id the dataset's names do not cover.
UNKNOWN = "#9e9e9e"
#: Hotkeys of the first ten classes; past the tenth, the class picker (plan 1c).
DEFAULT_HOTKEYS = "1234567890"


@dataclass(frozen=True)
class ClassInfo:
    cls_id: int
    name: str
    color: str
    hotkey: str     #: "" when the class has none


def class_color(cls_id: int, name: str, overrides: dict[str, str]) -> str:
    """The colour of a class: the user's choice for its name, else the palette's."""
    return overrides.get(name) or PALETTE[cls_id % len(PALETTE)]


def class_infos(dataset: Dataset, colors: dict[str, str], hotkeys: dict[str, str]) -> list[ClassInfo]:
    """Every class of the dataset, with the colour and hotkey in force."""
    out = []
    for cls_id, name in enumerate(dataset.names):
        default = DEFAULT_HOTKEYS[cls_id] if cls_id < len(DEFAULT_HOTKEYS) else ""
        out.append(ClassInfo(cls_id, name, class_color(cls_id, name, colors),
                             hotkeys.get(name, default)))
    return out


def text_color(background: str) -> str:
    """Black or white, whichever reads better on `background` (#rrggbb)."""
    r, g, b = (int(background[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#ffffff"
