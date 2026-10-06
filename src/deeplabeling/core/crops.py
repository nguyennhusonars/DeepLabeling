"""The review crop of a finding: the label is its subject; the model's box widens the view
only so far (docs/knowledge/matching.md#the-nearest-box-and-the-review-crop, ported from
`legacy/yolo_labeling/core/crops.py::render_review_crop`)."""

from __future__ import annotations

from .geometry import Box, corners

CONTEXT_FRAC = 0.25     #: the margin around the content, as a share of the label's larger side
MIN_PAD_PX = 4          #: at least this much, so an outline at the frame's edge stays visible
MAX_REACH = 2.0         #: how far past the label the model's box may widen it, in label sides


def crop_rect(label: Box, model: Box | None, w: int, h: int) -> tuple[int, int, int, int] | None:
    """The crop (x1, y1, x2, y2) in pixels of a w x h frame, or None when it is empty."""
    gx1, gy1, gx2, gy2 = (round(v * s) for v, s in zip(corners(label), (w, h, w, h)))
    ux1, uy1, ux2, uy2 = gx1, gy1, gx2, gy2
    side = max(gx2 - gx1, gy2 - gy1)
    if model is not None:
        # IoU bounds the area ratio, not the side ratio: a 400 x 40 prediction over a
        # 40 x 40 label is IoU 0.1, and unioned in full it left the label a sliver.
        px1, py1, px2, py2 = (round(v * s) for v, s in zip(corners(model), (w, h, w, h)))
        reach = round(MAX_REACH * side)
        ux1, uy1 = max(min(ux1, px1), gx1 - reach), max(min(uy1, py1), gy1 - reach)
        ux2, uy2 = min(max(ux2, px2), gx2 + reach), min(max(uy2, py2), gy2 + reach)
    pad = max(MIN_PAD_PX, round(CONTEXT_FRAC * side))
    x1, y1 = max(0, min(ux1 - pad, w)), max(0, min(uy1 - pad, h))
    x2, y2 = max(0, min(ux2 + pad, w)), max(0, min(uy2 + pad, h))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2
