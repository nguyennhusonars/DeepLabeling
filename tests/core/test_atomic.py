import os
import stat

import pytest

from deeplabeling.core import atomic
from deeplabeling.core.atomic import write_atomic


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_writes_the_exact_bytes(tmp_path):
    target = tmp_path / "a.txt"
    write_atomic(target, b"0 0.5 0.5 0.2 0.2\r\n\xff")
    assert target.read_bytes() == b"0 0.5 0.5 0.2 0.2\r\n\xff"


def test_replaces_an_existing_file(tmp_path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"old")
    write_atomic(target, b"new")
    assert target.read_bytes() == b"new"


def test_creates_missing_parent_folders(tmp_path):
    target = tmp_path / "x" / "labels" / "a.txt"
    write_atomic(target, b"")
    assert target.read_bytes() == b""


def test_a_failed_write_leaves_the_target_and_no_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_bytes(b"old")

    def full_disk(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(atomic.os, "replace", full_disk)
    with pytest.raises(OSError):
        write_atomic(target, b"new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]


def test_an_existing_file_keeps_its_permissions(tmp_path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"old")
    os.chmod(target, 0o664)
    write_atomic(target, b"new")
    assert mode(target) == 0o664


def test_a_new_file_gets_the_default_permissions_not_0600(tmp_path):
    target = tmp_path / "a.txt"
    write_atomic(target, b"new")
    assert mode(target) == 0o666 & ~atomic._UMASK
