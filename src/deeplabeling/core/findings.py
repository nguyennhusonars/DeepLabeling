"""Find Bad: the labels the model disagrees with (docs/design/2026-10-06-find-bad.md#findings).

The rules are docs/knowledge/matching.md's. A label's candidates are the predictions at or
above the floor, of any class, mapped or not, overlapping it at the matching IoU; the most
confident decides. An unmapped deciding prediction is inconclusive. Agreeing goes through
the yaml's class groups, and only a class the model could have seen can be "not an object".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import ClassVar

from .classmap import ClassMap
from .dataset import Dataset
from .disagree import checkable
from .geometry import Box, iou
from .edits import LineRef
from .inference import FLOOR, Prediction
from .queue import BuildContext, ImageFilter, QueueItem
from .ranges import range_error
from .store import ImageLabels

KINDS = ("wrong class", "not an object", "weakly seen")     #: also the order findings are walked in
NEAREST_MIN_IOU = 0.10      #: a not-an-object finding keeps its nearest box from this IoU


def agrees(a: int, b: int, dataset: Dataset) -> bool:
    """The same class, or classes of one group of the yaml's `groups:`."""
    if a == b:
        return True
    names = dataset.names
    if not (0 <= a < len(names) and 0 <= b < len(names)):
        return False
    return any(names[a] in members and names[b] in members for members in dataset.groups.values())


def _unit(value: float, name: str, lo: float = 0.0) -> None:
    if not lo <= value <= 1:
        raise ValueError(f"{name}: must be from {lo:g} to 1")


@dataclass(frozen=True)
class FindSettings:
    """What Find Bad reports (the spec's Settings table)."""

    floor: float = 0.40
    match_iou: float = 0.5
    wrong_class: bool = True
    ceiling: float = 1.0
    not_object: bool = True
    band: tuple[float, float | None] = (0.0, None)      #: None: up to the matching IoU
    weak: bool = False
    cutoff: float = 0.60

    def __post_init__(self):
        _unit(self.floor, "confidence floor", FLOOR)
        if not 0 < self.match_iou <= 1:
            raise ValueError("matching IoU: must be above 0 and at most 1")
        _unit(self.ceiling, "wrong-class ceiling")
        lo, hi = self.band
        if lo is None:
            raise ValueError("not-an-object band: the lower end must be a number")
        why = range_error(lo, hi, "not-an-object band", open_ends=True)
        if why:
            raise ValueError(why)
        if hi is None and lo > self.match_iou:
            raise ValueError(f"not-an-object band: {lo:g} is above the matching IoU {self.match_iou:g}")
        _unit(self.cutoff, "weak cutoff")
        # Settings under which a kind could never report are refused, not quietly kept.
        if self.ceiling < self.floor:
            raise ValueError(f"wrong-class ceiling: {self.ceiling:g} is below the confidence floor {self.floor:g}")
        if self.cutoff <= self.floor:
            raise ValueError(f"weak cutoff: {self.cutoff:g} is not above the confidence floor {self.floor:g}")

    @property
    def band_hi(self) -> float:
        return self.match_iou if self.band[1] is None else self.band[1]

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(k for k, on in zip(KINDS, (self.wrong_class, self.not_object, self.weak)) if on)

    def to_json(self) -> dict:
        return {"floor": self.floor, "match_iou": self.match_iou, "wrong_class": self.wrong_class,
                "ceiling": self.ceiling, "not_object": self.not_object, "band": list(self.band),
                "weak": self.weak, "cutoff": self.cutoff}

    @classmethod
    def from_json(cls, data) -> FindSettings:
        try:
            lo, hi = data["band"]
            return cls(float(data["floor"]), float(data["match_iou"]), bool(data["wrong_class"]),
                       float(data["ceiling"]), bool(data["not_object"]),
                       (float(lo), None if hi is None else float(hi)), bool(data["weak"]), float(data["cutoff"]))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"not Find Bad settings: {data!r}") from e


@dataclass(frozen=True)
class Finding:
    """One label the model disagrees with."""

    line: int                       #: the label line's index in its file
    text: str                       #: the line as it is, without its line ending
    kind: str                       #: one of KINDS
    score: float                    #: higher first, within a kind
    label_cls: int
    label_box: Box
    model_cls: int | None = None    #: the dataset class of the model's box, when mapped
    model_box: Box | None = None    #: the deciding prediction, or the nearest from NEAREST_MIN_IOU
    model_conf: float | None = None


def judge(labels: ImageLabels, preds: list[Prediction], cmap: ClassMap, dataset: Dataset,
          settings: FindSettings) -> list[Finding]:
    """The findings of one image, in line order."""
    seen = [p for p in preds if p.conf >= settings.floor]
    can_see = checkable(cmap, dataset)
    found = []
    for i, line in labels.boxes:
        overlaps = [(p, iou(line.bbox, p.box)) for p in seen]
        base = dict(line=i, text=line.raw.rstrip("\r\n"), label_cls=line.cls_id, label_box=line.bbox)
        candidates = [(p, v) for p, v in overlaps if v >= settings.match_iou]
        if candidates:
            p, _ = max(candidates, key=lambda c: (c[0].conf, c[1]))
            cls = cmap.translate(p.cls, dataset)
            if cls is None:
                continue                            # inconclusive: no weaker mapped box overrules it
            model = dict(model_cls=cls, model_box=p.box, model_conf=p.conf)
            if not agrees(cls, line.cls_id, dataset):
                if settings.wrong_class and p.conf <= settings.ceiling:
                    found.append(Finding(kind="wrong class", score=p.conf, **base, **model))
            elif settings.weak and p.conf < settings.cutoff:
                found.append(Finding(kind="weakly seen", score=1 - p.conf, **base, **model))
        elif settings.not_object and line.cls_id in can_see:
            nearest, near = max(overlaps, key=lambda o: o[1], default=(None, 0.0))
            if settings.band[0] <= near <= settings.band_hi:
                kept = nearest if nearest is not None and near >= NEAREST_MIN_IOU else None
                model = (dict(model_cls=cmap.translate(kept.cls, dataset), model_box=kept.box, model_conf=kept.conf)
                         if kept is not None else {})
                found.append(Finding(kind="not an object", score=1 - near, **base, **model))
    return found


@dataclass(frozen=True)
class Findings:
    """A queue of findings (docs/design/2026-10-06-find-bad.md#the-queue): the images its
    scope selects, judged with the loaded model's rows, one item per finding, ordered by
    kind and then score. Dismissed findings are left out; images never inferred are counted."""

    scope: ImageFilter = field(default_factory=ImageFilter)
    settings: FindSettings = field(default_factory=FindSettings)
    needs_model: ClassVar[bool] = True

    def items_for(self, entry, ctx: BuildContext) -> list[QueueItem]:
        """The findings of one image, as queue items."""
        if not self.scope.matches(entry, ctx):
            return []
        if ctx.model is None:
            ctx.count("no model", entry)
            return []
        preds = ctx.predictions(entry)
        if preds is None:
            ctx.count("not inferred", entry)
            return []
        found = judge(ctx.labels(entry), preds, ctx.model.class_map, ctx.dataset, self.settings)
        return [QueueItem(f"{entry.rel}#{f.line}#{f.kind}", entry,
                          rank=(KINDS.index(f.kind), -f.score, entry.order, f.line),
                          focus=LineRef(f.line, f.label_cls, f.label_box), finding=f)
                for f in found if (entry.rel, f.text, f.kind) not in ctx.dismissed]

    def build(self, ctx: BuildContext, emit, cancelled=lambda: False, *,
              batch: int = 500, interval: float = 0.2, progress=None) -> bool:
        """Scan, then stream the findings in their order. False when cancelled part-way.
        `progress(scanned, total)` is told at most every `interval` seconds, and at the end."""
        items, images, last = [], ctx.dataset.images, time.monotonic()
        for n, entry in enumerate(images, 1):
            if cancelled():
                return False
            items += self.items_for(entry, ctx)
            if progress is not None and time.monotonic() - last >= interval:
                progress(n, len(images))
                last = time.monotonic()
        if progress is not None:
            progress(len(images), len(images))
        items.sort(key=lambda item: item.sort_key)
        for start in range(0, len(items), batch):
            if cancelled():
                return False
            emit(items[start:start + batch])
        return True

    def still(self, entry, items: list[QueueItem], ctx: BuildContext) -> set[str]:
        """The keys of one image's `items` still found: the image judged once, each finding
        matched by its line's content and kind -- deleting another line shifts the numbers."""
        found = {(it.finding.text, it.finding.kind) for it in self.items_for(entry, ctx)}
        return {it.key for it in items if (it.finding.text, it.finding.kind) in found}

    def holds(self, item: QueueItem, ctx: BuildContext) -> bool:
        """Whether a finding is still there."""
        return item.key in self.still(item.entry, [item], ctx)

    def matches(self, entry, ctx: BuildContext) -> bool:
        return bool(self.items_for(entry, ctx))

    def highlight(self, labels, dataset, seen=None) -> frozenset[int]:
        return frozenset()          # a finding is shown by its focus, not by a highlight

    def highlight_predictions(self, labels, dataset, seen=None) -> frozenset[int]:
        return frozenset()

    def describe(self, dataset: Dataset) -> str:
        kinds = ", ".join(self.settings.kinds) or "nothing"
        text = f"findings: {kinds} (conf ≥ {self.settings.floor:.2f})"
        return text if self.scope == ImageFilter() else f"{text} of {self.scope.describe(dataset)}"

    def to_json(self) -> dict:
        return {"source": "findings", "scope": self.scope.to_json(), "settings": self.settings.to_json()}

    @classmethod
    def from_json(cls, data) -> Findings:
        try:
            return cls(ImageFilter.from_json(data["scope"]), FindSettings.from_json(data["settings"]))
        except (KeyError, TypeError) as e:
            raise ValueError(f"not a findings queue: {data!r}") from e
