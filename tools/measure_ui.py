#!/usr/bin/env python3
"""Measure slice 1's performance targets on a real dataset, read-only
(docs/design/2026-10-04-app-foundation.md#performance-targets).

App state goes to a temporary folder, so neither the dataset nor the real
.deeplabeling/ is written. The one write it times -- an edit -- goes to a small
dataset generated in that same temporary folder.

  /home/sonnn/miniconda3/bin/python3 tools/measure_ui.py DATA.yaml --class bus_l
"""

from __future__ import annotations

import argparse
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Answers:
    """A prompter for an unattended run: open whatever is asked, stop on any error."""

    def confirm_taxonomy(self, *args):
        return True

    def error(self, title, text):
        raise SystemExit(f"{title}: {text}")

    def choose_yaml(self):
        return None


def wait(app, condition, timeout=600.0) -> float:
    """Seconds until `condition()` holds, processing Qt events meanwhile."""
    start = time.perf_counter()
    while not condition():
        app.processEvents()
        if time.perf_counter() - start > timeout:
            raise SystemExit("timed out")
        time.sleep(0.0005)
    return time.perf_counter() - start


def edit_times(n: int = 50) -> list[float]:
    """Milliseconds per applied edit, on a generated one-image dataset."""
    from PIL import Image

    from deeplabeling.core.edits import AddBox, DeleteLine, Intent
    from deeplabeling.core.workspace import Workspace

    # On the home filesystem, not /tmp: /tmp is tmpfs here, where fsync costs nothing.
    root = Path(tempfile.mkdtemp(prefix="measure-ui-edit-", dir=Path.home() / ".cache"))
    (root / "images").mkdir(parents=True)
    Image.new("RGB", (64, 48)).save(root / "images" / "a.jpg")
    ws = Workspace.open(root / "images", confirm_taxonomy=lambda *a: True)
    image, times = root / "images" / "a.jpg", []
    for i in range(n):
        labels = ws.store.get(image)
        op = AddBox(0, (0.5, 0.5, 0.2, 0.2)) if i % 2 == 0 else DeleteLine(labels.ref(labels.boxes[0][0]))
        start = time.perf_counter()
        ws.editor.apply(Intent(image, (op,), "measure"))
        times.append((time.perf_counter() - start) * 1000)
    ws.close()
    shutil.rmtree(root)
    return times


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    ap.add_argument("--class", dest="cls", required=True, help="a class name for the class-condition queue")
    args = ap.parse_args(argv)
    state = tempfile.TemporaryDirectory(prefix="measure-ui-")     # removed at the end, or at exit
    tmp = state.name
    os.environ["DEEPLABELING_STATE_DIR"] = str(Path(tmp) / "state")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))

    from PIL import Image
    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch
    from deeplabeling.core.queue import HasClass, ImageFilter

    app = QApplication.instance() or QApplication(sys.argv[:1])
    rows = []

    start = time.perf_counter()
    window = launch([str(args.yaml)], Answers())
    window.resize(1440, 900)
    window.show()
    s = window.session
    wait(app, lambda: window.canvas.image_size is not None)
    rows.append(("launch to the first image shown", time.perf_counter() - start, "≤ 3 s"))

    def build(source):
        t0 = time.perf_counter()
        s.set_queue(source)
        first = wait(app, lambda: len(s.queue) > 0)
        complete = time.perf_counter() - t0 + wait(app, lambda: s.queue.complete)
        return first, complete

    first, complete = build(ImageFilter())
    rows.append(("an all-images queue: first items", first, "≤ 1 s"))
    rows.append(("an all-images queue: complete", complete, "≤ 3 s"))

    shown = []
    for _ in range(10):
        nxt = s.queue.items[s.queue.position() + 1].entry.path
        wait(app, lambda: s.images.get(nxt) is not None)            # prefetched
        t0 = time.perf_counter()
        s.move(1)
        shown.append(time.perf_counter() - t0 + wait(app, lambda: window._shown == nxt))
    rows.append(("next image, prefetched (max of 10)", max(shown), "≤ 100 ms"))

    big = None
    for item in s.queue.items[len(s.queue.items) // 2:]:
        with Image.open(item.entry.path) as im:
            if im.size[0] >= 4000:
                big = item
                break
    if big is not None:
        t0 = time.perf_counter()
        s.go_to(big.key)
        rows.append((f"an image not prefetched, {big.entry.path.name}",
                     time.perf_counter() - t0 + wait(app, lambda: window._shown == big.entry.path), "≤ 300 ms"))

    def page_shown() -> bool:
        """Every tile at least partly in view has its thumbnail, or its error."""
        paths = [s.queue.items[s.queue.index_of(key)].entry.path
                 for key in window.queue_panel.visible_keys(partial=True)]
        return bool(paths) and all(s.thumbs.get(p) is not None or s.thumbs.error(p) for p in paths)

    t0 = time.perf_counter()
    window.actions["toggle_grid"].trigger()
    rows.append(("the grid: the first page of thumbnails", time.perf_counter() - t0 + wait(app, page_shown),
                 "≤ 1 s"))
    far = s.queue.items[len(s.queue) // 2].key
    t0 = time.perf_counter()
    s.go_to(far)
    rows.append(("the grid: a page after a jump", time.perf_counter() - t0
                 + wait(app, lambda: far in window.queue_panel.visible_keys() and page_shown()), "≤ 1 s"))
    window.actions["toggle_grid"].trigger()                     # the builds below, as before

    _, first_pass = build(ImageFilter(conditions=(HasClass((args.cls,)),)))
    rows.append((f"has {args.cls}: first pass after open", first_pass, "≤ 30 s"))
    _, warm = build(ImageFilter(conditions=(HasClass((args.cls,)),)))
    rows.append((f"has {args.cls}: warm", warm, "≤ 5 s"))
    window.close()

    edits = edit_times()
    rows.append(("one edit applied and written (max of 50)", max(edits) / 1000, "≤ 20 ms"))

    for name, seconds, target in rows:
        shown = f"{seconds * 1000:.0f} ms" if seconds < 1 else f"{seconds:.2f} s"
        print(f"{name:45s} {shown:>10s}   target {target}")
    print(f"median edit {statistics.median(edits):.1f} ms")
    state.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
