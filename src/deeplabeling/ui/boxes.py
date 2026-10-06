"""What the canvas draws for an image's labels, computed without Qt so it is tested
headless (docs/design/2026-10-04-app-foundation.md#window)."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.assist import Shown
from ..core.dataset import Dataset
from ..core.geometry import norm_to_px
from ..core.overlap import STACKED, stack_counts
from ..core.store import ImageLabels
from .classes import UNKNOWN, class_color


@dataclass(frozen=True)
class BoxView:
    index: int                                  #: the line's index in the label file
    rect: tuple[float, float, float, float]     #: (x1, y1, x2, y2) in image pixels
    polygon: tuple[tuple[float, float], ...]    #: a polygon's points in pixels; () for a box
    color: str                                  #: #rrggbb
    caption: str                                #: "car", "car ×2", "#13?"
    known: bool                                 #: False: an id the names do not cover
    highlighted: bool                           #: a queue condition matched this box


def box_views(labels: ImageLabels, dataset: Dataset, size: tuple[int, int],
              colors: dict[str, str], highlight: frozenset[int] = frozenset()) -> list[BoxView]:
    """One view per parsed line. A box stacked on others captions the count (`car ×2`):
    identical rectangles otherwise draw as one. An id outside the names is drawn grey
    and captioned `#id?`, never dropped."""
    w, h = size
    boxes = labels.boxes
    stack = stack_counts([(line.cls_id, line.bbox) for _, line in boxes], *STACKED)
    views = []
    for pos, (index, line) in enumerate(boxes):
        cls_id = line.cls_id
        known = dataset.known(cls_id)
        if not known:
            base, color = f"#{cls_id}?", UNKNOWN
        elif dataset.names:
            base = dataset.names[cls_id]
            color = class_color(cls_id, base, colors)
        else:
            base = str(cls_id)
            color = class_color(cls_id, base, colors)
        caption = f"{base} ×{stack[pos]}" if pos in stack else base
        polygon = ()
        if line.is_polygon:
            polygon = tuple((x * w, y * h) for x, y in zip(line.coords[0::2], line.coords[1::2]))
        views.append(BoxView(index, norm_to_px(line.bbox, w, h), polygon, color, caption,
                             known, index in highlight))
    return views


@dataclass(frozen=True)
class PredictionView:
    index: int                                  #: its place in the shown list
    rect: tuple[float, float, float, float]     #: (x1, y1, x2, y2) in image pixels
    color: str                                  #: its class's colour, grey when unmapped
    caption: str                                #: "car 0.82", or "truck? 0.40" when unmapped
    faint: bool                                 #: not missing: an accept would not add it
    emphasised: bool = False                    #: a queue condition matched it: drawn thicker, never faint


def prediction_views(shown: list[Shown], dataset: Dataset, size: tuple[int, int],
                     colors: dict[str, str], model_names: tuple[str, ...],
                     emphasised: frozenset[int] = frozenset()) -> list[PredictionView]:
    """What the predictions layer draws (docs/design/2026-10-05-model-assist.md#the-predictions-layer)."""
    w, h = size
    views = []
    for index, s in enumerate(shown):
        if s.cls is None:
            name = model_names[s.pred.cls] if 0 <= s.pred.cls < len(model_names) else str(s.pred.cls)
            color, caption = UNKNOWN, f"{name}? {s.pred.conf:.2f}"
        else:
            name = dataset.names[s.cls] if s.cls < len(dataset.names) else str(s.cls)
            color, caption = class_color(s.cls, name, colors), f"{name} {s.pred.conf:.2f}"
        marked = index in emphasised
        views.append(PredictionView(index, norm_to_px(s.pred.box, w, h), color, caption,
                                    not s.missing and not marked, marked))
    return views
