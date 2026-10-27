"""The prediction store (docs/design/2026-10-05-model-assist.md#the-prediction-store).

One SQLite file per dataset root, keyed by (model, image). It holds what the model found
at the floor, in the model's own class ids; thresholds and the class map apply on read
(docs/knowledge/caches.md). A row is served only while the image's stamp still matches.
Its connections are `src/deeplabeling/core/sqlitefile.py::SqliteFile`'s.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable

from .inference import FLOOR, Prediction
from .sqlitefile import SqliteFile

STORE_NAME = "predictions.sqlite"
Stamp = tuple[int, int]             #: (size, mtime_ns) of an image file

VERSION = 1             #: PRAGMA user_version: a file of another version is set aside, as a corrupt one is
SCHEMA = """
CREATE TABLE IF NOT EXISTS preds (
    model TEXT NOT NULL,            -- the weights' name:size:mtime
    img TEXT NOT NULL,              -- the image's dataset-relative path
    size INTEGER NOT NULL,          -- the image's stamp when it was inferred
    mtime_ns INTEGER NOT NULL,
    floor REAL NOT NULL,            -- the confidence it was inferred at
    boxes TEXT NOT NULL,            -- JSON [[cls, cx, cy, w, h, conf], ...]
    PRIMARY KEY (model, img)
)
"""


def image_stamp(path) -> Stamp:
    stat = os.stat(path)
    return stat.st_size, stat.st_mtime_ns


def _encode(preds: Iterable[Prediction]) -> str:
    return json.dumps([[p.cls, *p.box, p.conf] for p in preds], separators=(",", ":"))


def _decode(text: str) -> list[Prediction]:
    return [Prediction(int(row[0]), tuple(row[1:5]), row[5]) for row in json.loads(text)]


class PredictionStore(SqliteFile):
    SCHEMA, VERSION = SCHEMA, VERSION

    def get(self, model: str, img: str, stamp: Stamp, conf: float = FLOOR) -> list[Prediction] | None:
        """What `model` found on `img`, at or above `conf`: None when it never looked at
        this image as it is now, or not down to `conf`; [] when it found nothing."""
        if self._closed:
            return None
        row = self._connection().execute(
            "SELECT size, mtime_ns, floor, boxes FROM preds WHERE model = ? AND img = ?",
            (model, img)).fetchone()
        if row is None or (row[0], row[1]) != tuple(stamp) or conf < row[2]:
            return None
        return [p for p in _decode(row[3]) if p.conf >= conf]

    def put(self, model: str, img: str, stamp: Stamp, preds: Iterable[Prediction]) -> None:
        self.put_many(model, [(img, stamp, preds)])

    def put_many(self, model: str, rows: Iterable[tuple[str, Stamp, Iterable[Prediction]]]) -> None:
        """Write rows in one transaction: a cancelled or crashed pass keeps every batch
        it committed. After close() they are dropped: the dataset they were for is shut."""
        if self._closed:
            return
        conn = self._connection()
        with conn:
            conn.executemany(
                "INSERT OR REPLACE INTO preds VALUES (?, ?, ?, ?, ?, ?)",
                [(model, img, stamp[0], stamp[1], FLOOR, _encode(preds)) for img, stamp, preds in rows])

    def inferred(self, model: str) -> dict[str, Stamp]:
        """Every image `model` has a row for, with the stamp it was inferred at: what a
        pass reads to know what is left, without reading the boxes."""
        if self._closed:
            return {}
        rows = self._connection().execute(
            "SELECT img, size, mtime_ns FROM preds WHERE model = ?", (model,))
        return {img: (size, mtime_ns) for img, size, mtime_ns in rows}
