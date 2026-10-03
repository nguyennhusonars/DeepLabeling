"""The 'Find Bad Annotations' configuration dialog and result ordering.

The dialog's job is to make a scan's meaning and cost knowable before it runs.
Most of what is pinned here is therefore refusal behaviour: a scan that cannot
answer the question asked should say so rather than run for an hour and return
an empty list.
"""

from __future__ import annotations

import pytest

from yolo_labeling.core import predcache as _predcache
from yolo_labeling.ui.crop_review import KIND_ORDER, _entry_rank

pytestmark = [pytest.mark.gui, pytest.mark.legacy]


def _entry(kind, score, **kw):
    e = {'kind': kind, 'score': score}
    e.update(kw)
    return e


# -- result ordering -------------------------------------------------------


def test_kinds_are_grouped_before_being_scored():
    """`score` means different things per kind, so a mixed sort on it alone
    put two scales in one ordering."""
    entries = [
        _entry('missing', 1.0),
        _entry('class_mismatch', 0.30),
        _entry('missing', 0.60),
        _entry('class_mismatch', 0.95),
    ]
    entries.sort(key=_entry_rank)
    assert [e['kind'] for e in entries] == [
        'class_mismatch', 'class_mismatch', 'missing', 'missing']


def test_within_a_kind_the_worst_comes_first():
    entries = [_entry('class_mismatch', 0.30), _entry('class_mismatch', 0.95)]
    entries.sort(key=_entry_rank)
    assert [e['score'] for e in entries] == [0.95, 0.30]


def test_an_unknown_kind_sorts_last_rather_than_crashing():
    entries = [_entry('something_new', 1.0), _entry('class_mismatch', 0.1)]
    entries.sort(key=_entry_rank)
    assert entries[0]['kind'] == 'class_mismatch'


def test_a_missing_score_does_not_break_the_sort():
    assert _entry_rank({'kind': 'missing'}) == (KIND_ORDER['missing'], 0.0)


# -- dialog guards ---------------------------------------------------------


@pytest.fixture
def opened(gui_app, monkeypatch):
    """Open the dialog and hand back its Start handler plus its widgets."""
    gui_app.pretrained_model = object()          # the dialog only checks truthiness
    gui_app.model_names = {0: "person"}

    started = {}
    monkeypatch.setattr(type(gui_app), "open_bad_label_review",
                        lambda self, config: started.setdefault('config', config))
    gui_app.show_find_bad_dialog()
    gui_app.root.update_idletasks()

    win = [w for w in gui_app.root.winfo_children()
           if isinstance(w, __import__('tkinter').Toplevel)
           and w.title() == "Find Bad Annotations"][-1]
    return gui_app, win, started


def _widgets(win, cls):
    out = []
    stack = [win]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        if isinstance(w, cls):
            out.append(w)
    return out


def _field(win, name):
    """An entry by its Tk widget name.

    By name, not by sorted screen position: two entries now share a row, so a
    top-to-bottom sort no longer gives a stable order.
    """
    import tkinter.ttk as ttk
    hits = [w for w in _widgets(win, ttk.Entry) if str(w).rsplit('.', 1)[-1] == name]
    assert len(hits) == 1, f"no single entry named {name!r}"
    return hits[0]


def _set(win, name, value):
    entry = _field(win, name)
    entry.delete(0, 'end')
    entry.insert(0, str(value))


def _click_start(win):
    import tkinter.ttk as ttk
    for b in _widgets(win, ttk.Button):
        if b.cget('text') == "Start scan":
            b.invoke()
            return
    raise AssertionError("no Start scan button")


def _status(win):
    import tkinter.ttk as ttk
    texts = []
    for lab in _widgets(win, ttk.Label):
        var = lab.cget('textvariable')
        if var:
            texts.append(win.getvar(var))
    return " ".join(t for t in texts if t)


def test_scan_refuses_when_nothing_is_selected_to_report(opened):
    app, win, started = opened
    for cb in _widgets(win, __import__('tkinter').ttk.Checkbutton):
        if cb.instate(['selected']):
            cb.invoke()                           # turn every enabled kind off
    _click_start(win)
    assert 'config' not in started
    assert "report" in _status(win).lower()


def test_a_model_says_restriction_without_wrong_class_is_refused(opened):
    """The restriction only applies to wrong-class entries, so this combination
    can only ever return nothing."""
    app, win, started = opened
    import tkinter.ttk as ttk
    combos = _widgets(win, ttk.Combobox)
    combos[0].set(combos[0].cget('values')[1])    # a concrete predicted class
    for cb in _widgets(win, ttk.Checkbutton):
        if "Wrong class" in cb.cget('text'):
            cb.invoke()                            # switch wrong-class OFF
    _click_start(win)
    assert 'config' not in started
    assert "Wrong class" in _status(win)


@pytest.mark.parametrize("field,value", [
    ("floor", "abc"), ("iou_match", "abc"),      # not numbers
    ("floor", "0"), ("iou_match", "0"),          # out of range low
    ("floor", "1.5"), ("iou_match", "1.5"),      # out of range high
])
def test_out_of_range_thresholds_are_refused(opened, field, value):
    app, win, started = opened
    _set(win, field, value)
    _click_start(win)
    assert 'config' not in started
    assert _status(win), "refused silently, with no reason given"


def test_a_valid_config_starts_the_scan(opened, ds):
    app, win, started = opened
    _click_start(win)
    cfg = started.get('config')
    assert cfg is not None
    assert cfg['conf'] == pytest.approx(0.40)
    assert cfg['iou_match'] == pytest.approx(0.50)
    assert cfg['mismatch'] and cfg['missing']
    assert cfg['paths'] == list(app.filtered_image_paths)


def test_scope_can_be_widened_to_all_images(opened):
    app, win, started = opened
    app.filtered_image_paths = app.image_paths[:2]
    import tkinter.ttk as ttk
    for rb in _widgets(win, ttk.Radiobutton):
        if "All loaded" in rb.cget('text'):
            rb.invoke()
    _click_start(win)
    assert started['config']['paths'] == list(app.image_paths)


def test_a_floor_below_the_cache_floor_is_refused_with_the_reason(opened):
    """The model is always run at CONF_FLOOR and the scan always reads the
    cache, so below the floor nothing exists at all. This used to ask whether
    to 're-run the model on every image' -- which was never true."""
    app, win, started = opened
    _set(win, "floor", _predcache.CONF_FLOOR / 2)
    _click_start(win)
    assert 'config' not in started
    assert f"{_predcache.CONF_FLOOR:.2f}" in _status(win)
    assert not app.dialogs.asks, "no question: there is nothing to decide"


def test_the_cache_floor_itself_is_accepted(opened):
    app, win, started = opened
    _set(win, "floor", _predcache.CONF_FLOOR)
    _click_start(win)
    assert started['config']['conf'] == pytest.approx(_predcache.CONF_FLOOR)


def test_at_or_above_the_floor_no_warning_is_raised(opened):
    app, win, started = opened
    app.dialogs.asks.clear()
    _click_start(win)
    assert not app.dialogs.asks
    assert 'config' in started


# -- ranges ----------------------------------------------------------------


def _kind(win, label):
    import tkinter.ttk as ttk
    hits = [cb for cb in _widgets(win, ttk.Checkbutton) if label in cb.cget('text')]
    assert len(hits) == 1, f"no single checkbox {label!r}"
    return hits[0]


def test_defaults_reproduce_the_old_scan(opened):
    """Nothing about an untouched dialog may change what a scan finds."""
    app, win, started = opened
    _click_start(win)
    cfg = started['config']
    assert cfg['mismatch_max'] == pytest.approx(1.0)
    assert cfg['missing_iou_lo'] == pytest.approx(0.0)
    assert cfg['missing_iou_hi'] is None, "follows the matching IoU"
    assert cfg['weak'] is False


def test_a_ceiling_below_the_floor_is_refused(opened):
    app, win, started = opened
    _set(win, "mismatch_max", 0.3)              # floor is 0.40
    _click_start(win)
    assert 'config' not in started
    assert "Wrong class" in _status(win)


def test_the_ceiling_reaches_the_scan(opened):
    app, win, started = opened
    _set(win, "mismatch_max", 0.6)
    _click_start(win)
    assert started['config']['mismatch_max'] == pytest.approx(0.6)


def test_an_overlap_band_above_the_matching_iou_is_refused(opened):
    """Anything above the matching IoU is a match, not 'not an object'."""
    app, win, started = opened
    _set(win, "missing_iou_hi", 0.7)            # matching IoU is 0.50
    _click_start(win)
    assert 'config' not in started
    assert "0.50" in _status(win)


def test_a_reversed_overlap_band_is_refused_by_name(opened):
    app, win, started = opened
    _set(win, "missing_iou_lo", 0.4)
    _set(win, "missing_iou_hi", 0.1)
    _click_start(win)
    assert 'config' not in started
    assert "not an object" in _status(win).lower()


def test_a_narrower_band_reaches_the_scan(opened):
    app, win, started = opened
    _set(win, "missing_iou_hi", 0.05)
    _click_start(win)
    assert started['config']['missing_iou_hi'] == pytest.approx(0.05)


def test_weakly_seen_with_defaults_is_valid(opened):
    """A cutoff of 0.30 against the 0.40 floor would make the kind refuse
    itself out of the box."""
    app, win, started = opened
    _kind(win, "Weakly seen").invoke()
    _click_start(win)
    assert started['config']['weak'] is True
    assert started['config']['weak_below'] > started['config']['conf']


def test_a_weak_cutoff_at_or_below_the_floor_is_refused(opened):
    app, win, started = opened
    _kind(win, "Weakly seen").invoke()
    _set(win, "weak_below", 0.40)               # == floor: an empty band
    _click_start(win)
    assert 'config' not in started
    assert "Weakly seen" in _status(win)


def test_a_disabled_kinds_junk_does_not_block_the_scan(opened):
    """Typing in a field you then switch off should not hold the scan hostage."""
    app, win, started = opened
    _set(win, "weak_below", "abc")              # Weakly seen is off
    _click_start(win)
    assert 'config' in started


# -- persistence -----------------------------------------------------------


def test_settings_survive_reopening_the_dialog(opened, monkeypatch):
    """The reset-on-open bug fixed last round for the overlap filter."""
    app, win, started = opened
    _set(win, "floor", 0.25)
    _set(win, "mismatch_max", 0.7)
    _kind(win, "Weakly seen").invoke()
    _click_start(win)

    started.clear()
    app.show_find_bad_dialog()
    app.root.update_idletasks()
    import tkinter as tk
    win2 = [w for w in app.root.winfo_children()
            if isinstance(w, tk.Toplevel) and w.title() == "Find Bad Annotations"][-1]
    assert float(_field(win2, "floor").get()) == pytest.approx(0.25)
    assert float(_field(win2, "mismatch_max").get()) == pytest.approx(0.7)
    assert _kind(win2, "Weakly seen").instate(['selected'])


def test_settings_reach_the_config_file(opened, tmp_path):
    import json
    app, win, started = opened
    _set(win, "floor", 0.25)
    _click_start(win)
    saved = json.loads(open(app.config_file).read())
    assert saved['find_bad']['conf'] == pytest.approx(0.25)


def test_a_band_that_follows_the_matching_iou_is_stored_as_following(opened):
    """Stored as a number, raising the matching IoU later would open a silent
    gap of boxes that are neither matched nor reported."""
    import json
    app, win, started = opened
    _click_start(win)
    saved = json.loads(open(app.config_file).read())
    assert saved['find_bad']['missing_iou_hi'] is None


# -- layout ----------------------------------------------------------------


def test_start_survives_a_short_window(opened):
    """The dialog grew; on a short screen Start must not be what gets clipped."""
    import tkinter.ttk as ttk
    app, win, started = opened
    win.geometry(f"{win.winfo_reqwidth()}x260")
    app.root.update()
    start = [b for b in _widgets(win, ttk.Button) if b.cget('text') == "Start scan"][0]
    assert start.winfo_ismapped()
    assert start.winfo_y() + start.winfo_height() <= win.winfo_height() + 2
