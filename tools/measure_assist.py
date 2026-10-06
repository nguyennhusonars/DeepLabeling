#!/usr/bin/env python3
"""Measure slice 2's performance targets with a real model on a real dataset, read-only
(docs/design/2026-10-05-model-assist.md#performance-targets).

App state -- the prediction store included -- goes to a temporary folder, deleted at the
end. Nothing in the dataset is written and no label is edited. Run it from the repository
root, so that `ultralytics` is the editable install
(docs/knowledge/environment.md#which-ultralytics-gets-imported).

  /home/sonnn/miniconda3/bin/python3 tools/measure_assist.py DATA.yaml WEIGHTS [--pass-seconds 60]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = Path.home() / ".config" / "Ultralytics" / "settings.json"


class Answers:
    """A prompter for an unattended run: open whatever is asked, stop on any error."""

    def confirm_taxonomy(self, *args):
        return True

    def error(self, title, text):
        raise SystemExit(f"{title}: {text}")

    def choose_yaml(self):
        return None


def wait(app, condition, timeout=120.0) -> float:
    """Seconds until `condition()` holds, processing Qt events meanwhile."""
    start = time.perf_counter()
    while not condition():
        app.processEvents()
        if time.perf_counter() - start > timeout:
            raise SystemExit("timed out")
        time.sleep(0.0005)
    return time.perf_counter() - start


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else "absent"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    ap.add_argument("weights", type=Path)
    ap.add_argument("--pass-seconds", type=float, default=60.0)
    args = ap.parse_args(argv)
    tmp = tempfile.TemporaryDirectory(prefix="measure-assist-")
    os.environ["DEEPLABELING_STATE_DIR"] = str(Path(tmp.name) / "state")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))
    print("ultralytics:", importlib.util.find_spec("ultralytics").origin)     # found, not imported
    settings_before = md5(SETTINGS)

    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch

    app = QApplication.instance() or QApplication(sys.argv[:1])
    rows = []
    window = launch([str(args.yaml)], Answers())
    window.resize(1440, 900)
    window.show()
    s, model = window.session, window.session.model
    wait(app, lambda: window.canvas.image_size is not None and s.queue is not None and s.queue.complete)

    t0 = time.perf_counter()
    model.load(args.weights)
    wait(app, lambda: model.state in ("ready", "failed"))
    if model.state == "failed":
        raise SystemExit(model.error)
    first = s.current().entry
    wait(app, lambda: model.predictions(first) is not None)
    rows.append(("loading the model, to the first image's predictions", time.perf_counter() - t0, "(none)"))

    def page() -> float:
        """Seconds to show the next image, prefetched: what the GUI thread does."""
        nxt = s.queue.items[s.queue.position() + 1].entry.path
        wait(app, lambda: s.images.get(nxt) is not None)
        t = time.perf_counter()
        s.move(1)
        return time.perf_counter() - t + wait(app, lambda: window._shown == nxt)

    alone = [page() for _ in range(10)]
    rows.append(("paging, no pass (worst of 10)", max(alone), "≤ 100 ms"))

    fresh, served = [], []
    for i in range(1, 11):
        item = s.queue.items[min(s.queue.position() + 200 * i, len(s.queue) - 1)]
        s.go_to(item.key)
        wait(app, lambda: window._shown == item.entry.path)
        fresh.append(wait(app, lambda: window.inspector.predictions_label.text() not in ("not inferred yet", "loading")))
        t = time.perf_counter()
        window._predictions_changed()                       # read from the store, matched, drawn
        served.append(time.perf_counter() - t)
    rows.append(("predictions not in the store, after the image shows (worst of 10)", max(fresh), "≤ 500 ms"))
    rows.append(("predictions in the store, read and drawn (worst of 10)", max(served), "≤ 50 ms"))

    store = s.workspace.predictions
    before = len(store.inferred(model.key))
    t = time.perf_counter()
    model.infer_queue()
    paging = []
    while time.perf_counter() - t < args.pass_seconds:
        end = time.perf_counter() + 0.5
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.001)
        paging.append(page())
    model.cancel_pass()
    wait(app, lambda: not model.passing)
    elapsed = time.perf_counter() - t
    rows_now = store.inferred(model.key)
    rate = (len(rows_now) - before) / elapsed
    rows.append((f"paging while a pass runs (worst of {len(paging)})", max(paging), "≤ 100 ms"))
    rows.append((f"a dataset pass, images/s over {elapsed:.0f} s", rate, "≥ 20"))

    t = time.perf_counter()
    store.inferred(model.key)
    rows.append((f"the store's rows read when a model loads ({len(rows_now):,} rows)", time.perf_counter() - t, "(none)"))
    files = [store.path, store.path.with_name(store.path.name + "-wal")]
    size = sum(f.stat().st_size for f in files if f.exists())
    rows.append(("the store, bytes per image", size / max(len(rows_now), 1), "≤ 2048"))
    window.close()

    for name, value, target in rows:
        if "images/s" in name or "bytes" in name:
            shown = f"{value:,.0f}"
        else:
            shown = f"{value * 1000:.0f} ms" if value < 1 else f"{value:.2f} s"
        print(f"{name:70s} {shown:>10s}   target {target}")
    print(f"median paging during the pass {statistics.median(paging) * 1000:.0f} ms; "
          f"median fresh predictions {statistics.median(fresh) * 1000:.0f} ms")
    print("ultralytics settings unchanged:", md5(SETTINGS) == settings_before)
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
