"""The score cache (docs/design/2026-10-27-blurry.md#the-score-cache).

One SQLite file per dataset root: every box of 8 px or more of an image, by its pixel
rectangle, with its two sharpness measures. A row is served only while the image's stamp
still matches. Written on the GUI thread; read by builds on any thread.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from .predstore import Stamp
from .sqlitefile import SqliteFile

SHARP_NAME = "sharpness.sqlite"
#: (x0, y0, x1, y1, lap, cr): the box's pixel rectangle and its measures; None for a flat crop.
BoxScore = tuple[int, int, int, int, "float | None", "float | None"]


class SharpnessStore(SqliteFile):
    VERSION = 1
    # Written on the GUI thread, and a loss costs only a rescore: never wait for the disk. A
    # cold build once held the window 1.8 s, most likely a checkpoint's sync (2026-10-27).
    SYNCHRONOUS = "OFF"
    SCHEMA = """
CREATE TABLE IF NOT EXISTS scores (
    img TEXT PRIMARY KEY,           -- the image's dataset-relative path
    size INTEGER NOT NULL,          -- the image's stamp when it was scored
    mtime_ns INTEGER NOT NULL,
    boxes TEXT NOT NULL             -- JSON [[x0, y0, x1, y1, lap, cr], ...]
)
"""

    def get(self, img: str, stamp: Stamp) -> list[BoxScore] | None:
        """The image's scores, or None when it was never scored as it is now."""
        if self._closed:
            return None
        row = self._connection().execute(
            "SELECT size, mtime_ns, boxes FROM scores WHERE img = ?", (img,)).fetchone()
        if row is None or (row[0], row[1]) != tuple(stamp):
            return None
        return [tuple(box) for box in json.loads(row[2])]

    def put_many(self, rows: Iterable[tuple[str, Stamp, list[BoxScore]]]) -> None:
        """Write rows in one transaction; after close() they are dropped."""
        if self._closed:
            return
        conn = self._connection()
        with conn:
            conn.executemany("INSERT OR REPLACE INTO scores VALUES (?, ?, ?, ?)",
                             [(img, stamp[0], stamp[1], json.dumps(boxes, separators=(",", ":")))
                              for img, stamp, boxes in rows])
