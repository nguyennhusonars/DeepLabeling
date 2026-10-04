"""The canvas: the whole frame and its labels (docs/design/2026-10-04-app-foundation.md#window).

Scene coordinates are image pixels. Plan 1b draws and navigates; plan 1c adds editing.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from .boxes import BoxView
from .classes import text_color

BACKGROUND = "#2b2b2b"


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
        self._fitted = True
        self._pan_from = None

    # -- what is shown -----------------------------------------------------------

    @property
    def image_size(self) -> tuple[int, int] | None:
        return self._size

    @property
    def message(self) -> str:
        return self._message.text() if self._message.isVisible() else ""

    def set_image(self, image: QImage | None, message: str = "") -> None:
        """Show an image, fitted to the view; or no image and a message saying why."""
        self._views = []
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

    def set_boxes(self, views: list[BoxView]) -> None:
        self._views = list(views)
        self._redraw()

    def set_layers(self, *, labels: bool, captions: bool) -> None:
        self.show_labels, self.show_captions = labels, captions
        self._redraw()

    def caption_items(self) -> list[CaptionItem]:
        return [it for it in self._items if isinstance(it, CaptionItem)]

    def _clear(self) -> None:
        for item in self._items:
            self.scene().removeItem(item)
        self._items = []

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
        self._items.append(shape)
        if self.show_captions:
            caption = CaptionItem(view.caption, view.color)
            caption.setPos(x1, y1)
            caption.setZValue(2)
            self.scene().addItem(caption)
            self._items.append(caption)

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
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pan_from is not None:
            point = event.position().toPoint()
            delta, self._pan_from = point - self._pan_from, point
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._fitted = False
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_from is not None and event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)
