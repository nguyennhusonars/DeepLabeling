"""Box geometry.

A normalised box is (cx, cy, w, h) in [0, 1]; a pixel box is (x1, y1, x2, y2) in
image pixels, unrounded. IoU does not change under independent x/y scaling, so it
is computed on normalised corners, with no image size
(docs/knowledge/matching.md#geometry).
"""

from __future__ import annotations

Box = tuple[float, float, float, float]


def corners(box: Box) -> Box:
    """(cx, cy, w, h) -> (x1, y1, x2, y2), in the same units."""
    cx, cy, w, h = box
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def iou_xyxy(a: Box, b: Box) -> float:
    """IoU of two (x1, y1, x2, y2) boxes; 0.0 for disjoint or degenerate ones."""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0.0 or iy <= 0.0:
        return 0.0
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0.0 else 0.0


def iou(a: Box, b: Box) -> float:
    """IoU of two normalised (cx, cy, w, h) boxes."""
    return iou_xyxy(corners(a), corners(b))


def norm_to_px(box: Box, img_w: int, img_h: int) -> Box:
    """Normalised (cx, cy, w, h) -> pixel (x1, y1, x2, y2), unrounded."""
    x1, y1, x2, y2 = corners(box)
    return (x1 * img_w, y1 * img_h, x2 * img_w, y2 * img_h)


def px_to_norm(x1: float, y1: float, x2: float, y2: float, img_w: int, img_h: int) -> Box:
    """Pixel corners, in either order -> normalised (cx, cy, w, h), clamped.

    Each corner is clamped to the image first, so the whole box lies inside it;
    clamping cx, cy, w and h one by one would not guarantee that.
    """
    if img_w <= 0 or img_h <= 0:
        raise ValueError(f"image size must be positive, got {img_w}x{img_h}")
    lx, hx = sorted((min(max(x1, 0.0), img_w), min(max(x2, 0.0), img_w)))
    ly, hy = sorted((min(max(y1, 0.0), img_h), min(max(y2, 0.0), img_h)))
    return ((lx + hx) / 2 / img_w, (ly + hy) / 2 / img_h, (hx - lx) / img_w, (hy - ly) / img_h)
