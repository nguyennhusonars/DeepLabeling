# Slice 4a: the Find Bad core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build slice 4's Qt-free core:
- the finding judge, with class groups;
- the review crop's geometry;
- the dismissals store;
- queues ordered by an item's own key;
- the `Findings` queue source.

**Architecture:**
- `core/findings.py` judges one image's labels against the model's predictions (`judge`, `FindSettings`, `Finding`). It holds the `Findings` source, which scans the images its scope selects and emits one `QueueItem` per finding, ordered by kind and score.
- `core/queue.py`'s `Queue` keeps items by their sort key, so an image queue keeps dataset order and a findings queue its own. It knows which items each image stands behind, and rechecks them through the source.
- `core/crops.py` and `core/dismissals.py` are small and pure. Plans 4b and 4c put it all on screen.

**Tech Stack:** Python 3.10 (conda base), pytest; slices 2 and 3's core.

**Spec:** [2026-10-06-find-bad.md](2026-10-06-find-bad.md). This plan implements:
- *Findings*: settings, judging, class groups, what a finding holds, dismissals;
- *The queue*'s core.

Plan 4b builds the full frame (the editor's source switch, list rows and the chip, the spotlight, `M`/`B`/`D`); plan 4c builds the grid (crop tiles, multi-select actions) and the measurements.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)).
- **`src/deeplabeling/core/` imports no Qt, nor ultralytics or torch** (`tests/core/test_core_imports_no_qt.py`, `tests/core/test_inference.py`).
- **The rules are [matching.md](../knowledge/matching.md)'s:**
  - the most confident candidate decides;
  - an unmapped class is inconclusive ([landmine 5](../../CLAUDE.md#landmines));
  - one floor, and ceilings that never remove a prediction from matching ([landmine 6](../../CLAUDE.md#landmines));
  - the checkable-class guard.
- **Dismissal files are written atomically**, as the review marks are. An unreadable one is set aside, never overwritten.
- **Tests write only to temporary folders** ([landmine 10](../../CLAUDE.md#landmines)).
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice4-find-bad`, which already holds the spec. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone cleaning with Find Bad. Each has a named test:

1. **NMS per class gives one car as `car 0.5` (exact) and `person 0.9` (looser).** The most confident decides, so the verdict never flips on a small IoU difference. *(Task 1 `test_the_most_confident_candidate_decides_not_the_best_overlap`.)*
2. **An unmapped prediction decides.** No finding, and a weaker mapped one does not overrule it. *(Task 1 `test_an_unmapped_deciding_prediction_is_inconclusive`.)*
3. **A coarse model whose `bus` stands for `bus_m` and `bus_l`.** A `bus_l` label called "bus" agrees, and a `bus_l` nothing overlaps is still checkable, through its group. *(Task 1 `test_a_class_of_the_same_group_agrees`, `test_a_class_is_checkable_through_its_group`.)*
4. **A 400×40 prediction near a 40×40 label.** The crop stays about the label. *(Task 2 `test_a_long_prediction_reaches_at_most_twice_the_label_s_side`.)*
5. **A dismissed finding whose label was edited since.** It comes back; an unchanged one stays dismissed, across saves. *(Task 3 `test_a_dismissal_is_the_image_the_line_as_it_is_and_the_kind`; Task 5 `test_a_dismissed_finding_is_left_out`.)*

## Found while building this plan

The plan's code was built in a scratch copy first, and its suite ran green there (826 passed).

- **The yaml's `groups:` was already read** (`src/deeplabeling/core/dataset.py::Dataset`), and slice 3's `checkable` ignored it. That spec deferred groups to this slice, so Task 1 makes `checkable` group-aware for both slices.
- **Plan 3b made dataset order a queue invariant.** A findings queue is ordered by kind and score, so Task 4 keeps items by a sort key of their own. An image item's key is still its dataset order, and an out-of-order item is still refused.
- **`core/findings.py` builds on `core/queue.py`**, so `source_from_json` imports `Findings` lazily.

## Decisions this plan makes

- **A finding's text is its label line without the line ending,** so a file turned from LF to CRLF keeps its dismissals.
- **A finding's sort key is `(kind, −score, dataset order, line)`**: unique, and stable between scans.
- **The scan collects every finding, then emits them sorted.** `progress(scanned, total)` is told at most every 0.2 s, and at the end.
- **`Findings.highlight` is empty:** a finding is shown by its item's `focus`, which plan 4b draws.
- **The session still asks `key in queue`,** which is right for image queues; plan 4b moves it to `Queue.has_image` for findings.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/core/findings.py`, `disagree.py` | `agrees`, `FindSettings`, `Finding`, `judge`; group-aware `checkable` | 1 |
| `src/deeplabeling/core/crops.py` | `crop_rect` | 2 |
| `src/deeplabeling/core/dismissals.py`, `workspace.py` | `Dismissals`; `Workspace.dismissals` | 3 |
| `src/deeplabeling/core/queue.py` | `QueueItem.rank`/`focus`/`finding`; rank-ordered `Queue`, `has_image`, `keys_of`; `ImageFilter.holds`/`items_for` | 4 |
| `src/deeplabeling/core/findings.py`, `queue.py` | `Findings`; `BuildContext.dismissed`; `source_from_json` | 5 |
| `CLAUDE.md`, the spec | the status | 6 |

---

### Task 1: Judging an image's labels, with class groups

**Files:**
- Create: `src/deeplabeling/core/findings.py`, `tests/core/test_findings.py`
- Modify: `src/deeplabeling/core/disagree.py`, `tests/core/test_disagree.py`

**Interfaces:**
- Consumes:
  - from slices 2 and 3: `ClassMap.translate`, `Prediction`, `FLOOR`, `geometry.iou`, `range_error`, `ImageLabels.boxes`;
  - `Dataset.groups` (`{group: (class names)}`).
- Produces in `deeplabeling.core.findings`:
  - `KINDS = ("wrong class", "not an object", "weakly seen")` and `NEAREST_MIN_IOU = 0.10`;
  - `agrees(a, b, dataset)`;
  - `FindSettings(floor=0.40, match_iou=0.5, wrong_class=True, ceiling=1.0, not_object=True, band=(0.0, None), weak=False, cutoff=0.60)`, with `.band_hi`, `.kinds`, `to_json`/`from_json`. It refuses unusable values by name (`ValueError`).
  - `Finding(line, text, kind, score, label_cls, label_box, model_cls=None, model_box=None, model_conf=None)`;
  - `judge(labels, preds, cmap, dataset, settings) -> list[Finding]`.
- Changes: `disagree.checkable(cmap, dataset)` also counts the classes of a mapped class's group.

- [ ] **Step 1: Commit this plan, on the spec's branch**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout slice4-find-bad
git add docs/design/2026-10-06-find-bad-core-plan.md
git commit -m "docs: the slice 4a Find Bad core plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/core/test_findings.py`:

```python
"""Find Bad's judgement of one image's labels (docs/design/2026-10-06-find-bad.md#findings,
docs/knowledge/matching.md)."""

import pytest
import yaml

from deeplabeling.core.classmap import ClassMap
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.findings import FindSettings, agrees, judge
from deeplabeling.core.inference import Prediction
from deeplabeling.core.store import LabelStore

MODEL = ("car", "person", "bus", "truck")   # car -> car, person -> person, bus -> bus_m (set), truck: unmapped
CAR, PERSON = (0.25, 0.25, 0.1, 0.1), (0.5, 0.5, 0.2, 0.3)     # camA/0001: line 1 a car, line 0 a person


def P(cls, box, conf):
    return Prediction(cls, box, conf)


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)                    # person, car, bus_m, bus_l; groups: bus = bus_m + bus_l


@pytest.fixture
def cmap(dataset):
    return ClassMap.seeded(MODEL, dataset.names).with_target(2, "bus_m")


@pytest.fixture
def labels(dataset):
    store = LabelStore(dataset)
    return lambda rel: store.get(dataset.root / rel)


def kinds(found):
    return [(f.line, f.kind, round(f.score, 3)) for f in found]


def test_a_confident_prediction_of_another_class_makes_a_wrong_class(labels, dataset, cmap):
    found = judge(labels("camA/images/0001.jpg"), [P(1, CAR, 0.8), P(1, PERSON, 0.9)], cmap, dataset, FindSettings())
    assert kinds(found) == [(1, "wrong class", 0.8)]
    [f] = found
    assert (f.model_cls, f.model_box, f.model_conf, f.label_cls) == (0, CAR, 0.8, 1)
    assert f.text == "1 0.250000 0.250000 0.100000 0.100000"


def test_the_most_confident_candidate_decides_not_the_best_overlap(labels, dataset, cmap):
    near = (0.26, 0.25, 0.1, 0.1)                                # IoU 0.82 with the car
    preds = [P(0, CAR, 0.5), P(1, near, 0.9), P(1, PERSON, 0.9)]
    assert kinds(judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings())) == [(1, "wrong class", 0.9)]


def test_an_unmapped_deciding_prediction_is_inconclusive(labels, dataset, cmap):
    preds = [P(3, CAR, 0.9), P(1, CAR, 0.5), P(1, PERSON, 0.9)]  # a truck decides; the person may not overrule it
    assert judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings()) == []


def test_a_ceiling_reports_less_but_never_removes_a_prediction_from_matching(labels, dataset, cmap):
    preds = [P(1, CAR, 0.8), P(1, PERSON, 0.9)]
    assert judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings(ceiling=0.7)) == []


def test_a_label_nothing_overlaps_is_not_an_object_with_its_nearest_box_from_0_1(labels, dataset, cmap):
    far = (0.33, 0.25, 0.1, 0.1)                                 # IoU 0.11 with the car
    found = judge(labels("camA/images/0001.jpg"), [P(1, PERSON, 0.9), P(0, far, 0.9)], cmap, dataset, FindSettings())
    assert kinds(found) == [(1, "not an object", 0.889)]
    assert found[0].model_box == far and found[0].model_cls == 1
    farther = (0.36, 0.25, 0.1, 0.1)                             # does not touch it: no box kept
    [f] = judge(labels("camA/images/0001.jpg"), [P(1, PERSON, 0.9), P(0, farther, 0.9)], cmap, dataset, FindSettings())
    assert f.kind == "not an object" and f.model_box is None and f.model_cls is None


def test_the_band_reports_only_nearest_boxes_inside_it(labels, dataset, cmap):
    far = (0.33, 0.25, 0.1, 0.1)
    preds = [P(1, PERSON, 0.9), P(0, far, 0.9)]
    assert judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings(band=(0.0, 0.1))) == []


def test_below_the_floor_the_model_sees_nothing(labels, dataset, cmap):
    found = judge(labels("camA/images/0001.jpg"), [P(0, CAR, 0.3), P(1, PERSON, 0.9)], cmap, dataset, FindSettings())
    assert kinds(found) == [(1, "not an object", 1.0)]


def test_weakly_seen_is_off_by_default_and_never_changes_the_other_kinds(labels, dataset, cmap):
    preds = [P(0, CAR, 0.45), P(1, PERSON, 0.95)]
    assert judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings()) == []
    assert kinds(judge(labels("camA/images/0001.jpg"), preds, cmap, dataset, FindSettings(weak=True))) == [
        (1, "weakly seen", 0.55)]


def test_a_class_of_the_same_group_agrees(labels, dataset, cmap, ds):
    ds.lbl("camB/0001").write_text("3 0.750000 0.750000 0.150000 0.150000\n")      # a bus_l
    bus = P(2, (0.75, 0.75, 0.15, 0.15), 0.9)                                     # the model's bus: bus_m
    assert judge(labels("camB/images/0001.jpg"), [bus], cmap, dataset, FindSettings()) == []
    assert agrees(3, 2, dataset) and not agrees(3, 1, dataset)


def test_a_class_is_checkable_through_its_group(labels, dataset, cmap, ds):
    ds.lbl("camB/0001").write_text("3 0.750000 0.750000 0.150000 0.150000\n")      # bus_l: nothing maps to it,
    found = judge(labels("camB/images/0001.jpg"), [], cmap, dataset, FindSettings())  # but bus_m, its group, does
    assert kinds(found) == [(0, "not an object", 1.0)]


def test_without_groups_each_class_stands_alone(labels, cmap, ds):
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    del data["groups"]
    (ds.root / "plain.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    plain = Dataset.open(ds.root / "plain.yaml")
    ds.lbl("camB/0001").write_text("3 0.750000 0.750000 0.150000 0.150000\n")
    store = LabelStore(plain)
    bus = P(2, (0.75, 0.75, 0.15, 0.15), 0.9)
    [f] = judge(store.get(plain.root / "camB/images/0001.jpg"), [bus], cmap, plain, FindSettings())
    assert f.kind == "wrong class"
    assert judge(store.get(plain.root / "camB/images/0001.jpg"), [], cmap, plain, FindSettings()) == []


@pytest.mark.parametrize("kw, why", [
    (dict(floor=0.05), "confidence floor: must be from 0.1 to 1"),
    (dict(match_iou=0.0), "matching IoU: must be above 0 and at most 1"),
    (dict(ceiling=1.5), "wrong-class ceiling: must be from 0 to 1"),
    (dict(band=(0.4, 0.2)), "not-an-object band: 0.4 is above 0.2: put the lower end first"),
    (dict(cutoff=-0.1), "weak cutoff: must be from 0 to 1"),
])
def test_unusable_settings_are_refused_by_name(kw, why):
    with pytest.raises(ValueError, match=why):
        FindSettings(**kw)


def test_settings_survive_their_json():
    s = FindSettings(floor=0.5, match_iou=0.6, ceiling=0.9, band=(0.0, None), weak=True, cutoff=0.7)
    assert FindSettings.from_json(s.to_json()) == s and FindSettings.from_json(FindSettings().to_json()) == FindSettings()
```

Append to `tests/core/test_disagree.py`:

```python
def test_a_class_is_checkable_through_its_group(dataset):
    from deeplabeling.core.disagree import checkable

    cmap = ClassMap.seeded(("car", "bus"), dataset.names).with_target(1, "bus_m")
    assert checkable(cmap, dataset) == {1, 2, 3}           # car; bus_m, and bus_l of its group
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_findings.py`
Expected: `No module named 'deeplabeling.core.findings'`.

- [ ] **Step 4: Judge one image; make checkable classes group-aware**

Create `src/deeplabeling/core/findings.py`:

```python
"""Find Bad: the labels the model disagrees with (docs/design/2026-10-06-find-bad.md#findings).

The rules are docs/knowledge/matching.md's. A label's candidates are the predictions at or
above the floor, of any class, mapped or not, overlapping it at the matching IoU; the most
confident decides. An unmapped deciding prediction is inconclusive. Agreeing goes through
the yaml's class groups, and only a class the model could have seen can be "not an object".
"""

from __future__ import annotations

from dataclasses import dataclass

from .classmap import ClassMap
from .dataset import Dataset
from .disagree import checkable
from .geometry import Box, iou
from .inference import FLOOR, Prediction
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
        why = range_error(*self.band, "not-an-object band", open_ends=True)
        if why:
            raise ValueError(why)
        _unit(self.cutoff, "weak cutoff")

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
```

In `src/deeplabeling/core/disagree.py`, replace:

```python

def checkable(cmap: ClassMap, dataset: Dataset) -> frozenset[int]:
    """The dataset classes some model class maps to: only their labels can be unseen
    (docs/knowledge/matching.md#the-checkable-class-guard)."""
    return frozenset(c for c in (cmap.translate(m, dataset) for m in range(len(cmap.model_names)))
                     if c is not None)


```

with:

```python

def checkable(cmap: ClassMap, dataset: Dataset) -> frozenset[int]:
    """The dataset classes some model class maps to, directly or into their group of the
    yaml's `groups:`: only their labels can be unseen
    (docs/knowledge/matching.md#the-checkable-class-guard)."""
    mapped = {c for c in (cmap.translate(m, dataset) for m in range(len(cmap.model_names))) if c is not None}
    names = {dataset.names[c] for c in mapped if 0 <= c < len(dataset.names)}
    for members in dataset.groups.values():
        if names & set(members):
            mapped |= {i for i in map(dataset.id_of, members) if i is not None}
    return frozenset(mapped)


```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_findings.py tests/core/test_disagree.py tests/core/test_conditions.py`
Expected: 58 passed.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 801 passed.

```bash
git add src/deeplabeling/core/findings.py src/deeplabeling/core/disagree.py tests/core/test_findings.py tests/core/test_disagree.py
git commit -m "core: Find Bad's judgement of an image's labels, agreeing through the yaml's class groups" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The review crop

**Files:**
- Create: `src/deeplabeling/core/crops.py`, `tests/core/test_crops.py`

**Interfaces:**
- Consumes: `geometry.corners`.
- Produces:
  - `crop_rect(label, model, w, h) -> (x1, y1, x2, y2) | None`, in pixels;
  - `CONTEXT_FRAC = 0.25`, `MIN_PAD_PX = 4` and `MAX_REACH = 2.0`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_crops.py`:

```python
"""The review crop: the label is its subject, the model's box widens it only so far
(docs/knowledge/matching.md#the-nearest-box-and-the-review-crop)."""

from deeplabeling.core.crops import crop_rect


def test_a_label_alone_is_padded_by_a_quarter_of_its_larger_side():
    # a 100 x 40 px label at the centre of a 1000 x 1000 frame: pad 25
    assert crop_rect((0.5, 0.5, 0.1, 0.04), None, 1000, 1000) == (425, 455, 575, 545)


def test_the_pad_is_at_least_4_px():
    # an 8 x 8 px label: a quarter of 8 is 2, so 4
    assert crop_rect((0.5, 0.5, 0.008, 0.008), None, 1000, 1000) == (492, 492, 508, 508)


def test_the_model_s_box_widens_the_crop_to_hold_both():
    label, model = (0.5, 0.5, 0.1, 0.1), (0.55, 0.5, 0.1, 0.1)
    assert crop_rect(label, model, 1000, 1000) == (425, 425, 625, 575)


def test_a_long_prediction_reaches_at_most_twice_the_label_s_side():
    # a 400 x 40 prediction over a 40 x 40 label (IoU 0.1): the crop reaches 80 px each way,
    # not 180, so the label keeps about a fifth of the crop's width
    label, model = (0.5, 0.5, 0.04, 0.04), (0.5, 0.5, 0.4, 0.04)
    x1, y1, x2, y2 = crop_rect(label, model, 1000, 1000)
    assert (x1, x2) == (480 - 80 - 10, 520 + 80 + 10) and (y1, y2) == (470, 530)


def test_the_crop_stays_inside_the_frame():
    assert crop_rect((0.02, 0.02, 0.04, 0.04), None, 1000, 1000) == (0, 0, 50, 50)


def test_a_box_outside_the_frame_has_no_crop():
    assert crop_rect((1.5, 1.5, 0.1, 0.1), None, 100, 100) is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_crops.py`
Expected: `No module named 'deeplabeling.core.crops'`.

- [ ] **Step 3: The crop**

Create `src/deeplabeling/core/crops.py`:

```python
"""The review crop of a finding: the label is its subject; the model's box widens the view
only so far (docs/knowledge/matching.md#the-nearest-box-and-the-review-crop, ported from
`legacy/yolo_labeling/core/crops.py::render_review_crop`)."""

from __future__ import annotations

from .geometry import Box, corners

CONTEXT_FRAC = 0.25     #: the margin around the content, as a share of the label's larger side
MIN_PAD_PX = 4          #: at least this much, so an outline at the frame's edge stays visible
MAX_REACH = 2.0         #: how far past the label the model's box may widen it, in label sides


def crop_rect(label: Box, model: Box | None, w: int, h: int) -> tuple[int, int, int, int] | None:
    """The crop (x1, y1, x2, y2) in pixels of a w x h frame, or None when it is empty."""
    gx1, gy1, gx2, gy2 = (round(v * s) for v, s in zip(corners(label), (w, h, w, h)))
    ux1, uy1, ux2, uy2 = gx1, gy1, gx2, gy2
    side = max(gx2 - gx1, gy2 - gy1)
    if model is not None:
        # IoU bounds the area ratio, not the side ratio: a 400 x 40 prediction over a
        # 40 x 40 label is IoU 0.1, and unioned in full it left the label a sliver.
        px1, py1, px2, py2 = (round(v * s) for v, s in zip(corners(model), (w, h, w, h)))
        reach = round(MAX_REACH * side)
        ux1, uy1 = max(min(ux1, px1), gx1 - reach), max(min(uy1, py1), gy1 - reach)
        ux2, uy2 = min(max(ux2, px2), gx2 + reach), min(max(uy2, py2), gy2 + reach)
    pad = max(MIN_PAD_PX, round(CONTEXT_FRAC * side))
    x1, y1 = max(0, min(ux1 - pad, w)), max(0, min(uy1 - pad, h))
    x2, y2 = max(0, min(ux2 + pad, w)), max(0, min(uy2 + pad, h))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_crops.py`
Expected: 6 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 807 passed.

```bash
git add src/deeplabeling/core/crops.py tests/core/test_crops.py
git commit -m "core: the review crop, the label its subject and the model's box widening it only so far" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Dismissals

**Files:**
- Create: `src/deeplabeling/core/dismissals.py`, `tests/core/test_dismissals.py`
- Modify: `src/deeplabeling/core/workspace.py`

**Interfaces:**
- Consumes: `atomic.write_atomic` and `state.set_aside`, as the review marks use them.
- Produces:
  - `Dismissals(path, root)`, with these members:
    - `has(rel, line, kind)`;
    - `dismiss(...)` and `undismiss(...)`, each returning a bool;
    - `toggle(...)`, which returns the new state;
    - `snapshot() -> frozenset`;
    - `save()`;
    - `warning`, `dirty` and `path`.
  - `Workspace.dismissals`, opened at `dismissals.json` in the dataset's state folder and saved with the workspace. Its warning joins `Workspace.warnings`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_dismissals.py`:

```python
"""Findings looked at and judged fine (docs/design/2026-10-06-find-bad.md#dismissals)."""

import json

from deeplabeling.core.dismissals import Dismissals

CAR = ("camA/images/0001.jpg", "1 0.250000 0.250000 0.100000 0.100000", "wrong class")


def dismissals(tmp_path):
    return Dismissals(tmp_path / "dismissals.json", tmp_path / "root")


def test_a_dismissal_is_the_image_the_line_as_it_is_and_the_kind(tmp_path):
    d = dismissals(tmp_path)
    assert d.dismiss(*CAR) and not d.dismiss(*CAR)
    assert d.has(*CAR)
    assert not d.has(CAR[0], "1 0.300000 0.250000 0.100000 0.100000", CAR[2])     # the line edited since
    assert not d.has(CAR[0], CAR[1], "weakly seen")                             # another kind
    assert d.toggle(*CAR) is False and not d.has(*CAR) and d.toggle(*CAR) is True


def test_a_snapshot_is_safe_to_hand_to_a_worker(tmp_path):
    d = dismissals(tmp_path)
    d.dismiss(*CAR)
    snap = d.snapshot()
    d.undismiss(*CAR)
    assert snap == frozenset({CAR}) and d.snapshot() == frozenset()


def test_save_writes_version_root_and_dismissals_and_reloads(tmp_path):
    d = dismissals(tmp_path)
    d.dismiss(*CAR)
    assert d.save() and not d.dirty
    data = json.loads((tmp_path / "dismissals.json").read_text())
    assert data == {"version": 1, "root": str(tmp_path / "root"), "dismissed": [list(CAR)]}
    assert dismissals(tmp_path).has(*CAR)


def test_nothing_to_save_writes_nothing(tmp_path):
    assert not dismissals(tmp_path).save()
    assert not (tmp_path / "dismissals.json").exists()


def test_an_unreadable_file_is_kept_and_dismissals_start_empty(tmp_path):
    (tmp_path / "dismissals.json").write_bytes(b"{broken")
    d = dismissals(tmp_path)
    assert d.snapshot() == frozenset() and "kept as" in d.warning
    d.dismiss(*CAR)
    assert d.save()
    kept = [p for p in tmp_path.iterdir() if ".unreadable-" in p.name]
    assert len(kept) == 1 and kept[0].read_bytes() == b"{broken"


def test_a_bad_entry_is_skipped_and_said(tmp_path):
    (tmp_path / "dismissals.json").write_text('{"version": 1, "dismissed": [["a", "0 1 1 1 1", "wrong class"], ["b"]]}')
    d = dismissals(tmp_path)
    assert d.snapshot() == {("a", "0 1 1 1 1", "wrong class")} and "1 dismissal" in d.warning


def test_a_workspace_keeps_and_saves_its_dataset_s_dismissals(ds):
    from deeplabeling.core.workspace import Workspace

    ws = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    ws.dismissals.dismiss(*CAR)
    ws.close()
    again = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    try:
        assert again.dismissals.has(*CAR) and again.dismissals.path.name == "dismissals.json"
    finally:
        again.close()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_dismissals.py`
Expected: `No module named 'deeplabeling.core.dismissals'`.

- [ ] **Step 3: The store, kept by the workspace**

Create `src/deeplabeling/core/dismissals.py`:

```python
"""Findings looked at and judged fine (docs/design/2026-10-06-find-bad.md#dismissals).

A dismissal is (image, the label line as it is, the finding kind), saved atomically as
{"version": 1, "root": ..., "dismissed": [[rel, line, kind], ...]}. Editing the label
changes its line, so its dismissals no longer match; a new model does not resurface them.
Dismissing is not an edit: undo leaves it alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from .atomic import write_atomic
from .state import set_aside

SCHEMA_VERSION = 1

Dismissal = tuple[str, str, str]        #: (dataset-relative image, label line, kind)


class Dismissals:
    def __init__(self, path: Path, root: Path):
        self.path = Path(path)
        self.root = Path(root)
        self._items: set[Dismissal] = set()
        self.dirty = False
        self.warning = ""
        self.writable = True
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_bytes())
            stored = data["dismissed"]
            if not isinstance(stored, list):
                raise TypeError("dismissed is not a list")
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.warning, self.writable = set_aside(self.path, e)
            return
        bad = 0
        for entry in stored:
            if isinstance(entry, list) and len(entry) == 3 and all(isinstance(v, str) for v in entry):
                self._items.add(tuple(entry))
            else:
                bad += 1
        if bad:
            self.warning = f"{bad} dismissal(s) in {self.path.name} could not be read and were skipped"

    def has(self, rel: str, line: str, kind: str) -> bool:
        return (rel, line, kind) in self._items

    def snapshot(self) -> frozenset[Dismissal]:
        """A copy, safe to hand to a worker thread."""
        return frozenset(self._items)

    def dismiss(self, rel: str, line: str, kind: str) -> bool:
        """False when it already was."""
        if (rel, line, kind) in self._items:
            return False
        self._items.add((rel, line, kind))
        self.dirty = True
        return True

    def undismiss(self, rel: str, line: str, kind: str) -> bool:
        if (rel, line, kind) not in self._items:
            return False
        self._items.discard((rel, line, kind))
        self.dirty = True
        return True

    def toggle(self, rel: str, line: str, kind: str) -> bool:
        """Flip one; its new state."""
        if self.undismiss(rel, line, kind):
            return False
        self.dismiss(rel, line, kind)
        return True

    def save(self) -> bool:
        if not self.dirty or not self.writable:
            return False
        payload = {"version": SCHEMA_VERSION, "root": str(self.root),
                   "dismissed": [list(d) for d in sorted(self._items)]}
        write_atomic(self.path, json.dumps(payload, indent=1).encode())
        self.dirty = False
        return True
```

In `src/deeplabeling/core/workspace.py`, replace:

```python

from .dataset import Dataset
from .editor import Editor
from .history import History
```

with:

```python

from .dataset import Dataset
from .dismissals import Dismissals
from .editor import Editor
from .history import History
```

In `src/deeplabeling/core/workspace.py`, replace:

```python
    editor: Editor
    predictions: PredictionStore
    sizes: ImageSizes = field(default_factory=ImageSizes)   #: its images' sizes, read from headers

```

with:

```python
    editor: Editor
    predictions: PredictionStore
    dismissals: Dismissals
    sizes: ImageSizes = field(default_factory=ImageSizes)   #: its images' sizes, read from headers

```

In `src/deeplabeling/core/workspace.py`, replace:

```python
                            on_history_changed=on_history_changed)
            predictions = PredictionStore(directory / STORE_NAME)
        except BaseException:
            lock.release()
```

with:

```python
                            on_history_changed=on_history_changed)
            predictions = PredictionStore(directory / STORE_NAME)
            dismissals = Dismissals(directory / "dismissals.json", dataset.root)
        except BaseException:
            lock.release()
```

In `src/deeplabeling/core/workspace.py`, replace:

```python
        return cls(dataset, directory, lock, file, root,
                   Settings(file, "opening", ("openings", dataset.opening_key)),
                   review, store, history, editor, predictions)

    @property
    def warnings(self) -> tuple[str, ...]:
        """State files that could not be read, for the notice strip."""
        return tuple(w for w in (self.file.warning, self.review.warning, self.predictions.warning) if w)

    def save(self) -> None:
        self.review.save()
        self.file.save()

```

with:

```python
        return cls(dataset, directory, lock, file, root,
                   Settings(file, "opening", ("openings", dataset.opening_key)),
                   review, store, history, editor, predictions, dismissals)

    @property
    def warnings(self) -> tuple[str, ...]:
        """State files that could not be read, for the notice strip."""
        return tuple(w for w in (self.file.warning, self.review.warning, self.predictions.warning,
                                 self.dismissals.warning) if w)

    def save(self) -> None:
        self.review.save()
        self.dismissals.save()
        self.file.save()

```

- [ ] **Step 4: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_dismissals.py tests/core/test_workspace.py`
Expected: 19 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 814 passed.

```bash
git add src/deeplabeling/core/dismissals.py src/deeplabeling/core/workspace.py tests/core/test_dismissals.py
git commit -m "core: dismissals, kept per dataset while the label is unchanged" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Queues ordered by their items' own key

**Files:**
- Modify: `src/deeplabeling/core/queue.py`, `tests/core/test_queue.py`

**Interfaces:**
- Consumes: plan 3b's bisected `Queue`; `edits.LineRef`.
- Produces:
  - `QueueItem(key, entry, rank=(), focus=None, finding=None)`, with `.sort_key`, which is `rank`, or `(entry.order,)` when the rank is empty.
  - In `Queue`:
    - `has_image(rel)` and `keys_of(rel)`;
    - `extend` refuses an item out of order (`ValueError`);
    - `insert` places an item by its sort key;
    - `recheck(entry, ctx)` asks `source.holds(item, ctx)` for each of the image's items.
  - `ImageFilter.holds(item, ctx)` and `ImageFilter.items_for(entry, ctx)`, and `build(..., progress=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/core/test_queue.py`:

```python
def test_a_queue_keeps_its_items_in_their_own_order(dataset):
    """A queue of findings is ordered by kind and score, not by image."""
    e = dataset.images
    items = [QueueItem(f"{e[3].rel}#0#wrong class", e[3], rank=(0, -0.9, e[3].order, 0)),
             QueueItem(f"{e[0].rel}#1#wrong class", e[0], rank=(0, -0.8, e[0].order, 1)),
             QueueItem(f"{e[0].rel}#0#not an object", e[0], rank=(1, -1.0, e[0].order, 0))]
    queue = Queue(ImageFilter())
    queue.extend(items)
    late = QueueItem(f"{e[5].rel}#0#wrong class", e[5], rank=(0, -0.85, e[5].order, 0))
    assert queue.insert(late) == 1
    assert [it.key for it in queue.items] == [items[0].key, late.key, items[1].key, items[2].key]
    assert queue.has_image(e[0].rel) and queue.keys_of(e[0].rel) == [items[1].key, items[2].key]
    assert queue.index_of(items[2].key) == 3 and not queue.has_image(e[1].rel)


def test_a_queue_refuses_items_out_of_their_order(dataset):
    e = dataset.images
    queue = Queue(ImageFilter())
    queue.extend([QueueItem(e[1].rel, e[1])])
    with pytest.raises(ValueError, match="out of order"):
        queue.extend([QueueItem(e[0].rel, e[0])])


def test_each_item_of_a_changed_image_is_rechecked_by_its_source(dataset, ctx):
    e = dataset.images[0]

    class OneHolds(ImageFilter):
        def holds(self, item, ctx):
            return item.key.endswith("#keep")

    queue = Queue(OneHolds())
    queue.extend([QueueItem(f"{e.rel}#keep", e, rank=(0,)), QueueItem(f"{e.rel}#gone", e, rank=(1,))])
    queue.recheck(e, ctx)
    assert queue.stale == {f"{e.rel}#gone"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_queue.py`
Expected: 3 failed, 39 passed.

- [ ] **Step 3: Rank items, index them by image, and recheck through the source**

In `src/deeplabeling/core/queue.py`, replace:

```python
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import ClassVar

from .classmap import ClassMap
from .dataset import Dataset, ImageEntry
from .disagree import unlabelled_predictions, unseen_labels
from .imagesize import ImageSizes, image_size
from .inference import FLOOR, Prediction
```

with:

```python
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from .classmap import ClassMap
from .dataset import Dataset, ImageEntry
from .disagree import unlabelled_predictions, unseen_labels
from .edits import LineRef
from .imagesize import ImageSizes, image_size
from .inference import FLOOR, Prediction
```

In `src/deeplabeling/core/queue.py`, replace:

```python
    key: str
    entry: ImageEntry


```

with:

```python
    key: str
    entry: ImageEntry
    rank: tuple = ()                #: where it sorts in its queue; () is dataset order
    focus: LineRef | None = None    #: the label line it is about: a finding's
    finding: Any = None             #: the findings.Finding it stands for, in a findings queue

    @property
    def sort_key(self) -> tuple:
        return self.rank or (self.entry.order,)


```

In `src/deeplabeling/core/queue.py`, replace:

```python
        return f"{text} in {' + '.join(self.splits)}" if self.splits else text

    def matches(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        if self.splits and entry.split not in self.splits:
```

with:

```python
        return f"{text} in {' + '.join(self.splits)}" if self.splits else text

    def holds(self, item: QueueItem, ctx: BuildContext) -> bool:
        """Whether an item still belongs: its image still matches."""
        return self.matches(item.entry, ctx)

    def items_for(self, entry: ImageEntry, ctx: BuildContext) -> list[QueueItem]:
        """The items one image stands behind: itself when it matches."""
        return [QueueItem(entry.rel, entry)] if self.matches(entry, ctx) else []

    def matches(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        if self.splits and entry.split not in self.splits:
```

In `src/deeplabeling/core/queue.py`, replace:

```python
    def build(self, ctx: BuildContext, emit: Callable[[list[QueueItem]], None],
              cancelled: Callable[[], bool] = lambda: False, *,
              batch: int = 500, interval: float = 0.2) -> bool:
        """Stream the matching items to `emit`. False when cancelled part-way."""
        pending: list[QueueItem] = []
```

with:

```python
    def build(self, ctx: BuildContext, emit: Callable[[list[QueueItem]], None],
              cancelled: Callable[[], bool] = lambda: False, *,
              batch: int = 500, interval: float = 0.2, progress=None) -> bool:
        """Stream the matching items to `emit`. False when cancelled part-way."""
        pending: list[QueueItem] = []
```

In `src/deeplabeling/core/queue.py`, replace:

```python

class Queue:
    """A queue's items in dataset order, one cursor (an identity key), and which items no
    longer match since the queue was built. Used on the GUI thread.

    Rows are found by bisecting the items' dataset orders, never stored: an image joining
    a 45k-item queue after its build (a pass filling a model queue) then costs two list
    insertions, not a re-numbering of every row after it."""

    def __init__(self, source: ImageFilter, *, follow: ImageEntry | None = None):
        self.source = source
        self.items: list[QueueItem] = []
```

with:

```python

class Queue:
    """A queue's items in their order -- dataset order for an image queue, kind and score
    for findings -- with one cursor (an identity key), and which items no longer hold since
    the queue was built. Used on the GUI thread.

    Rows are found by bisecting the items' sort keys, never stored: an item joining a
    45k-item queue after its build costs two list insertions, not a re-numbering of every
    row after it. An image may stand behind several items (its findings)."""

    def __init__(self, source, *, follow: ImageEntry | None = None):
        self.source = source
        self.items: list[QueueItem] = []
```

In `src/deeplabeling/core/queue.py`, replace:

```python
        self.waiting = False        #: a model condition waits for a model: nothing is built yet
        self.built_with = None      #: the model (key, class map) its build read, if any
        self._order: dict[str, int] = {}    #: each item's dataset order, by key
        self._orders: list[int] = []        #: the items' dataset orders, row by row: ascending
        self._follow = follow       #: the item the cursor was on before a rebuild
        self._moved = False
```

with:

```python
        self.waiting = False        #: a model condition waits for a model: nothing is built yet
        self.built_with = None      #: the model (key, class map) its build read, if any
        self._rank: dict[str, tuple] = {}           #: each item's sort key, by key
        self._ranks: list[tuple] = []               #: the items' sort keys, row by row: ascending
        self._by_image: dict[str, list[str]] = {}   #: the keys of each image's items
        self._follow = follow       #: the item the cursor was on before a rebuild
        self._moved = False
```

In `src/deeplabeling/core/queue.py`, replace:

```python

    def __contains__(self, key: str) -> bool:
        return key in self._order

    def _row(self, key: str) -> int:
        return bisect.bisect_left(self._orders, self._order[key])

    def extend(self, batch: Iterable[QueueItem]) -> None:
        for item in batch:
            if item.key in self._order:
                continue
            order = item.entry.order
            if self._orders and order < self._orders[-1]:
                raise ValueError(f"{item.key} arrives out of dataset order")
            self._order[item.key] = order
            self.items.append(item)
            self._orders.append(order)
            if self._follow is not None and not self._moved and item.key == self._follow.rel:
                self.cursor = item.key
```

with:

```python

    def __contains__(self, key: str) -> bool:
        return key in self._rank

    def has_image(self, rel: str) -> bool:
        return rel in self._by_image

    def keys_of(self, rel: str) -> list[str]:
        """The keys of the items an image stands behind, in queue order."""
        return sorted(self._by_image.get(rel, ()), key=self._rank.__getitem__)

    def _row(self, key: str) -> int:
        return bisect.bisect_left(self._ranks, self._rank[key])

    def _add(self, row: int, item: QueueItem) -> None:
        self.items.insert(row, item)
        self._ranks.insert(row, item.sort_key)
        self._rank[item.key] = item.sort_key
        self._by_image.setdefault(item.entry.rel, []).append(item.key)

    def extend(self, batch: Iterable[QueueItem]) -> None:
        for item in batch:
            if item.key in self._rank:
                continue
            if self._ranks and item.sort_key < self._ranks[-1]:
                raise ValueError(f"{item.key} arrives out of order")
            self._add(len(self.items), item)
            if self._follow is not None and not self._moved and item.key == self._follow.rel:
                self.cursor = item.key
```

In `src/deeplabeling/core/queue.py`, replace:

```python

    def insert(self, item: QueueItem) -> int | None:
        """Add an item after the build, in dataset order: an image whose predictions have
        arrived. Its row, or None when it is already there."""
        if item.key in self._order:
            return None
        row = bisect.bisect_right(self._orders, item.entry.order)
        self.items.insert(row, item)
        self._orders.insert(row, item.entry.order)
        self._order[item.key] = item.entry.order
        if self.cursor is None:
            self.cursor = item.key
```

with:

```python

    def insert(self, item: QueueItem) -> int | None:
        """Add an item after the build, in its place: an image whose predictions have
        arrived. Its row, or None when it is already there."""
        if item.key in self._rank:
            return None
        row = bisect.bisect_right(self._ranks, item.sort_key)
        self._add(row, item)
        if self.cursor is None:
            self.cursor = item.key
```

In `src/deeplabeling/core/queue.py`, replace:

```python
    def index_of(self, key: str) -> int | None:
        """The row of the item with this key, or None when it is not in the queue."""
        return self._row(key) if key in self._order else None

    def move(self, delta: int) -> bool:
```

with:

```python
    def index_of(self, key: str) -> int | None:
        """The row of the item with this key, or None when it is not in the queue."""
        return self._row(key) if key in self._rank else None

    def move(self, delta: int) -> bool:
```

In `src/deeplabeling/core/queue.py`, replace:

```python

    def go_to(self, key: str) -> bool:
        return key in self._order and self._set(key)

    def _set(self, key: str) -> bool:
```

with:

```python

    def go_to(self, key: str) -> bool:
        return key in self._rank and self._set(key)

    def _set(self, key: str) -> bool:
```

In `src/deeplabeling/core/queue.py`, replace:

```python

    def recheck(self, entry: ImageEntry, ctx: BuildContext) -> None:
        """After `entry` changed: mark its item stale while it no longer matches."""
        if entry.rel not in self._order:
            return
        if self.source.matches(entry, ctx):
            self.stale.discard(entry.rel)
        else:
            self.stale.add(entry.rel)
```

with:

```python

    def recheck(self, entry: ImageEntry, ctx: BuildContext) -> None:
        """After `entry` changed: mark each of its items stale while it no longer holds."""
        for key in self.keys_of(entry.rel):
            if self.source.holds(self.items[self._row(key)], ctx):
                self.stale.discard(key)
            else:
                self.stale.add(key)
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_queue.py tests/ui/test_filter_queue.py tests/ui/test_panels.py`
Expected: 71 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 817 passed.

```bash
git add src/deeplabeling/core/queue.py tests/core/test_queue.py
git commit -m "core: a queue keeps its items in their own order, several to an image, each rechecked by its source" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The Findings source

**Files:**
- Create: `tests/core/test_findings_source.py`
- Modify: `src/deeplabeling/core/findings.py`, `src/deeplabeling/core/queue.py`

**Interfaces:**
- Consumes:
  - from Tasks 1 and 4: `judge`, `FindSettings`, `KINDS`, `QueueItem(rank, focus, finding)`, `Queue`;
  - from slice 3: `BuildContext` (`model`, `predictions`, `count`).
- Produces:
  - `Findings(scope=ImageFilter(), settings=FindSettings())`, with these members:
    - `needs_model = True`;
    - `items_for(entry, ctx)`;
    - `build(ctx, emit, cancelled, *, batch, interval, progress)`;
    - `holds(item, ctx)`, `matches(entry, ctx)`, `highlight`, `highlight_predictions`;
    - `describe(dataset)`;
    - `to_json()` / `from_json(data)`, whose JSON is `{"source": "findings", "scope": …, "settings": …}`.
  - An item's key is `rel#line#kind`, its rank `(kind index, −score, order, line)`, its focus `LineRef(line, label class, label box)`, and its `finding` the `Finding`.
  - `BuildContext.dismissed`, a snapshot of `(rel, line text, kind)`.
  - `queue.source_from_json(data)`, which returns an `ImageFilter` or a `Findings`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_findings_source.py`:

```python
"""Findings as a queue source (docs/design/2026-10-06-find-bad.md#the-queue)."""

import pytest

from deeplabeling.core.classmap import ClassMap
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import LineRef
from deeplabeling.core.findings import Findings, FindSettings
from deeplabeling.core.inference import Prediction
from deeplabeling.core.predstore import PredictionStore, image_stamp
from deeplabeling.core.queue import BuildContext, ImageFilter, ModelSnapshot, Queue, source_from_json
from deeplabeling.core.store import LabelStore

KEY = "fake:best.pt"
MODEL = ("car", "person", "bus", "truck")
CAR, PERSON, BUS = (0.25, 0.25, 0.1, 0.1), (0.5, 0.5, 0.2, 0.3), (0.75, 0.75, 0.15, 0.15)


def P(cls, box, conf):
    return Prediction(cls, box, conf)


ROWS = {
    "camA/images/0001.jpg": [P(1, CAR, 0.8), P(1, PERSON, 0.9)],        # the car: a person, 0.8
    "camA/images/0002.jpg": [],                                          # a negative
    "camA/images/0003.jpg": [P(0, CAR, 0.9)],                            # no label file
    "camA/images/sub/0005.jpg": [P(0, BUS, 0.95)],                       # the bus_m: a car, 0.95
    "camB/images/0001.jpg": [],                                          # the bus_m: nothing there
    "weird/images/имя пробел.jpg": [P(1, (0.5, 0.5, 0.1, 0.1), 0.5)],    # the person, seen weakly
}
EXPECTED = ["camA/images/sub/0005.jpg#0#wrong class", "camA/images/0001.jpg#1#wrong class",
            "camB/images/0001.jpg#0#not an object"]


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


@pytest.fixture
def store(dataset, tmp_path):
    s = PredictionStore(tmp_path / "predictions.sqlite")
    for rel, preds in ROWS.items():
        s.put(KEY, rel, image_stamp(dataset.root / rel), preds)
    yield s
    s.close()


@pytest.fixture
def make_ctx(dataset, store):
    cmap = ClassMap.seeded(MODEL, dataset.names).with_target(2, "bus_m")
    labels = LabelStore(dataset)
    return lambda **kw: BuildContext(dataset, labels, frozenset(), model=ModelSnapshot(KEY, store, cmap), **kw)


def built(source, ctx, **kw):
    batches = []
    assert source.build(ctx, batches.append, **kw)
    return [item for batch in batches for item in batch]


def test_findings_come_ordered_by_kind_then_score(make_ctx):
    ctx = make_ctx()
    items = built(Findings(), ctx)
    assert [item.key for item in items] == EXPECTED
    car = items[1]
    assert car.focus == LineRef(1, 1, CAR) and car.finding.kind == "wrong class" and car.finding.model_cls == 0
    assert ctx.unsettled == {"not inferred": 9}


def test_weakly_seen_findings_come_last_when_asked_for(make_ctx):
    items = built(Findings(settings=FindSettings(weak=True)), make_ctx())
    assert [item.key for item in items] == EXPECTED + ["weird/images/имя пробел.jpg#0#weakly seen"]


def test_a_dismissed_finding_is_left_out(make_ctx):
    dismissed = frozenset({("camA/images/0001.jpg", "1 0.250000 0.250000 0.100000 0.100000", "wrong class")})
    assert [item.key for item in built(Findings(), make_ctx(dismissed=dismissed))] == [EXPECTED[0], EXPECTED[2]]


def test_the_scope_chooses_the_images(make_ctx):
    ctx = make_ctx()
    assert built(Findings(scope=ImageFilter(splits=("val",))), ctx) == []
    assert ctx.unsettled == {"not inferred": 5}


def test_without_a_model_nothing_is_found_and_it_is_said(dataset):
    ctx = BuildContext(dataset, LabelStore(dataset), frozenset())
    assert built(Findings(), ctx) == [] and ctx.unsettled == {"no model": 15}


def test_the_scan_says_how_far_it_is(make_ctx):
    said = []
    built(Findings(), make_ctx(), progress=lambda n, total: said.append((n, total)))
    assert said[-1] == (15, 15)


def test_a_finding_queue_holds_its_items_in_their_order_and_rechecks_them(make_ctx, dataset, ds):
    ctx = make_ctx()
    queue = Queue(Findings())
    queue.extend(built(Findings(), ctx))
    assert [item.key for item in queue.items] == EXPECTED
    ds.lbl("camA/0001").write_text("0 0.500000 0.500000 0.200000 0.300000\n0 0.250000 0.250000 0.100000 0.100000\n")
    queue.recheck(dataset.entry(dataset.root / "camA/images/0001.jpg"), make_ctx())  # the car is a person now
    assert queue.stale == {EXPECTED[1]}


@pytest.mark.parametrize("source, text", [
    (Findings(), "findings: wrong class, not an object (conf ≥ 0.40)"),
    (Findings(ImageFilter(splits=("val",)), FindSettings(weak=True, floor=0.5)),
     "findings: wrong class, not an object, weakly seen (conf ≥ 0.50) of all images in val"),
])
def test_a_findings_queue_reads_as_words_and_survives_its_json(source, text, dataset):
    assert source.describe(dataset) == text and source.needs_model
    assert source_from_json(source.to_json()) == source
    assert source_from_json(ImageFilter(splits=("val",)).to_json()) == ImageFilter(splits=("val",))
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_findings_source.py`
Expected: `cannot import name 'Findings'`.

- [ ] **Step 3: Scan, order, and save a findings queue**

In `src/deeplabeling/core/findings.py`, replace:

```python
from __future__ import annotations

from dataclasses import dataclass

from .classmap import ClassMap
```

with:

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import ClassVar

from .classmap import ClassMap
```

In `src/deeplabeling/core/findings.py`, replace:

```python
from .disagree import checkable
from .geometry import Box, iou
from .inference import FLOOR, Prediction
from .ranges import range_error
from .store import ImageLabels
```

with:

```python
from .disagree import checkable
from .geometry import Box, iou
from .edits import LineRef
from .inference import FLOOR, Prediction
from .queue import BuildContext, ImageFilter, QueueItem
from .ranges import range_error
from .store import ImageLabels
```

In `src/deeplabeling/core/findings.py`, replace:

```python
                found.append(Finding(kind="not an object", score=1 - near, **base, **model))
    return found
```

with:

```python
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

    def holds(self, item: QueueItem, ctx: BuildContext) -> bool:
        """Whether a finding is still there: its image judged again finds it."""
        return any(it.key == item.key for it in self.items_for(item.entry, ctx))

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
```

In `src/deeplabeling/core/queue.py`, replace:

```python
    sizes: ImageSizes | None = None     #: the open dataset's size cache, when there is one
    model: ModelSnapshot | None = None  #: the loaded model, when a condition asks for it
    #: Images a condition could not settle ("could not be sized", "not inferred"), counted
    #: for the queue chip. One build or recheck owns it; it is never shared across threads.
```

with:

```python
    sizes: ImageSizes | None = None     #: the open dataset's size cache, when there is one
    model: ModelSnapshot | None = None  #: the loaded model, when a condition asks for it
    #: Dismissed findings, (image, label line, kind), snapshotted before the build.
    dismissed: frozenset[tuple[str, str, str]] = frozenset()
    #: Images a condition could not settle ("could not be sized", "not inferred"), counted
    #: for the queue chip. One build or recheck owns it; it is never shared across threads.
```

In `src/deeplabeling/core/queue.py`, replace:

```python
            else:
                self.stale.add(key)
```

with:

```python
            else:
                self.stale.add(key)


def source_from_json(data):
    """A saved queue's source: an image filter, or Find Bad's findings."""
    if isinstance(data, dict) and data.get("source") == "findings":
        from .findings import Findings              # findings.py builds on this module
        return Findings.from_json(data)
    return ImageFilter.from_json(data)
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/core/test_findings_source.py tests/core/test_findings.py tests/core/test_queue.py tests/core/test_core_imports_no_qt.py`
Expected: 69 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 826 passed.

```bash
git add src/deeplabeling/core/findings.py src/deeplabeling/core/queue.py tests/core/test_findings_source.py
git commit -m "core: Find Bad as a queue source, its findings ordered by kind and score" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The status

**Files:**
- Modify: `CLAUDE.md`, `docs/design/2026-10-06-find-bad.md`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: the status.

- [ ] **Step 1: Update the status**

In `CLAUDE.md`, replace:

````markdown
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. The design and the plans are in [docs/design/](docs/design/).

```sh
````

with:

````markdown
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. Slice 4 (Find Bad) has its core built; its full frame (plan 4b) is next. The
design and the plans are in [docs/design/](docs/design/).

```sh
````

In `docs/design/2026-10-06-find-bad.md`, replace:

```markdown
# DeepLabeling — slice 4: Find Bad

**Status:** approved 2026-10-06 · plans 4a (the core), 4b (the full frame) and 4c (the grid) next
**Scope:** slice 4 of [the app foundation](2026-10-04-app-foundation.md#slices): a queue whose
items are the labels the model disagrees with, each focused on its label line; crop tiles in
```

with:

```markdown
# DeepLabeling — slice 4: Find Bad

**Status:** approved 2026-10-06 · plan 4a (the core) implemented; 4b (the full frame) and 4c (the grid) next
**Scope:** slice 4 of [the app foundation](2026-10-04-app-foundation.md#slices): a queue whose
items are the labels the model disagrees with, each focused on its label line; crop tiles in
```

- [ ] **Step 2: Check the docs, run the full suite, and commit**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 826 passed.

```bash
git add CLAUDE.md docs/design/2026-10-06-find-bad.md
git commit -m "docs: slice 4's core is built" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
