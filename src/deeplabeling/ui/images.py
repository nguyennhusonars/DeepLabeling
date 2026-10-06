"""Decoding images, thumbnails and findings' crops on workers, into caches bounded in
bytes (docs/design/2026-10-04-app-foundation.md#window,
docs/design/2026-10-06-find-bad.md#the-grid)."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QObject, QRect, QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader

from .workers import Handle, Jobs

THUMB_PX = 160                  #: a thumbnail's longer side, at most
THUMB_BYTES = 64 * 2**20        #: the thumbnail cache's budget (the spec)
TILE_PICTURE = (THUMB_PX, 120)  #: a grid tile's picture area: a crop is scaled to fill it


def decode_image(path) -> QImage:
    """Decode with EXIF orientation applied, as the size function in caches.md does.

    QImageReader.size() reports the stored, unrotated size; only the decoded image
    has the displayed one. Raises ValueError when the file is not a readable image.
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or "not an image")
    return image


def decode_thumb(path, longest: int = THUMB_PX) -> QImage:
    """A thumbnail at most `longest` px on its longer side, EXIF orientation applied.

    The decoder scales as it reads (a JPEG at a fraction of its size), so a page of
    tiles costs little; an image smaller than that is never enlarged. The stored size
    is scaled: rotation keeps the longer side. Raises ValueError like decode_image.
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > longest:
        reader.setScaledSize(size.scaled(longest, longest, Qt.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or "not an image")
    return image


class Crop(NamedTuple):
    """A finding's crop: an image and a rect (x1, y1, x2, y2) in its pixels as shown."""

    path: Path
    rect: tuple[int, int, int, int]

    @classmethod
    def of(cls, key) -> Crop:
        """The cache key: the same image, however its path was spelled."""
        return cls(Path(key.path), tuple(key.rect))


def _stored_rect(rect, w: int, h: int, turn) -> QRect:
    """`rect`, in the pixels of the image as shown, in the pixels the file stores (w x h).
    Qt shows a stored image mirrored and flipped as its EXIF says, then turned a quarter
    clockwise; this undoes that, a corner at a time."""
    T = QImageIOHandler.Transformation
    x1, y1, x2, y2 = rect
    corners = [(x1, y1), (x2, y2)]
    if turn == T.TransformationRotate270:
        corners = [(w - y, x) for x, y in corners]          # a quarter anticlockwise, undone
    else:
        if turn & T.TransformationRotate90:
            corners = [(y, h - x) for x, y in corners]
        if turn & T.TransformationMirror:
            corners = [(w - x, y) for x, y in corners]
        if turn & T.TransformationFlip:
            corners = [(x, h - y) for x, y in corners]
    (ax, ay), (bx, by) = corners
    return QRect(min(ax, bx), min(ay, by), abs(bx - ax), abs(by - ay))


def decode_crop(path, rect: tuple[int, int, int, int], fit: tuple[int, int]) -> QImage:
    """The part `rect` of the image as shown (EXIF orientation applied), scaled to fill
    `fit` with its aspect kept -- enlarged when it is smaller. The decoder clips and scales
    as it reads, so a crop of a large frame costs a fraction of its decode. Raises
    ValueError like decode_image."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    stored, turn = reader.size(), reader.transformation()
    if not stored.isValid():
        raise ValueError(reader.errorString() or "not an image")
    x1, y1, x2, y2 = rect
    size = QSize(x2 - x1, y2 - y1).scaled(QSize(*fit), Qt.KeepAspectRatio)
    if turn & QImageIOHandler.Transformation.TransformationRotate90:
        size.transpose()                                    # scaled before it is turned
    reader.setClipRect(_stored_rect(rect, stored.width(), stored.height(), turn))
    reader.setScaledSize(size)
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or "not an image")
    return image


def decode_tile(crop: Crop) -> QImage:
    """A finding's tile: its crop, scaled to fill the tile's picture area."""
    return decode_crop(crop.path, crop.rect, TILE_PICTURE)


class ImageCache(QObject):
    """Decoded images by path. The images it is told to keep -- the current one and
    its neighbours, or the tiles in view -- are decoded first and never evicted; the
    rest go oldest first once the cache is over its byte budget."""

    ready = Signal(object)          # path
    failed = Signal(object, str)    # path, why

    def __init__(self, jobs: Jobs, limit_bytes: int = 512 * 2**20,
                 decode: Callable[[Path], QImage] = decode_image, parent=None, *, key: Callable = Path):
        super().__init__(parent)
        self._jobs = jobs
        self._key = key                 #: what a request names, as the cache keys it: a Path, or a Crop
        self._limit = limit_bytes
        self._decode = decode
        self._images: OrderedDict[Path, QImage] = OrderedDict()
        self._errors: dict[Path, str] = {}
        self._pending: dict[Path, Handle] = {}
        self._keep: set[Path] = set()
        self._bytes = 0

    @property
    def cached_bytes(self) -> int:
        return self._bytes

    def get(self, path) -> QImage | None:
        path = self._key(path)
        image = self._images.get(path)
        if image is not None:
            self._images.move_to_end(path)
        return image

    def error(self, path) -> str | None:
        return self._errors.get(self._key(path))

    def keep(self, paths: Iterable) -> None:
        """Decode these, in this order, and keep them whatever the budget."""
        paths = [self._key(p) for p in paths]
        self._keep = set(paths)
        for path in paths:
            self.request(path)
        self._evict()

    def want(self, paths: Iterable) -> None:
        """Keep these and cancel every other decode still waiting: the tiles in view,
        when a scroll has taken the earlier ones out of it."""
        paths = [self._key(p) for p in paths]
        wanted = set(paths)
        for path in [p for p in self._pending if p not in wanted]:
            self._pending.pop(path).cancel()
        self.keep(paths)

    def request(self, path) -> None:
        path = self._key(path)
        if path in self._images or path in self._errors or path in self._pending:
            return
        decode = self._decode
        self._pending[path] = self._jobs.start(
            lambda emit, cancelled, p=path: None if cancelled() else decode(p),
            done=lambda image, p=path: self._decoded(p, image),
            failed=lambda why, p=path: self._failed(p, why))

    def clear(self) -> None:
        for job in self._pending.values():
            job.cancel()
        self._pending.clear()
        self._images.clear()
        self._errors.clear()
        self._keep = set()
        self._bytes = 0

    def _decoded(self, path: Path, image: QImage) -> None:
        if self._pending.pop(path, None) is None:
            return                                  # cleared while decoding
        self._images[path] = image
        self._bytes += image.sizeInBytes()
        self._evict()
        self.ready.emit(path)

    def _failed(self, path: Path, why: str) -> None:
        if self._pending.pop(path, None) is None:
            return
        self._errors[path] = why
        self.failed.emit(path, why)

    def _evict(self) -> None:
        while self._bytes > self._limit:
            victim = next((p for p in self._images if p not in self._keep), None)
            if victim is None:
                break
            self._bytes -= self._images.pop(victim).sizeInBytes()
