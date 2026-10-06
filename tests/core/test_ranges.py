"""Typed ranges: never swapped, never clamped; refused by name
(`legacy/yolo_labeling/core/ranges.py::range_error`)."""

from deeplabeling.core.ranges import range_error


def test_a_usable_range_has_no_error_and_a_point_is_a_range():
    assert range_error(0.5, 1.0, "IoU") is None and range_error(0.7, 0.7, "IoU") is None


def test_a_reversed_range_is_refused_by_name_not_swapped():
    assert range_error(0.9, 0.5, "IoU") == "IoU: 0.9 is above 0.5: put the lower end first"


def test_ends_outside_their_bounds_are_refused_not_clamped():
    assert range_error(-0.1, 0.5, "IoU") == "IoU: the lower end cannot be below 0"
    assert range_error(0.5, 1.2, "confidence") == "confidence: the upper end cannot be above 1"


def test_open_ends_only_where_allowed():
    assert range_error(None, 0.5, "IoU") == "IoU: both ends must be numbers"
    assert range_error(None, 30, "width", hi_max=None, open_ends=True) is None
    assert range_error(10, None, "width", hi_max=100, open_ends=True) is None
    assert range_error(10, 120, "width", hi_max=100, open_ends=True) == "width: the upper end cannot be above 100"
