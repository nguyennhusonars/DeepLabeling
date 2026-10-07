#!/usr/bin/env python3
"""Measure slice 5's performance targets (docs/design/2026-10-07-bulk-and-stats.md#performance-targets).

Read-only on the real dataset: app state goes to a temporary folder, deleted at the end.
Statistics are computed in the window over every image. Reassign looks over every image and
is answered No, so nothing is written. Its write is timed on a dataset generated in a
temporary folder -- --write-boxes images with one box each -- never on the real one.

  /home/sonnn/miniconda3/bin/python3 tools/measure_bulk_stats.py DATA.yaml [--write-boxes 10000]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from measure_assist import Answers, wait  # noqa: E402


class Progress:
    """A progress dialog nobody cancels."""

    def set(self, value):
        pass

    def cancelled(self):
        return False

    def close(self):
        pass


class Prompter(Answers):
    """Answers reassign with (from, to), then `confirm`; times the look and the write."""

    def __init__(self, choice, confirm):
        self.choice, self.confirm, self.asked_at = choice, confirm, None

    def progress(self, title, total):
        return Progress()

    def ask_reassign(self, names, unnamed_ids):
        return self.choice

    def confirm_reassign(self, text):
        self.asked_at = time.perf_counter()
        return self.confirm

    def confirm_queue_accept(self, text):
        return False


def generated(folder: Path, n: int) -> Path:
    """n images, each with one class-0 box, and their yaml."""
    images, labels = folder / "gen" / "images", folder / "gen" / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    import io

    from PIL import Image

    jpeg = io.BytesIO()
    Image.new("RGB", (64, 48)).save(jpeg, "JPEG")
    for i in range(n):
        (images / f"{i:06d}.jpg").write_bytes(jpeg.getvalue())
        (labels / f"{i:06d}.txt").write_text("0 0.500000 0.500000 0.100000 0.100000\n")
    yaml = folder / "gen.yaml"
    yaml.write_text(f"path: {folder}\ntrain: gen/images\nval: gen/images\nnames: [a, b]\n")
    return yaml


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    ap.add_argument("--write-boxes", type=int, default=10000)
    args = ap.parse_args(argv)
    tmp = tempfile.TemporaryDirectory(prefix="measure-bulk-stats-")
    os.environ["DEEPLABELING_STATE_DIR"] = str(Path(tmp.name) / "state")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch
    from deeplabeling.ui.reassign import reassign_queue
    from deeplabeling.ui.session import Session

    app = QApplication.instance() or QApplication(sys.argv[:1])
    rows = []
    prompter = Prompter((0, 1), confirm=False)
    window = launch([str(args.yaml)], prompter)
    window.resize(1440, 900)
    window.show()
    s = window.session
    wait(app, lambda: window.canvas.image_size is not None and s.queue is not None and s.queue.complete)
    images = len(s.queue_images())
    wait(app, lambda: s.io.pool.activeThreadCount() == 0, timeout=300)    # the open's id check, done

    def statistics(name: str) -> None:
        gaps, last = [], [time.perf_counter()]

        def tick():
            now = time.perf_counter()
            gaps.append(now - last[0])
            last[0] = now

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(5)
        t = time.perf_counter()
        if window.statistics is None:
            window.show_statistics()
        else:
            window.statistics.recompute()
        dialog = window.statistics
        total = wait(app, lambda: dialog._job is None and dialog.stats is not None, timeout=300)
        timer.stop()
        rows.append((f"statistics of {images:,} images, {name}: complete", total, "≤ 30 s cold, ≤ 5 s warm"))
        rows.append((f"statistics, {name}: the event loop's longest wait", max(gaps), "≤ 100 ms"))
        t = time.perf_counter()
        dialog.tabs.setCurrentWidget(dialog.charts)     # drawn as its tab shows: matplotlib's turn
        app.processEvents()
        rows.append((f"statistics, {name}: the charts drawn as their tab shows", time.perf_counter() - t, "≤ 1 s"))
        dialog.tabs.setCurrentIndex(0)                  # the next run computes with a table on show

    statistics("cold")                              # the image headers read for the first time
    statistics("warm")

    t = time.perf_counter()
    reassign_queue(s)
    wait(app, lambda: s.running is None and prompter.asked_at is not None, timeout=300)
    rows.append((f"reassign over {images:,} images: looking, answered No", prompter.asked_at - t, "≤ 30 s"))
    window.close()

    folder = Path(tmp.name) / "data"
    yaml = generated(folder, args.write_boxes)
    writer = Prompter((0, 1), confirm=True)
    session = Session(writer)
    session.open(str(yaml))
    wait(app, lambda: session.queue is not None and session.queue.complete, timeout=300)
    reassign_queue(session)
    wait(app, lambda: writer.asked_at is not None, timeout=300)
    wait(app, lambda: session.running is None, timeout=300)
    rows.append((f"reassign writing {args.write_boxes:,} boxes (generated dataset)", time.perf_counter() - writer.asked_at,
                 "≤ 30 s"))
    written = sum(1 for p in (folder / "gen" / "labels").iterdir() if p.read_text().startswith("1 "))
    session.close()

    for name, value, target in rows:
        shown = f"{value * 1000:.0f} ms" if value < 1 else f"{value:.2f} s"
        print(f"{name:72s} {shown:>10s}   target {target}")
    print(f"generated labels rewritten: {written:,} of {args.write_boxes:,}")
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
