"""Lazy per-operation SQLite connections shared by config storage and its durable client outbox."""
from __future__ import annotations

import os
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Callable, Iterator, Optional

from je_auto_control.utils.config_sync.contract import ConfigStoreError

if TYPE_CHECKING:
    from sqlite3 import Connection


# pylint: disable-next=too-few-public-methods  # reason: one connection factory owns lazy binding and cleanup
class SyncDatabase:
    """Resolve one stable database binding on first use and always close each owned connection."""

    def __init__(self, path: Optional[str | Path], environment: str, filename: str,
                 initialize: Callable[[Connection], None]) -> None:
        self._configured = path
        self._environment = environment
        self._filename = filename
        self._initialize = initialize
        self._resolved: Optional[Path] = None
        self._lock = Lock()

    def _path(self) -> Path:
        with self._lock:
            if self._resolved is None:
                value = self._configured or os.environ.get(self._environment)
                path = Path(value).expanduser() if value else Path.home() / ".autocontrol" / self._filename
                self._resolved = path.resolve()
            return self._resolved

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """Open optional SQLite only for an explicit operation, retaining framework storage errors."""
        # pylint: disable-next=import-outside-toplevel  # reason: SQLite remains optional until a storage operation
        import sqlite3
        try:
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(path, timeout=10, isolation_level=None)) as connection:
                self._initialize(connection)
                yield connection
        except (sqlite3.Error, OSError) as error:
            raise ConfigStoreError("config storage operation failed") from error
