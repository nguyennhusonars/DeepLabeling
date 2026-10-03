"""Validating the numeric ranges typed into the filter panel and the scan dialog.

Every threshold involved is a fraction in [0, 1] -- a confidence or an IoU -- and
most of them are now ranges rather than single cut-offs. The rules live here so
the Filters tab and the Find Bad Annotations dialog cannot drift apart on what
counts as a valid range.

Two deliberate refusals:

* `parse_unit` never clamps. Turning a typed 7 into 1.0 makes a typo into a query
  nobody asked for; the caller decides what to do with an out-of-range value.
* `range_error` never swaps a reversed range. People edit one end at a time, so
  `lo > hi` is a normal in-between state -- swapping it on the way past would
  scramble the edit. It is reported, by name, when the range is used.
"""

from __future__ import annotations

import math


def parse_unit(text):
    """The number in an entry's text, or None if it is not one."""
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def range_error(lo, hi, name, *, lo_min=0.0, hi_max=1.0):
    """Why `[lo, hi]` is not a usable range, or None if it is.

    Both ends are inclusive, so a point range (`lo == hi`) is valid.
    """
    if lo is None or hi is None:
        return f"{name}: both ends must be numbers."
    if lo < lo_min:
        return f"{name}: the lower end cannot be below {lo_min:g}."
    if hi > hi_max:
        return f"{name}: the upper end cannot be above {hi_max:g}."
    if lo > hi:
        return f"{name}: {lo:g} is above {hi:g} -- put the lower end first."
    return None


def coerce_unit(value, default, *, lo=0.0, hi=1.0):
    """A usable number in `[lo, hi]` from a config value, else `default`.

    For loading saved settings, where the alternative to forgiving is refusing to
    start: junk becomes the default and out-of-range values are clamped.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number):
        return default
    return min(max(number, lo), hi)
