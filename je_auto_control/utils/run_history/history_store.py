"""Thread-safe SQLite-backed run history.

Records every fire of a scheduled job, trigger, or hotkey binding so the GUI
and REST API can show "what ran, when, and whether it succeeded". The store
is intentionally minimal — no retention policy, no analytics — callers drive
pruning via :meth:`clear` or :meth:`prune`.
"""
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

SOURCE_SCHEDULER = "scheduler"
SOURCE_TRIGGER = "trigger"
SOURCE_HOTKEY = "hotkey"
SOURCE_MANUAL = "manual"
SOURCE_REST = "rest"

STATUS_RUNNING = "running"
STATUS_OK = "ok"
STATUS_ERROR = "error"

_VALID_SOURCES = frozenset({
    SOURCE_SCHEDULER, SOURCE_TRIGGER, SOURCE_HOTKEY,
    SOURCE_MANUAL, SOURCE_REST,
})
_VALID_STATUSES = frozenset({STATUS_RUNNING, STATUS_OK, STATUS_ERROR})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    script_path TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    status TEXT NOT NULL,
    error_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_source ON runs(source_type, source_id);
"""


@dataclass
class RunRecord:
    """One row of the ``runs`` table."""
    id: int
    source_type: str
    source_id: str
    script_path: str
    started_at: float
    finished_at: Optional[float]
    status: str
    error_text: Optional[str]

    @property
    def duration_seconds(self) -> Optional[float]:
        """End-to-end duration or ``None`` if the run is still in-flight."""
        if self.finished_at is None:
            return None
        return max(0.0, self.finished_at - self.started_at)


def _default_history_path() -> Path:
    """Return the per-user cache path for the default store."""
    return Path.home() / ".je_auto_control" / "run_history.sqlite"


def _validate_source(source_type: str) -> None:
    if source_type not in _VALID_SOURCES:
        raise ValueError(
            f"invalid source_type {source_type!r}; "
            f"expected one of {sorted(_VALID_SOURCES)}"
        )


def _validate_status(status: str) -> None:
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; expected one of {sorted(_VALID_STATUSES)}"
        )


class HistoryStore:
    """SQLite-backed run log. Safe to share across threads."""

    def __init__(self, path: Union[str, Path] = ":memory:") -> None:
        self._path = str(path) if path == ":memory:" else str(Path(path))
        if self._path != ":memory:":
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            self._path, check_same_thread=False, isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    @property
    def path(self) -> str:
        return self._path

    def start_run(self, source_type: str, source_id: str,
                  script_path: str, started_at: Optional[float] = None,
                  ) -> int:
        """Record a run that has just begun; return its row id."""
        _validate_source(source_type)
        ts = float(started_at) if started_at is not None else time.time()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO runs (source_type, source_id, script_path,"
                " started_at, status) VALUES (?, ?, ?, ?, ?)",
                (source_type, source_id, script_path, ts, STATUS_RUNNING),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str,
                   error_text: Optional[str] = None,
                   finished_at: Optional[float] = None) -> bool:
        """Update a pending run with its final status; return False if unknown."""
        _validate_status(status)
        if status == STATUS_RUNNING:
            raise ValueError("cannot finish a run with status=running")
        ts = float(finished_at) if finished_at is not None else time.time()
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE runs SET finished_at = ?, status = ?, error_text = ?"
                " WHERE id = ?",
                (ts, status, error_text, int(run_id)),
            )
            return cursor.rowcount > 0

    def list_runs(self, limit: int = 100,
                  source_type: Optional[str] = None,
                  ) -> List[RunRecord]:
        """Return the most recent runs (newest first)."""
        if limit <= 0:
            return []
        if source_type is not None:
            _validate_source(source_type)
        sql = "SELECT * FROM runs"
        params: list = []
        if source_type is not None:
            sql += " WHERE source_type = ?"
            params.append(source_type)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_run(self, run_id: int) -> Optional[RunRecord]:
        """Return a specific row or ``None`` if absent."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE id = ?", (int(run_id),),
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def count(self, source_type: Optional[str] = None) -> int:
        """Return the number of rows, optionally filtered by source."""
        if source_type is not None:
            _validate_source(source_type)
            with self._lock:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE source_type = ?",
                    (source_type,),
                ).fetchone()
        else:
            with self._lock:
                row = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()
        return int(row[0])

    def clear(self) -> int:
        """Delete every row; return the number removed."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM runs")
            return int(cursor.rowcount)

    def prune(self, keep_latest: int) -> int:
        """Keep only the newest ``keep_latest`` rows; return rows removed."""
        if keep_latest < 0:
            raise ValueError("keep_latest must be >= 0")
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM runs WHERE id NOT IN ("
                "SELECT id FROM runs ORDER BY started_at DESC LIMIT ?"
                ")",
                (int(keep_latest),),
            )
            return int(cursor.rowcount)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error as error:
                autocontrol_logger.warning("history close failed: %r", error)


def _row_to_record(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=int(row["id"]),
        source_type=str(row["source_type"]),
        source_id=str(row["source_id"]),
        script_path=str(row["script_path"]),
        started_at=float(row["started_at"]),
        finished_at=(float(row["finished_at"])
                     if row["finished_at"] is not None else None),
        status=str(row["status"]),
        error_text=(str(row["error_text"])
                    if row["error_text"] is not None else None),
    )


default_history_store = HistoryStore(path=_default_history_path())
