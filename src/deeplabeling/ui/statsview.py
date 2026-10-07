"""The statistics as tables -- a header and rows of text -- and as TSV, computed without Qt so
they are tested headless (docs/design/2026-10-07-bulk-and-stats.md#the-dialog)."""

from __future__ import annotations

from ..core.stats import FILE_STATES, PER_IMAGE_MAX, SIZE_LABELS, Stats
from .reassign_dialog import class_label

Table = tuple[list[str], list[list[str]]]


def table_classes(stats: Stats, names) -> list[int]:
    """The yaml's classes, then every id its labels hold that it does not name."""
    return [*range(len(names)), *(cls for cls in stats.classes() if not 0 <= cls < len(names))]


def class_table(stats: Stats, names) -> Table:
    header = ["class"] + [f"{split} {what}" for split in stats.splits for what in ("boxes", "images", "polygons")]
    rows = [[class_label(cls, names)] + [str(counter[(split, cls)]) for split in stats.splits
                                         for counter in (stats.boxes, stats.images_with, stats.polygons)]
            for cls in table_classes(stats, names)]
    return header, rows


def files_table(stats: Stats) -> Table:
    return ["split", *FILE_STATES], [[split] + [str(stats.files[(split, state)]) for state in FILE_STATES]
                                     for split in stats.splits]


def sizes_table(stats: Stats, names) -> Table:
    rows = [[class_label(cls, names)] + [str(stats.sizes[(cls, b)]) for b in range(len(SIZE_LABELS))]
            for cls in table_classes(stats, names)]
    return ["class", *SIZE_LABELS], rows + [[f"images whose header cannot be read: {stats.unsized}"]]


def per_image_table(stats: Stats) -> Table:
    return ["boxes", "images"], [[str(n) if n < PER_IMAGE_MAX else f"{n}+", str(stats.per_image[n])]
                                 for n in range(PER_IMAGE_MAX + 1)]


def tsv(header: list[str], rows: list[list[str]]) -> str:
    return "".join("\t".join(row) + "\n" for row in [header, *rows])
