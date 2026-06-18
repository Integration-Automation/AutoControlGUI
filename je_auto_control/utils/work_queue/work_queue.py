"""SQLite-backed transactional work queue (dispatcher / performer).

The standard production-RPA pattern: instead of one long script, a
*dispatcher* enqueues work items and a *performer* processes them one at
a time with per-item status, retry, and dedup — so a run of 10k items is
resumable after a crash and parallelizable across workers.

Two failure kinds, mirroring REFramework:

* **application error** (transient — a timeout, a stale element): the item
  is retried up to ``max_retries`` then marked ``failed``.
* **business error** (the data itself is invalid): never retried — marked
  ``failed`` immediately. Raise :class:`BusinessError` (or pass
  ``kind="business"``) to signal it.

Pure standard library (``sqlite3``); imports no ``PySide6``.
"""
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

STATUS_NEW = "new"
STATUS_IN_PROGRESS = "in_progress"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


class BusinessError(Exception):
    """A non-retryable, data-level failure of a work item."""


@dataclass
class WorkItem:
    """One unit of work and its processing state."""
    id: int
    reference: str
    data: Dict[str, Any]
    status: str
    retries: int
    error: str = ""
    output: str = ""


class WorkQueue:
    """A named, SQLite-backed queue of work items."""

    def __init__(self, db_path: str, name: str = "default") -> None:
        self._db_path = db_path
        self._name = name
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0,
                               isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS work_items ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, queue TEXT NOT NULL, "
                "reference TEXT, data TEXT NOT NULL, status TEXT NOT NULL, "
                "retries INTEGER NOT NULL DEFAULT 0, error TEXT DEFAULT '', "
                "output TEXT DEFAULT '', updated REAL NOT NULL)")

    def add(self, data: Dict[str, Any], *, reference: Optional[str] = None,
            dedupe: bool = True) -> Optional[int]:
        """Enqueue an item; skip (return None) on a live duplicate reference."""
        with self._connect() as conn:
            if dedupe and reference and self._has_pending(conn, reference):
                return None
            cur = conn.execute(
                "INSERT INTO work_items (queue, reference, data, status, "
                "updated) VALUES (?, ?, ?, ?, ?)",
                (self._name, reference or "", json.dumps(data), STATUS_NEW,
                 time.time()))
            return int(cur.lastrowid)

    def _has_pending(self, conn: sqlite3.Connection, reference: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM work_items WHERE queue=? AND reference=? AND "
            "status IN (?, ?) LIMIT 1",
            (self._name, reference, STATUS_NEW, STATUS_IN_PROGRESS)).fetchone()
        return row is not None

    def get_next(self) -> Optional[WorkItem]:
        """Atomically claim the oldest ``new`` item, marking it in-progress."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM work_items WHERE queue=? AND status=? "
                "ORDER BY id LIMIT 1", (self._name, STATUS_NEW)).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            conn.execute(
                "UPDATE work_items SET status=?, updated=? WHERE id=?",
                (STATUS_IN_PROGRESS, time.time(), row["id"]))
            conn.execute("COMMIT")
            return _row_to_item(dict(row), status=STATUS_IN_PROGRESS)

    def complete(self, item_id: int, *, output: Any = None) -> None:
        """Mark an item successfully processed."""
        self._set_status(item_id, STATUS_SUCCESS,
                         output=json.dumps(output) if output is not None else "")

    def fail(self, item_id: int, error: str, *, kind: str = "application",
             max_retries: int = 3) -> str:
        """Fail an item; application errors retry, business errors don't.

        Returns the resulting status (``new`` when requeued, else ``failed``).
        """
        with self._connect() as conn:
            row = conn.execute("SELECT retries FROM work_items WHERE id=?",
                               (item_id,)).fetchone()
            retries = int(row["retries"]) if row else 0
            retryable = kind == "application" and retries < int(max_retries)
            status = STATUS_NEW if retryable else STATUS_FAILED
            conn.execute(
                "UPDATE work_items SET status=?, retries=?, error=?, updated=? "
                "WHERE id=?",
                (status, retries + 1, str(error), time.time(), item_id))
            return status

    def _set_status(self, item_id: int, status: str, *, output: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE work_items SET status=?, output=?, updated=? WHERE id=?",
                (status, output, time.time(), item_id))

    def stats(self) -> Dict[str, int]:
        """Return a count of items per status for this queue."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) c FROM work_items WHERE queue=? "
                "GROUP BY status", (self._name,)).fetchall()
        counts = {STATUS_NEW: 0, STATUS_IN_PROGRESS: 0,
                  STATUS_SUCCESS: 0, STATUS_FAILED: 0}
        for row in rows:
            counts[row["status"]] = int(row["c"])
        return counts

    def list_items(self, *, status: Optional[str] = None,
                   limit: int = 100) -> List[WorkItem]:
        """List items, optionally filtered by status."""
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM work_items WHERE queue=? AND status=? "
                    "ORDER BY id LIMIT ?",
                    (self._name, status, int(limit))).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM work_items WHERE queue=? ORDER BY id "
                    "LIMIT ?", (self._name, int(limit))).fetchall()
        return [_row_to_item(dict(row)) for row in rows]


def _row_to_item(row: Dict[str, Any],
                 status: Optional[str] = None) -> WorkItem:
    return WorkItem(
        id=int(row["id"]), reference=row["reference"] or "",
        data=json.loads(row["data"]), status=status or row["status"],
        retries=int(row["retries"]), error=row.get("error") or "",
        output=row.get("output") or "")
