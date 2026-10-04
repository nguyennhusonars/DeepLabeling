"""Decoding images on workers, into a cache bounded in bytes
(docs/design/2026-10-04-app-foundation.md#window)."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QImageReader

from .workers import Handle, Jobs


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


class ImageCache(QObject):
    """Decoded images by path. The images it is told to keep -- the current one and
    its neighbours -- are decoded first and never evicted; the rest go oldest first
    once the cache is over its byte budget."""

    ready = Signal(object)          # path
    failed = Signal(object, str)    # path, why

    def __init__(self, jobs: Jobs, limit_bytes: int = 512 * 2**20, parent=None):
        super().__init__(parent)
        self._jobs = jobs
        self._limit = limit_bytes
        self._images: OrderedDict[Path, QImage] = OrderedDict()
        self._errors: dict[Path, str] = {}
        self._pending: dict[Path, Handle] = {}
        self._keep: set[Path] = set()
        self._bytes = 0

    @property
    def cached_bytes(self) -> int:
        return self._bytes

    def get(self, path) -> QImage | None:
        path = Path(path)
        image = self._images.get(path)
        if image is not None:
            self._images.move_to_end(path)
        return image

    def error(self, path) -> str | None:
        return self._errors.get(Path(path))

    def keep(self, paths: Iterable) -> None:
        """Decode these, in this order, and keep them whatever the budget."""
        paths = [Path(p) for p in paths]
        self._keep = set(paths)
        for path in paths:
            self.request(path)
        self._evict()

    def request(self, path) -> None:
        path = Path(path)
        if path in self._images or path in self._errors or path in self._pending:
            return
        self._pending[path] = self._jobs.start(
            lambda emit, cancelled, p=path: decode_image(p),
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
