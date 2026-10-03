"""Review ordering for the bad-annotation list.

Clicking a crop jumps the main window to its frame and decodes it, and the
raw-frame cache holds 32. So the order is not cosmetic: scattering one image's
problems across pages means visiting and re-decoding that frame once per
problem.
"""

from __future__ import annotations

import pytest

from yolo_labeling.ui.crop_review import (
    DEFAULT_SORT,
    SORT_MODES,
    _entry_rank,
    sort_entries,
)


def e(img, kind, score, line=0):
    return {"img_path": img, "kind": kind, "score": score, "line_idx": line}


#: One frame with three problems, interleaved with other frames by score.
ENTRIES = [
    e("cam_A/0042.jpg", "class_mismatch", 0.91, 1),
    e("cam_A/0042.jpg", "class_mismatch", 0.38, 7),
    e("cam_A/0042.jpg", "missing", 0.97, 4),
    e("cam_B/0007.jpg", "class_mismatch", 0.88, 0),
    e("cam_B/0007.jpg", "missing", 0.95, 3),
    e("cam_C/0100.jpg", "class_mismatch", 0.62, 2),
    e("cam_E/0300.jpg", "missing", 0.99, 5),
]


def _paths(entries):
    return [x["img_path"] for x in entries]


def _is_contiguous(entries):
    """True when no image's crops are split by another image's."""
    seen, prev = set(), None
    for p in _paths(entries):
        if p != prev:
            if p in seen:
                return False
            seen.add(p)
            prev = p
    return True


# -- grouped (the default) -------------------------------------------------


def test_grouped_keeps_each_images_crops_together():
    out = sort_entries(ENTRIES, "grouped")
    assert _is_contiguous(out), _paths(out)


def test_grouped_still_puts_the_worst_frame_first():
    out = sort_entries(ENTRIES, "grouped")
    assert out[0]["img_path"] == "cam_A/0042.jpg", "0.91 mismatch is the worst"


def test_grouped_orders_within_a_frame_by_severity():
    out = [x for x in sort_entries(ENTRIES, "grouped")
           if x["img_path"] == "cam_A/0042.jpg"]
    assert [x["score"] for x in out] == [0.91, 0.38, 0.97]
    assert [x["kind"] for x in out] == ["class_mismatch", "class_mismatch", "missing"]


def test_grouped_ranks_a_mismatch_frame_above_a_missing_only_frame():
    """cam_E scores 0.99 but only has a 'missing'; the two scores are not the
    same quantity, so kind stays the primary axis."""
    out = _paths(sort_entries(ENTRIES, "grouped"))
    assert out.index("cam_C/0100.jpg") < out.index("cam_E/0300.jpg")


def test_grouped_is_the_default():
    assert DEFAULT_SORT == "grouped"
    assert sort_entries(ENTRIES) == sort_entries(ENTRIES, "grouped")


# -- severity (the old behaviour) -----------------------------------------


def test_severity_ranks_every_box_independently():
    out = sort_entries(ENTRIES, "severity")
    assert [x["score"] for x in out] == [0.91, 0.88, 0.62, 0.38, 0.99, 0.97, 0.95]


def test_severity_is_what_scatters_a_frame():
    """The behaviour the grouped mode exists to fix — pinned so the contrast
    stays visible."""
    assert not _is_contiguous(sort_entries(ENTRIES, "severity"))


# -- file order ------------------------------------------------------------


def test_file_order_walks_paths_then_line_numbers():
    out = sort_entries(ENTRIES, "file")
    assert _paths(out) == sorted(_paths(ENTRIES))
    a = [x["line_idx"] for x in out if x["img_path"] == "cam_A/0042.jpg"]
    assert a == [1, 4, 7], "within a file, label-line order"


def test_file_order_ignores_severity():
    out = sort_entries(ENTRIES, "file")
    assert out[0]["img_path"] == "cam_A/0042.jpg"
    assert _is_contiguous(out)


# -- shared properties -----------------------------------------------------


@pytest.mark.parametrize("mode", list(SORT_MODES))
def test_no_mode_loses_or_duplicates_an_entry(mode):
    out = sort_entries(ENTRIES, mode)
    assert len(out) == len(ENTRIES)
    assert {id(x) for x in out} == {id(x) for x in ENTRIES}


@pytest.mark.parametrize("mode", list(SORT_MODES))
def test_every_mode_is_stable_across_repeated_calls(mode):
    """Entries stream in during a scan and the list is re-sorted each batch;
    an unstable order would reshuffle the page under the user."""
    once = sort_entries(ENTRIES, mode)
    twice = sort_entries(list(reversed(ENTRIES)), mode)
    assert [(_paths([x])[0], x["score"]) for x in once] == \
           [(_paths([x])[0], x["score"]) for x in twice]


@pytest.mark.parametrize("mode", list(SORT_MODES))
def test_an_empty_list_is_fine(mode):
    assert sort_entries([], mode) == []


def test_an_unknown_mode_falls_back_to_grouped():
    assert sort_entries(ENTRIES, "nonsense") == sort_entries(ENTRIES, "grouped")


def test_entry_rank_still_orders_kinds_before_scores():
    assert _entry_rank(e("x", "class_mismatch", 0.1)) < _entry_rank(e("x", "missing", 0.9))


# -- the picker ------------------------------------------------------------


@pytest.mark.gui
@pytest.mark.legacy
class TestSortPicker:
    @staticmethod
    def _open(app, ds):
        entries = [
            {"img_path": ds.image("camA/0001.jpg"), "line_idx": 0, "cls_id": 0,
             "bbox_norm": (.5, .5, .2, .3), "pred_cls_id": 1, "pred_conf": .4,
             "iou": .7, "score": 0.40, "kind": "class_mismatch"},
            {"img_path": ds.image("camB/0001.jpg"), "line_idx": 0, "cls_id": 2,
             "bbox_norm": (.7, .7, .2, .2), "pred_cls_id": 1, "pred_conf": .9,
             "iou": .7, "score": 0.90, "kind": "class_mismatch"},
            {"img_path": ds.image("camA/0001.jpg"), "line_idx": 1, "cls_id": 1,
             "bbox_norm": (.2, .2, .1, .1), "pred_cls_id": 0, "pred_conf": .5,
             "iou": .0, "score": 0.50, "kind": "missing"},
        ]
        app._open_crop_review_window(entries=list(entries), target_class=None,
                                     mode='bad')
        app.root.update_idletasks()
        return app

    def test_the_picker_exists_and_shows_the_default(self, gui_app, ds):
        app = self._open(gui_app, ds)
        assert app._crop_review_sort == DEFAULT_SORT
        assert app._crop_review_sort_var.get() == SORT_MODES[DEFAULT_SORT]

    def test_choosing_a_mode_reorders_the_list(self, gui_app, ds):
        app = self._open(gui_app, ds)
        app._crop_review_sort_var.set(SORT_MODES["severity"])
        app._crop_review_resort()
        assert app._crop_review_sort == "severity"
        assert [e["score"] for e in app._crop_review_entries] == [0.90, 0.40, 0.50]

        app._crop_review_sort_var.set(SORT_MODES["grouped"])
        app._crop_review_resort()
        # camB owns the worst single box (0.90) so it still leads. camA holds
        # the 0.40 mismatch AND the 0.50 missing, and grouping pulls those two
        # together instead of splitting them across the kind boundary.
        paths = [str(e["img_path"]) for e in app._crop_review_entries]
        assert "camB" in paths[0], "worst frame still first"
        assert paths[1] == paths[2], "camA's two crops are adjacent"
        assert "camA" in paths[1]

    def test_the_selection_follows_the_crop_not_the_index(self, gui_app, ds):
        """Re-sorting moves every index. Keeping the number would quietly
        select a different crop, and the next keystroke would reassign or
        delete the wrong box."""
        app = self._open(gui_app, ds)
        app._crop_review_sort_var.set(SORT_MODES["severity"])
        app._crop_review_resort()

        app._crop_review_selected = 0
        picked = app._crop_review_entries[0]
        assert picked["score"] == 0.90

        app._crop_review_sort_var.set(SORT_MODES["file"])
        app._crop_review_resort()
        assert app._crop_review_entries[app._crop_review_selected] is picked

    def test_resorting_pages_the_selection_back_into_view(self, gui_app, ds):
        app = self._open(gui_app, ds)
        app._crop_review_selected = 2
        app._crop_review_sort_var.set(SORT_MODES["file"])
        app._crop_review_resort()
        rows, cols = app._crop_review_get_grid()
        assert app._crop_review_page == app._crop_review_selected // (rows * cols)

    def test_no_selection_resorts_without_error(self, gui_app, ds):
        app = self._open(gui_app, ds)
        app._crop_review_selected = None
        app._crop_review_sort_var.set(SORT_MODES["file"])
        app._crop_review_resort()
        assert app._crop_review_page == 0
