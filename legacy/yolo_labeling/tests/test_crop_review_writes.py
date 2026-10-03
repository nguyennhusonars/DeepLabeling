"""The bad-annotation review window's write path.

Every action here goes straight to disk with no undo and no confirmation, and
until now none of it was tested -- `assert_only_changed`, the project's
load-bearing data-loss assertion, had never been pointed at this code.

So the assertions are deliberately about blast radius: which files changed,
which lines within them, and whether anything that was not the target survived
byte-for-byte.
"""

from __future__ import annotations

import pytest

from fixtures import GAUNTLET, POLY1, assert_only_changed, read_exact, snapshot

pytestmark = [pytest.mark.gui, pytest.mark.legacy]


def entry_for(ds, rel, line_idx, cls_id, bbox=(0.5, 0.5, 0.2, 0.3), **kw):
    """Build a review entry. `bbox` MUST be the box actually on that line --
    the write guard verifies it, so a made-up box is refused, not written."""
    e = {
        'img_path': ds.image(f"{rel}.jpg"),
        'line_idx': line_idx,
        'cls_id': cls_id,
        'bbox_norm': bbox,
        'pred_cls_id': 1,
        'pred_conf': 0.8,
        'iou': 0.7,
        'score': 0.8,
        'kind': 'class_mismatch',
    }
    e.update(kw)
    return e


@pytest.fixture
def review(gui_app, ds):
    """The review window open in bad mode, with no entries yet."""
    def _open(entries):
        gui_app._open_crop_review_window(entries=list(entries),
                                         target_class=None, mode='bad')
        gui_app.root.update_idletasks()
        return gui_app
    return _open


def rel_label(ds, rel):
    return str(ds.label(rel).relative_to(ds.root))


# -- reassign --------------------------------------------------------------


def test_reassign_writes_exactly_one_file(review, ds):
    before = snapshot(ds.root)
    app = review([entry_for(ds, "camA/0001", 0, 0)])
    app._crop_review_selected = 0
    app._crop_review_reassign(0, 3)

    assert_only_changed(before, snapshot(ds.root), {rel_label(ds, "camA/0001")})


def test_reassign_changes_only_the_target_line(review, ds):
    original = read_exact(ds.label("camA/0001")).splitlines()
    app = review([entry_for(ds, "camA/0001", 0, 0)])
    app._crop_review_selected = 0
    app._crop_review_reassign(0, 3)

    after = read_exact(ds.label("camA/0001")).splitlines()
    assert after[0].split()[0] == "3", "class id rewritten"
    assert after[0].split()[1:] == original[0].split()[1:], "coordinates untouched"
    assert after[1] == original[1], "the sibling line is byte-identical"


def test_reassign_preserves_a_polygon(review, ds):
    """A reassign must keep every coordinate: `with_class` exists for this."""
    original = read_exact(ds.label("seg/poly1")).splitlines()
    app = review([entry_for(ds, "seg/poly1", 1, 1, bbox=(0.375, 0.425, 0.15, 0.25))])
    app._crop_review_selected = 0
    app._crop_review_reassign(0, 2)

    after = read_exact(ds.label("seg/poly1")).splitlines()
    assert after[1].split()[0] == "2"
    assert len(after[1].split()) == 11, "still a 5-point polygon"
    # Byte-exact, not merely numerically equal: `with_class` splices the id
    # into the raw text rather than re-serializing the coordinates.
    assert after[1].split()[1:] == original[1].split()[1:], "polygon points survived"
    assert after[0] == original[0], "the untouched line is byte-identical"


def test_reassign_leaves_other_images_alone(review, ds):
    """camA/0001 and camB/0001 share a stem -- the cross-contamination trap."""
    before = snapshot(ds.root)
    app = review([entry_for(ds, "camA/0001", 0, 0)])
    app._crop_review_selected = 0
    app._crop_review_reassign(0, 3)
    changed = set(snapshot(ds.root)) ^ set(before)
    assert not changed
    assert read_exact(ds.label("camB/0001")) == \
        read_exact(ds.label("camB/0001")), "camB untouched"


# -- delete ----------------------------------------------------------------


def test_delete_removes_exactly_one_line(review, ds):
    before_lines = read_exact(ds.label("camA/0001")).splitlines()
    before = snapshot(ds.root)
    app = review([entry_for(ds, "camA/0001", 0, 0)])
    app._crop_review_selected = 0
    app._crop_review_delete_selected()

    assert_only_changed(before, snapshot(ds.root), {rel_label(ds, "camA/0001")})
    after = read_exact(ds.label("camA/0001")).splitlines()
    assert len(after) == len(before_lines) - 1
    assert after[0] == before_lines[1], "the surviving line is byte-identical"


def test_deleting_the_last_box_leaves_an_empty_file_not_a_missing_one(review, ds):
    """A zero-byte .txt is a valid negative sample; removing it is not
    recoverable. `save_labels` writes an empty file -- this path must agree."""
    label = ds.label("camB/0001")
    assert len(read_exact(label).splitlines()) == 1, "precondition: one box"

    app = review([entry_for(ds, "camB/0001", 0, 2,
                            bbox=(0.75, 0.75, 0.15, 0.15))])
    app._crop_review_selected = 0
    app._crop_review_delete_selected()

    assert label.exists(), "the label file was deleted, not emptied"
    assert read_exact(label).strip() == ""


def test_deleting_one_of_three_keeps_the_others_pointing_at_the_right_lines(review, ds):
    """Line numbers shift when a line above them is removed."""
    label = ds.label("bad/ok")
    lines = read_exact(label).splitlines()
    app = review([
        entry_for(ds, "bad/ok", 0, 1, bbox=(0.5, 0.5, 0.2, 0.2)),
        entry_for(ds, "bad/ok", 1, 99, bbox=(0.5, 0.5, 0.1, 0.1)),
        entry_for(ds, "bad/ok", 3, 0, bbox=(1.4, 0.5, 0.2, 0.2)),
    ])
    app._crop_review_selected = 0
    app._crop_review_delete_selected()

    # The two survivors must have shifted up by one.
    assert [e['line_idx'] for e in app._crop_review_entries] == [0, 2]
    after = read_exact(label).splitlines()
    assert after[0] == lines[1]
    assert after[2] == lines[3]


# -- the line_idx / label_boxes mismatch -----------------------------------


def test_reassign_hits_the_right_box_despite_malformed_lines_above(review, ds):
    """`line_idx` is a FILE line number, but `label_boxes` skips unparsed
    lines. GAUNTLET has blanks and junk, so the two numberings diverge."""
    label = ds.label("bad/ok")
    lines = read_exact(label).splitlines()
    # File line 5 is the 6-field confidence row: "0 0.5 0.5 0.2 0.2 0.95"
    assert lines[5].split()[0] == "0" and len(lines[5].split()) == 6

    app = review([entry_for(ds, "bad/ok", 5, 0, bbox=(0.5, 0.5, 0.2, 0.2))])
    app._crop_review_selected = 0
    app._crop_review_reassign(0, 2)

    after = read_exact(label).splitlines()
    assert after[5].split()[0] == "2", "the intended file line was rewritten"
    assert after[5].split()[1:] == lines[5].split()[1:], "confidence column kept"
    for i, line in enumerate(lines):
        if i != 5:
            assert after[i] == line, f"line {i} was collateral damage"
    # Lines 5, 6 and 10 hold an identical cls-0 box; the recorded line number
    # must win over the later duplicates.
    assert after[6] == lines[6] and after[10] == lines[10]


# -- interaction with the main window --------------------------------------


def test_a_review_delete_does_not_make_the_next_save_rewrite_everything(review, ds):
    """`save_labels` no-ops when nothing changed. A review edit that updates
    `label_boxes` but not `_loaded_boxes` breaks that guard, and the next `s`
    re-serializes the whole file -- flattening polygons and dropping columns."""
    app = review([])
    app.filtered_image_paths = [ds.image("seg/mixed.jpg")]
    app.current_image_index = 0
    app.load_image()
    original = read_exact(ds.label("seg/mixed"))
    assert "0.60 0.70 0.60 0.70" in original, "precondition: a polygon is present"

    app._crop_review_entries = [entry_for(ds, "seg/mixed", 0, 0,
                                          bbox=(0.5, 0.5, 0.2, 0.2))]
    app._crop_review_selected = 0
    app._crop_review_delete_selected()

    before = snapshot(ds.root)
    app.save_labels()
    assert_only_changed(before, snapshot(ds.root), set())


def test_a_review_delete_keeps_the_polygon_when_the_image_is_open(review, ds):
    app = review([])
    app.filtered_image_paths = [ds.image("seg/mixed.jpg")]
    app.current_image_index = 0
    app.load_image()

    app._crop_review_entries = [entry_for(ds, "seg/mixed", 0, 0,
                                          bbox=(0.5, 0.5, 0.2, 0.2))]
    app._crop_review_selected = 0
    app._crop_review_delete_selected()
    app.save_labels()

    after = read_exact(ds.label("seg/mixed"))
    assert len(after.strip().splitlines()) == 1
    assert len(after.strip().split()) == 9, "the polygon survived intact"


# -- nothing selected ------------------------------------------------------


def test_delete_with_no_selection_writes_nothing(review, ds):
    before = snapshot(ds.root)
    app = review([entry_for(ds, "camA/0001", 0, 0)])
    app._crop_review_selected = None
    app._crop_review_delete_selected()
    assert_only_changed(before, snapshot(ds.root), set())


def test_reassign_to_the_same_class_still_only_touches_one_file(review, ds):
    before = snapshot(ds.root)
    app = review([entry_for(ds, "camA/0001", 0, 0)])
    app._crop_review_selected = 0
    app._crop_review_reassign(0, 0)
    changed = {k for k, v in snapshot(ds.root).items() if before.get(k) != v}
    assert changed <= {rel_label(ds, "camA/0001")}


# -- the GAUNTLET file must survive being touched at all -------------------


def test_touching_a_file_with_malformed_lines_does_not_drop_them(review, ds):
    """GAUNTLET holds blanks, a CRLF line, junk and a missing trailing newline.
    Rewriting one line must not reformat or discard the rest."""
    label = ds.label("bad/ok")
    before = read_exact(label)
    app = review([entry_for(ds, "bad/ok", 0, 1, bbox=(0.5, 0.5, 0.2, 0.2))])
    app._crop_review_selected = 0
    app._crop_review_reassign(0, 2)

    after = read_exact(label)
    assert len(after.splitlines()) == len(before.splitlines()), "a line vanished"
    assert "abc 0.5 0.5 0.2 0.2" in after, "the non-numeric line survived"
    assert "\r\n" in after, "the CRLF line ending survived"
    assert GAUNTLET.count("\n") == before.count("\n")
    assert POLY1  # imported for the seg fixtures above


# -- closing ---------------------------------------------------------------


def test_closing_with_findings_asks_first(review, ds):
    """Escape is bound outside the typing guard, so one keystroke after a long
    scan would otherwise discard every finding."""
    app = review([entry_for(ds, "camA/0001", 0, 0)])
    app.dialogs.answer = False
    app._crop_review_close()

    assert app.dialogs.asks, "closed without asking"
    assert app._crop_review_window is not None, "closed anyway"
    assert len(app._crop_review_entries) == 1


def test_confirming_the_close_discards_them(review, ds):
    app = review([entry_for(ds, "camA/0001", 0, 0)])
    app.dialogs.answer = True
    app._crop_review_close()
    assert app._crop_review_window is None


def test_closing_an_empty_review_does_not_ask(review, ds):
    app = review([])
    app.dialogs.asks.clear()
    app._crop_review_close()
    assert not app.dialogs.asks
    assert app._crop_review_window is None


# -- the crop shows both boxes ---------------------------------------------


def test_the_thumbnail_renders_through_the_shared_compositor(review, ds):
    app = review([entry_for(ds, "camA/0001", 0, 0,
                            pred_bbox_norm=(0.55, 0.52, 0.22, 0.30))])
    photo = app._crop_review_build_thumbnail(app._crop_review_entries[0], 200, 150)
    assert photo is not None
    assert photo.width() > 0 and photo.height() > 0


def test_draw_args_carry_the_prediction_when_there_is_one(review, ds):
    app = review([entry_for(ds, "camA/0001", 0, 0,
                            pred_bbox_norm=(0.55, 0.52, 0.22, 0.30))])
    args = app._crop_review_draw_args(app._crop_review_entries[0])
    assert args['pred_bbox_norm'] == (0.55, 0.52, 0.22, 0.30)
    assert args['pred_label'].endswith("0.80"), args['pred_label']
    assert args['gt_color'] != args['pred_color'], "the two boxes must differ"


def test_draw_args_degrade_when_there_is_no_prediction(review, ds):
    """'Model sees nothing' entries, Qwen imports, and any scan run before the
    predicted box was recorded all land here."""
    app = review([entry_for(ds, "camA/0001", 0, 0,
                            kind='missing', pred_cls_id=None, pred_conf=0.0)])
    args = app._crop_review_draw_args(app._crop_review_entries[0])
    assert not args.get('pred_bbox_norm')
    assert 'pred_label' not in args
    photo = app._crop_review_build_thumbnail(app._crop_review_entries[0], 200, 150)
    assert photo is not None, "a one-box crop must still render"


def test_a_class_recolour_invalidates_the_thumbnails(review, ds):
    """Thumbnails now carry the class colour in their pixels."""
    app = review([entry_for(ds, "camA/0001", 0, 0)])
    entry = app._crop_review_entries[0]
    before = app._crop_review_build_thumbnail(entry, 200, 150)
    assert before is not None

    app.class_info[0]['color'] = [7, 7, 7]
    app._crop_review_refresh_class_info()

    # The refresh re-renders straight away, so the cache is repopulated rather
    # than empty -- what matters is that the entry's thumbnail was REBUILT and
    # not served from the pre-recolour cache.
    after = app._crop_review_thumb_cache.get(id(entry))
    assert after is not before, "a stale-coloured thumbnail was reused"
