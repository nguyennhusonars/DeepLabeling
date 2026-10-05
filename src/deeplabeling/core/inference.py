"""The model's side of model assist (docs/design/2026-10-05-model-assist.md#the-inference-thread).

A Predictor turns image files into Predictions: the model's own class ids, normalised
boxes, at the floor (docs/knowledge/caches.md#store-at-a-floor-and-filter-on-read).
UltralyticsPredictor imports ultralytics only when a model is loaded, never on import:
which ultralytics loads depends on the launch directory (CLAUDE.md landmine 8), and
importing it costs seconds.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .geometry import Box

FLOOR = 0.10        #: every prediction is inferred, and stored, at this confidence
MAX_BOXES = 100     #: the strongest this many are kept per image
#: Decoding a 2592x1944 JPEG takes 22 ms and capped a pass at 20 images/s; decoded on 4
#: threads (cv2 releases the GIL) a batch of 8 ran at 70/s on a GTX 1660 SUPER (2026-10-05).
DECODE_THREADS = 4


@dataclass(frozen=True)
class Prediction:
    cls: int        #: the model's class id; the class map gives the dataset's
    box: Box        #: normalised (cx, cy, w, h), against the image as the model read it
    conf: float


@dataclass(frozen=True)
class Failure:
    """An image the model could not predict on, and why."""

    why: str


class ModelError(Exception):
    """A weights file that cannot be used: it does not load, or it does not detect."""


class Predictor(Protocol):
    key: str                        #: model_key of the weights
    names: tuple[str, ...]          #: the model's class names, by id

    def predict(self, paths: Sequence[Path]) -> list[list[Prediction] | Failure]: ...


def model_key(weights) -> str:
    """`name:size:mtime`: a file retrained in place gets a new key, so its old rows are
    never served for it (docs/knowledge/caches.md#the-durable-store)."""
    path = Path(weights)
    stat = path.stat()
    return f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}"


def _inside(box) -> Box | None:
    """A box as corners rounded and clipped to the image, then centre and size: rounding
    cx, cy, w and h one by one put boxes at the frame's edge up to 7.5e-7 outside it, which
    the write path refuses. None when nothing is left inside."""
    cx, cy, w, h = (float(v) for v in box)
    x1, y1 = (min(max(round(v, 6), 0.0), 1.0) for v in (cx - w / 2, cy - h / 2))
    x2, y2 = (min(max(round(v, 6), 0.0), 1.0) for v in (cx + w / 2, cy + h / 2))
    if x2 <= x1 or y2 <= y1:
        return None
    # 10 decimals drop float noise (0.09999999999999998) and stay within 7.5e-11 of the
    # clipped corners, inside the write path's 1e-9.
    return tuple(round(v, 10) for v in ((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1))


def predictions_from(result) -> list[Prediction]:
    """One ultralytics result as Predictions, strongest first, at the floor and capped."""
    boxes = result.boxes
    found = []
    for box, cls, conf in zip(boxes.xywhn.tolist(), boxes.cls.tolist(), boxes.conf.tolist()):
        inside = _inside(box)
        if conf >= FLOOR and inside is not None:
            found.append(Prediction(int(cls), inside, round(float(conf), 3)))
    found.sort(key=lambda p: -p.conf)
    return found[:MAX_BOXES]


def _read(path: Path):
    """The image as the model reads it: cv2 applies EXIF orientation as Qt's decode does
    (docs/knowledge/caches.md#image-sizes). None when it is not an image."""
    import cv2

    return cv2.imread(str(path))


class UltralyticsPredictor:
    """A detection model from an ultralytics weights file. Not thread-safe: one thread
    loads it and asks it everything."""

    def __init__(self, weights, device: str | None = None):
        path = Path(weights)
        try:
            from ultralytics import YOLO

            model = YOLO(str(path))
        except Exception as e:                      # whatever the file or the library raises
            raise ModelError(f"{path.name} could not be loaded: {e}") from e
        if model.task != "detect":
            raise ModelError(f"{path.name} is a {model.task} model, not a detection model")
        self.key = model_key(path)
        self.names = tuple(str(model.names[i]) for i in sorted(model.names))
        self._model, self._device = model, device
        self._decoder = ThreadPoolExecutor(DECODE_THREADS)

    def predict(self, paths: Sequence[Path]) -> list[list[Prediction] | Failure]:
        """One answer per path. An image that cannot be read fails alone; a batch the
        model fails on is retried image by image, so one bad image never fails the rest."""
        images = list(self._decoder.map(_read, paths))
        answers: list[list[Prediction] | Failure] = [
            Failure(f"{Path(p).name} could not be read as an image") if image is None else []
            for p, image in zip(paths, images)]
        readable = [i for i, image in enumerate(images) if image is not None]
        for i, found in zip(readable, self._run([images[i] for i in readable])):
            answers[i] = found
        return answers

    def _run(self, images: list) -> list[list[Prediction] | Failure]:
        if not images:
            return []
        try:
            results = self._model.predict(images, conf=FLOOR, max_det=MAX_BOXES, batch=len(images),
                                          device=self._device, verbose=False)
            if len(results) != len(images):
                raise ValueError(f"{len(results)} results for {len(images)} images")
            return [predictions_from(r) for r in results]
        except Exception as e:                      # CUDA out of memory, a library error
            if len(images) == 1:
                return [Failure(f"{type(e).__name__}: {e}")]
            return [self._run([image])[0] for image in images]
