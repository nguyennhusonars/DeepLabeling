"""The canvas: the whole frame and its labels (docs/design/2026-10-04-app-foundation.md#window).

Scene coordinates are image pixels. The canvas edits nothing itself: a finished drag
or click becomes a signal in image pixels -- drawn, picked, moved, resized -- and the
window turns it into an intent. While the mouse moves, the canvas only previews.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from .boxes import BoxView
from .classes import text_color

BACKGROUND = "#2b2b2b"
DRAG_PX = 3             #: a press that moves less than this far is a click (the spec)
HANDLE_PX = 8           #: a handle's size on screen, the same at every zoom
GRAB_PX = 6             #: how near a handle's centre a press takes the handle
SELECTED_ALPHA = 70     #: a selected box is filled with its colour at this opacity
CROSSHAIR = "#ffffff"
#: the eight handles of a box, as fractions of its width and height
HANDLES = ((0, 0), (0.5, 0), (1, 0), (1, 0.5), (1, 1), (0.5, 1), (0, 1), (0, 0.5))


@dataclass
class _Drag:
    kind: str                           #: "draw", "move" or "resize"
    press: QPointF                      #: where the button went down, in viewport pixels
    start: QPointF                      #: the same point in the scene
    shift: bool
    handle: tuple[float, float] | None = None
    active: bool = False                #: moved DRAG_PX or more: a drag, not a click
    origins: dict = field(default_factory=dict)     #: item -> its position at the press


class CaptionItem(QGraphicsItem):
    """A caption on a solid plate, inside its box's top edge. It ignores the view's
    zoom, so it stays readable; the plate keeps it legible on any image."""

    def __init__(self, text: str, color: str):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.text, self.color = text, QColor(color)
        self._font = QFont()
        self._font.setPointSize(9)
        metrics = QFontMetricsF(self._font)
        self._rect = QRectF(0, 0, metrics.horizontalAdvance(text) + 6, metrics.height() + 2)

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.fillRect(self._rect, self.color)
        painter.setPen(QColor(text_color(self.color.name())))
        painter.setFont(self._font)
        painter.drawText(self._rect.adjusted(3, 0, -3, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text)


class Canvas(QGraphicsView):
    drawn = Signal(object)              #: (x1, y1, x2, y2) in image pixels, inside the image
    picked = Signal(list)               #: the line indices to select now
    moved = Signal(float, float)        #: the selected boxes' shift, in image pixels
    resized = Signal(int, object)       #: a line index and its new (x1, y1, x2, y2)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor(BACKGROUND))
        self.setFocusPolicy(Qt.NoFocus)             # keys belong to the window's actions
        self._pixmap = QGraphicsPixmapItem()
        self._pixmap.setTransformationMode(Qt.SmoothTransformation)
        self.scene().addItem(self._pixmap)
        self._message = QGraphicsSimpleTextItem()
        self._message.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self._message.setBrush(QColor("#e0e0e0"))
        self.scene().addItem(self._message)
        self._items: list[QGraphicsItem] = []
        self._views: list[BoxView] = []
        self._size: tuple[int, int] | None = None
        self.show_labels = True
        self.show_captions = True
        self.show_crosshair = False
        self._fitted = True
        self._pan_from = None
        self._selected: frozenset[int] = frozenset()
        self._box_items: dict[int, list[QGraphicsItem]] = {}   #: line index -> its items
        self._handles: list[QGraphicsRectItem] = []
        self._drag: _Drag | None = None
        self._preview: QGraphicsRectItem | None = None
        self._draw_color = "#ffffff"
        self._mouse: QPointF | None = None          #: the crosshair's scene point
        self.viewport().setMouseTracking(True)

    # -- what is shown -----------------------------------------------------------

    @property
    def image_size(self) -> tuple[int, int] | None:
        return self._size

    @property
    def message(self) -> str:
        return self._message.text() if self._message.isVisible() else ""

    def set_image(self, image: QImage | None, message: str = "") -> None:
        """Show an image, fitted to the view; or no image and a message saying why."""
        self._views, self._selected = [], frozenset()
        self._clear()
        if image is None:
            self._pixmap.setPixmap(QPixmap())
            self._size = None
            self._message.setText(message)
            self._message.setVisible(bool(message))
            self.scene().setSceneRect(QRectF(0, 0, 1, 1))
            self.resetTransform()
            self._message.setPos(0, 0)
            self.centerOn(0, 0)
            return
        self._message.setVisible(False)
        self._pixmap.setPixmap(QPixmap.fromImage(image))
        self._size = (image.width(), image.height())
        self.scene().setSceneRect(QRectF(0, 0, image.width(), image.height()))
        self.fit()

    def set_boxes(self, views: list[BoxView], selected=()) -> None:
        self._views, self._selected = list(views), frozenset(selected)
        self._redraw()

    def set_selected(self, indices) -> None:
        self._selected = frozenset(indices)
        self._redraw()

    def set_layers(self, *, labels: bool, captions: bool) -> None:
        self.show_labels, self.show_captions = labels, captions
        self._redraw()

    def set_draw_color(self, color: str) -> None:
        """The colour of the box being drawn: the active class's."""
        self._draw_color = color

    def set_crosshair(self, on: bool) -> None:
        self.show_crosshair = on
        self.viewport().update()

    def caption_items(self) -> list[CaptionItem]:
        return [it for it in self._items if isinstance(it, CaptionItem)]

    def handle_items(self) -> list[QGraphicsRectItem]:
        return list(self._handles)

    def _clear(self) -> None:
        self._drag = None                           # whatever it previewed is gone
        for item in self._items + ([self._preview] if self._preview else []):
            self.scene().removeItem(item)
        self._items, self._box_items, self._handles, self._preview = [], {}, [], None

    def _redraw(self) -> None:
        self._clear()
        if not self.show_labels or self._size is None:
            return
        for view in self._views:
            self._draw(view)

    def _draw(self, view: BoxView) -> None:
        pen = QPen(QColor(view.color))
        pen.setCosmetic(True)                       # the same width at every zoom
        pen.setWidth(4 if view.highlighted else 2)
        if not view.known:
            pen.setStyle(Qt.DashLine)
        x1, y1, x2, y2 = view.rect
        if view.polygon:
            shape = self.scene().addPolygon(QPolygonF([QPointF(x, y) for x, y in view.polygon]), pen)
        else:
            shape = self.scene().addRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)), pen)
        shape.setZValue(1)
        items = [shape]
        if view.index in self._selected:
            fill = QColor(view.color)
            fill.setAlpha(SELECTED_ALPHA)
            shape.setBrush(QBrush(fill))
        if self.show_captions:
            caption = CaptionItem(view.caption, view.color)
            caption.setPos(x1, y1)
            caption.setZValue(2)
            self.scene().addItem(caption)
            items.append(caption)
        if self._selected == {view.index} and not view.polygon:
            for fx, fy in HANDLES:
                handle = QGraphicsRectItem(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX)
                handle.setFlag(QGraphicsItem.ItemIgnoresTransformations)
                handle.setBrush(QColor("#ffffff"))
                handle.setPen(QPen(QColor("#202020"), 0))
                handle.setPos(x1 + fx * (x2 - x1), y1 + fy * (y2 - y1))
                handle.setZValue(4)
                self.scene().addItem(handle)
                self._handles.append(handle)
            items += self._handles
        self._items += items
        self._box_items[view.index] = items

    # -- the mouse: draw, select, move, resize -------------------------------------------

    def _editable(self) -> bool:
        return self._size is not None and self.show_labels

    def _contains(self, view: BoxView, point: QPointF) -> bool:
        if view.polygon:
            return QPolygonF([QPointF(x, y) for x, y in view.polygon]).containsPoint(point, Qt.OddEvenFill)
        x1, y1, x2, y2 = view.rect
        return x1 <= point.x() <= x2 and y1 <= point.y() <= y2

    def _boxes_at(self, point: QPointF) -> list[int]:
        """The line indices of the boxes under a scene point, smallest first."""
        under = [v for v in self._views if self._contains(v, point)]
        under.sort(key=lambda v: ((v.rect[2] - v.rect[0]) * (v.rect[3] - v.rect[1]), v.index))
        return [v.index for v in under]

    def _handle_at(self, pos: QPointF) -> tuple[float, float] | None:
        """The handle of the one selected box nearest a viewport point, if near enough."""
        views = [v for v in self._views if v.index in self._selected]
        if len(self._selected) != 1 or len(views) != 1 or views[0].polygon:
            return None
        x1, y1, x2, y2 = views[0].rect
        a, b = self.mapFromScene(QPointF(x1, y1)), self.mapFromScene(QPointF(x2, y2))
        # A box a few pixels across on screen would be all handle: its middle moves it.
        best, handle = min(GRAB_PX, min(b.x() - a.x(), b.y() - a.y()) / 4), None
        for fx, fy in HANDLES:
            at = self.mapFromScene(QPointF(x1 + fx * (x2 - x1), y1 + fy * (y2 - y1)))
            distance = math.hypot(at.x() - pos.x(), at.y() - pos.y())
            if distance <= best:
                best, handle = distance, (fx, fy)
        return handle

    def _inside_image(self, point: QPointF) -> QPointF:
        w, h = self._size
        return QPointF(min(max(point.x(), 0.0), w), min(max(point.y(), 0.0), h))

    def _resized_rect(self, view: BoxView, handle, delta: QPointF) -> tuple[float, float, float, float]:
        """A box's rect with the handle's edges shifted by `delta`, inside the image."""
        x1, y1, x2, y2 = view.rect
        fx, fy = handle
        if fx == 0:
            x1 += delta.x()
        elif fx == 1:
            x2 += delta.x()
        if fy == 0:
            y1 += delta.y()
        elif fy == 1:
            y2 += delta.y()
        a, b = self._inside_image(QPointF(x1, y1)), self._inside_image(QPointF(x2, y2))
        return (min(a.x(), b.x()), min(a.y(), b.y()), max(a.x(), b.x()), max(a.y(), b.y()))

    def _view(self, index: int) -> BoxView:
        return next(v for v in self._views if v.index == index)

    def cancel_drag(self) -> bool:
        """Drop the drag in progress and its preview. True when a drag was showing."""
        drag = self._drag
        if drag is None:
            return False
        self._redraw()                              # puts back what the drag moved
        return drag.active

    def _start(self, drag: _Drag) -> None:
        drag.active = True
        if drag.kind == "draw":
            pen = QPen(QColor(self._draw_color))
            pen.setCosmetic(True)
            pen.setWidth(2)
            self._preview = self.scene().addRect(QRectF(drag.start, drag.start), pen)
            self._preview.setZValue(3)
        else:
            moving = self._selected if drag.kind == "move" else ()
            drag.origins = {item: item.pos() for i in moving for item in self._box_items.get(i, ())}

    def _move_delta(self, delta: QPointF) -> QPointF:
        """`delta`, cut so every selected box stays inside the image: they move together."""
        w, h = self._size
        rects = [v.rect for v in self._views if v.index in self._selected]
        if not rects:
            return delta
        dx = min(max(delta.x(), max(-r[0] for r in rects)), min(w - r[2] for r in rects))
        dy = min(max(delta.y(), max(-r[1] for r in rects)), min(h - r[3] for r in rects))
        return QPointF(dx, dy)

    def _preview_to(self, drag: _Drag, point: QPointF) -> None:
        delta = point - drag.start
        if drag.kind == "draw":
            self._preview.setRect(QRectF(drag.start, self._inside_image(point)).normalized())
        elif drag.kind == "move":
            delta = self._move_delta(delta)
            for item, origin in drag.origins.items():
                item.setPos(origin + delta)
        else:
            [index] = self._selected
            x1, y1, x2, y2 = self._resized_rect(self._view(index), drag.handle, delta)
            shape, *rest = self._box_items[index]
            shape.setRect(QRectF(x1, y1, x2 - x1, y2 - y1))
            for item in rest:
                if isinstance(item, CaptionItem):
                    item.setPos(x1, y1)
            for handle, (fx, fy) in zip(self._handles, HANDLES):
                handle.setPos(x1 + fx * (x2 - x1), y1 + fy * (y2 - y1))

    def _finish(self, drag: _Drag, point: QPointF) -> None:
        self._redraw()                              # the window shows the saved result
        if drag.kind == "draw":
            a, b = self._inside_image(drag.start), self._inside_image(point)
            rect = (min(a.x(), b.x()), min(a.y(), b.y()), max(a.x(), b.x()), max(a.y(), b.y()))
            if rect[2] - rect[0] >= 1 and rect[3] - rect[1] >= 1:
                self.drawn.emit(rect)
        elif drag.kind == "move":
            delta = self._move_delta(point - drag.start)
            if delta.x() or delta.y():
                self.moved.emit(delta.x(), delta.y())
        else:
            [index] = self._selected
            view = self._view(index)
            rect = self._resized_rect(view, drag.handle, point - drag.start)
            if rect != view.rect and rect[2] - rect[0] >= 1 and rect[3] - rect[1] >= 1:
                self.resized.emit(index, rect)

    def _click(self, point: QPointF, shift: bool) -> None:
        under = self._boxes_at(point)
        if shift:
            if under:
                self.picked.emit(sorted(self._selected ^ {under[0]}))
            return
        if not under:
            self.picked.emit([])
        elif len(self._selected) == 1 and next(iter(self._selected)) in under:
            at = under.index(next(iter(self._selected)))
            self.picked.emit([under[(at + 1) % len(under)]])
        else:
            self.picked.emit([under[0]])

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if not self.show_crosshair or self._mouse is None or self._size is None:
            return
        w, h = self._size
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(QColor(CROSSHAIR))
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(QPointF(self._mouse.x(), 0), QPointF(self._mouse.x(), h))
        painter.drawLine(QPointF(0, self._mouse.y()), QPointF(w, self._mouse.y()))
        painter.restore()

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Leave and self._mouse is not None:
            self._mouse = None
            self.viewport().update()
        return super().viewportEvent(event)

    # -- zoom and pan --------------------------------------------------------------

    def fit(self) -> None:
        if self._size is not None:
            self.fitInView(self._pixmap, Qt.KeepAspectRatio)
            self._fitted = True

    def zoom_by(self, factor: float) -> None:
        if self._size is not None:
            self.scale(factor, factor)
            self._fitted = False

    def wheelEvent(self, event) -> None:
        self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fitted:
            self.fit()

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = event.position().toPoint()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._editable() and self._drag is None:
            pos = event.position()
            point = self.mapToScene(pos.toPoint())
            handle = self._handle_at(pos)
            selected = any(self._contains(v, point) for v in self._views if v.index in self._selected)
            kind = "resize" if handle else "move" if selected else "draw"
            self._drag = _Drag(kind, pos, point, bool(event.modifiers() & Qt.ShiftModifier), handle)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.show_crosshair:
            self._mouse = self.mapToScene(event.position().toPoint())
            self.viewport().update()
        if self._pan_from is not None:
            point = event.position().toPoint()
            delta, self._pan_from = point - self._pan_from, point
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._fitted = False
            event.accept()
            return
        drag = self._drag
        if drag is not None:
            pos = event.position()
            if not drag.active and math.hypot(pos.x() - drag.press.x(), pos.y() - drag.press.y()) < DRAG_PX:
                return
            if not drag.active:
                self._start(drag)
            self._preview_to(drag, self.mapToScene(pos.toPoint()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_from is not None and event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = None
            self.viewport().unsetCursor()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._drag is not None:
            drag, self._drag = self._drag, None
            point = self.mapToScene(event.position().toPoint())
            if drag.active:
                self._finish(drag, point)
            elif drag.kind != "resize":             # a click on a handle selects nothing new
                self._click(drag.start, drag.shift)
            event.accept()
            return
        super().mouseReleaseEvent(event)
