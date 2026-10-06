"""The prediction store (docs/design/2026-10-05-model-assist.md#the-prediction-store).

One SQLite file per dataset root, keyed by (model, image). It holds what the model found
at the floor, in the model's own class ids; thresholds and the class map apply on read
(docs/knowledge/caches.md). A row is served only while the image's stamp still matches.
Each thread talks to it through its own connection.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from .inference import FLOOR, Prediction
from .state import set_aside

STORE_NAME = "predictions.sqlite"
Stamp = tuple[int, int]             #: (size, mtime_ns) of an image file

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


class PredictionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.warning = ""                           # for the notice strip
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._closed = False
        try:
            try:
                self._connection()
            except sqlite3.OperationalError:
                raise                               # locked, full, unreadable: not corrupt
            except sqlite3.DatabaseError as e:      # "file is not a database"
                self._close_all()
                self.warning, writable = set_aside(self.path, e)
                if not writable:
                    raise OSError(self.warning) from e
                self._connection()
        except sqlite3.OperationalError as e:       # the open says why, as for any OSError
            self._close_all()
            raise OSError(f"{self.path.name}: {e}") from e

    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute(SCHEMA)
                conn.commit()
            except sqlite3.DatabaseError:
                conn.close()
                raise
            self._local.conn = conn
            with self._lock:
                self._all.append(conn)
        return conn

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

    def _close_all(self) -> None:
        with self._lock:
            for conn in self._all:
                conn.close()
            self._all.clear()
        self._local = threading.local()

    def close(self) -> None:
        """Close every connection; afterwards the store answers nothing and writes nothing,
        rather than opening a connection again for a thread that comes late."""
        self._closed = True
        self._close_all()
