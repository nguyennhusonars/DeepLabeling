"""The overlap filter's scope and threshold survive a restart.

Both reset to their constructor defaults on every launch -- scope to
'different', threshold to 0.5 -- while the user's last query was something else
entirely. On pvn-vehicle that is the difference between 8 flagged images
(same-class @ 0.9) and 123 (different-class @ 0.5): the same button, a
fifteen-fold different answer, with nothing on screen to say why.
"""

from __future__ import annotations

import json

import pytest

from yolo_labeling.ui import classes as _classes


def _probe(tmp_path):
    """Bare ClassManagementMixin with just enough state to save and load."""
    p = type("P", (_classes.ClassManagementMixin,), {})()
    p.config_file = str(tmp_path / "class_config.json")
    p.class_info = {0: {"name": "car", "color": [0, 0, 255]}}
    p.class_hotkeys = {}
    p.class_groups = {}
    p.prediction_maps = {}
    p._cleanup_hotkeys = lambda: None
    p._init_default_hotkeys = lambda: None
    p._rebuild_class_group_lookup = lambda: None
    return p


# -- round trip ------------------------------------------------------------


def test_scope_and_threshold_are_written(tmp_path):
    p = _probe(tmp_path)
    p.filter_overlap_scope = 'same'
    p.filter_overlap_threshold = 0.9
    p.save_class_config()

    saved = json.loads((tmp_path / "class_config.json").read_text())
    assert saved['filters']['overlap_scope'] == 'same'
    assert saved['filters']['overlap_threshold'] == 0.9


def test_they_come_back_on_the_next_launch(tmp_path):
    p = _probe(tmp_path)
    p.filter_overlap_scope = 'same'
    p.filter_overlap_threshold = 0.9
    p.save_class_config()

    fresh = _probe(tmp_path)
    fresh.load_class_config()
    assert fresh.filter_overlap_scope == 'same'
    assert fresh.filter_overlap_threshold == 0.9


def test_an_old_config_without_the_block_still_loads(tmp_path):
    """Every existing class_config.json predates this key."""
    (tmp_path / "class_config.json").write_text(json.dumps({
        'classes': {'0': {'name': 'car', 'color': [0, 0, 255]}},
    }))
    p = _probe(tmp_path)
    p.load_class_config()
    assert p.filter_overlap_scope == 'different'
    assert p.filter_overlap_threshold == 0.5


@pytest.mark.parametrize("bad", ["sideways", "", None, 5])
def test_a_junk_scope_falls_back_rather_than_filtering_on_nonsense(tmp_path, bad):
    """`overlap_pair_counts` treats any unrecognised scope as 'different', so a
    corrupt value would silently change what the filter means."""
    (tmp_path / "class_config.json").write_text(json.dumps({
        'classes': {'0': {'name': 'car', 'color': [0, 0, 255]}},
        'filters': {'overlap_scope': bad, 'overlap_threshold': 0.9},
    }))
    p = _probe(tmp_path)
    p.load_class_config()
    assert p.filter_overlap_scope == 'different'


@pytest.mark.parametrize("bad,expected", [
    ("abc", 0.5), (None, 0.5), (-1.0, 0.0), (7.5, 1.0),
])
def test_a_junk_threshold_is_clamped_or_defaulted(tmp_path, bad, expected):
    (tmp_path / "class_config.json").write_text(json.dumps({
        'classes': {'0': {'name': 'car', 'color': [0, 0, 255]}},
        'filters': {'overlap_scope': 'same', 'overlap_threshold': bad},
    }))
    p = _probe(tmp_path)
    p.load_class_config()
    assert p.filter_overlap_threshold == expected


def test_saving_classes_does_not_drop_the_filter_block(tmp_path):
    """`save_class_config` runs on every class rename, add and delete."""
    p = _probe(tmp_path)
    p.filter_overlap_scope = 'any'
    p.filter_overlap_threshold = 0.75
    p.save_class_config()

    reopened = _probe(tmp_path)
    reopened.load_class_config()
    reopened.class_info[1] = {"name": "bus", "color": [255, 0, 0]}
    reopened.save_class_config()

    saved = json.loads((tmp_path / "class_config.json").read_text())
    # The keys this test set -- not exact equality: the block gains keys as
    # filters do, and that must not read as the block being dropped.
    assert saved['filters']['overlap_scope'] == 'any'
    assert saved['filters']['overlap_threshold'] == 0.75


# -- the panel must agree with the state ----------------------------------


@pytest.mark.gui
def test_the_panel_shows_what_the_filter_will_actually_use(gui_app):
    """The failure this whole change exists to prevent: the widgets saying one
    thing while `apply_filters` reads another."""
    app = gui_app
    assert app.filter_overlap_scope_var.get() == app.filter_overlap_scope
    assert float(app.filter_overlap_threshold_var.get()) == app.filter_overlap_threshold


@pytest.mark.gui
@pytest.mark.parametrize("launch", ["yaml", "no_yaml"])
def test_a_restored_setting_reaches_both_the_widget_and_the_filter(
        gui_app, monolith, ds, launch):
    """Set it, save it, rebuild the app, and check both halves came back.

    Parametrized over BOTH launch paths. The first version of this test built
    the second app with `yaml_path=app.yaml_path` -- an attribute that does not
    exist, so it always launched without a yaml and never noticed that a yaml
    launch skips `load_class_config` and drops every saved setting.
    """
    import tkinter as tk

    app = gui_app
    app.filter_overlap_scope_var.set('same')
    app._on_overlap_scope_change()
    app.filter_overlap_threshold_var.set('0.9')
    app.update_filter()
    assert app.filter_overlap_threshold == 0.9

    root2 = tk.Tk()
    root2.geometry("1200x800")
    try:
        app2 = monolith.YOLOLabelingTool(
            root2, yaml_path=str(ds.yaml) if launch == "yaml" else None)
        root2.update_idletasks()
        assert app2.filter_overlap_scope == 'same'
        assert app2.filter_overlap_threshold == 0.9
        assert app2.filter_overlap_scope_var.get() == 'same'
        assert float(app2.filter_overlap_threshold_var.get()) == 0.9
    finally:
        root2.destroy()


@pytest.mark.gui
def test_a_yaml_launch_does_not_write_defaults_over_saved_settings(gui_app, monolith, ds):
    """A yaml with a `groups:` block saves the config during startup. Before the
    saved settings were restored on that path, that save wrote the constructor
    defaults over them -- so they were lost even for the NEXT launch."""
    import json
    import tkinter as tk

    import yaml as _yaml

    app = gui_app
    app.filter_overlap_scope_var.set('any')
    app._on_overlap_scope_change()
    app.find_bad_prefs = dict(app._find_bad_settings(), conf=0.25)
    app.save_class_config()

    src = _yaml.safe_load(ds.yaml.read_text())
    names = src['names']
    first = names[0] if isinstance(names, list) else next(iter(names.values()))
    src['groups'] = {'g': [first]}
    grouped = ds.root / "data_groups.yaml"
    grouped.write_text(_yaml.safe_dump(src, sort_keys=False), encoding="utf-8")

    root2 = tk.Tk()
    try:
        monolith.YOLOLabelingTool(root2, yaml_path=str(grouped))
        root2.update_idletasks()
    finally:
        root2.destroy()
    saved = json.loads(open(app.config_file).read())
    assert saved['filters']['overlap_scope'] == 'any'
    assert saved['find_bad']['conf'] == 0.25


def test_find_bad_settings_round_trip(tmp_path):
    p = _probe(tmp_path)
    p.find_bad_prefs = dict(_classes.FIND_BAD_DEFAULTS, conf=0.3, weak=True,
                            missing_iou_hi=0.05)
    p.save_class_config()
    fresh = _probe(tmp_path)
    fresh.load_class_config()
    assert fresh.find_bad_prefs['conf'] == 0.3
    assert fresh.find_bad_prefs['weak'] is True
    assert fresh.find_bad_prefs['missing_iou_hi'] == 0.05


def test_junk_find_bad_settings_fall_back_key_by_key(tmp_path):
    """One corrupt key costs that key, not the block."""
    (tmp_path / "class_config.json").write_text(json.dumps({
        'classes': {'0': {'name': 'car', 'color': [0, 0, 255]}},
        'find_bad': {'conf': 'abc', 'weak': 'yes', 'mismatch_max': 0.7,
                     'missing_iou_hi': 'x'},
    }))
    p = _probe(tmp_path)
    p.load_class_config()
    prefs = p.find_bad_prefs
    assert prefs['conf'] == _classes.FIND_BAD_DEFAULTS['conf']
    assert prefs['weak'] is False, "a non-bool is not 'true'"
    assert prefs['mismatch_max'] == 0.7, "the good key survived"
    assert prefs['missing_iou_hi'] is None


def test_a_saved_floor_below_the_cache_floor_is_raised_to_it(tmp_path):
    """Below the cache floor nothing exists; the dialog would refuse it."""
    from yolo_labeling.core import predcache
    (tmp_path / "class_config.json").write_text(json.dumps({
        'classes': {'0': {'name': 'car', 'color': [0, 0, 255]}},
        'find_bad': {'conf': 0.01},
    }))
    p = _probe(tmp_path)
    p.load_class_config()
    assert p.find_bad_prefs['conf'] == predcache.CONF_FLOOR
