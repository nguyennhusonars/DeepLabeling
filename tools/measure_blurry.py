#!/usr/bin/env python3
"""Measure the Blurry queue's performance targets on a real dataset, read-only
(docs/design/2026-10-27-blurry.md#performance-targets).

App state -- the score cache included -- goes to a temporary folder, deleted at the end.
Nothing in the dataset is written: no label is edited and nothing is dismissed.

  /home/sonnn/miniconda3/bin/python3 tools/measure_blurry.py DATA.yaml
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    args = ap.parse_args(argv)
    tmp = tempfile.TemporaryDirectory(prefix="measure-blurry-")
    os.environ["DEEPLABELING_STATE_DIR"] = str(Path(tmp.name) / "state")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch
    from deeplabeling.core.blurry import Blurry

    app = QApplication.instance() or QApplication(sys.argv[:1])
    rows = []
    window = launch([str(args.yaml)], Answers())
    window.resize(1440, 900)
    window.show()
    s = window.session
    wait(app, lambda: window.canvas.image_size is not None and s.queue is not None and s.queue.complete)
    print(f"{len(s.workspace.dataset.images):,} images")

    def build(name: str, target: str) -> None:
        """A Blurry queue built in the window: complete, and the longest the event loop went
        without a turn meanwhile, which is what paging would wait."""
        gaps, last = [], [time.perf_counter()]

        def tick():
            now = time.perf_counter()
            gaps.append(now - last[0])
            last[0] = now

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(10)
        s.set_queue(Blurry())
        total = wait(app, lambda: s.queue.complete, timeout=1800)
        timer.stop()
        rows.append((f"a Blurry build, {name}: complete, {len(s.queue):,} listed{s.progress_text()}", total, target))
        rows.append((f"a Blurry build, {name}: the event loop's longest wait", max(gaps), "≤ 100 ms"))

    build("cold", "≤ 6 min")
    build("warm", "≤ 10 s")

    window.queue_panel.set_grid(True)
    window.resizeDocks([window.queue_dock], [4 * 176 + 40], Qt.Horizontal)      # four columns of tiles
    app.processEvents()
    s.crops.clear()
    t = time.perf_counter()
    app.processEvents()
    wanted = lambda: [c for c in map(s.crop_of, (s.queue.items[r] for r in window.queue_panel._visible_rows(True)))
                      if c is not None]
    wait(app, lambda: wanted() and all(s.crops.get(c) is not None or s.crops.error(c) for c in wanted()))
    rows.append((f"a page of crop tiles ({len(wanted())} tiles)", time.perf_counter() - t, "≤ 1 s"))
    window.close()

    for name, value, target in rows:
        shown = f"{value * 1000:.0f} ms" if value < 1 else f"{value:.2f} s"
        print(f"{name:110s} {shown:>10s}   target {target}")
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
