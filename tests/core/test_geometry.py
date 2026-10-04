import math

import pytest

from deeplabeling.core.geometry import corners, iou, iou_xyxy, norm_to_px, px_to_norm


def test_corners():
    assert corners((0.5, 0.5, 0.2, 0.4)) == pytest.approx((0.4, 0.3, 0.6, 0.7))


def test_identical_boxes_have_iou_exactly_one():
    assert iou((0.5, 0.5, 0.2, 0.2), (0.5, 0.5, 0.2, 0.2)) == 1.0


def test_disjoint_and_touching_boxes_have_iou_zero():
    assert iou((0.2, 0.2, 0.1, 0.1), (0.8, 0.8, 0.1, 0.1)) == 0.0
    assert iou_xyxy((0, 0, 1, 1), (1, 0, 2, 1)) == 0.0


def test_a_known_overlap():
    assert iou_xyxy((0, 0, 2, 1), (1, 0, 3, 1)) == pytest.approx(1 / 3)


def test_degenerate_boxes_have_iou_zero():
    assert iou_xyxy((0, 0, 0, 0), (0, 0, 0, 0)) == 0.0


def test_iou_does_not_depend_on_the_image_size():
    a, b = (0.4, 0.5, 0.3, 0.2), (0.5, 0.45, 0.2, 0.3)
    assert iou(a, b) == pytest.approx(iou_xyxy(norm_to_px(a, 1920, 1080), norm_to_px(b, 1920, 1080)))


def test_pixels_and_back():
    box = (0.31, 0.47, 0.123, 0.456)
    assert px_to_norm(*norm_to_px(box, 640, 480), 640, 480) == pytest.approx(box)


def test_corners_in_any_order():
    assert px_to_norm(60, 40, 20, 10, 100, 100) == pytest.approx((0.4, 0.25, 0.4, 0.3))


def test_a_box_partly_outside_is_clamped_to_the_image():
    cx, cy, w, h = px_to_norm(-10, -10, 30, 30, 100, 100)
    assert (cx, cy, w, h) == pytest.approx((0.15, 0.15, 0.3, 0.3))
    assert cx - w / 2 >= 0 and cy - h / 2 >= 0


def test_a_zero_size_image_is_an_error():
    with pytest.raises(ValueError):
        px_to_norm(0, 0, 1, 1, 0, 10)


def test_no_nan_from_a_box_entirely_outside():
    assert not any(math.isnan(v) for v in px_to_norm(200, 200, 300, 300, 100, 100))
