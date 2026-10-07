import os
import subprocess
import sys
from pathlib import Path

import pytest

from deeplabeling.core import state
from deeplabeling.core.state import DatasetLock, Locked, dataset_state_dir, set_aside, state_dir
from fixtures import SRC, held_elsewhere


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


RACE = """
import sys, time
from pathlib import Path
sys.path.insert(0, {src!r})
from deeplabeling.core.state import DatasetLock, Locked
go = Path({go!r})
while not go.exists():
    time.sleep(0.001)
lock = DatasetLock({directory!r})
try:
    lock.acquire()
    print("ok", flush=True)
except Locked:
    print("locked", flush=True)
time.sleep(1)
"""


def test_a_lock_records_our_pid_while_held(tmp_path):
    lock = DatasetLock(tmp_path)
    lock.acquire()
    assert lock.path.read_text().strip() == str(os.getpid()) and lock.held
    lock.release()
    assert not lock.held


def test_a_lock_held_by_another_live_process_refuses(tmp_path):
    with held_elsewhere(tmp_path) as pid:
        with pytest.raises(Locked) as caught:
            DatasetLock(tmp_path).acquire()
    assert caught.value.pid == pid and str(pid) in str(caught.value)


def test_a_lock_file_left_without_a_holder_is_taken(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    (tmp_path / "lock").write_text(f"{child.pid}\n")
    lock = DatasetLock(tmp_path)
    lock.acquire()
    assert lock.path.read_text().strip() == str(os.getpid())


def test_a_holder_that_dies_frees_the_lock(tmp_path):
    with held_elsewhere(tmp_path):
        pass
    DatasetLock(tmp_path).acquire()


def test_a_second_lock_in_the_same_process_is_refused(tmp_path):
    first = DatasetLock(tmp_path)
    first.acquire()
    with pytest.raises(Locked) as caught:
        DatasetLock(tmp_path).acquire()
    assert caught.value.pid == os.getpid()
    first.release()
    DatasetLock(tmp_path).acquire()


def test_only_one_of_two_racing_processes_gets_the_lock(tmp_path):
    go = tmp_path / "go"
    script = RACE.format(src=str(SRC), go=str(go), directory=str(tmp_path))
    children = [subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
                for _ in range(2)]
    go.touch()
    results = sorted(child.communicate(timeout=30)[0].strip() for child in children)
    assert results == ["locked", "ok"]


def test_releasing_a_lock_never_taken_is_harmless(tmp_path):
    DatasetLock(tmp_path).release()


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
    assert not writable and bad.read_bytes() == b"{not json" and "nothing saved" in warning
