"""What a finding shows -- its row, the inspector's line and the spotlight -- computed
without Qt so it is tested headless (docs/design/2026-10-06-find-bad.md#window)."""

from __future__ import annotations

from ..core.crops import crop_rect
from ..core.dataset import Dataset
from ..core.findings import Finding
from ..core.geometry import norm_to_px
from .boxes import PredictionView
from .classes import UNKNOWN, class_color


def _name(cls: int, dataset: Dataset) -> str:
    return dataset.names[cls] if 0 <= cls < len(dataset.names) else f"#{cls}?"


def _model_name(f: Finding, dataset: Dataset, model_names: tuple[str, ...]) -> str:
    """The dataset class of the model's box, or the model's own name with `?` when unmapped."""
    if f.model_cls is not None:
        return _name(f.model_cls, dataset)
    raw = f.model_raw
    return f"{model_names[raw] if raw is not None and 0 <= raw < len(model_names) else raw}?"


def finding_text(f: Finding, dataset: Dataset) -> str:
    """`wrong class: car → truck 0.82`, `not an object: bus_m (nearest 0.03)`, `weakly seen: car 0.41`."""
    label = _name(f.label_cls, dataset)
    if f.kind == "wrong class":
        return f"wrong class: {label} → {_name(f.model_cls, dataset)} {f.model_conf:.2f}"
    if f.kind == "not an object":
        return f"not an object: {label} (nearest {1 - f.score:.2f})"
    return f"weakly seen: {label} {f.model_conf:.2f}"


def finding_detail(f: Finding, dataset: Dataset, model_names: tuple[str, ...]) -> str:
    """The inspector's line: the kind, the score, the model's class and confidence."""
    model = ("nothing near" if f.model_box is None
             else f"{_model_name(f, dataset, model_names)} {f.model_conf:.2f}")
    return f"{f.kind} · {f.score:.2f} · the model: {model}"


def spotlight(f: Finding, dataset: Dataset, size: tuple[int, int], colors: dict[str, str],
              model_names: tuple[str, ...]):
    """(the crop in pixels, the model's box as drawn or None), or None when the crop is empty."""
    w, h = size
    rect = crop_rect(f.label_box, f.model_box, w, h)
    if rect is None:
        return None
    if f.model_box is None:
        return rect, None
    name = _model_name(f, dataset, model_names)
    color = UNKNOWN if f.model_cls is None else class_color(f.model_cls, name, colors)
    return rect, PredictionView(-1, norm_to_px(f.model_box, w, h), color, f"{name} {f.model_conf:.2f}",
                                False, emphasised=True)
