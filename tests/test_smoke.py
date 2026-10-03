"""The window must be VISIBLE and render pixels, not merely exist.

The legacy app twice shipped a feature whose tests passed on widget state while
the user could not see it. Assert what is on screen.
"""

from deeplabeling.__main__ import build_window


def test_the_main_window_is_visible_and_titled(qtbot):
    window = build_window()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    assert window.windowTitle() == "DeepLabeling"
    assert window.width() > 0 and window.height() > 0


def test_the_window_renders_pixels(qtbot):
    window = build_window()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    image = window.grab().toImage()
    assert not image.isNull()
    assert (image.width(), image.height()) == (window.width(), window.height())
