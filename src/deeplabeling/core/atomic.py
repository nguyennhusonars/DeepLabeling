"""The one atomic file writer. Every file DeepLabeling writes goes through it."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

#: Read once, at import: the umask can only be read by setting it, which must not
#: race with other threads creating files.
_UMASK = os.umask(0)
os.umask(_UMASK)


def write_atomic(path, data: bytes) -> None:
    """Replace `path` with `data` so that a crash leaves the old file or the new one.

    The bytes go to a temporary file beside the target, are flushed and fsynced,
    and `os.replace` moves them into place. On any failure the temporary file is
    removed and the target is untouched. Missing parent folders are created.

    The file keeps the target's permission bits, or gets the default ones (0o666
    less the umask) when new. `mkstemp` alone creates 0o600, which made every
    label file the legacy app edited private to its owner.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = os.stat(path).st_mode & 0o7777
    except FileNotFoundError:
        mode = 0o666 & ~_UMASK
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
