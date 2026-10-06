#!/usr/bin/env python3
"""Measure slice 4's performance targets with a real model on a real dataset, read-only
(docs/design/2026-10-06-find-bad.md#performance-targets).

App state -- the prediction store included -- goes to a temporary folder, deleted at the
end. A dataset pass of --pass-seconds fills the store first, so the scan has findings to
judge. Nothing in the dataset is written: no label is edited and nothing is dismissed.
Run it from the repository root, so that `ultralytics` is the editable install
(docs/knowledge/environment.md#which-ultralytics-gets-imported).

  /home/sonnn/miniconda3/bin/python3 tools/measure_find_bad.py DATA.yaml WEIGHTS [--pass-seconds 60]
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from measure_assist import SETTINGS, Answers, md5, wait  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    ap.add_argument("weights", type=Path)
    ap.add_argument("--pass-seconds", type=float, default=60.0)
    args = ap.parse_args(argv)
    tmp = tempfile.TemporaryDirectory(prefix="measure-find-bad-")
    os.environ["DEEPLABELING_STATE_DIR"] = str(Path(tmp.name) / "state")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))
    print("ultralytics:", importlib.util.find_spec("ultralytics").origin)     # found, not imported
    settings_before = md5(SETTINGS)

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch
    from deeplabeling.core.findings import Findings

    app = QApplication.instance() or QApplication(sys.argv[:1])
    rows = []
    window = launch([str(args.yaml)], Answers())
    window.resize(1440, 900)
    window.show()
    s, model = window.session, window.session.model
    wait(app, lambda: window.canvas.image_size is not None and s.queue is not None and s.queue.complete)
    model.load(args.weights)
    wait(app, lambda: model.state in ("ready", "failed"))
    if model.state == "failed":
        raise SystemExit(model.error)

    t = time.perf_counter()
    model.infer_queue()
    while time.perf_counter() - t < args.pass_seconds:
        app.processEvents()
        time.sleep(0.001)
    model.cancel_pass()
    wait(app, lambda: not model.passing)
    print(f"{len(s.workspace.predictions.inferred(model.key)):,} images inferred")

    def scan(name: str) -> None:
        """A findings queue built in the window: complete, and the longest the event loop
        went without a turn meanwhile, which is what paging would wait."""
        gaps, last = [], [time.perf_counter()]

        def tick():
            now = time.perf_counter()
            gaps.append(now - last[0])
            last[0] = now

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(5)
        t = time.perf_counter()
        s.set_queue(Findings())
        total = wait(app, lambda: s.queue.complete, timeout=300)
        timer.stop()
        rows.append((f"a Findings scan, {name}: complete, {len(s.queue):,} findings{s.progress_text()}", total,
                     "≤ 30 s cold, ≤ 5 s warm"))
        rows.append((f"a Findings scan, {name}: the event loop's longest wait", max(gaps), "≤ 100 ms"))

    scan("cold")                                    # every inferred image's label file read
    scan("warm")
    if len(s.queue) < 2:
        raise SystemExit("too few findings to page: pass longer")

    def page() -> float:
        """Seconds to show the next finding on another image, prefetched."""
        nxt = s.queue.items[s.queue.position() + 1].entry.path
        wait(app, lambda: s.images.get(nxt) is not None)
        t = time.perf_counter()
        s.move(1)
        return time.perf_counter() - t + wait(app, lambda: window._shown == nxt and window.canvas.spotlight is not None)

    paging = []
    while len(paging) < 10 and s.queue.position() + 1 < len(s.queue):
        here = s.current().entry.path
        if s.queue.items[s.queue.position() + 1].entry.path == here:
            s.move(1)                               # the same image: nothing to decode
            continue
        paging.append(page())
    rows.append((f"the next finding, prefetched (worst of {len(paging)})", max(paging), "≤ 100 ms"))

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
        print(f"{name:90s} {shown:>10s}   target {target}")
    print("ultralytics settings unchanged:", md5(SETTINGS) == settings_before)
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
