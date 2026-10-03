#!/usr/bin/env python3
"""Labels the model does not see, and predictions no label covers — read-only.

Reads the legacy prediction cache (SQLite table `preds`: model, img, size, mtime,
floor, boxes = JSON [cls, x1, y1, x2, y2, conf] in pixels). Labels are found by
the images/ -> labels/ convention; image sizes from the file header.

Matching is geometry only (any class), as in docs/knowledge/matching.md. There is
no checkable-class guard here: labels of a class the model cannot emit will show as
unseen. Restrict the predictions direction with --classes.

  python3 unmatched.py --cache .../predictions.sqlite --conf-lo 0.8
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from PIL import Image


def open_ro(path):
    return sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0.0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def image_size(path: Path):
    with Image.open(path) as im:
        w, h = im.size
        if im.getexif().get(274, 1) in (5, 6, 7, 8):
            w, h = h, w
    return w, h


def label_file(img: Path) -> Path:
    parts = list(img.parts)
    i = len(parts) - 1 - parts[::-1].index("images")
    parts[i] = "labels"
    return Path(*parts).with_suffix(".txt")


def labels_px(lf: Path, w, h):
    out = []
    if not lf.is_file():
        return out
    for line in lf.read_text(errors="replace").splitlines():
        t = line.split()
        if len(t) < 5:
            continue
        try:
            cls = int(float(t[0]))
            cx, cy, bw, bh = map(float, t[1:5])
        except ValueError:
            continue
        out.append((cls, ((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h)))
    return out


def models(db):
    return db.execute("select model, count(*) from preds group by model order by 2 desc").fetchall()


def analyse(db, model, conf_lo, conf_hi, match, classes=None):
    out = {"images": 0, "no_label_file": 0, "unmatched_preds": [], "unseen_labels": []}
    for img, raw in db.execute("select img, boxes from preds where model = ?", (model,)):
        path = Path(img)
        try:
            w, h = image_size(path)
        except OSError:
            continue
        out["images"] += 1
        lf = label_file(path)
        if not lf.is_file():
            out["no_label_file"] += 1
        labels = labels_px(lf, w, h)
        preds = [(int(b[0]), float(b[5]), tuple(b[1:5])) for b in json.loads(raw) if float(b[5]) >= conf_lo]
        for cls, conf, box in preds:
            if conf > conf_hi or (classes is not None and cls not in classes):
                continue
            if not any(iou(box, lb) >= match for _, lb in labels):
                out["unmatched_preds"].append((img, cls, conf))
        for cls, lb in labels:
            if not any(iou(lb, box) >= match for _, _, box in preds):
                out["unseen_labels"].append((img, cls))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--model", help="model key; default: the one with the most rows")
    ap.add_argument("--conf-lo", type=float, default=0.25)
    ap.add_argument("--conf-hi", type=float, default=1.0)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--classes", help="comma-separated model class ids for the predictions direction")
    ap.add_argument("--examples", type=int, default=5)
    args = ap.parse_args(argv)
    db = open_ro(args.cache)
    available = models(db)
    for key, n in available:
        print(f"  {n:>8,}  {key}")
    model = args.model or available[0][0]
    classes = {int(c) for c in args.classes.split(",")} if args.classes else None
    out = analyse(db, model, args.conf_lo, args.conf_hi, args.iou, classes)
    print(f"model {model}: {out['images']:,} images, {out['no_label_file']:,} with no label file")
    print(f"predictions with no label (conf {args.conf_lo}-{args.conf_hi}): {len(out['unmatched_preds']):,}")
    for row in out["unmatched_preds"][:args.examples]:
        print("   ", row)
    print(f"labels the model does not see (conf >= {args.conf_lo}): {len(out['unseen_labels']):,}")
    for row in out["unseen_labels"][:args.examples]:
        print("   ", row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
