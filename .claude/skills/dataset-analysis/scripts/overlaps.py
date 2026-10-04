#!/usr/bin/env python3
"""Images whose labels overlap each other — from the label files alone, read-only.

IoU is computed on normalised coordinates, which is exact: IoU does not change
under independent x/y scaling, so no image sizes are needed. A pair counts when
its IoU is inside [--min, --max] (inclusive) and above zero. The parsing and the
overlap predicate are deeplabeling.core's, so this script agrees with the app.

  python3 overlaps.py /path/to/dataset --min 0.99 --max 1 --scope same
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from deeplabeling.core.geometry import iou  # noqa: E402
from deeplabeling.core.labelio import parse_label_bytes  # noqa: E402
from deeplabeling.core.overlap import SCOPES, iou_in_range, pair_counts  # noqa: E402


def boxes(label_file: Path):
    """(class, normalised box) for every parsed line; a polygon by its extent."""
    return [(line.cls_id, line.bbox)
            for line in parse_label_bytes(label_file.read_bytes()) if line.parsed]


def scan(root: Path, lo: float, hi: float, scope: str):
    """[(worst qualifying IoU, label file)] for every file with a qualifying pair."""
    hits = []
    for lf in sorted(Path(root).rglob("*.txt")):
        if "labels" not in lf.parts:
            continue
        bs = boxes(lf)
        qualifying = [v for i, p in enumerate(bs) for q in bs[i + 1:]
                      if pair_counts(scope, p[0], q[0])
                      for v in [iou(p[1], q[1])] if iou_in_range(v, lo, hi)]
        if qualifying:
            hits.append((max(qualifying), lf))
    return sorted(hits, key=lambda h: (-h[0], str(h[1])))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=Path)
    ap.add_argument("--min", type=float, default=0.5)
    ap.add_argument("--max", type=float, default=1.0)
    ap.add_argument("--scope", choices=SCOPES, default="different")
    ap.add_argument("--list", type=int, default=10, help="show this many files")
    args = ap.parse_args(argv)
    hits = scan(args.root, args.min, args.max, args.scope)
    print(f"{len(hits)} file(s) with a {args.scope}-class pair at IoU {args.min}-{args.max}")
    for value, lf in hits[:args.list]:
        print(f"  {value:.4f}  {lf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
