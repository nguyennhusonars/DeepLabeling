import os
import subprocess
import sys
from pathlib import Path

import pytest

from deeplabeling.core import state
from deeplabeling.core.state import DatasetLock, Locked, dataset_state_dir, set_aside, state_dir


def test_the_state_folder_comes_from_the_environment():
    assert state_dir() == Path(os.environ[state.ENV])


def test_without_the_override_it_is_the_repository_folder(monkeypatch):
    monkeypatch.delenv(state.ENV)
    assert state_dir() == Path(__file__).resolve().parents[2] / ".deeplabeling"


def test_dataset_folders_are_stable_and_distinct(tmp_path):
    a, b = tmp_path / "x" / "pvn", tmp_path / "y" / "pvn"
    assert dataset_state_dir(a) == dataset_state_dir(a)
    assert dataset_state_dir(a) != dataset_state_dir(b)
    assert dataset_state_dir(a).name.startswith("pvn-")
    assert dataset_state_dir(a).parent == state_dir() / "datasets"


def test_a_lock_holds_our_pid_until_released(tmp_path):
    lock = DatasetLock(tmp_path)
    lock.acquire()
    assert lock.path.read_text().strip() == str(os.getpid()) and lock.held
    lock.release()
    assert not lock.path.exists() and not lock.held


def test_a_lock_held_by_another_live_process_refuses(tmp_path):
    (tmp_path / "lock").write_text(f"{os.getppid()}\n")
    with pytest.raises(Locked) as caught:
        DatasetLock(tmp_path).acquire()
    assert caught.value.pid == os.getppid()
    assert "delete" in str(caught.value)


def test_a_lock_left_by_a_dead_process_is_taken_over(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    (tmp_path / "lock").write_text(f"{child.pid}\n")
    lock = DatasetLock(tmp_path)
    lock.acquire()
    assert lock.path.read_text().strip() == str(os.getpid())


def test_our_own_lock_can_be_taken_again(tmp_path):
    DatasetLock(tmp_path).acquire()
    DatasetLock(tmp_path).acquire()


def test_release_leaves_someone_elses_lock(tmp_path):
    lock = DatasetLock(tmp_path)
    lock.acquire()
    lock.path.write_text(f"{os.getppid()}\n")
    lock.release()
    assert lock.path.exists()


def test_set_aside_keeps_the_unreadable_file(tmp_path):
    bad = tmp_path / "review.json"
    bad.write_bytes(b"{not json")
    warning, writable = set_aside(bad, ValueError("bad"))
    assert writable and not bad.exists()
    kept = [p for p in tmp_path.iterdir() if p.name.startswith("review.json.unreadable-")]
    assert len(kept) == 1 and kept[0].read_bytes() == b"{not json"
    assert kept[0].name in warning


def test_set_aside_that_cannot_move_forbids_writing(tmp_path, monkeypatch):
    bad = tmp_path / "review.json"
    bad.write_bytes(b"{not json")

    def cannot(src, dst):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(state.os, "replace", cannot)
    warning, writable = set_aside(bad, ValueError("bad"))
    assert not writable and bad.read_bytes() == b"{not json" and "nothing will be saved" in warning
