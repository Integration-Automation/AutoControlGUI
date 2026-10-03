"""Shared lazy SQLite connection lifecycle for config persistence."""
from __future__ import annotations
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, Union
from je_auto_control.utils.sqlite_support import SQLITE_ERRORS, require_sqlite3

if TYPE_CHECKING:
    import sqlite3

StorePath = Union[str, Path, Callable[[], Path]]


class LazyConfigDatabase:
    """Resolve one host-owned path on first use and release failed or closed connections."""

    def __init__(self, path: StorePath, schema: str) -> None:
        self._source = path
        self._schema = schema
        self._path: Optional[str] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    def connection(self) -> sqlite3.Connection:
        """Open once; callers serialize their database operations using their own lock."""
        with self._lock:
            if self._conn is not None:
                return self._conn
            if self._path is None:
                self._path = str(self._source() if callable(self._source) else self._source)
            if self._path != ':memory:':
                Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            conn = require_sqlite3().connect(self._path, isolation_level=None, check_same_thread=False)
            try:
                conn.executescript(self._schema)
            except SQLITE_ERRORS:
                conn.close()
                raise
            self._conn = conn
            return conn

    def close(self) -> None:
        """Close while preserving the resolved path for reopening."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
