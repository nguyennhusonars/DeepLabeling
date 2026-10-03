"""`labels_cache` must notice when a label file changes underneath it.

`get_label_boxes` keyed the cache on the image path alone, with no check that
the file it parsed is still the file on disk. Importing a label archive while
the app is open -- which is the normal round trip here, export, edit, import --
left every filter reporting the previous contents until the app was restarted.

The cache still has to earn its keep: it exists because re-parsing 50k label
files cost 30-90s per 'Apply Filters' click, so an unchanged file must not be
read twice.
"""

from __future__ import annotations

import os

import pytest

from yolo_labeling.ui import filters as _filters

IMG = "/ds/images/frame.jpg"


def _probe():
    p = type("P", (_filters.FiltersMixin,), {})()
    p.labels_cache = {}
    p._labels_cache_stat = {}
    p.image_dimensions_cache = {IMG: (100, 100)}
    return p


def _write(path, text, *, mtime=None):
    path.write_text(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_a_changed_file_is_re_read(tmp_path):
    lf = tmp_path / "frame.txt"
    _write(lf, "0 0.5 0.5 0.2 0.2\n", mtime=1_000_000)
    p = _probe()
    assert len(p.get_label_boxes(IMG, lf)) == 1

    _write(lf, "0 0.5 0.5 0.2 0.2\n1 0.2 0.2 0.1 0.1\n", mtime=2_000_000)
    assert len(p.get_label_boxes(IMG, lf)) == 2, "served the pre-import contents"


def test_a_file_emptied_by_an_import_is_noticed(tmp_path):
    """A zero-byte .txt is a valid negative sample, not a missing file."""
    lf = tmp_path / "frame.txt"
    _write(lf, "0 0.5 0.5 0.2 0.2\n", mtime=1_000_000)
    p = _probe()
    assert len(p.get_label_boxes(IMG, lf)) == 1

    _write(lf, "", mtime=2_000_000)
    assert p.get_label_boxes(IMG, lf) == []


def test_a_same_size_edit_is_still_noticed(tmp_path):
    """Reassigning a class changes one byte and not the length, so a size-only
    check would miss exactly the edit the review window makes most often."""
    lf = tmp_path / "frame.txt"
    _write(lf, "0 0.5 0.5 0.2 0.2\n", mtime=1_000_000)
    p = _probe()
    assert p.get_label_boxes(IMG, lf)[0][0] == 0

    _write(lf, "7 0.5 0.5 0.2 0.2\n", mtime=2_000_000)
    assert p.get_label_boxes(IMG, lf)[0][0] == 7


def test_an_unchanged_file_is_parsed_only_once(tmp_path, monkeypatch):
    """The cache is a 30-90s optimisation; the staleness check must not undo it."""
    lf = tmp_path / "frame.txt"
    _write(lf, "0 0.5 0.5 0.2 0.2\n", mtime=1_000_000)

    from yolo_labeling.core import labelio as _labelio
    reads = []
    real = _labelio.read_label_file
    monkeypatch.setattr(_filters._labelio, "read_label_file",
                        lambda path: (reads.append(path), real(path))[1])

    p = _probe()
    for _ in range(5):
        p.get_label_boxes(IMG, lf)
    assert len(reads) == 1, f"re-parsed an untouched file {len(reads)} times"


def test_a_vanished_label_file_does_not_serve_stale_boxes(tmp_path):
    lf = tmp_path / "frame.txt"
    _write(lf, "0 0.5 0.5 0.2 0.2\n", mtime=1_000_000)
    p = _probe()
    assert len(p.get_label_boxes(IMG, lf)) == 1

    lf.unlink()
    assert p.get_label_boxes(IMG, lf) == []


@pytest.mark.gui
def test_saving_from_the_editor_leaves_the_cache_trusted(gui_app):
    """`save_labels` seeds the cache itself. If the stamp is not seeded with it,
    the next filter run re-parses every file the user touched."""
    app = gui_app
    app.load_image()
    cls = next(iter(app.class_info))
    app.user_boxes = [(cls, 5, 5, 40, 40)]
    app.save_labels()

    key = str(app.current_image_path)
    label_path = app._resolver().resolve(app.current_image_path)
    assert key in app.labels_cache
    assert app._labels_cache_fresh(key, label_path), \
        "cache stamp was not seeded on save, so the entry is always stale"
