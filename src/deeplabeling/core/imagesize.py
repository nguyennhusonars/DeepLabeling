"""Image sizes from the file header, EXIF orientation honoured: never a decode
(docs/knowledge/caches.md#image-sizes). A size condition over 45k frames reads 45k
headers; decoding them instead cost minutes."""

from __future__ import annotations

import threading
from pathlib import Path

from PIL import Image

ORIENTATION = 274                   #: the EXIF orientation tag
QUARTER_TURNS = {5, 6, 7, 8}        #: orientations shown turned a quarter: width and height swap
#: The formats the canvas's decode (Qt) turns by their EXIF orientation. It shows a PNG or a
#: WebP as stored, whatever its EXIF says, and Pillow already reports a TIFF as shown.
TURNED = {"JPEG", "MPO"}


def image_size(path) -> tuple[int, int] | None:
    """(width, height) as the canvas shows the image, or None when it is not a readable
    image. Only the header is read: the EXIF comes from what opening it parsed, never
    from `getexif()`, which decodes a PNG to look for EXIF after its pixels."""
    try:
        with Image.open(path) as im:
            width, height = im.size
            turn = _orientation(im.info.get("exif")) if im.format in TURNED else None
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None
    return (height, width) if turn in QUARTER_TURNS else (width, height)


def _orientation(raw: bytes | None) -> int | None:
    if not raw:
        return None
    exif = Image.Exif()
    exif.load(raw)
    return exif.get(ORIENTATION)


class ImageSizes:
    """The open dataset's image sizes, kept in memory, each stamped with its file's size
    and mtime: an image replaced on disk is read again. Safe across threads: a queue
    build asks from a worker while the GUI asks for the image on screen."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sizes: dict[Path, tuple[tuple[int, int], tuple[int, int] | None]] = {}

    def get(self, path) -> tuple[int, int] | None:
        path = Path(path)
        try:
            st = path.stat()
        except OSError:
            return None
        stamp = (st.st_size, st.st_mtime_ns)
        with self._lock:
            hit = self._sizes.get(path)
        if hit is not None and hit[0] == stamp:
            return hit[1]
        size = image_size(path)
        with self._lock:
            self._sizes[path] = (stamp, size)
        return size
