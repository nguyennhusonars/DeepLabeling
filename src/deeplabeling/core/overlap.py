"""Which labelled boxes overlap one another: the one predicate the canvas's stack
counts and slice 3's overlap filter share
(docs/knowledge/matching.md#overlap-between-labels)."""

from __future__ import annotations

from collections.abc import Sequence

from .geometry import Box, iou

SCOPES = ("any", "same", "different")

#: What the canvas counts on every caption (`car ×2`): boxes drawn nearly on top of each
#: other, of any class (docs/design/2026-10-06-filters.md#stack-counts). Below 0.9 the
#: rectangles are visibly apart, and the count would mark ordinary occlusion.
STACKED = ("any", 0.9, 1.0)


def pair_counts(scope: str, cls_a: int, cls_b: int) -> bool:
    """Whether a pair of classes counts as an overlap under `scope`."""
    if scope == "any":
        return True
    if scope == "same":
        return cls_a == cls_b
    if scope == "different":
        return cls_a != cls_b
    raise ValueError(f"unknown overlap scope {scope!r}")


def iou_in_range(value: float, lo: float, hi: float) -> bool:
    """Inclusive at both ends; a pair that does not touch never counts, even from 0."""
    return value > 0.0 and lo <= value <= hi


def stack_counts(boxes: Sequence[tuple[int, Box]], scope: str, lo: float, hi: float) -> dict[int, int]:
    """{position: boxes stacked on it, itself included} for every box with a partner.

    `boxes` are (class, normalised box) pairs. The count is per box, not per
    group: in a chain A-B-C where A and C do not touch, A reads 2 and B reads 3.
    """
    partners: dict[int, int] = {}
    for i in range(len(boxes)):
        ci, bi = boxes[i]
        for j in range(i + 1, len(boxes)):
            cj, bj = boxes[j]
            if pair_counts(scope, ci, cj) and iou_in_range(iou(bi, bj), lo, hi):
                partners[i] = partners.get(i, 0) + 1
                partners[j] = partners.get(j, 0) + 1
    return {i: n + 1 for i, n in partners.items()}
