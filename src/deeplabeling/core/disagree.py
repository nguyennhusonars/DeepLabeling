"""Where the model and the labels disagree, for the Label/Prediction IoU condition
(docs/knowledge/matching.md#the-iou-filter).

"The model does not see this label" is geometry against every prediction at or above the
lower confidence bound, mapped or not; "nobody labelled this" counts only predictions of a
class the dataset has, inside the confidence range. The upper bound never removes a
prediction from matching (docs/knowledge/matching.md#one-floor-and-per-kind-ceilings).
"""

from __future__ import annotations

from collections.abc import Sequence

from .classmap import ClassMap
from .dataset import Dataset
from .geometry import iou
from .inference import Prediction
from .store import ImageLabels


def checkable(cmap: ClassMap, dataset: Dataset) -> frozenset[int]:
    """The dataset classes some model class maps to: only their labels can be unseen
    (docs/knowledge/matching.md#the-checkable-class-guard)."""
    return frozenset(c for c in (cmap.translate(m, dataset) for m in range(len(cmap.model_names)))
                     if c is not None)


def unseen_labels(labels: ImageLabels, preds: Sequence[Prediction], cmap: ClassMap, dataset: Dataset,
                  match_iou: float, conf_lo: float) -> frozenset[int]:
    """Line indices of the labels no prediction at or above `conf_lo` overlaps at IoU >=
    `match_iou`, of any class, mapped or not."""
    seen_by = [p.box for p in preds if p.conf >= conf_lo]
    can_see = checkable(cmap, dataset)
    return frozenset(i for i, line in labels.boxes
                     if line.cls_id in can_see and not any(iou(line.bbox, b) >= match_iou for b in seen_by))


def unlabelled_predictions(labels: ImageLabels, preds: Sequence[Prediction], cmap: ClassMap,
                           dataset: Dataset, match_iou: float, conf_lo: float,
                           conf_hi: float) -> frozenset[int]:
    """Indices of the mapped predictions inside [conf_lo, conf_hi] that overlap no label
    at IoU >= `match_iou`."""
    boxes = [line.bbox for _, line in labels.boxes]
    return frozenset(k for k, p in enumerate(preds)
                     if conf_lo <= p.conf <= conf_hi and cmap.translate(p.cls, dataset) is not None
                     and not any(iou(p.box, b) >= match_iou for b in boxes))
