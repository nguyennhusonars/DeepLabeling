"""The window must be VISIBLE and render pixels, not merely exist.

The legacy app twice shipped a feature whose tests passed on widget state while
the user could not see it. Assert what is on screen.
"""

from deeplabeling.__main__ import launch
from fixtures import FakePrompter


def test_the_main_window_is_visible_and_titled(qtbot):
    window = launch([], FakePrompter())             # no dataset and no last one
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    assert window.windowTitle() == "DeepLabeling"
    assert window.width() >= 1024 and window.height() >= 640
    window.close()


def test_the_window_renders_pixels(qtbot):
    window = launch([], FakePrompter())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    image = window.grab().toImage()
    assert not image.isNull()
    assert (image.width(), image.height()) == (window.width(), window.height())
    window.close()
