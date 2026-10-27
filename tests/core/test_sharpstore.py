"""The score cache (docs/design/2026-10-27-blurry.md#the-score-cache)."""

import sqlite3

from deeplabeling.core.sharpstore import SHARP_NAME, SharpnessStore


def test_a_row_comes_back_while_its_stamp_matches(tmp_path):
    s = SharpnessStore(tmp_path / SHARP_NAME)
    s.put_many([("a/1.jpg", (10, 20), [(0, 0, 16, 16, 1.25, 0.31), (4, 4, 30, 30, None, None)])])
    assert s.get("a/1.jpg", (10, 20)) == [(0, 0, 16, 16, 1.25, 0.31), (4, 4, 30, 30, None, None)]
    assert s.get("a/1.jpg", (10, 21)) is None and s.get("b.jpg", (10, 20)) is None


def test_rows_survive_closing_and_a_rewrite_replaces_the_row(tmp_path):
    s = SharpnessStore(tmp_path / SHARP_NAME)
    s.put_many([("a.jpg", (1, 2), [(0, 0, 8, 8, 0.5, 0.5)])])
    s.put_many([("a.jpg", (1, 3), [(0, 0, 9, 9, 0.7, 0.2)])])
    s.close()
    again = SharpnessStore(tmp_path / SHARP_NAME)
    assert again.get("a.jpg", (1, 2)) is None and again.get("a.jpg", (1, 3)) == [(0, 0, 9, 9, 0.7, 0.2)]


def test_a_corrupt_file_is_set_aside_and_started_again(tmp_path):
    (tmp_path / SHARP_NAME).write_bytes(b"not a database" * 100)
    s = SharpnessStore(tmp_path / SHARP_NAME)
    assert "sharpness.sqlite unreadable" in s.warning and s.get("x", (1, 1)) is None
    s.put_many([("x", (1, 1), [])])
    assert s.get("x", (1, 1)) == []


def test_another_version_is_set_aside(tmp_path):
    old = sqlite3.connect(tmp_path / SHARP_NAME)
    old.execute("PRAGMA user_version = 7")
    old.commit()
    old.close()
    s = SharpnessStore(tmp_path / SHARP_NAME)
    assert "of version 7" in s.warning and s.get("x", (1, 1)) is None


def test_after_close_it_answers_nothing_and_writes_nothing(tmp_path):
    s = SharpnessStore(tmp_path / SHARP_NAME)
    s.put_many([("a.jpg", (1, 2), [(0, 0, 8, 8, 0.5, 0.5)])])
    s.close()
    s.put_many([("b.jpg", (1, 2), [])])
    assert s.get("a.jpg", (1, 2)) is None
    assert SharpnessStore(tmp_path / SHARP_NAME).get("b.jpg", (1, 2)) is None


def test_the_score_cache_never_waits_for_the_disk(tmp_path):
    """It is written on the GUI thread and costs only a rescore to lose: a cold build once
    held the window 1.8 s, most likely a checkpoint's sync (2026-10-27). The prediction store keeps
    its syncs."""
    from deeplabeling.core.predstore import STORE_NAME, PredictionStore

    s = SharpnessStore(tmp_path / SHARP_NAME)
    assert s._connection().execute("PRAGMA synchronous").fetchone()[0] == 0              # OFF
    p = PredictionStore(tmp_path / STORE_NAME)
    assert p._connection().execute("PRAGMA synchronous").fetchone()[0] == 1              # NORMAL
