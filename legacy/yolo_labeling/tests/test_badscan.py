"""What a model's predictions say about one labelled box.

Pure logic, no Tk, no model: predictions are `(cls, conf, x1, y1, x2, y2)` in
pixels, already narrowed to the shared confidence floor, exactly as the scan
worker hands them over.

The two rules every threshold here follows:

1. An upper confidence bound never removes a prediction from MATCHING -- it only
   limits which findings are REPORTED. Otherwise a box the model sees at 0.95
   becomes "not an object" the moment the ceiling drops below 0.95.
2. A kind's findings never depend on which other kinds are switched on.
"""

from __future__ import annotations

import itertools

import pytest

from yolo_labeling.core import badscan as B

GT = (10.0, 10.0, 50.0, 50.0)
SAME = (10.0, 10.0, 50.0, 50.0)                 # IoU 1.0 with GT
SHIFTED = (14.0, 10.0, 54.0, 50.0)              # IoU ~0.82 with GT
FAR = (200.0, 200.0, 240.0, 240.0)              # IoU 0


def same_class(a, b):
    return a == b


def cfg(**kw):
    return B.ScanConfig(**kw)


def classify(gt_cls, preds, **kw):
    return B.classify_gt(gt_cls, GT, preds, cfg(**kw), same_class)


# -- rule 1: the ceiling never hides a prediction --------------------------


def test_a_strongly_seen_box_is_never_not_an_object_whatever_the_ceiling():
    """The bug the naive reading of 'a range' would introduce."""
    preds = [(5, 0.95, *SAME)]
    assert classify(5, preds, mismatch_max=0.6) is None


def test_a_confident_wrong_class_is_hidden_by_a_low_ceiling():
    preds = [(4, 0.95, *SAME)]
    assert classify(5, preds, mismatch_max=0.6) is None


def test_a_wrong_class_inside_the_range_is_reported():
    preds = [(4, 0.5, *SAME)]
    f = classify(5, preds, mismatch_max=0.6)
    assert f.kind == 'class_mismatch'
    assert f.pred[0] == 4 and f.score == pytest.approx(0.5)


def test_the_ceiling_is_inclusive():
    f = classify(5, [(4, 0.6, *SAME)], mismatch_max=0.6)
    assert f is not None and f.kind == 'class_mismatch'


# -- deciding between duplicate boxes on one object -----------------------


def test_per_class_nms_duplicates_are_decided_by_confidence_not_overlap():
    """Ultralytics runs NMS per class by default, so one car routinely yields a
    confident 'car' and a weak 'truck'. Deciding on the higher-IoU box made the
    verdict flip on a 0.02 IoU difference."""
    preds = [(6, 0.35, *SHIFTED), (5, 0.80, *SAME)]
    assert classify(5, preds) is None, "GT car: the model is confident it is a car"


def test_the_confident_box_is_also_what_exposes_a_real_error():
    preds = [(6, 0.35, *SAME), (5, 0.80, *SHIFTED)]
    f = classify(6, preds)
    assert f.kind == 'class_mismatch'
    assert f.pred[0] == 5 and f.pred[1] == pytest.approx(0.80)


def test_an_unmapped_deciding_box_is_inconclusive():
    """The model's strongest opinion has no dataset class: it says nothing about
    whether the label's class is right, and it must not be overridden by a
    weaker mapped box either."""
    preds = [(None, 0.9, *SAME), (4, 0.4, *SAME)]
    assert classify(5, preds) is None


def test_an_unmapped_box_still_proves_something_is_there():
    assert classify(5, [(None, 0.9, *SAME)]) is None


# -- not an object --------------------------------------------------------


def test_nothing_there_is_not_an_object():
    f = classify(5, [])
    assert f.kind == 'missing' and f.iou == 0.0 and f.pred is None
    assert f.score == pytest.approx(1.0)


def test_the_band_separates_stray_from_misaligned():
    """Near 0: nothing there, delete. Higher: the model sees it, redraw."""
    loose = (20.0, 20.0, 60.0, 60.0)           # IoU ~0.39 with GT
    stray = classify(5, [], missing_iou_lo=0.0, missing_iou_hi=0.05)
    assert stray is not None and stray.kind == 'missing'
    assert classify(5, [(5, 0.9, *loose)], missing_iou_lo=0.0, missing_iou_hi=0.05) is None

    misaligned = classify(5, [(5, 0.9, *loose)], missing_iou_lo=0.1, missing_iou_hi=0.5)
    assert misaligned.kind == 'missing'
    assert 0.1 <= misaligned.iou <= 0.5
    assert classify(5, [], missing_iou_lo=0.1, missing_iou_hi=0.5) is None


def test_the_band_follows_the_matching_iou_by_default():
    """`missing_iou_hi=None` means 'up to the matching IoU', so raising the
    matching IoU later never opens a silent gap."""
    loose = (20.0, 20.0, 60.0, 60.0)           # IoU ~0.39
    f = classify(5, [(5, 0.9, *loose)], iou_match=0.5, missing_iou_hi=None)
    assert f.kind == 'missing'
    assert classify(5, [(5, 0.9, *loose)], iou_match=0.3) is None, "0.39 now matches"


def test_the_nearest_box_is_kept_only_when_it_is_comparable():
    """The crop is the union of both boxes; a huge nearest box at a sliver of
    overlap would shrink a small stray label to a few pixels."""
    loose = (20.0, 20.0, 60.0, 60.0)           # IoU ~0.39 -> kept
    assert classify(5, [(5, 0.9, *loose)]).pred is not None

    huge = (0.0, 0.0, 400.0, 400.0)            # IoU 0.01 -> dropped
    f = classify(5, [(5, 0.9, *huge)])
    assert f.kind == 'missing' and f.pred is None
    assert f.iou == pytest.approx(1600 / 160000)


def test_a_class_the_model_cannot_emit_is_never_not_an_object():
    """Its silence proves nothing -- reporting it recommends deleting valid labels."""
    f = B.classify_gt(5, GT, [], cfg(), same_class, checkable=False)
    assert f is None


def test_an_uncheckable_class_can_still_be_a_wrong_class():
    f = B.classify_gt(5, GT, [(4, 0.9, *SAME)], cfg(), same_class, checkable=False)
    assert f.kind == 'class_mismatch'


# -- weakly seen ----------------------------------------------------------


def test_a_weak_agreement_is_weakly_seen():
    f = classify(5, [(5, 0.45, *SAME)], weak=True, weak_below=0.6)
    assert f.kind == 'weak'
    assert f.score == pytest.approx(0.55), "weakest first"


def test_a_confident_agreement_is_not_weak():
    assert classify(5, [(5, 0.75, *SAME)], weak=True, weak_below=0.6) is None


def test_weak_is_exclusive_of_the_cutoff():
    assert classify(5, [(5, 0.6, *SAME)], weak=True, weak_below=0.6) is None


def test_a_weak_disagreement_is_a_wrong_class_not_weakly_seen():
    f = classify(5, [(4, 0.45, *SAME)], weak=True, weak_below=0.6)
    assert f.kind == 'class_mismatch'


def test_weak_ignores_the_wrong_class_ceiling():
    """The ceiling bounds wrong-class evidence only."""
    f = classify(5, [(5, 0.45, *SAME)], weak=True, weak_below=0.6, mismatch_max=0.3)
    assert f.kind == 'weak'


def test_weak_is_not_reported_under_a_model_says_restriction():
    """In pair mode agreement is raw equality, so 'labelled A, model says B'
    with A != B can never be an agreement. Rather than a kind that silently
    returns nothing, it is off."""
    f = classify(5, [(5, 0.45, *SAME)], weak=True, weak_below=0.6,
                 gt_class=5, pred_class=5)
    assert f is None


# -- the confusion pair ---------------------------------------------------


def test_a_model_says_restriction_filters_wrong_class():
    preds = [(4, 0.9, *SAME)]
    assert classify(5, preds, pred_class=4).kind == 'class_mismatch'
    assert classify(5, preds, pred_class=6) is None


def test_a_model_says_restriction_excludes_not_an_object():
    """A missing entry has no prediction to match the restriction against."""
    assert classify(5, [], pred_class=4) is None


def test_pair_mode_overrides_groups():
    """Naming both sides asks for that raw pair, even within one group."""
    def grouped(a, b):
        return {a, b} <= {2, 3, 4}             # bus_m / bus_l / bus_xl

    preds = [(2, 0.9, *SAME)]
    assert B.classify_gt(3, GT, preds, cfg(), grouped) is None
    f = B.classify_gt(3, GT, preds, cfg(gt_class=3, pred_class=2), grouped)
    assert f.kind == 'class_mismatch'


# -- rule 2: kinds are independent ----------------------------------------


SCENES = [
    [],
    [(5, 0.95, *SAME)],
    [(4, 0.95, *SAME)],
    [(4, 0.50, *SAME)],
    [(5, 0.45, *SAME)],
    [(6, 0.35, *SHIFTED), (5, 0.80, *SAME)],
    [(5, 0.9, 20.0, 20.0, 60.0, 60.0)],
    [(None, 0.9, *SAME)],
    [(5, 0.9, *FAR)],
]
KINDS = ('mismatch', 'missing', 'weak')


@pytest.mark.parametrize("scene", SCENES)
def test_each_kind_finds_the_same_thing_alone_as_together(scene):
    """Ticking 'Weakly seen' must not change what 'Wrong class' finds."""
    base = dict(mismatch_max=0.9, weak_below=0.6, missing_iou_lo=0.0)
    together = classify(5, scene, mismatch=True, missing=True, weak=True, **base)
    for kind in KINDS:
        alone = classify(5, scene, **{k: k == kind for k in KINDS}, **base)
        expected = together if together and _flag(together.kind) == kind else None
        assert alone == expected, f"{kind} alone differs from all-on for {scene}"


def _flag(kind):
    return {'class_mismatch': 'mismatch', 'missing': 'missing', 'weak': 'weak'}[kind]


def test_a_box_gets_at_most_one_finding():
    for scene, on in itertools.product(SCENES, itertools.product([True, False], repeat=3)):
        f = classify(5, scene, **dict(zip(KINDS, on)), weak_below=0.6)
        assert f is None or f.kind in ('class_mismatch', 'missing', 'weak')


# -- the shared matching helpers ------------------------------------------


def test_candidates_are_those_at_or_above_the_matching_iou():
    preds = [(5, 0.9, *SAME), (5, 0.9, *SHIFTED), (5, 0.9, *FAR)]
    got = B.candidates(GT, preds, 0.8)
    assert [p for p, _ in got] == preds[:2]


def test_deciding_breaks_confidence_ties_on_overlap():
    a, b = (5, 0.8, *SHIFTED), (4, 0.8, *SAME)
    pred, _ = B.deciding(B.candidates(GT, [a, b], 0.5))
    assert pred == b


def test_nearest_with_no_overlap_reports_zero():
    assert B.nearest(GT, [(5, 0.9, *FAR)]) == (None, 0.0)
    assert B.nearest(GT, []) == (None, 0.0)
