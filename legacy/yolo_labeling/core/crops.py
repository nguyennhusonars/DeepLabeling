"""Compose a review crop: the labelled box, the model's box, and some context.

The bad-annotation review used to show exactly the bounding box and nothing
else. That is the wrong picture for the question being asked. A crop with no
surroundings cannot answer "is this really a bus_l" or "did the model see
nothing *here*", and because the box was the image edge you could not tell a
tight box from an offset one either.

So a crop is now the union of the ground-truth box and the model's box, plus a
margin, with both boxes outlined inside it. Where a class disagreement used to
be a caption you had to trust, it is now two rectangles you can compare.

This lives in `core/` for one concrete reason: the crop is built both on the
GUI thread and on the prefetch worker thread, and those two used to be separate
copies of the same arithmetic. One function, no Tk, no `self`.
"""

from __future__ import annotations

import cv2

from yolo_labeling.core import draw as _draw
from yolo_labeling.core import geometry as _geom

#: Context around the content, as a fraction of the GT box's larger side.
#: Relative rather than fixed because boxes here run from ~10px to most of the
#: frame; any constant is either invisible or swallows the object.
CONTEXT_FRAC = 0.25

#: Floor for that margin. Without it a box at the frame edge would have its
#: outline drawn on the very first pixel row and be effectively invisible.
MIN_PAD_PX = 4

#: How far beyond the label a prediction may widen the crop, in multiples of
#: the label's larger side. Keeps the label at least ~1/5 of the view per axis.
#: Wrong-class predictions match at IoU >= 0.5 and never reach this far; it
#: exists for the nearest box on a 'not an object' entry, which may barely
#: overlap.
MAX_REACH = 2.0

#: Below this cell height the in-image tags cost more than they tell -- the
#: caption under the cell already names both classes and the score.
MIN_LABEL_CELL_H = 90


def render_review_crop(img, bbox_norm, cell_w, cell_h, *,
                       pred_bbox_norm=None,
                       gt_color=(255, 255, 255),
                       pred_color=(255, 200, 0),
                       gt_label=None, pred_label=None,
                       context_frac=CONTEXT_FRAC, min_pad=MIN_PAD_PX):
    """Crop `img` around a label box and return an RGB array fitted to a cell.

    Args:
        img: the full frame, BGR, as `cv2.imread` returns it.
        bbox_norm: the ground-truth box, normalised `(cx, cy, w, h)`.
        pred_bbox_norm: the model's box in the same units, or None. Absent for
            'model sees nothing' entries, for Qwen imports, and for any scan
            run before the box was recorded -- so it is genuinely optional,
            not an error case.

    Returns None when the region is degenerate, which the caller already
    renders as "(failed to read)".
    """
    if img is None or not bbox_norm:
        return None
    ih, iw = img.shape[:2]

    gx1, gy1, gx2, gy2 = _geom.yolo_to_pixel(*bbox_norm[:4], iw, ih,
                                             rounding='round', clip=False)
    px = None
    if pred_bbox_norm:
        px = _geom.yolo_to_pixel(*pred_bbox_norm[:4], iw, ih,
                                 rounding='round', clip=False)

    # Union first, then pad. With no prediction the union collapses to the GT
    # box, so one formula covers both cases -- and a prediction that pokes well
    # outside the label is always fully visible without inflating the margin
    # for everyone else.
    ux1, uy1, ux2, uy2 = gx1, gy1, gx2, gy2
    side = max(gx2 - gx1, gy2 - gy1)
    if px is not None:
        # ...but only so far. IoU bounds the AREA ratio, not the side ratio: a
        # 400x40 prediction over a 40x40 label is IoU 0.1 and, unioned in full,
        # left the label a sliver of the cell. Past the reach the model's box
        # is drawn clipped at the edge, which still shows where it runs.
        reach = round(MAX_REACH * side)       # pixels: these become slice indices
        ux1, uy1 = max(min(ux1, px[0]), gx1 - reach), max(min(uy1, px[1]), gy1 - reach)
        ux2, uy2 = min(max(ux2, px[2]), gx2 + reach), min(max(uy2, px[3]), gy2 + reach)

    pad = max(min_pad, round(context_frac * side))
    cx1, cy1 = max(0, min(ux1 - pad, iw)), max(0, min(uy1 - pad, ih))
    cx2, cy2 = max(0, min(ux2 + pad, iw)), max(0, min(uy2 + pad, ih))
    if cx2 <= cx1 or cy2 <= cy1:
        return None

    crop = img[cy1:cy2, cx1:cx2]
    ch, cw = crop.shape[:2]
    fit = min(cell_w / cw, cell_h / ch)
    nw, nh = max(1, int(cw * fit)), max(1, int(ch * fit))
    buf = cv2.cvtColor(cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA),
                       cv2.COLOR_BGR2RGB)

    # Scale from the ACTUAL output size, not `fit`: nw is truncated, so `fit`
    # overshoots by up to a pixel on the right and bottom edges.
    sx, sy = nw / cw, nh / ch

    def to_cell(x1, y1, x2, y2):
        return (round((x1 - cx1) * sx), round((y1 - cy1) * sy),
                round((x2 - cx1) * sx), round((y2 - cy1) * sy))

    # Drawn AFTER the resize. A 2px rectangle drawn before an 11x upscale
    # becomes a 22px border that swallows the object it outlines.
    if px is not None:
        qx1, qy1, qx2, qy2 = to_cell(*px)
        cv2.rectangle(buf, (qx1, qy1), (qx2, qy2), pred_color, 1)  # thin: a suggestion
    bx1, by1, bx2, by2 = to_cell(gx1, gy1, gx2, gy2)
    cv2.rectangle(buf, (bx1, by1), (bx2, by2), gt_color, 2)        # thick: committed

    # Same above/below split `core.draw` exists for: both boxes sit on the same
    # object, so stacking both tags on one corner is how they become unreadable.
    if cell_h >= MIN_LABEL_CELL_H:
        if px is not None and pred_label:
            _draw.draw_tag(buf, pred_label, qx1, qy1, pred_color,
                           scale=0.32, thickness=1, anchor='above')
        if gt_label:
            _draw.draw_tag(buf, gt_label, bx1, by1 + 2, gt_color,
                           scale=0.35, thickness=1, anchor='below')
    return buf
