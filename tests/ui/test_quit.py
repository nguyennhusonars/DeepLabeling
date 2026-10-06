"""Quitting while the model thread is busy ends the process cleanly: Qt aborts the process
when a running QThread is destroyed (docs/design/2026-10-05-model-assist.md#the-inference-thread)."""

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = textwrap.dedent("""
    import sys, time
    sys.path[:0] = [{src!r}, {tests!r}]
    sys.modules["ultralytics"] = None                    # never a real model
    import deeplabeling.ui.model as model
    from fixtures import FakePredictor

    def slow(path):                                      # a load that outlasts the close
        time.sleep(8)
        return FakePredictor(path)

    model.UltralyticsPredictor = slow
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    import deeplabeling.__main__ as entry
    from deeplabeling.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])

    def window():
        return next(w for w in app.topLevelWidgets() if isinstance(w, MainWindow))

    QTimer.singleShot(300, lambda: window().session.model.load({weights!r}))
    QTimer.singleShot(600, lambda: window().close())
    raise SystemExit(entry.main([{yaml!r}]))
""")


def test_quitting_while_a_model_loads_exits_cleanly_without_waiting_for_it(ds, tmp_path, state_dir):
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    script = tmp_path / "quit.py"
    script.write_text(SCRIPT.format(src=str(ROOT / "src"), tests=str(ROOT / "tests"),
                                    weights=str(weights), yaml=str(ds.yaml)))
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "DEEPLABELING_STATE_DIR": str(state_dir)}
    started = time.monotonic()
    done = subprocess.run([sys.executable, str(script)], env=env, cwd=tmp_path,
                          capture_output=True, text=True, timeout=30)
    assert "Destroyed while thread" not in done.stderr
    assert done.returncode == 0, done.stderr[-2000:]
    assert time.monotonic() - started < 7                # the 8 s load was not waited for
