"""class_config.json and the prediction cache live in the package directory.

Both used to be relative to wherever the app was started. Launching from another
folder therefore began with no classes, hotkeys, prediction maps or cached
predictions -- and quietly wrote a fresh default config there, which is how a
`class_config.json` full of default thresholds appeared one level above the
package while the real one sat unread inside it.

The suite redirects STATE_DIR to a temporary folder (see conftest), deliberately
a DIFFERENT one from the working directory: if the two were the same, a test
could not tell "next to the package" from "wherever we were launched".
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_the_state_dir_is_the_package_directory(monkeypatch):
    from yolo_labeling import app

    monkeypatch.undo()           # the real value, not the suite's redirect
    assert app.STATE_DIR == Path(app.__file__).resolve().parent


def test_the_suite_redirects_state_away_from_the_launch_directory(state_dir, tmp_path):
    from yolo_labeling import app

    assert app.STATE_DIR == state_dir
    assert Path.cwd() == tmp_path and state_dir != tmp_path


def test_the_prediction_cache_is_created_in_the_state_dir(monolith, state_dir, tmp_path):
    app = object.__new__(monolith.YOLOLabelingTool)
    app.pred_cache = None
    app.model_predictions_cache = {}
    app.update_status = lambda *a, **k: None
    model = tmp_path / "best.pt"
    model.write_bytes(b"not really a model")
    try:
        app._open_pred_cache(str(model))
        assert app.pred_cache is not None
        assert (state_dir / ".yolo_labeling_cache" / "predictions.sqlite").is_file()
        assert not (tmp_path / ".yolo_labeling_cache").exists(), \
            "cache created in the launch directory"
    finally:
        if app.pred_cache is not None:
            app.pred_cache.close()


@pytest.mark.gui
def test_the_config_is_written_to_the_state_dir(gui_app, state_dir, tmp_path):
    app = gui_app
    assert Path(app.config_file) == state_dir / "class_config.json"
    app.save_class_config()
    assert (state_dir / "class_config.json").is_file()
    assert not (tmp_path / "class_config.json").exists(), \
        "config written to the launch directory"


@pytest.mark.gui
def test_a_config_in_the_launch_directory_is_not_read(gui_app, monolith, ds, state_dir, tmp_path):
    """The stray-file situation: a config one level up must not shadow the real one."""
    import json
    import tkinter as tk

    app = gui_app
    app.filter_overlap_scope_var.set('same')
    app._on_overlap_scope_change()                    # saved to the state dir
    (tmp_path / "class_config.json").write_text(json.dumps({
        "classes": {"0": {"name": "x", "color": [0, 0, 255]}},
        "filters": {"overlap_scope": "any"},
    }))

    root2 = tk.Tk()
    try:
        app2 = monolith.YOLOLabelingTool(root2, yaml_path=str(ds.yaml))
        root2.update_idletasks()
        assert app2.filter_overlap_scope == 'same'
    finally:
        root2.destroy()
