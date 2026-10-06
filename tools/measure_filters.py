#!/usr/bin/env python3
"""Measure slice 3's size and overlap conditions on a real dataset, read-only
(docs/design/2026-10-06-filters.md#performance-targets).

It opens the dataset and its label files directly: no app state, no lock, no write.
The model condition is measured with the window, where the model's rows are.

  /home/sonnn/miniconda3/bin/python3 tools/measure_filters.py DATA.yaml
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT / "src"))

    from deeplabeling.core.dataset import Dataset
    from deeplabeling.core.imagesize import ImageSizes
    from deeplabeling.core.queue import Boxes, BuildContext, ImageFilter, Overlap
    from deeplabeling.core.store import LabelStore

    dataset = Dataset.open(args.yaml)
    print(f"{len(dataset.images):,} images")
    warm = (LabelStore(dataset), ImageSizes())

    def build(condition, cold):
        """Cold: a fresh label store and size cache, as the first build after opening."""
        store, sizes = (LabelStore(dataset), ImageSizes()) if cold else warm
        ctx = BuildContext(dataset, store, frozenset(), sizes=sizes)
        found, first, start = [], None, time.perf_counter()

        def emit(items):
            nonlocal first
            if first is None:
                first = time.perf_counter() - start
            found.extend(items)

        ImageFilter(conditions=(condition,)).build(ctx, emit)
        return first, time.perf_counter() - start, len(found), dict(ctx.unsettled)

    px = Boxes((), w=(None, 10), unit="px")
    runs = [("a size in px", px), ("a size in %", Boxes((), w=(None, 1), unit="%")),
            ("overlap, same class, IoU 0.9-1.0", Overlap("same", 0.9, 1.0)),
            ("overlap, different classes, IoU 0.5-1.0", Overlap("different", 0.5, 1.0)),
            ("overlap, any class, IoU 0.5-1.0", Overlap("any", 0.5, 1.0))]
    build(px, cold=False)                                       # fills the warm caches
    for name, condition in [(f"{n}, cold", c) for n, c in runs] + [(f"{n}, warm", c) for n, c in runs]:
        first, total, n, unsettled = build(condition, cold=name.endswith("cold"))
        first_text = "—" if first is None else f"{first * 1000:.0f} ms"
        print(f"{name:45s} first {first_text:>8s}   complete {total:6.2f} s   "
              f"{n:6,} images{'   ' + str(unsettled) if unsettled else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
