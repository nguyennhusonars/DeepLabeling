"""Where DeepLabeling keeps its state (docs/knowledge/caches.md#where-app-state-lives):
one fixed folder found from this file's location, never from the launch folder."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from .atomic import write_atomic

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
    def __init__(self, pid: int, path: Path):
        super().__init__(f"this dataset is open in another DeepLabeling (process {pid}); "
                         f"if none is running, delete {path}")
        self.pid = pid


class DatasetLock:
    """One DeepLabeling per dataset root: a file holding the owner's process id."""

    def __init__(self, directory: Path):
        self.path = Path(directory) / "lock"
        self.held = False

    def acquire(self) -> None:
        pid = _read_pid(self.path)
        if pid is not None and pid != os.getpid() and _alive(pid):
            raise Locked(pid, self.path)
        write_atomic(self.path, f"{os.getpid()}\n".encode())
        self.held = True

    def release(self) -> None:
        if self.held and _read_pid(self.path) == os.getpid():
            self.path.unlink(missing_ok=True)
        self.held = False


def set_aside(path: Path, error: Exception) -> tuple[str, bool]:
    """Move an unreadable state file aside so that nothing overwrites it.

    Returns the warning to show and whether `path` may be written afterwards.
    """
    aside = path.with_name(f"{path.name}.unreadable-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        os.replace(path, aside)
    except OSError:
        return (f"{path.name} could not be read ({error}) or moved aside; it is left as "
                "it is, and nothing will be saved to it", False)
    return (f"{path.name} could not be read ({error}); it was kept as {aside.name}, "
            "and its contents start empty", True)


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
