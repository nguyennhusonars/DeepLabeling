"""Blurry boxes (docs/design/2026-10-27-blurry.md): every label box scored for sharpness,
ranked against boxes of its own class and size, the blurriest share of each group listed."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

#: Short sides in px: a box is compared only with boxes of its class in its octave.
OCTAVES = ((8, 15), (16, 31), (32, 63), (64, 127), (128, None))
MIN_PEERS = 20          #: a smaller group is not ranked
MAD_SCALE = 1.4826      #: MAD to a standard deviation, for normal data


def octave(side: int) -> int:
    return next(i for i, (lo, hi) in enumerate(OCTAVES) if hi is None or side <= hi)


def octave_name(i: int) -> str:
    lo, hi = OCTAVES[i]
    return f"{lo}+ px" if hi is None else f"{lo}–{hi} px"


@dataclass(frozen=True)
class BlurSettings:
    share: float = 0.05     #: of each group, listed
    min_side: int = 16      #: px: smaller boxes are too small to judge

    def __post_init__(self):
        if not 0 < self.share <= 1:
            raise ValueError("share: must be above 0% and at most 100%")
        if isinstance(self.min_side, bool) or not isinstance(self.min_side, int) or not 8 <= self.min_side <= 4096:
            raise ValueError("minimum side: must be from 8 to 4096 px")

    def to_json(self) -> dict:
        return {"share": self.share, "min_side": self.min_side}

    @classmethod
    def from_json(cls, data) -> BlurSettings:
        try:
            return cls(float(data["share"]), data["min_side"])
        except (KeyError, TypeError, ValueError, OverflowError) as e:
            raise ValueError(f"not Blurry settings: {data!r}") from e


@dataclass(frozen=True)
class Candidate:
    """A scored box, ready to rank."""

    key: str
    entry_order: int
    line: int
    cls: int
    side: int
    lap: float      #: the tiled Laplacian ratio: higher is sharper
    cr: float       #: Crété-Roffet: higher is blurrier


def _z(values: np.ndarray) -> np.ndarray:
    med = np.median(values)
    return (values - med) / max(MAD_SCALE * float(np.median(np.abs(values - med))), 1e-6)


def rank(candidates: list[Candidate], share: float) -> tuple[dict[str, tuple[float, float]], set[str]]:
    """{key: (z, rank)} of the first `ceil(share · n)` of each group of at least MIN_PEERS,
    blurriest first; and the keys of the groups too small to rank."""
    groups: dict[tuple[int, int], list[Candidate]] = defaultdict(list)
    for c in candidates:
        groups[(c.cls, octave(c.side))].append(c)
    listed, small = {}, set()
    for members in groups.values():
        n = len(members)
        if n < MIN_PEERS:
            small.update(c.key for c in members)
            continue
        z = (_z(np.array([c.lap for c in members])) + _z(-np.array([c.cr for c in members]))) / 2
        order = sorted(range(n), key=lambda i: (z[i], members[i].entry_order, members[i].line))
        for place, i in enumerate(order[:math.ceil(share * n - 1e-9)]):
            listed[members[i].key] = (float(z[i]), place / n)
    return listed, small
