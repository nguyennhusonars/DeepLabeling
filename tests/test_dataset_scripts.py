"""The analysis scripts produce numbers the user acts on, so their arithmetic is
pinned on tiny synthetic datasets."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / ".claude/skills/dataset-analysis/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- overlaps.py -----------------------------------------------------------

@pytest.fixture
def labelled(tmp_path):
    labels = tmp_path / "ds" / "labels"
    labels.mkdir(parents=True)
    (labels / "dup.txt").write_text("0 0.5 0.5 0.2 0.2\n0 0.5 0.5 0.2 0.2\n")       # IoU 1.0
    (labels / "partial.txt").write_text("0 0.5 0.5 0.2 0.2\n0 0.52 0.5 0.2 0.2\n")  # IoU ~0.82
    (labels / "classes.txt").write_text("0 0.5 0.5 0.2 0.2\n1 0.5 0.5 0.2 0.2\n")   # diff class
    (labels / "apart.txt").write_text("0 0.2 0.2 0.1 0.1\n0 0.8 0.8 0.1 0.1\n")     # no overlap
    return tmp_path / "ds"


def names(hits):
    return sorted(p.name for _, p in hits)


def test_exact_duplicates_only(labelled):
    assert names(load("overlaps").scan(labelled, 0.99, 1.0, "same")) == ["dup.txt"]


def test_partial_overlaps_only(labelled):
    assert names(load("overlaps").scan(labelled, 0.5, 0.9, "same")) == ["partial.txt"]


def test_scope_different(labelled):
    assert names(load("overlaps").scan(labelled, 0.5, 1.0, "different")) == ["classes.txt"]


def test_non_overlapping_boxes_never_count_even_from_zero(labelled):
    assert "apart.txt" not in names(load("overlaps").scan(labelled, 0.0, 1.0, "any"))


def test_polygons_are_compared_by_their_extent(tmp_path):
    labels = tmp_path / "ds" / "labels"
    labels.mkdir(parents=True)
    # a square polygon 0.1..0.3 and the box with exactly that extent
    (labels / "poly.txt").write_text("0 0.1 0.1 0.3 0.1 0.3 0.3 0.1 0.3\n0 0.2 0.2 0.2 0.2\n")
    assert names(load("overlaps").scan(tmp_path / "ds", 0.99, 1.0, "same")) == ["poly.txt"]


# -- unmatched.py ----------------------------------------------------------

@pytest.fixture
def cached(tmp_path):
    images, labels = tmp_path / "ds/images", tmp_path / "ds/labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    for name in ("a.png", "b.png"):
        Image.new("RGB", (100, 100)).save(images / name)
    (labels / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n")          # box 40..60
    db_path = tmp_path / "predictions.sqlite"
    db = sqlite3.connect(db_path)
    db.execute("create table preds (model text, img text, size integer, mtime integer, floor real, boxes text)")
    rows = {
        "a.png": [[0, 40, 40, 60, 60, 0.9], [0, 0, 0, 10, 10, 0.85]],   # one match, one unlabelled
        "b.png": [[0, 10, 10, 30, 30, 0.9]],                             # frame with no label file
    }
    for name, boxes in rows.items():
        db.execute("insert into preds values (?,?,?,?,?,?)",
                   ("m.pt:1:1", str(images / name), 0, 0, 0.1, json.dumps(boxes)))
    db.commit()
    db.close()
    return db_path


def test_unmatched_predictions_and_unlabelled_frames(cached):
    um = load("unmatched")
    db = um.open_ro(cached)
    out = um.analyse(db, "m.pt:1:1", 0.8, 1.0, 0.5)
    assert out["images"] == 2 and out["no_label_file"] == 1
    assert len(out["unmatched_preds"]) == 2
    assert out["unseen_labels"] == []


def test_a_floor_above_the_evidence_makes_the_label_unseen(cached):
    um = load("unmatched")
    out = um.analyse(um.open_ro(cached), "m.pt:1:1", 0.95, 1.0, 0.5)
    assert len(out["unseen_labels"]) == 1 and out["unmatched_preds"] == []


def test_the_cache_is_never_written(cached):
    before = cached.stat().st_mtime_ns
    um = load("unmatched")
    um.analyse(um.open_ro(cached), "m.pt:1:1", 0.25, 1.0, 0.5)
    with pytest.raises(sqlite3.OperationalError):
        um.open_ro(cached).execute("delete from preds")
    assert cached.stat().st_mtime_ns == before


# -- size_cut_sim.py -------------------------------------------------------

def test_val_rect_shapes_pad_the_long_side_too():
    """1080p val images are 672x384: a 1.02%-wide box is BELOW a 1% cut."""
    sim = load("size_cut_sim")
    assert sim.val_keep(0.0102, 0.5, 1920, 1080, 0.01) is False
    assert sim.val_keep(0.0106, 0.5, 1920, 1080, 0.01) is True


def test_val_height_cut_on_1080p():
    sim = load("size_cut_sim")
    assert sim.val_keep(0.5, 0.012, 1920, 1080, 0.01) is True     # 0.012*360/384 = 0.01125
    assert sim.val_keep(0.5, 0.010, 1920, 1080, 0.01) is False


def test_train_keep_probability_on_the_square_canvas():
    sim = load("size_cut_sim")
    p = sim.p_train_keep(0.5, 0.012, 1920, 1080, 0.01, scale=0.5)
    assert p == pytest.approx((1.5 - 0.01 / (0.012 * 0.5625)) / 1.0, rel=1e-6)


def test_train_keep_is_a_probability():
    sim = load("size_cut_sim")
    assert sim.p_train_keep(0.5, 0.5, 1920, 1080, 0.01) == 1.0
    assert sim.p_train_keep(0.001, 0.001, 1920, 1080, 0.01) == 0.0
