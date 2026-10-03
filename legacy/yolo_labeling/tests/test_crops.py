"""The review crop compositor.

A crop used to be exactly the bounding box, which cannot answer the question
the review is asking. These pin the three things that changed: there is context
around the box, the box is outlined, and the model's box is visible even when
it falls outside the label.

Synthetic frames rather than the JPEG fixtures, so colour assertions are exact.
"""

from __future__ import annotations

import numpy as np
import pytest

from yolo_labeling.core.crops import (
    CONTEXT_FRAC,
    MIN_LABEL_CELL_H,
    MIN_PAD_PX,
    render_review_crop,
)

GT = (255, 0, 0)        # red, RGB
PRED = (0, 255, 0)      # green, RGB


def frame(w=200, h=200, value=30):
    return np.full((h, w, 3), value, np.uint8)


def norm(x1, y1, x2, y2, w=200, h=200):
    """Pixel xyxy -> normalised (cx, cy, bw, bh)."""
    return ((x1 + x2) / 2 / w, (y1 + y2) / 2 / h, (x2 - x1) / w, (y2 - y1) / h)


def count(buf, color):
    return int(np.all(buf == np.array(color, np.uint8), axis=2).sum())


# -- context ---------------------------------------------------------------


def test_the_crop_is_wider_than_the_box():
    """The old behaviour was a crop exactly the size of the box."""
    box = norm(90, 90, 110, 110)          # 20x20, centred
    out = render_review_crop(frame(), box, 300, 300, gt_color=GT)
    # 20px box + 25% of 20 per side = 30px of source, scaled to the cell.
    assert out is not None
    h, w = out.shape[:2]
    assert w == h == 300
    # The GT rectangle should sit inside, not on, the border.
    assert count(out[:2, :], GT) == 0, "the box is drawn at the very edge"


def test_the_margin_scales_with_the_box():
    small = render_review_crop(frame(600, 600), norm(295, 295, 305, 305, 600, 600),
                               300, 300, gt_color=GT)
    large = render_review_crop(frame(600, 600), norm(100, 100, 500, 500, 600, 600),
                               300, 300, gt_color=GT)
    # Both fill the cell, but the GT rectangle occupies the same fraction --
    # that is what "relative margin" means.
    assert small is not None and large is not None
    assert count(small, GT) == pytest.approx(count(large, GT), rel=0.25)


def test_a_tiny_box_still_gets_a_usable_margin():
    """MIN_PAD_PX stops a 2px box getting a 0px margin."""
    out = render_review_crop(frame(), norm(100, 100, 102, 102), 200, 200,
                             gt_color=GT)
    assert out is not None
    assert count(out, GT) > 0


# -- the model's box -------------------------------------------------------


def test_no_prediction_draws_one_rectangle():
    out = render_review_crop(frame(), norm(80, 80, 120, 120), 200, 200,
                             gt_color=GT, pred_color=PRED)
    assert count(out, GT) > 0
    assert count(out, PRED) == 0


def test_a_prediction_draws_a_second_rectangle():
    out = render_review_crop(frame(), norm(80, 80, 120, 120), 200, 200,
                             pred_bbox_norm=norm(85, 85, 125, 125),
                             gt_color=GT, pred_color=PRED)
    assert count(out, GT) > 0
    assert count(out, PRED) > 0


def test_a_prediction_outside_the_label_is_still_visible():
    """The reason the crop region is the UNION. A tight crop around the label
    would clip this away entirely -- and a disagreement you cannot see is the
    whole problem the picture exists to solve."""
    out = render_review_crop(frame(), norm(90, 90, 110, 110), 300, 300,
                             pred_bbox_norm=norm(130, 130, 170, 170),
                             gt_color=GT, pred_color=PRED)
    assert out is not None
    assert count(out, PRED) > 0, "the model's box was cropped out of frame"
    assert count(out, GT) > 0, "...and the label must still be there too"


def test_the_ground_truth_box_is_drawn_thicker():
    """Thickness is what distinguishes committed from suggested, the same
    language the batch grid already uses."""
    out = render_review_crop(frame(400, 400), norm(100, 100, 300, 300, 400, 400),
                             400, 400,
                             pred_bbox_norm=norm(105, 105, 305, 305, 400, 400),
                             gt_color=GT, pred_color=PRED)
    assert count(out, GT) > count(out, PRED)


# -- scale -----------------------------------------------------------------


def test_the_outline_stays_thin_on_a_heavily_upscaled_box():
    """Drawn after the resize. Before it, a 2px line on a 6px box becomes a
    ~60px border that swallows the object."""
    out = render_review_crop(frame(), norm(97, 97, 103, 103), 300, 300, gt_color=GT)
    assert out is not None
    # A 2px border on a 300px cell is a few percent of the pixels, not most.
    assert count(out, GT) < 0.25 * out.shape[0] * out.shape[1]


# -- labels ----------------------------------------------------------------


def test_labels_are_suppressed_on_a_small_cell():
    box = norm(80, 80, 120, 120)
    small = render_review_crop(frame(), box, 80, MIN_LABEL_CELL_H - 20,
                               gt_color=GT, gt_label="car")
    big = render_review_crop(frame(), box, 300, 300, gt_color=GT, gt_label="car")
    # The tag is drawn on a plate of the class colour, so it adds GT pixels.
    assert count(big, GT) > count(small, GT) * 2


# -- degenerate inputs -----------------------------------------------------


def test_a_zero_area_box_still_shows_where_it_is():
    """It used to render as "(failed to read)", which was a lie -- the image
    is fine, the BOX is junk. And a zero-area box is precisely the kind of
    thing the 'probably not an object' scan exists to surface, so hiding it
    was the worst possible response. The margin gives it somewhere to show."""
    out = render_review_crop(frame(), (0.5, 0.5, 0.0, 0.0), 100, 100, gt_color=GT)
    assert out is not None and out.size > 0
    assert count(out, GT) > 0, "the degenerate box is still outlined"


def test_a_box_entirely_outside_the_frame_returns_none():
    assert render_review_crop(frame(), (5.0, 5.0, 0.1, 0.1), 100, 100) is None


def test_a_box_at_the_corner_does_not_raise():
    out = render_review_crop(frame(), norm(0, 0, 20, 20), 100, 100, gt_color=GT)
    assert out is not None and out.size > 0


def test_a_missing_image_returns_none():
    assert render_review_crop(None, (0.5, 0.5, 0.2, 0.2), 100, 100) is None


def test_a_missing_bbox_returns_none():
    assert render_review_crop(frame(), None, 100, 100) is None


def test_the_constants_are_sane():
    assert 0 < CONTEXT_FRAC < 1
    assert MIN_PAD_PX >= 1


# -- a prediction must not shrink the label away ---------------------------


def _gt_width_share(out):
    cols = np.where(np.any(np.all(out == np.array(GT, np.uint8), axis=2), axis=0))[0]
    return (cols.max() - cols.min() + 1) / out.shape[1]


def test_a_long_thin_prediction_does_not_shrink_the_label_to_a_sliver():
    """IoU >= 0.1 bounds the AREA ratio to 10x, not the side ratio. A 400x40
    prediction over a 40x40 label is IoU 0.1 and, unioned in full, left the
    label at ~10% of the crop width -- a few pixels in a review cell."""
    out = render_review_crop(frame(600, 200), norm(280, 80, 320, 120, 600, 200),
                             300, 300,
                             pred_bbox_norm=norm(100, 80, 500, 120, 600, 200),
                             gt_color=GT, pred_color=PRED)
    assert _gt_width_share(out) >= 0.15
    assert count(out, PRED) > 0, "the model's box is still drawn, clipped at the edge"


def test_a_comparable_prediction_is_still_shown_in_full():
    """The cap must not bite in the ordinary case."""
    out = render_review_crop(frame(), norm(80, 80, 120, 120), 300, 300,
                             pred_bbox_norm=norm(70, 70, 140, 140),
                             gt_color=GT, pred_color=PRED)
    rows = np.where(np.any(np.all(out == np.array(PRED, np.uint8), axis=2), axis=1))[0]
    cols = np.where(np.any(np.all(out == np.array(PRED, np.uint8), axis=2), axis=0))[0]
    assert rows.min() > 0 and cols.min() > 0, "prediction clipped at the top/left"
    assert rows.max() < out.shape[0] - 1 and cols.max() < out.shape[1] - 1
