"""What a model's predictions say about one labelled box.

Find Bad Annotations and the Label/Prediction IoU filter ask the same question --
"does the model see this label, and does it agree?" -- and used to answer it with
two separate pieces of code. They live here so they cannot disagree.

Predictions are ``(cls, conf, x1, y1, x2, y2)`` in pixels, with ``cls`` already
translated to a dataset id (None for a model class with no mapping), and already
narrowed to the shared confidence floor by the caller.

Two rules every threshold here follows:

1. **An upper confidence bound never removes a prediction from matching.** It
   only limits which findings are reported. Filtering predictions to a
   ``[lo, hi]`` band first is the obvious reading of "a range" and it is wrong: a
   box the model sees at 0.95 would become "not an object" as soon as the ceiling
   dropped below 0.95.
2. **A kind's findings never depend on which other kinds are enabled.** That is
   why there is one shared floor rather than one per kind -- separate floors would
   let the same box be both "not an object" and "weakly seen".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from yolo_labeling.core.geometry import iou_xyxy

#: Below this overlap the nearest prediction is not recorded on a 'missing'
#: finding. The review crop is the union of both boxes, and a huge box at a
#: sliver of overlap would shrink a small stray label to a few pixels. IoU >= 0.1
#: bounds the area ratio to 10x, so the label keeps a usable share of the crop.
NEAREST_MIN_IOU = 0.10


@dataclass(frozen=True)
class ScanConfig:
    """Which findings to report, and with what evidence.

    `iou_match` decides whether a prediction is the same object as the label.
    Everything else bounds what is reported; none of it changes matching.
    """

    iou_match: float = 0.5
    #: Wrong class: a matched prediction disagrees on the class.
    mismatch: bool = True
    mismatch_max: float = 1.0          # ...and its confidence is at most this
    #: Not an object: nothing matches. The band is on the NEAREST box's IoU, so
    #: near 0 isolates stray boxes and higher isolates badly-drawn ones.
    missing: bool = True
    missing_iou_lo: float = 0.0
    missing_iou_hi: float | None = None    # None = up to `iou_match`
    #: Weakly seen: the model agrees, but with confidence below this.
    weak: bool = False
    weak_below: float = 0.6
    #: Optional confusion pair. Naming both sides asks for that raw pair.
    gt_class: int | None = None
    pred_class: int | None = None


class Finding(NamedTuple):
    kind: str          # 'class_mismatch' | 'missing' | 'weak'
    pred: tuple | None  # the deciding (or, for 'missing', nearest) prediction
    iou: float
    score: float       # sort key, higher = review first


def candidates(gt_box, preds, iou_match):
    """``[(pred, iou)]`` for every prediction that is the same object as `gt_box`."""
    out = []
    for pred in preds:
        iou = iou_xyxy(gt_box, pred[2:6])
        if iou >= iou_match:
            out.append((pred, iou))
    return out


def deciding(cands):
    """The candidate that speaks for the model: its most confident one.

    Not the best-overlapping one. Ultralytics runs NMS per class by default, so
    one car routinely produces a confident 'car' and a weak 'truck' a hair
    better aligned -- deciding on overlap made the verdict flip on a 0.02 IoU
    difference. Ties on confidence go to the better overlap.
    """
    if not cands:
        return None
    return max(cands, key=lambda c: (float(c[0][1]), c[1]))


def nearest(gt_box, preds):
    """``(pred, iou)`` of the best-overlapping prediction, or ``(None, 0.0)``."""
    best, best_iou = None, 0.0
    for pred in preds:
        iou = iou_xyxy(gt_box, pred[2:6])
        if iou > best_iou:
            best, best_iou = pred, iou
    return best, best_iou


def classify_gt(gt_cls, gt_box, preds, cfg, equivalent, checkable=True):
    """The finding for one labelled box, or None if there is nothing to report.

    Args:
        equivalent: ``(a, b) -> bool``, the class-group relation.
        checkable: False when the model cannot emit this label's class at all.
            Its silence then proves nothing, so the box is never reported as
            'not an object' -- doing so recommends deleting valid labels.
    """
    cands = candidates(gt_box, preds, cfg.iou_match)

    if not cands:
        # A 'missing' finding has no prediction to satisfy a "model says"
        # restriction with.
        if not (cfg.missing and checkable and cfg.pred_class is None):
            return None
        pred, iou = nearest(gt_box, preds)
        hi = cfg.iou_match if cfg.missing_iou_hi is None else cfg.missing_iou_hi
        if not (cfg.missing_iou_lo <= iou <= hi):
            return None
        kept = pred if iou >= NEAREST_MIN_IOU else None
        return Finding('missing', kept, iou, 1.0 - iou)

    pred, iou = deciding(cands)
    pcls, pconf = pred[0], float(pred[1])
    if pcls is None:
        # The model's strongest opinion has no dataset class. It proves an
        # object is here, but says nothing about which -- and a weaker mapped
        # box must not be allowed to overrule it.
        return None

    pair_mode = cfg.gt_class is not None and cfg.pred_class is not None
    agrees = (pcls == gt_cls) if pair_mode else equivalent(gt_cls, pcls)

    if not agrees:
        if (cfg.mismatch and pconf <= cfg.mismatch_max
                and (cfg.pred_class is None or pcls == cfg.pred_class)):
            return Finding('class_mismatch', pred, iou, pconf)
        return None

    # In pair mode agreement is raw equality, so a weak agreement under a
    # "model says" restriction is a contradiction. Off, rather than a kind that
    # silently returns nothing.
    if cfg.weak and cfg.pred_class is None and pconf < cfg.weak_below:
        return Finding('weak', pred, iou, 1.0 - pconf)
    return None
