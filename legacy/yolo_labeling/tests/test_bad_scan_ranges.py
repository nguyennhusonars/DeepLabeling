"""The scan worker with ranges, the 'weak' kind and the checkable-class guard.

`core/badscan.py` is tested on its own in test_badscan.py. These drive the real
`_bad_scan_worker` end to end -- label file in, entries out -- to pin that the
worker hands the right things to it and builds entries from what comes back.
"""

from __future__ import annotations

import queue

import pytest

from yolo_labeling.core.classmap import PredictionClassMap

from test_bad_scan_classmap import (  # noqa: E402  (tests dir is on sys.path)
    MAPPING, SAME_BOX, FakeModel, _Box, _gt, _probe,
)


def _run(app, paths, **overrides):
    """Run the worker synchronously; return (entries, other messages)."""
    config = {"paths": list(paths), "conf": 0.25, "iou_match": 0.5,
              "mismatch": True, "missing": True}
    config.update(overrides)
    app._bad_scan_worker(config)
    entries, other = [], []
    while True:
        try:
            msg = app._bad_scan_queue.get_nowait()
        except queue.Empty:
            break
        if msg[0] == "entry":
            entries.append(msg[1])
        elif msg[0] == "error":                     # pragma: no cover
            pytest.fail(f"scan reported an error: {msg[1]}")
        else:
            other.append(msg)
    return entries, other


@pytest.fixture
def one_image(ds):
    return ds.image("camA/0001.jpg")


def _mapped(monolith, boxes, **kw):
    return _probe(monolith, FakeModel(boxes), PredictionClassMap(mapping=dict(MAPPING)), **kw)


# -- the ceiling ----------------------------------------------------------


def test_a_ceiling_below_the_evidence_hides_a_wrong_class(ds, monolith, one_image):
    _gt(ds, 5)                                            # car
    app = _mapped(monolith, [_Box(4, 0.95, SAME_BOX)])    # model: human 0.95
    assert _run(app, [one_image], mismatch_max=0.6)[0] == []
    entries, _ = _run(_mapped(monolith, [_Box(4, 0.95, SAME_BOX)]), [one_image])
    assert [e["kind"] for e in entries] == ["class_mismatch"]


def test_a_ceiling_never_turns_a_seen_box_into_not_an_object(ds, monolith, one_image):
    _gt(ds, 5)
    app = _mapped(monolith, [_Box(3, 0.95, SAME_BOX)])    # model: car 0.95
    assert _run(app, [one_image], mismatch_max=0.3)[0] == []


def test_an_old_config_without_the_new_keys_behaves_as_before(ds, monolith, one_image):
    """Every existing caller -- and the Qwen-free test suite -- passes the old
    five keys. Missing keys must mean today's behaviour, not an error."""
    _gt(ds, 5)
    entries, _ = _run(_mapped(monolith, []), [one_image])
    assert [e["kind"] for e in entries] == ["missing"]


# -- duplicate boxes on one object ----------------------------------------


def test_nms_duplicates_are_decided_by_the_confident_box(ds, monolith, one_image):
    """car 0.80 and a slightly better-aligned truck 0.35 on one car GT."""
    _gt(ds, 5)
    shifted = (17, 12, 49, 36)
    app = _mapped(monolith, [_Box(6, 0.35, SAME_BOX), _Box(3, 0.80, shifted)])
    assert _run(app, [one_image])[0] == []


# -- weakly seen ----------------------------------------------------------


def test_a_weak_agreement_becomes_a_weak_entry(ds, monolith, one_image):
    _gt(ds, 5)
    app = _mapped(monolith, [_Box(3, 0.45, SAME_BOX)])    # car 0.45 over GT car
    entries, _ = _run(app, [one_image], weak=True, weak_below=0.6)
    assert [e["kind"] for e in entries] == ["weak"]
    e = entries[0]
    assert e["pred_cls_id"] == 5 and e["pred_conf"] == pytest.approx(0.45)
    assert e["pred_bbox_norm"] is not None, "the crop should draw the model's box"
    assert e["score"] == pytest.approx(0.55)


def test_weak_is_off_unless_asked_for(ds, monolith, one_image):
    _gt(ds, 5)
    app = _mapped(monolith, [_Box(3, 0.45, SAME_BOX)])
    assert _run(app, [one_image])[0] == []


# -- not an object: the band and the nearest box --------------------------


def test_a_misaligned_box_records_the_models_box(ds, monolith, one_image):
    """With IoU in the band, the crop must show what the model drew instead."""
    _gt(ds, 5)
    loose = (24, 18, 56, 42)                  # IoU ~0.39 with the GT box
    app = _mapped(monolith, [_Box(3, 0.9, loose)])
    entries, _ = _run(app, [one_image], missing_iou_lo=0.1)
    assert [e["kind"] for e in entries] == ["missing"]
    e = entries[0]
    assert 0.1 <= e["iou"] < 0.5
    assert e["pred_cls_id"] == 5 and e["pred_bbox_norm"] is not None


def test_a_stray_box_carries_no_model_box(ds, monolith, one_image):
    _gt(ds, 5)
    entries, _ = _run(_mapped(monolith, []), [one_image], missing_iou_hi=0.05)
    assert [e["kind"] for e in entries] == ["missing"]
    assert entries[0]["pred_cls_id"] is None
    assert entries[0].get("pred_bbox_norm") is None


def test_the_band_excludes_what_is_outside_it(ds, monolith, one_image):
    _gt(ds, 5)
    loose = (24, 18, 56, 42)
    app = _mapped(monolith, [_Box(3, 0.9, loose)])
    assert _run(app, [one_image], missing_iou_hi=0.05)[0] == [], "0.39 is not stray"


# -- classes the model cannot emit ----------------------------------------


def test_a_class_the_model_cannot_emit_is_not_reported_missing(ds, monolith, one_image):
    """Map has no entry producing 'BSV' (id 1): the model can never see one."""
    _gt(ds, 1)
    cmap = PredictionClassMap(mapping={k: v for k, v in MAPPING.items() if v != 1})
    app = _probe(monolith, FakeModel([]), cmap)
    entries, other = _run(app, [one_image])
    assert entries == []
    assert ("unchecked", 1) in other, "the skip must be visible, not silent"


def test_group_members_of_an_emittable_class_are_checkable(ds, monolith, one_image):
    """bus_l is never emitted, but its group's 'bus' is: silence there IS evidence."""
    from test_bad_scan_classmap import GROUPS

    _gt(ds, 3)                                            # bus_l
    app = _mapped(monolith, [], groups=GROUPS)
    entries, other = _run(app, [one_image])
    assert [e["kind"] for e in entries] == ["missing"]
    assert ("unchecked", 0) in other


def test_without_a_known_model_vocabulary_nothing_is_skipped(ds, monolith, one_image):
    """If we cannot tell what the model emits, we cannot claim it is blind."""
    _gt(ds, 1)
    app = _probe(monolith, FakeModel([]), PredictionClassMap(mapping={}))
    app.model_names = {}
    entries, _ = _run(app, [one_image])
    assert [e["kind"] for e in entries] == ["missing"]


def test_a_precomputed_checkable_set_is_used_as_given(ds, monolith, one_image):
    """`open_bad_label_review` snapshots it on the main thread; the worker must
    not recompute it from class state the user can edit mid-scan."""
    _gt(ds, 5)
    app = _mapped(monolith, [])
    assert _run(app, [one_image], checkable=frozenset())[0] == []
    assert len(_run(_mapped(monolith, []), [one_image], checkable=frozenset({5}))[0]) == 1


# -- captions -------------------------------------------------------------


def _captioner(monolith, floor=0.40):
    from pathlib import Path

    from test_bad_scan_classmap import DATASET
    app = object.__new__(monolith.YOLOLabelingTool)
    app.class_info = {i: {"name": n} for i, n in enumerate(DATASET)}
    app._crop_review_target = None
    app._bad_scan_floor = floor
    return app, Path("/ds/images/f.jpg")


def _entry(path, **kw):
    e = {"img_path": path, "line_idx": 0, "cls_id": 5, "pred_cls_id": None,
         "pred_conf": 0.0, "iou": 0.0, "score": 1.0}
    e.update(kw)
    return e


def test_a_weak_caption_says_the_model_agrees_weakly(monolith):
    app, p = _captioner(monolith)
    text = app._crop_review_caption_text(
        _entry(p, kind="weak", pred_cls_id=5, pred_conf=0.45, pred_bbox_norm=(0.5,) * 4))
    assert "agrees only at 0.45" in text
    assert "→" not in text, "weak used to fall into the class-filter caption"


def test_a_stray_caption_names_the_floor(monolith):
    """'Sees nothing' is untrue if there were predictions below the floor."""
    app, p = _captioner(monolith, floor=0.40)
    text = app._crop_review_caption_text(_entry(p, kind="missing"))
    assert "nothing ≥0.40" in text


def test_a_misaligned_caption_describes_the_models_box(monolith):
    app, p = _captioner(monolith)
    text = app._crop_review_caption_text(_entry(
        p, kind="missing", pred_cls_id=5, pred_conf=0.9, iou=0.39,
        pred_bbox_norm=(0.5,) * 4))
    assert "model's box: car 0.90" in text and "IoU 0.39" in text


def test_an_unmapped_nearest_box_is_called_unmapped(monolith):
    app, p = _captioner(monolith)
    text = app._crop_review_caption_text(_entry(
        p, kind="missing", pred_cls_id=None, pred_conf=0.9, iou=0.39,
        pred_bbox_norm=(0.5,) * 4))
    assert "unmapped" in text and "None" not in text


def test_weak_sorts_after_the_other_kinds():
    from yolo_labeling.ui.crop_review import KIND_ORDER
    assert KIND_ORDER['class_mismatch'] < KIND_ORDER['missing'] < KIND_ORDER['weak']
