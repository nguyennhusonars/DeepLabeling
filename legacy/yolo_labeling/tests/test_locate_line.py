"""`locate_line` — the guard that stops a review action touching the wrong box.

The review window records a line NUMBER, but line numbers move: deleting a
sibling shifts everything below it, and a main-window save renumbers around any
line it could not parse. Acting on a stale number rewrites a different object
and reports success, so this decides between "act", "relocate" and "refuse".
"""

from __future__ import annotations

import pytest

from yolo_labeling.core.labelio import (
    LOCATE_TOL,
    locate_line,
    parse_label_text,
)

# Three distinct boxes, plus two later duplicates of the first.
TEXT = (
    "0 0.50 0.50 0.20 0.20\n"      # 0
    "1 0.10 0.10 0.05 0.05\n"      # 1
    "2 0.90 0.90 0.08 0.08\n"      # 2
)
DUPES = TEXT + "0 0.50 0.50 0.20 0.20\n"   # line 3 duplicates line 0


def lines(text=TEXT):
    return parse_label_text(text)


# -- the hint is right (the common case) ----------------------------------


def test_a_correct_hint_is_used_as_is():
    assert locate_line(lines(), 1, (0.10, 0.10, 0.05, 0.05), 1) == 1


def test_a_hint_is_checked_before_searching():
    """With duplicates present, the recorded line must win -- otherwise a
    correct hint could be overruled by an earlier identical box."""
    assert locate_line(lines(DUPES), 0, (0.50, 0.50, 0.20, 0.20), 3) == 3


# -- relocation ------------------------------------------------------------


def test_a_shifted_line_is_relocated():
    """A sibling above was deleted, so everything moved up by one."""
    assert locate_line(lines(), 2, (0.90, 0.90, 0.08, 0.08), 99) == 2


def test_relocation_requires_the_class_to_match_too():
    """Geometry alone would relocate onto a duplicate box of another class --
    the 'one object labelled twice' error the overlap filter looks for."""
    text = "0 0.5 0.5 0.2 0.2\n7 0.5 0.5 0.2 0.2\n"
    assert locate_line(parse_label_text(text), 7, (0.5, 0.5, 0.2, 0.2), 0) == 1


def test_an_ambiguous_relocation_is_refused():
    """Two identical candidates and a bad hint: picking one would be a coin
    flip written straight to disk."""
    assert locate_line(lines(DUPES), 0, (0.50, 0.50, 0.20, 0.20), 99) is None


def test_a_box_that_is_gone_is_refused():
    assert locate_line(lines(), 0, (0.33, 0.33, 0.10, 0.10), 0) is None


def test_a_changed_class_on_the_hinted_line_is_refused():
    assert locate_line(lines(), 5, (0.50, 0.50, 0.20, 0.20), 0) is None


# -- tolerance -------------------------------------------------------------


def test_a_save_round_trip_still_verifies():
    """`%.6f` serialization and pixel round-tripping move coordinates a little;
    the guard must not reject a box nobody touched."""
    nudged = tuple(v + LOCATE_TOL * 0.4 for v in (0.50, 0.50, 0.20, 0.20))
    assert locate_line(lines(), 0, nudged, 0) == 0


def test_a_real_move_is_refused():
    moved = (0.50 + LOCATE_TOL * 20, 0.50, 0.20, 0.20)
    assert locate_line(lines(), 0, moved, 0) is None


# -- polygons --------------------------------------------------------------


def test_a_polygon_matches_on_its_extent():
    """`LabelLine.bbox` gives a polygon's axis-aligned extent."""
    poly = "3 0.10 0.10 0.20 0.10 0.20 0.20 0.10 0.20\n"
    assert locate_line(parse_label_text(poly), 3, (0.15, 0.15, 0.10, 0.10), 0) == 0


def test_the_scans_polygon_misparse_is_refused_rather_than_written():
    """The scan reads `parts[1:5]` with no arity check, so a polygon's first
    two POINTS become its 'box'. That entry must not write anything."""
    poly = "3 0.10 0.10 0.20 0.10 0.20 0.20 0.10 0.20\n"
    misparsed = (0.10, 0.10, 0.20, 0.10)        # what the scan would record
    assert locate_line(parse_label_text(poly), 3, misparsed, 0) is None


# -- degenerate inputs -----------------------------------------------------


@pytest.mark.parametrize("hint", [None, -1, 99])
def test_a_useless_hint_still_finds_a_unique_box(hint):
    assert locate_line(lines(), 2, (0.90, 0.90, 0.08, 0.08), hint) == 2


def test_no_bbox_falls_back_to_the_bare_hint():
    """Filter-mode entries carry no prediction context; preserve old behaviour."""
    assert locate_line(lines(), None, None, 1) == 1
    assert locate_line(lines(), None, None, 99) is None


def test_an_empty_file_matches_nothing():
    assert locate_line([], 0, (0.5, 0.5, 0.2, 0.2), 0) is None


def test_unparsed_lines_are_never_matched():
    text = "\nabc 0.5 0.5 0.2 0.2\n0 0.50 0.50 0.20 0.20\n"
    assert locate_line(parse_label_text(text), 0, (0.50, 0.50, 0.20, 0.20), 0) == 2
