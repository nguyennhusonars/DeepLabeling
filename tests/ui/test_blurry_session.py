"""A Blurry queue in the session (docs/design/2026-10-27-blurry.md#the-queue): built, its
scores written on the GUI thread, a cancelled build's kept, restored on a relaunch."""

import sqlite3
import time

import cv2
import pytest

import deeplabeling.core.blurry as blurry_module
from deeplabeling.core.blurry import Blurry, BlurSettings
from deeplabeling.core.predstore import image_stamp
from deeplabeling.core.queue import ImageFilter
from fixtures import build_blur_dataset, open_session

SHARE = Blurry(settings=BlurSettings(share=0.1))


@pytest.fixture
def blur(tmp_path):
    return build_blur_dataset(tmp_path / "b")


def built(qtbot, s, source=SHARE):
    s.set_queue(source)
    qtbot.waitUntil(lambda: s.queue.complete, timeout=10000)


def slow_decodes(monkeypatch, seconds=0.03):
    real = cv2.imread
    monkeypatch.setattr(blurry_module.cv2, "imread", lambda *a: (time.sleep(seconds), real(*a))[1])


def test_a_blurry_queue_builds_and_its_scores_are_kept(qtbot, blur):
    s = open_session(qtbot, blur.yaml)
    built(qtbot, s)
    assert s.progress_text() == " · 6 blurry"                           # 3 heads, 3 humans
    assert s.workspace.sharpness.get("cam/images/0003.jpg", image_stamp(blur.root / "cam/images/0003.jpg"))
    assert s.current().finding.kind == "blurry"
    s.close()


def test_the_chip_says_scoring_while_it_builds(qtbot, blur, monkeypatch):
    s = open_session(qtbot, blur.yaml)
    slow_decodes(monkeypatch)
    s.set_queue(SHARE)
    qtbot.waitUntil(lambda: s.progress_text().startswith(" · scoring "), timeout=5000)
    assert s.progress_text().endswith(" / 30")
    qtbot.waitUntil(lambda: s.queue.complete, timeout=10000)
    s.close()


def test_a_replaced_build_still_writes_its_scores(qtbot, blur, monkeypatch):
    s = open_session(qtbot, blur.yaml)
    slow_decodes(monkeypatch)
    s.set_queue(SHARE)
    qtbot.waitUntil(lambda: s.progress_text().startswith(" · scoring "), timeout=5000)
    s.set_queue(ImageFilter())                                          # the blurry build is cancelled
    s.io.wait(10000)
    qtbot.wait(50)                                                      # its last batches, delivered
    scored = [e for e in s.workspace.dataset.images
              if s.workspace.sharpness.get(e.rel, image_stamp(e.path)) is not None]
    assert 0 < len(scored) < 30 and s.queue.source == ImageFilter()
    s.close()


def test_a_closed_datasets_late_scores_are_dropped(qtbot, blur, tmp_path, monkeypatch):
    s = open_session(qtbot, blur.yaml)
    slow_decodes(monkeypatch)
    s.set_queue(SHARE)
    qtbot.waitUntil(lambda: s.progress_text().startswith(" · scoring "), timeout=5000)
    other = build_blur_dataset(tmp_path / "other", n=20)
    assert s.open(other.yaml)                                           # the first dataset closes
    s.io.wait(10000)
    qtbot.wait(50)
    stamp = image_stamp(blur.root / "cam/images/0000.jpg")
    assert s.workspace.sharpness.get("cam/images/0000.jpg", stamp) is None    # never written to the next one
    s.close()


def test_a_failed_write_is_said_once(qtbot, blur, monkeypatch):
    s = open_session(qtbot, blur.yaml)
    said = []
    s.notice.connect(lambda level, text, image: said.append(text))

    def full(rows):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(s.workspace.sharpness, "put_many", full)
    built(qtbot, s, Blurry(settings=BlurSettings(share=0.1)))
    blurry_module_batch = [t for t in said if t.startswith("scores not saved:")]
    assert blurry_module_batch == ["scores not saved: database or disk is full"]
    assert len(s.queue) == 6                                            # the build went on
    s.close()


def test_a_blurry_queue_and_its_cursor_survive_a_relaunch(qtbot, blur):
    s = open_session(qtbot, blur.yaml)
    built(qtbot, s)
    s.move(2)
    key = s.current().key
    s.close()
    again = open_session(qtbot, blur.yaml)
    assert again.queue.source == SHARE
    qtbot.waitUntil(lambda: again.queue.complete, timeout=10000)
    assert again.current().key == key and key.endswith("#blurry")
    again.close()
