"""How many boxes are stacked here?

Two identical label lines draw two identical rectangles: same coordinates, same
colour, same caption, same pixels. On screen that is indistinguishable from one
box, so the overlap filter could flag an image the editor was physically unable
to show a problem in -- measured on pvn-vehicle, 7 of the 8 same-class hits at
IoU >= 0.9 were byte-identical duplicate lines.

`detect_current_overlaps` knew which boxes overlapped but threw away how many.
These pin that it now reports the count, and that the count reaches the caption.
"""

from __future__ import annotations

import pytest

from yolo_labeling.ui import filters as _filters

BOX = (10.0, 10.0, 50.0, 50.0)
NEAR = (12.0, 12.0, 52.0, 52.0)     # overlaps BOX heavily
FAR = (200.0, 200.0, 240.0, 240.0)


def _app(boxes, scope='same', threshold=0.5):
    """Bare object carrying only what `detect_current_overlaps` reads."""
    from yolo_labeling import app as _appmod

    p = type("P", (_filters.FiltersMixin,), {})()
    p.detect_current_overlaps = _appmod.YOLOLabelingTool.detect_current_overlaps.__get__(p)
    p.label_boxes = [(float(c), *b) for c, b in boxes]
    p.filter_overlap_scope = scope
    p.filter_overlap_threshold = threshold
    return p


# -- the counts ------------------------------------------------------------


def test_two_identical_boxes_each_report_a_stack_of_two():
    """The case that is invisible on screen."""
    app = _app([(0, BOX), (0, BOX)])
    app.detect_current_overlaps()
    assert app.overlapping_boxes == [0, 1]
    assert app.overlap_counts == {0: 2, 1: 2}


def test_three_identical_boxes_each_report_three():
    app = _app([(0, BOX), (0, BOX), (0, BOX)])
    app.detect_current_overlaps()
    assert app.overlap_counts == {0: 3, 1: 3, 2: 3}


def test_the_count_is_per_box_not_per_group():
    """A chain A-B-C where A and C do not touch.

    B overlaps two boxes, A and C overlap one each. Reporting the group size (3)
    for all three would tell the user to look for three stacked boxes at A.
    """
    a = (10.0, 10.0, 50.0, 50.0)
    b = (12.0, 12.0, 52.0, 52.0)
    c = (14.0, 14.0, 54.0, 54.0)
    app = _app([(0, a), (0, b), (0, c)], threshold=0.7)
    app.detect_current_overlaps()
    assert app.overlap_counts == {0: 2, 1: 3, 2: 2}


def test_no_overlap_leaves_the_counts_empty():
    app = _app([(0, BOX), (0, FAR)])
    app.detect_current_overlaps()
    assert app.overlapping_boxes == []
    assert app.overlap_counts == {}


def test_counts_follow_the_scope():
    """Same-class scope must not count a different-class neighbour."""
    app = _app([(0, BOX), (1, BOX)], scope='same')
    app.detect_current_overlaps()
    assert app.overlap_counts == {}

    app = _app([(0, BOX), (1, BOX)], scope='different')
    app.detect_current_overlaps()
    assert app.overlap_counts == {0: 2, 1: 2}


def test_an_empty_image_does_not_leave_stale_counts():
    app = _app([(0, BOX), (0, BOX)])
    app.detect_current_overlaps()
    assert app.overlap_counts
    app.label_boxes = []
    app.detect_current_overlaps()
    assert app.overlap_counts == {}


# -- the caption -----------------------------------------------------------


@pytest.mark.gui
def test_the_caption_names_the_stack_size(gui_app, monkeypatch, tmp_path):
    """The count has to reach the screen, not just the attribute.

    `draw_tag` is captured rather than the pixels: this asserts what the user is
    told, without depending on font metrics.
    """
    from yolo_labeling.core import draw as _draw

    app = gui_app
    tags: list[str] = []
    real = _draw.draw_tag
    monkeypatch.setattr(_draw, "draw_tag",
                        lambda img, text, *a, **k: (tags.append(text), real(img, text, *a, **k))[1])

    img_path = app.filtered_image_paths[0] if app.filtered_image_paths else None
    if img_path is None:
        pytest.skip("fixture dataset produced no images")
    app.load_image()
    # Two identical boxes, the duplicate-line case.
    cls = next(iter(app.class_info))
    app.label_boxes = [(float(cls), 5, 5, 40, 40), (float(cls), 5, 5, 40, 40)]
    app.user_boxes = []
    app.show_label_boxes = True
    app.show_box_labels = True
    app.highlight_overlaps = True
    app.filter_overlap_scope = 'same'
    app.filter_overlap_threshold = 0.5
    app.detect_current_overlaps()
    tags.clear()
    app.display_image()

    stacked = [t for t in tags if '2' in t and t.startswith('L ')]
    assert stacked, f"no caption reported the stack size; captions were {tags}"


@pytest.mark.gui
def test_captions_are_ascii_so_opencv_can_render_them(gui_app, monkeypatch):
    """cv2's Hershey fonts draw any non-ASCII codepoint as '?'.

    The overlap caption used to end in U+26A0, which reached the user as
    'L bus ?'. Nothing in the suite noticed, because nothing looked at the text.
    """
    from yolo_labeling.core import draw as _draw

    app = gui_app
    tags: list[str] = []
    real = _draw.draw_tag
    monkeypatch.setattr(_draw, "draw_tag",
                        lambda img, text, *a, **k: (tags.append(text), real(img, text, *a, **k))[1])

    app.load_image()
    cls = next(iter(app.class_info))
    app.label_boxes = [(float(cls), 5, 5, 40, 40), (float(cls), 5, 5, 40, 40)]
    app.user_boxes = []
    app.show_label_boxes = True
    app.show_box_labels = True
    app.highlight_overlaps = True
    app.filter_overlap_scope = 'same'
    app.detect_current_overlaps()
    tags.clear()
    app.display_image()

    bad = [t for t in tags if any(ord(ch) > 127 for ch in t)]
    assert not bad, f"these captions render as '?' in cv2: {bad}"


# -- the always-visible counter -------------------------------------------


@pytest.mark.gui
def test_the_corner_overlay_reports_overlapping_boxes(gui_app):
    """Captions can be switched off (Shift+T) precisely because they cover small
    objects -- so the count must also appear somewhere that is always on."""
    app = gui_app
    app.load_image()
    cls = next(iter(app.class_info))
    app.label_boxes = [(float(cls), 5, 5, 40, 40), (float(cls), 5, 5, 40, 40)]
    app.user_boxes = []
    app.show_box_labels = False
    app.highlight_overlaps = True
    app.filter_overlap_scope = 'same'
    app.detect_current_overlaps()
    app.display_image()

    texts = [app.canvas.itemcget(i, 'text')
             for i in app.canvas.find_withtag('filename_overlay')
             if app.canvas.type(i) == 'text']
    # '!2', not just '2' -- "L:2" already contains a 2, so a looser assertion
    # would pass without the feature existing.
    assert any('!2' in t for t in texts), \
        f"overlay did not report the overlap count: {texts}"


@pytest.mark.gui
def test_the_overlay_stays_quiet_when_nothing_overlaps(gui_app):
    app = gui_app
    app.load_image()
    cls = next(iter(app.class_info))
    app.label_boxes = [(float(cls), 5, 5, 20, 20), (float(cls), 60, 60, 90, 90)]
    app.user_boxes = []
    app.highlight_overlaps = True
    app.detect_current_overlaps()
    app.display_image()

    texts = [app.canvas.itemcget(i, 'text')
             for i in app.canvas.find_withtag('filename_overlay')
             if app.canvas.type(i) == 'text']
    counts = [t for t in texts if 'L:' in t]
    assert counts and all('!' not in t for t in counts), \
        f"overlay warned with no overlaps present: {counts}"
