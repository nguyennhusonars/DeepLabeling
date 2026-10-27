"""One SQLite cache file in a dataset's state folder, shared by the prediction store and the
score cache: each thread talks to it through its own connection; a corrupt file, or one of
another version, is set aside and started again; a read-only one is read as it is."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import ClassVar

from .state import set_aside


class SqliteFile:
    SCHEMA: ClassVar[str]
    VERSION: ClassVar[int]      #: PRAGMA user_version: a file of another version is set aside, as a corrupt one is
    SYNCHRONOUS: ClassVar[str] = "NORMAL"

    def __init__(self, path):
        self.path = Path(path)
        self.warning = ""                           # for the notice strip
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._closed = False
        try:
            try:
                self._connection()
            except sqlite3.OperationalError:
                raise                               # locked, full, unreadable: not corrupt
            except sqlite3.DatabaseError as e:      # "file is not a database"
                self._close_all()
                self.warning, writable = set_aside(self.path, e)
                if not writable:
                    raise OSError(self.warning) from e
                self._connection()
        except sqlite3.OperationalError as e:       # the open says why, as for any OSError
            self._close_all()
            raise OSError(f"{self.path.name}: {e}") from e

    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(f"PRAGMA synchronous={self.SYNCHRONOUS}")
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, self.VERSION):    # 0: made before versions, this same schema
                    raise sqlite3.DatabaseError(f"a store of version {version}, this app reads {self.VERSION}")
                if version == 0:                    # new, or made before versions: stamped once
                    try:
                        conn.execute(self.SCHEMA)
                        conn.execute(f"PRAGMA user_version = {self.VERSION}")
                        conn.commit()
                    except sqlite3.OperationalError as e:
                        if "readonly" not in str(e):
                            raise
                        conn.rollback()             # a store made read-only: read as it is
            except sqlite3.DatabaseError:
                conn.close()
                raise
            with self._lock:
                if self._closed:                    # closed while this one opened: not kept
                    conn.close()
                    raise sqlite3.ProgrammingError("the store is closed")
                self._all.append(conn)
            self._local.conn = conn
        return conn

    def _close_all(self) -> None:
        with self._lock:
            for conn in self._all:
                conn.close()
            self._all.clear()
        self._local = threading.local()

    def close(self) -> None:
        """Close every connection; afterwards the store answers nothing and writes nothing,
        rather than opening a connection again for a thread that comes late."""
        self._closed = True
        self._close_all()
