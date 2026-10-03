"""Validation of the ranges typed into the filter panel and the scan dialog.

Every threshold involved is a fraction -- a confidence or an IoU -- and most of
them are now ranges. The rules live in one place so the panel and the dialog
cannot disagree about what a valid range is.
"""

from __future__ import annotations

import math

import pytest

from yolo_labeling.core import ranges as R


@pytest.mark.parametrize("text,expected", [
    ("0.4", 0.4), (" 0.40 ", 0.4), ("1", 1.0), ("0", 0.0), (".5", 0.5),
])
def test_parse_unit_reads_numbers(text, expected):
    assert R.parse_unit(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "0.4.1", None, "nan", "inf", "-inf"])
def test_parse_unit_refuses_non_numbers(text):
    assert R.parse_unit(text) is None


def test_parse_unit_never_clamps():
    """Clamping is a policy for the caller; silently turning 7 into 1 is how a
    typo becomes a query nobody asked for."""
    assert R.parse_unit("7") == 7.0
    assert R.parse_unit("-0.2") == -0.2


def test_a_valid_range_has_no_error():
    assert R.range_error(0.4, 1.0, "Confidence") is None
    assert R.range_error(0.5, 0.5, "Confidence") is None, "a point range is allowed"


def test_a_reversed_range_is_named_not_swapped():
    msg = R.range_error(0.8, 0.5, "Overlap IoU")
    assert msg and "Overlap IoU" in msg and "0.8" in msg and "0.5" in msg


@pytest.mark.parametrize("lo,hi", [(-0.1, 0.5), (0.2, 1.5)])
def test_out_of_bounds_ends_are_refused(lo, hi):
    assert R.range_error(lo, hi, "IoU")


def test_a_missing_end_is_refused():
    assert R.range_error(None, 0.5, "IoU")
    assert R.range_error(0.5, None, "IoU")


def test_bounds_can_be_tightened():
    """The confidence floor cannot go below the cache floor -- nothing exists there."""
    assert R.range_error(0.05, 1.0, "Confidence", lo_min=0.10)
    assert R.range_error(0.10, 1.0, "Confidence", lo_min=0.10) is None


@pytest.mark.parametrize("value,expected", [
    (0.7, 0.7), ("0.7", 0.7), (-1, 0.0), (9, 1.0),
    ("junk", 0.5), (None, 0.5), (float("nan"), 0.5),
])
def test_coerce_unit_is_forgiving_for_config_files(value, expected):
    """A hand-edited or corrupt config must load, not crash or propagate junk."""
    assert R.coerce_unit(value, 0.5) == pytest.approx(expected)


def test_coerce_unit_honours_custom_bounds():
    assert R.coerce_unit(0.01, 0.25, lo=0.10) == pytest.approx(0.10)
    assert not math.isnan(R.coerce_unit(float("nan"), 0.25))
