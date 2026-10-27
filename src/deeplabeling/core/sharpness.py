"""How sharp a label box is (docs/design/2026-10-27-blurry.md#the-measure): a tiled
Laplacian ratio and Crété-Roffet, on the box's own grey pixels, as the image is shown."""

from __future__ import annotations

import math
from collections.abc import Iterable

import cv2
import numpy as np

from .crops import px_corners
from .geometry import Box
from .sharpstore import BoxScore

MIN_SCORED = 8          #: boxes with a shorter side are not scored at all
FLAT_STD = 2.0          #: a crop with less grey deviation has nothing to measure
TILE_MIN_VAR = 25.0     #: tiles under std 5 are plain wall, floor or skin: skipped
DENOISE = 0.7           #: the Gaussian before the Laplacian: noise is not detail
PERCENTILE = 80


def box_rect(box: Box, w: int, h: int) -> tuple[int, int, int, int] | None:
    """The box's pixel rectangle in a w x h frame, as the crop grid rounds it, clipped to the
    frame; None when nothing is left."""
    x0, y0, x1, y1 = px_corners(box, w, h)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def is_flat(grey: np.ndarray) -> bool:
    return float(grey.std()) < FLAT_STD


def _local_var(a: np.ndarray, t: int) -> np.ndarray:
    """Every t x t window's variance, sampled at half-tile steps, windows wholly inside."""
    mean = cv2.blur(a, (t, t), borderType=cv2.BORDER_REFLECT)
    sq = cv2.blur(a * a, (t, t), borderType=cv2.BORDER_REFLECT)
    step = max(1, t // 2)
    h, w = a.shape
    return np.maximum(sq - mean * mean, 0)[t // 2:h - (t - 1) // 2:step, t // 2:w - (t - 1) // 2:step]


def tiled_ratio(grey: np.ndarray) -> float:
    """log10 of the 80th percentile, over tiles with detail, of Laplacian variance over grey
    variance: an object is as sharp as its detailed parts, not its plain background."""
    f = grey.astype(np.float64)
    lap = cv2.Laplacian(cv2.GaussianBlur(f, (0, 0), DENOISE), cv2.CV_64F)
    t = max(MIN_SCORED, min(grey.shape) // 3)
    var, lap_var = _local_var(f, t), _local_var(lap, t)
    keep = var >= TILE_MIN_VAR
    if not keep.any():
        return math.log10((lap.var() + 1e-3) / (f.var() + 1))
    return math.log10(float(np.percentile((lap_var[keep] + 1e-3) / (var[keep] + 1), PERCENTILE)))


def crete_roffet(grey: np.ndarray, h_size: int = 11) -> float:
    """Crété-Roffet's blur effect, as `skimage.measure.blur_effect` computes it: 0 sharp, 1
    blurry; the larger of the two axes. Re-blurring a sharp crop changes its edges a lot."""
    f = grey.astype(np.float64) / 255
    eps = np.spacing(1)
    inner = (slice(2, f.shape[0] - 1), slice(2, f.shape[1] - 1))
    out = []
    for dx, dy, ksize in ((0, 1, (1, h_size)), (1, 0, (h_size, 1))):      # along rows, then columns
        blurred = cv2.blur(f, ksize, borderType=cv2.BORDER_REFLECT)
        sharp = np.maximum(eps, np.abs(cv2.Sobel(f, cv2.CV_64F, dx, dy, ksize=3, borderType=cv2.BORDER_REFLECT)))
        soft = np.maximum(eps, np.abs(cv2.Sobel(blurred, cv2.CV_64F, dx, dy, ksize=3, borderType=cv2.BORDER_REFLECT)))
        m1 = sharp[inner].sum()
        m2 = np.maximum(0, sharp - soft)[inner].sum()
        out.append(abs(m1 - m2) / m1)
    return max(out)


def score_image(grey: np.ndarray, boxes: Iterable[Box]) -> list[BoxScore]:
    """One score per distinct rectangle of short side ≥ 8 px; a flat crop's measures None."""
    h, w = grey.shape
    seen, out = set(), []
    for box in boxes:
        rect = box_rect(box, w, h)
        if rect is None or rect in seen or min(rect[2] - rect[0], rect[3] - rect[1]) < MIN_SCORED:
            continue
        seen.add(rect)
        crop = grey[rect[1]:rect[3], rect[0]:rect[2]]
        out.append((*rect, None, None) if is_flat(crop) else (*rect, tiled_ratio(crop), crete_roffet(crop)))
    return out
