import pytest

from deeplabeling.core.overlap import STACKED, iou_in_range, pair_counts, stack_counts

A = (0.5, 0.5, 0.2, 0.2)
FAR = (0.1, 0.1, 0.05, 0.05)


def test_identical_boxes_are_counted():
    assert stack_counts([(0, A), (0, A), (1, FAR)], *STACKED) == {0: 2, 1: 2}


def test_three_identical_boxes_each_read_three():
    assert stack_counts([(0, A), (0, A), (2, A)], *STACKED) == {0: 3, 1: 3, 2: 3}


def test_the_count_is_per_box_in_a_chain():
    a, b, c = (0.30, 0.5, 0.2, 0.2), (0.40, 0.5, 0.2, 0.2), (0.55, 0.5, 0.2, 0.2)
    assert stack_counts([(0, a), (0, b), (0, c)], "any", 0.1, 1.0) == {0: 2, 1: 3, 2: 2}


@pytest.mark.parametrize("scope, expected", [("any", True), ("same", False), ("different", True)])
def test_scope_for_a_different_class_pair(scope, expected):
    assert pair_counts(scope, 0, 1) is expected


@pytest.mark.parametrize("scope, expected", [("any", True), ("same", True), ("different", False)])
def test_scope_for_a_same_class_pair(scope, expected):
    assert pair_counts(scope, 2, 2) is expected


def test_a_pair_that_does_not_touch_never_counts_even_from_zero():
    assert stack_counts([(0, A), (0, FAR)], "any", 0.0, 1.0) == {}


def test_a_max_below_one_hides_exact_duplicates():
    assert stack_counts([(0, A), (0, A)], "any", 0.5, 0.9) == {}


def test_the_range_is_inclusive():
    assert iou_in_range(1.0, 0.99, 1.0) and iou_in_range(0.99, 0.99, 1.0)


def test_an_unknown_scope_is_an_error():
    with pytest.raises(ValueError):
        pair_counts("both", 0, 0)


def test_boxes_count_as_stacked_from_an_iou_of_0_9():
    near, apart = (0.5083, 0.5, 0.2, 0.2), (0.5162, 0.5, 0.2, 0.2)     # IoU 0.92 and 0.85 with A
    assert stack_counts([(0, A), (1, near)], *STACKED) == {0: 2, 1: 2}
    assert stack_counts([(0, A), (1, apart)], *STACKED) == {}
