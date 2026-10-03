"""The Label/Prediction IoU filter: direction, its own confidence range, and
reading predictions that are actually there.

Before this it read only the in-memory prediction dict, so after a restart --
with every image inferred into the durable cache -- it silently excluded every
image not yet opened this session. It also discarded images where the model saw
nothing, and dropped unmapped classes, which made labels look unmatched.

The 'unmatched predictions' direction is what finds objects nobody labelled.
"""

from __future__ import annotations

import pytest

from yolo_labeling.core import badscan as _badscan
from yolo_labeling.core.classmap import PredictionClassMap

IMG = "/ds/images/f.jpg"
BOX = (10, 10, 50, 50)
FAR = (200, 200, 240, 240)
LOOSE = (20, 20, 60, 60)            # IoU ~0.39 with BOX


class FakeStore:
    """Stands in for the durable SQLite prediction cache."""

    def __init__(self, rows):
        self.rows = dict(rows)
        self.reads = 0

    def get(self, img_path, conf=None):
        self.reads += 1
        return self.rows.get(str(img_path))


def _raw(cls, conf, box):
    """A cached prediction as the model writes it: (cls, x1, y1, x2, y2, conf)."""
    return (cls, *box, conf)


def _probe(monolith, labels, preds, *, direction='either', lo=0.25, hi=1.0,
           match=0.5, mapping=None, model_ids=(0, 1, 2), stored=True, tmp_path=None):
    """A bare app with a warm label cache and predictions only in the STORE --
    exactly the state right after a restart."""
    app = object.__new__(monolith.YOLOLabelingTool)
    app.class_info = {0: {"name": "car"}, 1: {"name": "bus"}, 2: {"name": "human"}}
    app.class_groups = {}
    app._rebuild_class_group_lookup()
    app.model_names = {i: str(i) for i in model_ids}
    app.prediction_class_map = PredictionClassMap(
        mapping=dict(mapping if mapping is not None else {0: 0, 1: 1, 2: 2}))
    app.prediction_conf = 0.25
    app.model_predictions_cache = {}
    app.pred_cache = FakeStore({IMG: [_raw(*p) for p in preds]} if stored else {})
    lf = tmp_path / "f.txt"
    lf.write_text("")
    app.labels_cache = {IMG: [(c, *b, 0) for c, b in labels]}
    app._labels_cache_stat = {IMG: app._label_stamp(lf)}
    app.image_dimensions_cache = {IMG: (640, 480)}
    for flag in ("filter_by_class_enabled", "filter_by_size_enabled",
                 "filter_by_class_presence_enabled", "filter_by_overlap_enabled",
                 "filter_by_relsize_enabled"):
        setattr(app, flag, False)
    app.filter_by_iou_enabled = True
    app.filter_iou_direction = direction
    app.filter_iou_threshold = match
    app.filter_iou_conf_lo, app.filter_iou_conf_hi = lo, hi
    app._begin_iou_filter_pass()
    return app, lf


def _passes(monolith, tmp_path, labels, preds, **kw):
    app, lf = _probe(monolith, labels, preds, tmp_path=tmp_path, **kw)
    return app.image_passes_filters(IMG, lf)


# -- reading what is actually there ---------------------------------------


def test_it_reads_the_durable_cache_after_a_restart(monolith, tmp_path):
    """Memory is empty, the store is full: the filter must still see the label
    the model missed. It used to see no predictions and exclude the image."""
    assert _passes(monolith, tmp_path, [(0, BOX)], [(0, 0.9, FAR)]) is True


def test_it_does_not_promote_every_image_into_memory(monolith, tmp_path):
    """One Apply over 46k images would otherwise hold ~1 GB of boxes."""
    app, lf = _probe(monolith, [(0, BOX)], [(0, 0.9, FAR)], tmp_path=tmp_path)
    app.image_passes_filters(IMG, lf)
    assert app.model_predictions_cache == {}
    assert app.pred_cache.reads == 1


def test_a_never_inferred_image_is_counted_not_passed(monolith, tmp_path):
    """Unknown is not the same as 'the model saw nothing'."""
    app, lf = _probe(monolith, [(0, BOX)], [], stored=False, tmp_path=tmp_path)
    assert app.image_passes_filters(IMG, lf) is False
    assert app._iou_not_inferred == 1


@pytest.mark.parametrize("direction,expected", [
    ('labels', True), ('either', True), ('predictions', False)])
def test_an_inferred_empty_result_is_evaluated(monolith, tmp_path, direction, expected):
    """The model ran and saw nothing: every label is unmatched. This was
    `if not preds: return False` -- the maximal disagreement, discarded."""
    assert _passes(monolith, tmp_path, [(0, BOX)], [], direction=direction) is expected


# -- unmatched labels -----------------------------------------------------


def test_an_unmapped_prediction_still_matches_a_label(monolith, tmp_path):
    """Geometry only. Dropping unmapped classes first fabricated unmatched
    labels -- the bug already fixed once in the scan."""
    assert _passes(monolith, tmp_path, [(0, BOX)], [(2, 0.9, BOX)],
                   direction='labels', mapping={0: 0, 1: 1}) is False


def test_the_ceiling_never_hides_a_prediction_from_matching(monolith, tmp_path):
    """A label the model sees at 0.95 is matched, whatever the upper bound."""
    assert _passes(monolith, tmp_path, [(0, BOX)], [(0, 0.95, BOX)],
                   direction='labels', hi=0.6) is False


def test_below_the_floor_counts_as_unseen(monolith, tmp_path):
    assert _passes(monolith, tmp_path, [(0, BOX)], [(0, 0.2, BOX)],
                   direction='labels', lo=0.25) is True


def test_a_label_of_a_class_the_model_cannot_emit_is_not_unmatched(monolith, tmp_path):
    """Same guard as the scan: the model's silence about a class it cannot
    predict says nothing about the label."""
    assert _passes(monolith, tmp_path, [(2, BOX)], [], direction='labels',
                   mapping={0: 0, 1: 1}) is False


# -- unmatched predictions ------------------------------------------------


def test_a_confident_prediction_with_no_label_is_found(monolith, tmp_path):
    assert _passes(monolith, tmp_path, [(0, BOX)], [(0, 0.9, FAR)],
                   direction='predictions', lo=0.8) is True


def test_a_prediction_outside_the_range_is_not_evidence(monolith, tmp_path):
    assert _passes(monolith, tmp_path, [(0, BOX)], [(0, 0.5, FAR)],
                   direction='predictions', lo=0.8) is False
    assert _passes(monolith, tmp_path, [(0, BOX)], [(0, 0.95, FAR)],
                   direction='predictions', lo=0.25, hi=0.6) is False


def test_an_unmapped_prediction_is_never_an_unlabelled_object(monolith, tmp_path):
    """Or every COCO 'chair' a dataset does not care about would be flagged."""
    assert _passes(monolith, tmp_path, [], [(2, 0.9, FAR)],
                   direction='predictions', mapping={0: 0, 1: 1}) is False


def test_a_matched_prediction_is_not_unlabelled(monolith, tmp_path):
    assert _passes(monolith, tmp_path, [(1, BOX)], [(0, 0.9, BOX)],
                   direction='predictions') is False, "geometry, not class"


def test_an_image_with_no_labels_at_all_is_found(monolith, tmp_path):
    """Never-labelled frames are where unlabelled objects live."""
    assert _passes(monolith, tmp_path, [], [(0, 0.9, BOX)],
                   direction='predictions') is True


# -- independence from the display ----------------------------------------


def test_the_display_slider_does_not_change_the_result(monolith, tmp_path):
    app, lf = _probe(monolith, [(0, BOX)], [(0, 0.3, BOX)], direction='labels',
                     lo=0.25, tmp_path=tmp_path)
    app.prediction_conf = 0.25
    first = app.image_passes_filters(IMG, lf)
    app.prediction_conf = 0.9
    assert app.image_passes_filters(IMG, lf) is first


# -- agreement with the scan ----------------------------------------------


SCENES = [
    [],
    [(0, 0.9, BOX)],
    [(0, 0.9, LOOSE)],
    [(0, 0.2, BOX)],
    [(None, 0.9, BOX)],
    [(1, 0.9, BOX)],
    [(0, 0.9, FAR)],
]


@pytest.mark.parametrize("scene", SCENES)
def test_unmatched_labels_agrees_with_a_not_an_object_scan(monolith, tmp_path, scene):
    """Same floor, same IoU: the filter selects an image exactly when the scan
    would report its label as 'not an object'. They share core/badscan."""
    lo, match = 0.25, 0.5
    raw = [(c if c is not None else 9, conf, b) for c, conf, b in scene]
    filt = _passes(monolith, tmp_path, [(0, BOX)], raw, direction='labels',
                   lo=lo, match=match)

    preds = [(c, conf, *b) for c, conf, b in scene if conf >= lo]
    cfg = _badscan.ScanConfig(iou_match=match, mismatch=False, missing=True)
    scan = _badscan.classify_gt(0, BOX, preds, cfg, lambda a, b: a == b)
    assert filt is (scan is not None)


# -- the panel (gui) ------------------------------------------------------


def _frames(app):
    import tkinter.ttk as ttk
    return {w.cget('text'): w for w in app.filters_tab.winfo_children()
            if isinstance(w, ttk.Labelframe)}


def _named(app, name):
    import tkinter.ttk as ttk
    stack, hits = [app.root], []
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        if isinstance(w, ttk.Entry) and str(w).rsplit('.', 1)[-1] == name:
            hits.append(w)
    assert len(hits) == 1, f"no single entry named {name!r}"
    return hits[0]


def _with_store(app, rows, mapping=None):
    """Give a real app predictions in the durable store only."""
    app.pretrained_model = object()
    app.model_names = {0: "0"}
    app.prediction_class_map = PredictionClassMap(mapping=mapping or {0: 0})
    app.model_predictions_cache = {}
    app.pred_cache = FakeStore(rows)


@pytest.mark.gui
def test_the_iou_entries_are_never_disabled(gui_app):
    """Setup runs before any model loads, so the old 'disable when no model'
    check disabled the threshold for good."""
    for name in ("iou_filter_match", "iou_filter_conf_lo", "iou_filter_conf_hi"):
        assert str(_named(gui_app, name).cget('state')) != 'disabled'


@pytest.mark.gui
def test_the_iou_frame_sits_above_apply(gui_app):
    slaves = gui_app.filters_tab.pack_slaves()
    iou = _frames(gui_app)["Filter by Label/Prediction IOU"]
    assert slaves.index(iou) < slaves.index(gui_app._apply_filters_btn)


@pytest.mark.gui
def test_rebuilt_frames_do_not_widen_the_panel(gui_app):
    """The panel is a 250px canvas with no horizontal scrollbar: anything wider
    than what was already there is clipped."""
    gui_app.root.update_idletasks()
    frames = _frames(gui_app)
    widest_untouched = max(frames[t].winfo_reqwidth() for t in frames
                           if "Overlapping" not in t and "IOU" not in t)
    for title in ("Filter by Overlapping Labels", "Filter by Label/Prediction IOU"):
        assert frames[title].winfo_reqwidth() <= widest_untouched, title


@pytest.mark.gui
def test_iou_filter_without_predictions_says_why(gui_app):
    app = gui_app
    app.pred_cache, app.model_predictions_cache = None, {}
    app.filter_iou_var.set(True)
    app.toggle_iou_filter()
    app.apply_filters()
    assert "load a model" in app.filter_result_var.get()


@pytest.mark.gui
def test_a_reversed_confidence_range_is_refused(gui_app):
    app = gui_app
    _with_store(app, {})
    app.filter_iou_var.set(True)
    app.toggle_iou_filter()
    app.iou_conf_lo_var.set("0.9")
    app.iou_conf_hi_var.set("0.5")
    app.update_filter()
    app.apply_filters()
    assert "Prediction confidence" in app.filter_result_var.get()


@pytest.mark.gui
def test_a_frame_with_no_label_file_is_found_by_unmatched_predictions(gui_app):
    """The fixture dataset has images without a .txt; a confident prediction on
    one must be found, because nobody has labelled that frame at all."""
    app = gui_app
    resolver = app._resolver()
    unlabelled = [p for p in app.image_paths if not resolver.resolve(p).exists()]
    if not unlabelled:
        pytest.skip("fixture has no unlabelled image")
    target = unlabelled[0]
    _with_store(app, {str(p): [] for p in app.image_paths})
    app.pred_cache.rows[str(target)] = [_raw(0, 0.9, (1, 1, 20, 20))]
    app.filter_iou_var.set(True)
    app.toggle_iou_filter()
    app.filter_iou_direction_var.set('predictions')
    app.update_filter()
    app.apply_filters()
    assert target in app.filtered_image_paths
    assert "Found:" in app.filter_result_var.get()


@pytest.mark.gui
def test_never_inferred_frames_are_reported_in_the_result(gui_app):
    app = gui_app
    _with_store(app, {})                         # nothing inferred at all
    app.filter_iou_var.set(True)
    app.toggle_iou_filter()
    app.apply_filters()
    assert "not inferred" in app.filter_result_var.get()


@pytest.mark.gui
def test_an_overlap_only_run_reports_found_not_showing_all(gui_app):
    app = gui_app
    app.filter_overlap_var.set(True)
    app.toggle_overlap_filter()
    app.apply_filters()
    text = app.filter_result_var.get()
    assert text.startswith("Found:"), text


@pytest.mark.gui
def test_iou_filter_settings_survive_a_relaunch(gui_app, monolith, ds):
    import tkinter as tk

    app = gui_app
    app.filter_iou_direction_var.set('predictions')
    app.iou_conf_lo_var.set("0.8")
    app.update_filter()
    root2 = tk.Tk()
    try:
        app2 = monolith.YOLOLabelingTool(root2, yaml_path=str(ds.yaml))
        root2.update_idletasks()
        assert app2.filter_iou_direction == 'predictions'
        assert app2.filter_iou_conf_lo == 0.8
        assert app2.filter_iou_direction_var.get() == 'predictions'
        assert float(app2.iou_conf_lo_var.get()) == 0.8
    finally:
        root2.destroy()
