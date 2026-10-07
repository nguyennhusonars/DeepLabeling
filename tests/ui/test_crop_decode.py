"""A finding's crop, clipped and scaled as it is decoded, EXIF orientation honoured
(docs/design/2026-10-06-find-bad.md#the-grid)."""

import pytest
from PIL import Image
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor

from deeplabeling.ui.images import Crop, ImageCache, decode_crop, decode_image
from deeplabeling.ui.workers import Jobs



def pattern(path, orientation, size=(64, 48)):
    """A stored gradient -- red across, green down: every pixel its own colour -- tagged
    with an EXIF orientation."""
    w, h = size
    im = Image.new("RGB", size)
    im.putdata([(255 * x // (w - 1), 255 * y // (h - 1), 128) for y in range(h) for x in range(w)])
    exif = Image.Exif()
    exif[274] = orientation
    im.save(path, **({"quality": 95} if path.suffix == ".jpg" else {"lossless": True} if path.suffix == ".webp" else {}),
            exif=exif.tobytes())
    return path


def difference(a, b) -> float:
    """The mean difference per channel, over every pixel."""
    total = 0
    for y in range(a.height()):
        for x in range(a.width()):
            p, q = QColor(a.pixel(x, y)), QColor(b.pixel(x, y))
            total += abs(p.red() - q.red()) + abs(p.green() - q.green()) + abs(p.blue() - q.blue())
    return total / (3 * a.width() * a.height())


@pytest.mark.parametrize("suffix", [".jpg", ".png", ".webp", ".tif"])
@pytest.mark.parametrize("orientation", range(1, 9))
def test_a_crop_is_the_shown_image_cut_and_scaled(tmp_path, orientation, suffix):
    """Qt turns a JPEG by its EXIF and shows the other formats as stored: either way the crop
    is cut from what the canvas shows."""
    path = pattern(tmp_path / f"o{orientation}{suffix}", orientation)
    shown = decode_image(path)                                  # the canvas's picture
    rect = (4, 2, 40, 30)                                       # in the shown image's pixels
    crop = decode_crop(path, rect, (160, 120))
    want = shown.copy(QRect(4, 2, 36, 28)).scaled(QSize(160, 120), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    assert crop.size() == want.size() and difference(crop, want) < 6


@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
@pytest.mark.parametrize("corner", ["the whole frame", "bottom right", "left edge"])
def test_a_crop_at_the_frame_s_edge_is_cut_from_there(tmp_path, orientation, corner):
    path = pattern(tmp_path / "o.jpg", orientation)
    shown = decode_image(path)
    w, h = shown.width(), shown.height()
    rect = {"the whole frame": (0, 0, w, h), "bottom right": (w - 12, h - 10, w, h), "left edge": (0, 8, 10, h - 8)}[corner]
    crop = decode_crop(path, rect, (160, 120))
    x1, y1, x2, y2 = rect
    want = shown.copy(QRect(x1, y1, x2 - x1, y2 - y1)).scaled(QSize(160, 120), Qt.KeepAspectRatio,
                                                               Qt.SmoothTransformation)
    assert crop.size() == want.size() and difference(crop, want) < 6


def test_a_small_crop_is_enlarged_to_fill_the_tile_and_a_large_one_shrunk(tmp_path):
    path = pattern(tmp_path / "p.jpg", 1, (640, 480))
    assert decode_crop(path, (0, 0, 16, 12), (160, 120)).size() == QSize(160, 120)
    assert decode_crop(path, (0, 0, 640, 240), (160, 120)).size() == QSize(160, 60)


def test_an_unreadable_image_is_refused(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a jpeg")
    with pytest.raises(ValueError):
        decode_crop(bad, (0, 0, 4, 4), (160, 120))


def test_crops_are_cached_by_image_and_rect(qtbot, tmp_path):
    path = pattern(tmp_path / "p.jpg", 6)
    cache = ImageCache(Jobs(1), decode=lambda c: decode_crop(c.path, c.rect, (160, 120)), key=Crop.of)
    a, b = Crop(path, (0, 0, 8, 8)), Crop(path, (8, 8, 24, 24))
    with qtbot.waitSignals([cache.ready, cache.ready], timeout=5000):
        cache.want([a, b])
    assert cache.get(a) is not None and cache.get(b) is not None and cache.get(a) != cache.get(b)
    assert cache.get(Crop(str(path), (0, 0, 8, 8))) is cache.get(a)       # a str path is the same image
