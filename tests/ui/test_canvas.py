"""What the canvas shows, read back from its pixels (the run-and-verify-ui skill)."""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

from deeplabeling.ui.boxes import BoxView
from deeplabeling.ui.canvas import Canvas
from drive import click, drag, mouse, vp

GREY = QColor(80, 80, 80)
RED = BoxView(0, (50, 25, 150, 75), (), "#ff0000", "car", True, False)


def grey_image(w=200, h=100):
    image = QImage(w, h, QImage.Format_RGB32)
    image.fill(GREY)
    return image


@pytest.fixture
def canvas(qtbot):
    c = Canvas()
    qtbot.addWidget(c)
    c.resize(400, 300)
    c.show()
    qtbot.waitUntil(c.isVisible)
    return c


def shot(canvas):
    return canvas.viewport().grab().toImage()


def pixel(canvas, x, y, image=None):
    image = image or shot(canvas)
    return QColor(image.pixel(canvas.mapFromScene(QPointF(x, y))))


def is_red(c):
    return c.red() > 200 and c.green() < 80 and c.blue() < 80


def near(canvas, x, y, image=None, radius=2):
    """The pixels within `radius` of a scene point: a line on a pixel boundary is
    antialiased across two pixels, so one exact pixel can be half its colour."""
    image = image or shot(canvas)
    centre = canvas.mapFromScene(QPointF(x, y))
    return [QColor(image.pixel(centre.x() + dx, centre.y() + dy))
            for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)]


def test_a_box_is_drawn_in_its_colour_where_it_is(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    assert any(map(is_red, near(canvas, 100, 25))) and any(map(is_red, near(canvas, 150, 50)))
    assert pixel(canvas, 100, 50) == GREY


def test_the_caption_sits_on_a_plate_inside_the_top_edge(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    corner = canvas.mapFromScene(QPointF(50, 25))
    assert is_red(QColor(shot(canvas).pixel(corner + QPoint(4, 6))))
    [caption] = canvas.caption_items()
    assert caption.text == "car" and caption.isVisible()
    assert canvas.viewport().rect().contains(corner + QPoint(int(caption.boundingRect().width()) - 1, 6))


def test_an_unknown_class_is_drawn_grey_and_dashed(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BoxView(1, (50, 25, 150, 75), (), "#9e9e9e", "#99?", False, False)])
    image = shot(canvas)
    x = canvas.mapFromScene(QPointF(150, 50)).x()
    top, bottom = canvas.mapFromScene(QPointF(150, 35)).y(), canvas.mapFromScene(QPointF(150, 70)).y()
    # across the line only, row by row: dashes read near the pen's grey, gaps near the image's
    edge = [max(QColor(image.pixel(x + dx, y)).red() for dx in range(-2, 3)) for y in range(top, bottom)]
    assert any(v > 140 for v in edge) and any(v <= 110 for v in edge)


def test_a_highlighted_box_is_drawn_thicker(canvas):
    def thickness(view):
        canvas.set_image(grey_image())
        canvas.set_boxes([view])
        image = shot(canvas)
        x = canvas.mapFromScene(QPointF(120, 25)).x()
        y0 = canvas.mapFromScene(QPointF(120, 25)).y()
        return sum(is_red(QColor(image.pixel(x, y))) for y in range(y0 - 6, y0 + 7))

    plain = thickness(RED)
    thick = thickness(BoxView(0, RED.rect, (), "#ff0000", "car", True, True))
    assert thick > plain >= 1


def test_a_polygon_is_drawn_by_its_points(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BoxView(0, (20, 10, 60, 50), ((20, 10), (60, 10), (20, 50)), "#ff0000", "car", True, False)])
    assert is_red(pixel(canvas, 40, 30))           # on the diagonal
    assert pixel(canvas, 55, 45) == GREY           # inside the extent, outside the triangle


def test_layers_hide_the_labels_or_only_the_captions(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    canvas.set_layers(labels=True, captions=False)
    assert canvas.caption_items() == [] and is_red(pixel(canvas, 100, 25))
    canvas.set_layers(labels=False, captions=True)
    assert not is_red(pixel(canvas, 100, 25))


def test_no_image_shows_why(canvas):
    canvas.set_image(None, "cannot decode bad/images/corrupt.jpg")
    assert canvas.message == "cannot decode bad/images/corrupt.jpg" and canvas.image_size is None
    origin = canvas.mapFromScene(QPointF(0, 0))
    assert canvas.viewport().rect().contains(origin)
    image = shot(canvas)
    light = sum(QColor(image.pixel(origin.x() + dx, origin.y() + dy)).red() > 150
                for dx in range(0, 120) for dy in range(0, 14))
    assert light > 20


def test_a_new_image_drops_the_old_boxes(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    canvas.set_image(grey_image())
    assert canvas.caption_items() == [] and not is_red(pixel(canvas, 100, 25))


def test_fit_and_zoom(canvas):
    canvas.set_image(grey_image())
    assert canvas.transform().m11() == pytest.approx(2.0, rel=0.05)
    canvas.zoom_by(2)
    assert canvas.transform().m11() == pytest.approx(4.0, rel=0.05)
    canvas.fit()
    assert canvas.transform().m11() == pytest.approx(2.0, rel=0.05)


def test_resizing_refits_until_the_user_zooms(qtbot, canvas):
    canvas.set_image(grey_image())
    canvas.resize(800, 600)
    qtbot.waitUntil(lambda: canvas.transform().m11() == pytest.approx(4.0, rel=0.05))
    canvas.zoom_by(1.5)
    scale = canvas.transform().m11()
    canvas.resize(400, 300)
    qtbot.wait(20)
    assert canvas.transform().m11() == pytest.approx(scale)


def send(widget, kind, button, pos):
    buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else button
    event = QMouseEvent(kind, QPointF(pos), widget.mapToGlobal(QPointF(pos)), button, buttons, Qt.NoModifier)
    QApplication.sendEvent(widget, event)


def test_a_middle_drag_pans(canvas):
    canvas.set_image(grey_image())
    canvas.zoom_by(4)
    before = canvas.horizontalScrollBar().value()
    vp = canvas.viewport()
    send(vp, QEvent.MouseButtonPress, Qt.MiddleButton, QPoint(200, 150))
    send(vp, QEvent.MouseMove, Qt.MiddleButton, QPoint(150, 150))
    send(vp, QEvent.MouseButtonRelease, Qt.MiddleButton, QPoint(150, 150))
    assert canvas.horizontalScrollBar().value() == before + 50


# -- editing (plan 1c) ---------------------------------------------------------------

BIG = BoxView(0, (20, 10, 180, 90), (), "#ff0000", "bus", True, False)
SMALL = BoxView(1, (60, 30, 100, 70), (), "#ff0000", "car", True, False)
TRIANGLE = BoxView(0, (20, 10, 60, 50), ((20, 10), (60, 10), (20, 50)), "#ff0000", "car", True, False)


def record(canvas):
    seen = []
    canvas.drawn.connect(lambda rect: seen.append(("drawn", rect)))
    canvas.picked.connect(lambda indices: seen.append(("picked", indices)))
    canvas.moved.connect(lambda dx, dy: seen.append(("moved", (dx, dy))))
    canvas.resized.connect(lambda index, rect: seen.append(("resized", index, rect)))
    return seen


def test_a_drag_draws_a_box_and_shows_it_while_dragging(canvas):
    canvas.set_image(grey_image())
    canvas.set_draw_color("#00ff00")
    seen = record(canvas)
    drag(canvas, (20, 20), (80, 60), release=False)
    assert any(c.green() > 200 and c.red() < 80 for c in near(canvas, 80, 40))
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 80, 60))
    [(kind, rect)] = seen
    assert kind == "drawn" and rect == pytest.approx((20, 20, 80, 60), abs=1)
    assert all(c == GREY for c in near(canvas, 80, 40))     # the window draws the saved box


def test_a_drawn_box_is_clamped_to_the_image(canvas):
    canvas.set_image(grey_image())
    seen = record(canvas)
    drag(canvas, (150, 50), (190, 120))
    assert seen[0][1] == pytest.approx((150, 50, 190, 100), abs=1)


def test_a_drag_under_three_pixels_is_a_click(canvas):
    canvas.set_image(grey_image())
    seen = record(canvas)
    start = vp(canvas, 100, 50)
    mouse(canvas, QEvent.MouseButtonPress, start)
    mouse(canvas, QEvent.MouseMove, start + QPoint(2, 0), buttons=Qt.LeftButton)
    mouse(canvas, QEvent.MouseButtonRelease, start + QPoint(2, 0))
    assert seen == [("picked", [])]


def test_a_click_selects_the_smallest_box_under_the_cursor(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BIG, SMALL])
    seen = record(canvas)
    click(canvas, (80, 50))
    click(canvas, (30, 20))
    assert seen == [("picked", [1]), ("picked", [0])]


def test_clicking_a_selected_box_again_cycles_to_the_next_one_under_the_cursor(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BIG, SMALL], selected=[1])
    seen = record(canvas)
    click(canvas, (80, 50))
    canvas.set_selected([0])
    click(canvas, (80, 50))
    assert seen == [("picked", [0]), ("picked", [1])]


def test_shift_click_adds_to_and_removes_from_the_selection(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BIG, SMALL], selected=[0])
    seen = record(canvas)
    click(canvas, (80, 50), Qt.ShiftModifier)
    canvas.set_selected([0, 1])
    click(canvas, (80, 50), Qt.ShiftModifier)
    click(canvas, (190, 95), Qt.ShiftModifier)              # empty space: nothing changes
    assert seen == [("picked", [0, 1]), ("picked", [0])]


def test_a_click_on_empty_space_clears_the_selection(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([SMALL], selected=[1])
    seen = record(canvas)
    click(canvas, (190, 95))
    assert seen == [("picked", [])]


def test_a_click_inside_a_polygon_selects_it_and_outside_it_does_not(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([TRIANGLE])
    seen = record(canvas)
    click(canvas, (25, 15))
    click(canvas, (55, 45))                                  # inside the extent only
    assert seen == [("picked", [0]), ("picked", [])]


def test_a_selected_box_is_filled_and_one_selected_box_shows_eight_handles(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED])
    assert pixel(canvas, 100, 50) == GREY and canvas.handle_items() == []
    canvas.set_selected([0])
    inside = pixel(canvas, 100, 50)
    assert inside.red() > inside.green() + 30
    assert len(canvas.handle_items()) == 8
    corner = vp(canvas, 150, 75)
    assert QColor(shot(canvas).pixel(corner + QPoint(2, -2))).lightness() > 200


def test_several_selected_boxes_or_a_polygon_show_no_handles(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([BIG, SMALL], selected=[0, 1])
    assert canvas.handle_items() == []
    canvas.set_boxes([TRIANGLE], selected=[0])
    assert canvas.handle_items() == []


def test_dragging_a_selected_box_moves_it(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED], selected=[0])
    seen = record(canvas)
    drag(canvas, (100, 50), (120, 60), release=False)
    assert any(map(is_red, near(canvas, 170, 45))) and not any(map(is_red, near(canvas, 150, 40)))
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 120, 60))
    [(kind, delta)] = seen
    assert kind == "moved" and delta == pytest.approx((20, 10), abs=1)
    assert any(map(is_red, near(canvas, 150, 40)))          # back until the window redraws


def test_dragging_a_corner_handle_resizes_the_box(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED], selected=[0])
    seen = record(canvas)
    drag(canvas, (150, 75), (170, 90), release=False)
    assert any(map(is_red, near(canvas, 170, 82)))
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 170, 90))
    [(kind, index, rect)] = seen
    assert (kind, index) == ("resized", 0) and rect == pytest.approx((50, 25, 170, 90), abs=1)


def test_an_edge_handle_moves_one_edge_and_past_the_other_edge_flips(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED], selected=[0])
    seen = record(canvas)
    drag(canvas, (150, 50), (160, 70))                       # the right edge's handle
    drag(canvas, (50, 50), (170, 50))                        # the left edge, past the right
    assert seen[0][2] == pytest.approx((50, 25, 160, 75), abs=1)
    assert seen[1][2] == pytest.approx((150, 25, 170, 75), abs=1)


def test_esc_cancels_a_drag(canvas):
    canvas.set_image(grey_image())
    canvas.set_draw_color("#00ff00")
    seen = record(canvas)
    assert canvas.cancel_drag() is False
    drag(canvas, (20, 20), (80, 60), release=False)
    assert canvas.cancel_drag() is True
    assert all(c == GREY for c in near(canvas, 80, 40))
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 80, 60))
    assert seen == []


def test_labels_redrawn_during_a_drag_cancel_it(canvas):
    canvas.set_image(grey_image())
    canvas.set_boxes([RED], selected=[0])
    seen = record(canvas)
    drag(canvas, (100, 50), (120, 60), release=False)
    canvas.set_boxes([RED], selected=[0])                    # the file changed meanwhile
    mouse(canvas, QEvent.MouseButtonRelease, vp(canvas, 120, 60))
    assert seen == []


def test_nothing_is_edited_without_an_image_or_with_the_labels_hidden(canvas):
    seen = record(canvas)
    canvas.set_image(None, "cannot decode")
    drag(canvas, (20, 20), (80, 60))
    canvas.set_image(grey_image())
    canvas.set_layers(labels=False, captions=True)
    drag(canvas, (20, 20), (80, 60))
    assert seen == []


def test_the_crosshair_follows_the_mouse(canvas):
    canvas.set_image(grey_image())
    canvas.set_crosshair(True)
    mouse(canvas, QEvent.MouseMove, vp(canvas, 100, 50), button=Qt.NoButton)
    assert any(c.lightness() > 200 for c in near(canvas, 100, 10))     # its column
    assert any(c.lightness() > 200 for c in near(canvas, 180, 50))     # its row
    QApplication.sendEvent(canvas.viewport(), QEvent(QEvent.Leave))
    assert all(c == GREY for c in near(canvas, 100, 10))
    mouse(canvas, QEvent.MouseMove, vp(canvas, 100, 50), button=Qt.NoButton)
    canvas.set_crosshair(False)
    assert all(c == GREY for c in near(canvas, 100, 10))
