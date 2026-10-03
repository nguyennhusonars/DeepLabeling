#!/usr/bin/env python3
"""What a training-time size cut (min_rel_wh / MinBoxFilter) keeps, in train vs val.

MinBoxFilter normalises by the AUGMENTED output image and keeps a box only if
w_rel >= t AND h_rel >= t.
  train: mosaic -> square imgsz canvas; each tile's long side = imgsz; scale jitter
         s ~ U(1 - scale, 1 + scale).  w_rel = wn*(W/L)*s, h_rel = hn*(H/L)*s
  val:   rect batches; each side = ceil(side/L * imgsz/stride + pad) * stride with
         pad 0.5 (BaseDataset.set_rectangle), so a 1080p image is 672 x 384.
Per-image approximation of the batch shape; ignores mosaic crops and cutmix.

  python3 size_cut_sim.py --yaml .../data_13class.yaml --val-thr 0.01 --train-thr 0.005
"""

from __future__ import annotations

import argparse
import collections
import math
from pathlib import Path

import yaml
from PIL import Image


def p_train_keep(wn, hn, W, H, t, scale=0.5):
    L = max(W, H)
    m = min(wn * W / L, hn * H / L)
    if m <= 0:
        return 0.0
    s_min = t / m
    lo, hi = 1 - scale, 1 + scale
    return min(max((hi - s_min) / (hi - lo), 0.0), 1.0)


def val_keep(wn, hn, W, H, t, imgsz=640, stride=32, pad=0.5):
    L = max(W, H)
    r = imgsz / L
    w_rect = math.ceil(W / L * imgsz / stride + pad) * stride
    h_rect = math.ceil(H / L * imgsz / stride + pad) * stride
    return wn * W * r / w_rect >= t and hn * H * r / h_rect >= t


def frames(data, base, split):
    folders = data.get(split) or []
    for rel in [folders] if isinstance(folders, str) else folders:
        d = base / rel
        if not d.is_dir():
            continue
        for img in sorted(d.iterdir()):
            if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp"):
                continue
            lf = img.parent.parent / "labels" / (img.stem + ".txt")
            if not lf.is_file():
                continue
            try:
                with Image.open(img) as im:
                    W, H = im.size
                    if im.getexif().get(274, 1) in (5, 6, 7, 8):
                        W, H = H, W
            except OSError:
                continue
            rows = []
            for line in lf.read_text(errors="replace").splitlines():
                t = line.split()
                if len(t) >= 5:
                    try:
                        rows.append((int(float(t[0])), float(t[3]), float(t[4])))
                    except ValueError:
                        pass
            yield W, H, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yaml", required=True, type=Path)
    ap.add_argument("--val-thr", type=float, default=0.01)
    ap.add_argument("--train-thr", type=float, help="default: same as --val-thr")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--scale", type=float, default=0.5)
    args = ap.parse_args(argv)
    train_thr = args.val_thr if args.train_thr is None else args.train_thr
    data = yaml.safe_load(args.yaml.read_text())
    base = Path(data.get("path") or args.yaml.parent)
    names = data["names"]
    names = dict(enumerate(names)) if isinstance(names, list) else {int(k): v for k, v in names.items()}

    seen, dropped = collections.Counter(), collections.defaultdict(float)
    for W, H, rows in frames(data, base, "train"):
        for c, wn, hn in rows:
            seen[c] += 1
            dropped[c] += 1 - p_train_keep(wn, hn, W, H, train_thr, args.scale)
    print(f"TRAIN (thr {train_thr}): expected share dropped per epoch")
    for c in sorted(seen):
        print(f"  {names.get(c, c):>24}: {dropped[c] / seen[c]:6.1%} of {seen[c]:>8,}")

    ev, starved, total = collections.Counter(), collections.Counter(), 0
    for W, H, rows in frames(data, base, "val"):
        for c, wn, hn in rows:
            total += 1
            if val_keep(wn, hn, W, H, args.val_thr, args.imgsz):
                ev[c] += 1
                starved[c] += p_train_keep(wn, hn, W, H, train_thr, args.scale) < 0.5
    print(f"VAL (thr {args.val_thr}): {total - sum(ev.values()):,} of {total:,} GT removed "
          "(a correct detection of any is scored as a false positive)")
    for c in sorted(ev):
        print(f"  {names.get(c, c):>24}: {ev[c]:>7,} evaluated, "
              f"{starved[c] / ev[c]:6.1%} trained as background in >50% of samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
