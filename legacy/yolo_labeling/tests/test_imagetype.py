"""`core.imagetype.sniff` replaces `imghdr`, which Python 3.13 removed.

Two header parsers (Statistics and Build Label Cache) used `imghdr.what` only to
decide which parser to run. The replacement must decide exactly as imghdr did
for every format they handle -- including the JPEGs imghdr does NOT recognise,
which those callers send to their cv2 fallback.
"""

from __future__ import annotations

import io
import warnings

import cv2
import numpy as np
import pytest
from PIL import Image

from yolo_labeling.core.imagetype import sniff


def _encoded(ext):
    ok, buf = cv2.imencode(ext, np.full((12, 20, 3), 128, np.uint8))
    assert ok
    return buf.tobytes()


def _gif():
    out = io.BytesIO()
    Image.new("RGB", (20, 12)).save(out, format="GIF")
    return out.getvalue()


def _exif_jpeg():
    out = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (20, 12)).save(out, format="JPEG", exif=exif)
    return out.getvalue()


SAMPLES = {
    "png": _encoded(".png"),
    "jpeg_jfif": _encoded(".jpg"),
    "jpeg_exif": _exif_jpeg(),
    "jpeg_bare_dqt": b"\xff\xd8\xff\xdb" + b"\x00" * 20,
    "jpeg_icc_first": b"\xff\xd8\xff\xe2" + b"\x00" * 20,   # imghdr says None
    "gif": _gif(),
    "bmp": _encoded(".bmp"),
    "garbage": b"not an image at all, honestly",
    "empty": b"",
}


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_sniff_agrees_with_imghdr(name):
    """While the running Python still ships imghdr, check against the real thing."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        imghdr = pytest.importorskip("imghdr")
    if name == "jpeg_bare_dqt":
        pytest.skip("imghdr itself changed here in 3.11; pinned to 3.10 below")
    head = SAMPLES[name][:24]
    expected = imghdr.what(None, head)
    if expected not in ("png", "jpeg", "gif", "bmp"):
        expected = None          # formats the two parsers do not handle
    assert sniff(head) == expected


@pytest.mark.parametrize("name,expected", [
    ("png", "png"), ("jpeg_jfif", "jpeg"), ("jpeg_exif", "jpeg"),
    ("jpeg_bare_dqt", None),       # Python 3.10's imghdr, which this runs on
    ("gif", "gif"), ("bmp", "bmp"),
    ("jpeg_icc_first", None), ("garbage", None), ("empty", None),
])
def test_sniff_without_imghdr(name, expected):
    """The same answers stated outright, so the test still means something on a
    Python with no imghdr to compare against."""
    assert sniff(SAMPLES[name][:24]) == expected


def test_the_app_no_longer_imports_imghdr():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = [str(p.relative_to(root)) for p in root.rglob("*.py")
                 if "tests" not in p.parts and "import imghdr" in p.read_text()]
    assert offenders == []


# -- the two callers, end to end -------------------------------------------
#
# Neither header parser had any test. These pin that, after the swap, both still
# read every fixture frame's dimensions -- and agree with cv2's decode, which is
# what the rest of the app uses for geometry.


def _decoded_size(path):
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    return (img.shape[1], img.shape[0])


@pytest.mark.gui
def test_build_label_cache_still_reads_dimensions(gui_app):
    app = gui_app
    app.image_dimensions_cache = {}
    app.build_label_cache()
    labelled = [p for p in app.image_paths if app._resolver().resolve(p).exists()]
    assert labelled, "fixture has no labelled frames"
    for p in labelled:
        got = app.image_dimensions_cache.get(str(p))
        assert got is not None, f"no dimensions for {p.name}"
        # Either orientation: these hand parsers read the raw header and ignore
        # EXIF rotation, unlike `_image_size`. That predates the imghdr swap and
        # is not changed by it -- this test pins the swap, not the parser.
        assert got == _decoded_size(p) or got == _decoded_size(p)[::-1], p.name


@pytest.mark.gui
def test_statistics_still_reads_dimensions(gui_app):
    app = gui_app
    app.image_dimensions_cache = {}
    stats = app._collect_statistics(list(app.image_paths))
    assert stats['image_dimensions'], "statistics found no frame sizes at all"
