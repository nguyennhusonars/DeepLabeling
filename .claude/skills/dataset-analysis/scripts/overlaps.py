#!/usr/bin/env python3
"""Images whose labels overlap each other — from the label files alone, read-only.

IoU is computed on normalised coordinates, which is exact: IoU does not change
under independent x/y scaling, so no image sizes are needed. A pair counts when
its IoU is inside [--min, --max] (inclusive) and above zero.

  python3 overlaps.py /path/to/dataset --min 0.99 --max 1 --scope same
"""

from __future__ import annotations

import argparse
from pathlib import Path

SCOPES = ("same", "different", "any")


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0.0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def boxes(label_file: Path):
    out = []
    for line in label_file.read_text(errors="replace").splitlines():
        t = line.split()
        if len(t) < 5:
            continue
        try:
            cls = int(float(t[0]))
            cx, cy, w, h = map(float, t[1:5])
        except ValueError:
            continue
        out.append((cls, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)))
    return out


def counts(scope, a, b):
    return {"same": a == b, "different": a != b, "any": True}[scope]


def scan(root: Path, lo: float, hi: float, scope: str):
    """[(worst qualifying IoU, label file)] for every file with a qualifying pair."""
    hits = []
    for lf in sorted(Path(root).rglob("*.txt")):
        if "labels" not in lf.parts:
            continue
        bs = boxes(lf)
        qualifying = [v for i, p in enumerate(bs) for q in bs[i + 1:]
                      if counts(scope, p[0], q[0])
                      for v in [iou(p[1], q[1])] if v > 0.0 and lo <= v <= hi]
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
