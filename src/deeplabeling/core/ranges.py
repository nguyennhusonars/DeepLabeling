"""Ranges typed by a person: inclusive at both ends, never swapped and never clamped
(`legacy/yolo_labeling/core/ranges.py::range_error`). People edit one end at a time, so a
reversed range is a normal state while typing; it is refused, by name, when used."""

from __future__ import annotations


def range_error(lo, hi, name: str, *, lo_min: float = 0.0, hi_max: float | None = 1.0,
                open_ends: bool = False) -> str | None:
    """Why [lo, hi] is not a usable range, or None. An end may be None (open) only with
    `open_ends`; `hi_max` None means no upper bound."""
    if not open_ends and (lo is None or hi is None):
        return f"{name}: both ends must be numbers"
    if lo is not None and lo < lo_min:
        return f"{name}: the lower end cannot be below {lo_min:g}"
    if hi is not None and hi_max is not None and hi > hi_max:
        return f"{name}: the upper end cannot be above {hi_max:g}"
    if lo is not None and hi is not None and lo > hi:
        return f"{name}: {lo:g} is above {hi:g}: put the lower end first"
    return None
