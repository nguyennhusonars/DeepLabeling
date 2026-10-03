"""The overlap filter's IoU is a range, not just a floor.

`0.99 – 1.00` isolates exact duplicates -- the 7 of 8 same-class hits on
pvn-vehicle that were byte-identical lines, and the only overlaps safe to clean
in bulk. `0.50 – 0.90` isolates partial overlaps, which are often legitimate
occlusion and want a human. A floor alone could not separate them.

The filter and the red highlighter must keep agreeing: what one selects, the
other draws.
"""

from __future__ import annotations

import json

import pytest

from yolo_labeling.core import geometry as _geom
from yolo_labeling.ui import filters as _filters

BOX = (10.0, 10.0, 50.0, 50.0)
NUDGED = (12.0, 12.0, 52.0, 52.0)       # IoU ~0.82 with BOX


def _probe(boxes, lo, hi=None, tmp_path=None):
    """Bare FiltersMixin with a warm, stamped cache and the detector bound in."""
    from yolo_labeling import app as _appmod

    p = type("P", (_filters.FiltersMixin,), {})()
    p.calculate_iou = staticmethod(_geom.iou_xyxy)
    p.detect_current_overlaps = _appmod.YOLOLabelingTool.detect_current_overlaps.__get__(p)
    p.label_boxes = [(float(c), *b) for c, b in boxes]
    p.labels_cache = {"img": [(c, *b, 0) for c, b in boxes]}
    lf = tmp_path / "img.txt"
    lf.write_text("")
    p._labels_cache_stat = {"img": p._label_stamp(lf)}
    p.image_dimensions_cache = {"img": (640, 480)}
    p.filter_overlap_scope = 'same'
    p.filter_overlap_threshold = lo
    if hi is not None:
        p.filter_overlap_max = hi
    p.filter_by_overlap_enabled = True
    for flag in ("filter_by_class_enabled", "filter_by_size_enabled",
                 "filter_by_iou_enabled", "filter_by_class_presence_enabled",
                 "filter_by_relsize_enabled"):
        setattr(p, flag, False)
    return p, lf


def _both(boxes, lo, hi, tmp_path):
    p, lf = _probe(boxes, lo, hi, tmp_path)
    selected = p.image_passes_filters("img", lf)
    p.detect_current_overlaps()
    return selected, bool(p.overlap_counts)


DUPLICATE = [(0, BOX), (0, BOX)]        # IoU 1.0
PARTIAL = [(0, BOX), (0, NUDGED)]       # IoU ~0.82


@pytest.mark.parametrize("boxes,lo,hi,expected", [
    (DUPLICATE, 0.99, 1.0, True),       # exact duplicates only...
    (PARTIAL,   0.99, 1.0, False),      # ...so a near-duplicate is out
    (DUPLICATE, 0.5,  0.9, False),      # partial overlaps only...
    (PARTIAL,   0.5,  0.9, True),       # ...so the exact duplicate is out
    (DUPLICATE, 0.5,  1.0, True),       # the default: everything from the floor up
    (PARTIAL,   0.5,  1.0, True),
])
def test_filter_and_highlighter_agree_on_the_range(boxes, lo, hi, expected, tmp_path):
    selected, highlighted = _both(boxes, lo, hi, tmp_path)
    assert selected is expected
    assert highlighted is expected, "the highlighter drew something the filter did not select"


def test_both_ends_are_inclusive(tmp_path):
    """Two identical boxes are exactly 1.0 -- an exclusive max would drop the
    very duplicates the range exists to isolate."""
    assert _both(DUPLICATE, 1.0, 1.0, tmp_path) == (True, True)


def test_a_probe_without_a_max_keeps_the_old_floor_only_behaviour(tmp_path):
    """Older callers and bare test objects set only the threshold."""
    p, lf = _probe(DUPLICATE, 0.5, None, tmp_path)
    assert not hasattr(p, 'filter_overlap_max')
    assert p.image_passes_filters("img", lf) is True


def test_the_predicate_does_not_clamp(tmp_path):
    """An unreachable floor must stay unreachable; clamping 1.01 to 1.0 would
    quietly select every exact duplicate."""
    p, lf = _probe(DUPLICATE, 1.01, None, tmp_path)
    assert p.image_passes_filters("img", lf) is False


# -- persistence ----------------------------------------------------------


def _cfg_probe(tmp_path):
    from yolo_labeling.ui import classes as _classes

    p = type("C", (_classes.ClassManagementMixin,), {})()
    p.config_file = str(tmp_path / "class_config.json")
    p.class_info = {0: {"name": "car", "color": [0, 0, 255]}}
    p.class_hotkeys, p.class_groups, p.prediction_maps = {}, {}, {}
    p._cleanup_hotkeys = p._init_default_hotkeys = lambda: None
    p._rebuild_class_group_lookup = lambda: None
    return p


def test_the_max_round_trips(tmp_path):
    p = _cfg_probe(tmp_path)
    p.filter_overlap_threshold, p.filter_overlap_max = 0.99, 1.0
    p.filter_overlap_scope = 'same'
    p.save_class_config()
    p.filter_overlap_max = 0.9
    p.save_class_config()
    fresh = _cfg_probe(tmp_path)
    fresh.load_class_config()
    assert fresh.filter_overlap_max == 0.9


def test_an_old_config_gets_a_max_of_one(tmp_path):
    (tmp_path / "class_config.json").write_text(json.dumps({
        'classes': {'0': {'name': 'car', 'color': [0, 0, 255]}},
        'filters': {'overlap_scope': 'same', 'overlap_threshold': 0.9},
    }))
    p = _cfg_probe(tmp_path)
    p.load_class_config()
    assert p.filter_overlap_threshold == 0.9 and p.filter_overlap_max == 1.0


# -- the panel ------------------------------------------------------------


def _entry(app, name):
    import tkinter.ttk as ttk

    stack, hits = [app.root], []
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        if isinstance(w, ttk.Entry) and str(w).rsplit('.', 1)[-1] == name:
            hits.append(w)
    assert len(hits) == 1, f"no single entry named {name!r}"
    return hits[0]


@pytest.mark.gui
def test_changing_only_the_max_is_persisted(gui_app):
    """`update_filter` saves only when something it persists changed -- a check
    that used to look at the scope and the floor alone."""
    app = gui_app
    app.filter_overlap_max_var.set("0.9")
    app.update_filter()
    saved = json.loads(open(app.config_file).read())
    assert saved['filters']['overlap_max'] == 0.9


@pytest.mark.gui
def test_a_reversed_range_is_refused_at_apply_not_swapped(gui_app):
    """Swapping on the way past would scramble an edit made one end at a time."""
    app = gui_app
    app.filter_overlap_var.set(True)
    app.toggle_overlap_filter()
    app.filter_overlap_threshold_var.set("0.9")
    app.filter_overlap_max_var.set("0.5")
    app.update_filter()
    assert app.filter_overlap_threshold_var.get() == "0.9", "rewritten mid-edit"
    before = list(app.filtered_image_paths)
    app.apply_filters()
    assert app.filtered_image_paths == before, "applied a reversed range"
    assert "0.9" in app.filter_result_var.get() and "0.5" in app.filter_result_var.get()


@pytest.mark.gui
def test_junk_text_keeps_the_previous_value(gui_app):
    app = gui_app
    app.filter_overlap_max_var.set("0.8")
    app.update_filter()
    app.filter_overlap_max_var.set("abc")
    app.update_filter()
    assert app.filter_overlap_max == 0.8
    assert app.filter_overlap_max_var.get() == "0.8"


@pytest.mark.gui
def test_the_range_entries_exist_and_are_named(gui_app):
    _entry(gui_app, "overlap_min")
    _entry(gui_app, "overlap_max")
