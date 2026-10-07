"""Where DeepLabeling keeps its state (docs/knowledge/caches.md#where-app-state-lives):
one fixed folder found from this file's location, never from the launch folder."""

from __future__ import annotations

import fcntl
import hashlib
import os
import time
from pathlib import Path

ENV = "DEEPLABELING_STATE_DIR"

#: src/deeplabeling/core/state.py -> the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]


def state_dir() -> Path:
    override = os.environ.get(ENV)
    return Path(override) if override else REPO_ROOT / ".deeplabeling"


def dataset_state_dir(root: Path) -> Path:
    """One dataset root's folder: a readable name plus a hash of the whole root."""
    digest = hashlib.sha1(os.fsencode(str(root))).hexdigest()[:8]
    return state_dir() / "datasets" / f"{root.name or 'root'}-{digest}"


class Locked(Exception):
    def __init__(self, pid: int | None, path: Path):
        holder = f"process {pid}" if pid is not None else "another process"
        super().__init__(f"already open in DeepLabeling ({holder}) — close it there first")
        self.pid = pid
        self.path = path


class DatasetLock:
    """One open dataset per root, across processes and within one.

    An exclusive flock on the `lock` file, held while the dataset is open. The
    kernel drops it when the process dies, so a crash never leaves a stale lock,
    and two opens in one process conflict too, since a flock belongs to the open
    file, not the process. The file holds the holder's pid, for the message only.
    It is never deleted: deleting a lock file lets a late opener lock the orphaned
    file while a newcomer locks a fresh one.
    """

    def __init__(self, directory: Path):
        self.path = Path(directory) / "lock"
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o666)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise Locked(_read_pid(self.path), self.path) from None
        except BaseException:
            os.close(fd)
            raise
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
        except OSError:
            pass                # the pid only feeds the message; the flock is the lock
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)  # closing the file drops the flock
            self._fd = None


def set_aside(path: Path, error: Exception) -> tuple[str, bool]:
    """Move an unreadable state file aside so that nothing overwrites it.

    Returns the warning to show and whether `path` may be written afterwards.
    """
    aside = path.with_name(f"{path.name}.unreadable-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        os.replace(path, aside)
    except OSError:
        return (f"{path.name} unreadable ({error}) and not movable aside: left as is, nothing saved to it", False)
    return (f"{path.name} unreadable ({error}): kept as {aside.name}, starting empty", True)


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None
