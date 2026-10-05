"""Driving the UI as a person would: mouse gestures on the canvas, and a launched window."""

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication


def vp(canvas, x, y):
    """The viewport point showing scene (image pixel) point (x, y)."""
    return canvas.mapFromScene(QPointF(x, y))


def mouse(canvas, kind, pos, button=Qt.LeftButton, buttons=None, modifiers=Qt.NoModifier):
    if buttons is None:
        buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else button
    if kind == QEvent.MouseMove:
        button = Qt.NoButton
    event = QMouseEvent(kind, QPointF(pos), canvas.viewport().mapToGlobal(QPointF(pos)),
                        button, buttons, modifiers)
    QApplication.sendEvent(canvas.viewport(), event)


def drag(canvas, a, b, modifiers=Qt.NoModifier, release=True):
    """Press at scene point `a`, move to `b` in steps, and release there."""
    pa, pb = vp(canvas, *a), vp(canvas, *b)
    mouse(canvas, QEvent.MouseButtonPress, pa, modifiers=modifiers)
    for t in (0.25, 0.5, 1.0):
        mouse(canvas, QEvent.MouseMove, pa + (pb - pa) * t, modifiers=modifiers)
    if release:
        mouse(canvas, QEvent.MouseButtonRelease, pb, modifiers=modifiers)


def click(canvas, at, modifiers=Qt.NoModifier):
    drag(canvas, at, at, modifiers)


def start(qtbot, argv, prompter=None):
    """The app launched on `argv`, shown and active, its queue built and image shown."""
    from deeplabeling.__main__ import launch
    from fixtures import FakePrompter

    w = launch(argv, prompter or FakePrompter())
    qtbot.addWidget(w)
    w.resize(1440, 900)
    with qtbot.waitActive(w):
        w.show()
        w.activateWindow()
    if w.session.workspace is not None:
        qtbot.waitUntil(lambda: w.session.queue is not None and w.session.queue.complete)
        qtbot.waitUntil(lambda: w.canvas.image_size is not None)
    return w
