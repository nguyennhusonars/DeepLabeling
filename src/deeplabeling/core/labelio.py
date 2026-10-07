"""Reading and editing YOLO label files, byte for byte.

The rules are in docs/knowledge/label-files.md: every line keeps its exact source
text, line ending included, and only a line the user changed is re-serialised;
the parser never raises; a line to act on is located by class and box.

Bytes are decoded with `surrogateescape`, so bytes that are not UTF-8 survive too:
`encode_label_text(decode_label_bytes(b)) == b` for every `b`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

Box = tuple[float, float, float, float]

#: Digits after the point in a re-serialised coordinate.
PRECISION = 6

#: How far a recorded box may drift from a line's box and still be that line.
LOCATE_TOL = 0.002

#: Leading whitespace and the class token, for splicing in a new class id.
_FIRST_TOKEN = re.compile(r"^(\s*)(\S+)")


def decode_label_bytes(data: bytes) -> str:
    return data.decode("utf-8", "surrogateescape")


def encode_label_text(text: str) -> bytes:
    return text.encode("utf-8", "surrogateescape")


@dataclass(frozen=True)
class LabelLine:
    """One line of a label file, emitted exactly as `raw`.

    `cls_id` is None when the line could not be parsed. `coords` holds every
    number after the class id: 4 for a box, 5 for a box with an extra column,
    more for a polygon.
    """

    cls_id: int | None
    coords: tuple[float, ...]
    raw: str

    @property
    def parsed(self) -> bool:
        return self.cls_id is not None and len(self.coords) >= 4

    @property
    def is_polygon(self) -> bool:
        """More than a box and one extra column: ultralytics reads it as a segment."""
        return len(self.coords) > 5

    @property
    def bbox(self) -> Box:
        """Normalised (cx, cy, w, h); for a polygon, the extent of its points."""
        if not self.parsed:
            return (0.0, 0.0, 0.0, 0.0)
        if self.is_polygon:
            xs, ys = self.coords[0::2], self.coords[1::2]
            x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
            return ((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)
        cx, cy, w, h = self.coords[:4]
        return (cx, cy, w, h)

    @property
    def terminator(self) -> str:
        """The line's own line ending; "" for a last line without one."""
        body = self.raw.splitlines()
        return self.raw[len(body[0]):] if body else self.raw

    def with_class(self, cls_id: int) -> LabelLine:
        """This line with another class id, spliced into the raw text.

        Every coordinate keeps its exact digits, and the line keeps its ending -- or its
        lack of one: whatever is appended after it gives it the file's own ending first
        (`src/deeplabeling/core/edits.py::materialize`).
        """
        raw = _FIRST_TOKEN.sub(lambda m: f"{m.group(1)}{int(cls_id)}", self.raw, count=1)
        return LabelLine(int(cls_id), self.coords, raw)

    def with_bbox(self, bbox: Box) -> LabelLine:
        """This line as a plain 5-token box at `bbox`, keeping a CRLF ending.

        Polygon points and extra columns are dropped: callers refuse polygons.
        """
        return format_box(self.cls_id, bbox, "\r\n" if self.terminator == "\r\n" else "\n")


def format_box(cls_id: int, bbox: Box, terminator: str = "\n") -> LabelLine:
    """A new 5-token box line with coordinates at PRECISION digits."""
    text = " ".join(f"{v + 0.0:.{PRECISION}f}" for v in bbox)   # + 0.0 turns -0.0 into 0.0
    coords = tuple(float(t) for t in text.split())
    return LabelLine(int(cls_id), coords, f"{int(cls_id)} {text}{terminator}")


def parse_label_text(text: str) -> tuple[LabelLine, ...]:
    """Every line of `text`, each keeping its raw text. Never raises."""
    lines = []
    for raw in text.splitlines(keepends=True):
        parts = raw.split()
        if len(parts) < 5:
            lines.append(LabelLine(None, (), raw))
            continue
        try:
            cls_id = int(float(parts[0]))
            coords = tuple(float(p) for p in parts[1:])
        except (ValueError, OverflowError):
            lines.append(LabelLine(None, (), raw))
            continue
        lines.append(LabelLine(cls_id, coords, raw))
    return tuple(lines)


def parse_label_bytes(data: bytes) -> tuple[LabelLine, ...]:
    return parse_label_text(decode_label_bytes(data))


def render_label_bytes(lines: Sequence[LabelLine]) -> bytes:
    return encode_label_text("".join(line.raw for line in lines))


def locate_line(lines: Sequence[LabelLine], cls_id: int, bbox: Box,
                hint: int | None = None) -> int | None:
    """Index of the one line holding class `cls_id` at `bbox`, or None.

    `hint`, the index the line had when it was recorded, is tried first since it
    is nearly always right. Otherwise every line is searched, and None is
    returned unless exactly one matches: class AND box must agree, and two
    identical lines make the answer ambiguous.
    """
    def holds(line: LabelLine) -> bool:
        return (line.parsed and line.cls_id == cls_id
                and all(abs(a - b) <= LOCATE_TOL for a, b in zip(line.bbox, bbox)))

    if hint is not None and 0 <= hint < len(lines) and holds(lines[hint]):
        return hint
    hits = [i for i, line in enumerate(lines) if holds(line)]
    return hits[0] if len(hits) == 1 else None
