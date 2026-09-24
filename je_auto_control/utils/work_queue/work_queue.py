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
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ContextManager, Dict, List, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.sqlite_support import (
    autocommit_connection, last_row_id,
)

if TYPE_CHECKING:  # reason: sqlite3 types are named only in annotations
    import sqlite3

STATUS_NEW = "new"
STATUS_IN_PROGRESS = "in_progress"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


class BusinessError(AutoControlException):
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
    claim: int = 0


_ABANDONED = "abandoned: claimed and never settled"


def _require_in_progress(item_id: int, row: Any,
                         claim: Optional[int] = None) -> None:
    """Refuse to settle an item that is unknown, not claimed, or claimed again.

    Completing a never-claimed item, or failing one that had already
    succeeded (requeueing it for a second run), used to be accepted. The
    status alone cannot tell a stale performer from the one that re-claimed
    the item, so each claim is numbered; a performer that passes its
    ``claim`` back is refused once someone else has claimed the item since.
    """
    if row is None:
        raise AutoControlException(f"no work item with id {item_id}")
    if row["status"] != STATUS_IN_PROGRESS:
        raise AutoControlException(
            f"work item {item_id} is {row['status']}, not {STATUS_IN_PROGRESS}")
    if claim is not None and int(row["claim"]) != int(claim):
        raise AutoControlException(
            f"work item {item_id} was claimed again (claim {row['claim']}); "
            f"claim {claim} is stale")


class WorkQueue:
    """A named, SQLite-backed queue of work items."""

    def __init__(self, db_path: str, name: str = "default") -> None:
        self._db_path = db_path
        self._name = name
        self._ensure_schema()

    def _connect(self) -> ContextManager["sqlite3.Connection"]:
        return autocommit_connection(self._db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS work_items ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, queue TEXT NOT NULL, "
                "reference TEXT, data TEXT NOT NULL, status TEXT NOT NULL, "
                "retries INTEGER NOT NULL DEFAULT 0, error TEXT DEFAULT '', "
                "output TEXT DEFAULT '', updated REAL NOT NULL, "
                "claim INTEGER NOT NULL DEFAULT 0)")
            columns = {row["name"] for row in
                       conn.execute("PRAGMA table_info(work_items)")}
            if "claim" not in columns:
                conn.execute("ALTER TABLE work_items ADD COLUMN "
                             "claim INTEGER NOT NULL DEFAULT 0")

    def add(self, data: Dict[str, Any], *, reference: Optional[str] = None,
            dedupe: bool = True) -> Optional[int]:
        """Enqueue an item; skip (return None) on a live duplicate reference."""
        with self._connect() as conn:
            # One write transaction for the check and the insert: in autocommit
            # two dispatchers could both pass the check and enqueue twice.
            conn.execute("BEGIN IMMEDIATE")
            if dedupe and reference and self._has_pending(conn, reference):
                conn.execute("COMMIT")
                return None
            cur = conn.execute(
                "INSERT INTO work_items (queue, reference, data, status, "
                "updated) VALUES (?, ?, ?, ?, ?)",
                (self._name, reference or "", json.dumps(data), STATUS_NEW,
                 time.time()))
            conn.execute("COMMIT")
            return last_row_id(cur)

    def _has_pending(self, conn: "sqlite3.Connection", reference: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM work_items WHERE queue=? AND reference=? AND "
            "status IN (?, ?) LIMIT 1",
            (self._name, reference, STATUS_NEW, STATUS_IN_PROGRESS)).fetchone()
        return row is not None

    def get_next(self, *, stale_after_s: Optional[float] = None,
                 max_retries: int = 3) -> Optional[WorkItem]:
        """Atomically claim the oldest ``new`` item, marking it in-progress.

        With ``stale_after_s``, an ``in_progress`` item not updated for that
        long is claimable again too: a performer that crashed mid-item left
        it in progress for good -- and, since a live duplicate blocks
        ``add``, it could not even be enqueued again. Such a reclaim counts
        as a retry, and an item already abandoned ``max_retries`` times is
        marked ``failed`` instead of being handed out forever.

        The returned item's ``claim`` numbers this claim; pass it back to
        :meth:`complete` / :meth:`fail` so a performer whose item was
        reclaimed meanwhile cannot settle it.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._claimable(conn, stale_after_s, max_retries)
            if row is None:
                conn.execute("COMMIT")
                return None
            item = _row_to_item(dict(row), status=STATUS_IN_PROGRESS)
            if row["status"] == STATUS_IN_PROGRESS:
                item.retries += 1
            item.claim += 1
            conn.execute(
                "UPDATE work_items SET status=?, retries=?, claim=?, updated=? "
                "WHERE id=?",
                (STATUS_IN_PROGRESS, item.retries, item.claim, time.time(),
                 item.id))
            conn.execute("COMMIT")
            return item

    def _claimable(self, conn: "sqlite3.Connection",
                   stale_after_s: Optional[float],
                   max_retries: int) -> Optional[Any]:
        """The next row to claim, failing exhausted stale items first."""
        if stale_after_s is None:
            return conn.execute(
                "SELECT * FROM work_items WHERE queue=? AND status=? "
                "ORDER BY id LIMIT 1", (self._name, STATUS_NEW)).fetchone()
        cutoff = time.time() - float(stale_after_s)
        conn.execute(
            "UPDATE work_items SET status=?, error=?, updated=? WHERE queue=? "
            "AND status=? AND updated<? AND retries>=?",
            (STATUS_FAILED, _ABANDONED, time.time(), self._name,
             STATUS_IN_PROGRESS, cutoff, int(max_retries)))
        return conn.execute(
            "SELECT * FROM work_items WHERE queue=? AND (status=? OR "
            "(status=? AND updated<?)) ORDER BY id LIMIT 1",
            (self._name, STATUS_NEW, STATUS_IN_PROGRESS, cutoff)).fetchone()

    def complete(self, item_id: int, *, output: Any = None,
                 claim: Optional[int] = None) -> None:
        """Mark an item successfully processed (refused if ``claim`` is stale)."""
        self._set_status(item_id, STATUS_SUCCESS, claim=claim,
                         output=json.dumps(output) if output is not None else "")

    def fail(self, item_id: int, error: str, *, kind: str = "application",
             max_retries: int = 3, claim: Optional[int] = None) -> str:
        """Fail an item; application errors retry, business errors don't.

        Returns the resulting status (``new`` when requeued, else ``failed``).
        A stale ``claim`` is refused as in :meth:`complete`.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT retries, status, claim FROM work_items WHERE id=?",
                (item_id,)).fetchone()
            try:
                _require_in_progress(item_id, row, claim)
            except AutoControlException:
                conn.execute("ROLLBACK")
                raise
            retries = int(row["retries"])
            retryable = kind == "application" and retries < int(max_retries)
            status = STATUS_NEW if retryable else STATUS_FAILED
            conn.execute(
                "UPDATE work_items SET status=?, retries=?, error=?, updated=? "
                "WHERE id=?",
                (status, retries + 1, str(error), time.time(), item_id))
            conn.execute("COMMIT")
            return status

    def _set_status(self, item_id: int, status: str, *, output: str = "",
                    claim: Optional[int] = None) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE work_items SET status=?, output=?, updated=? "
                "WHERE id=? AND status=? AND (? IS NULL OR claim=?)",
                (status, output, time.time(), item_id, STATUS_IN_PROGRESS,
                 claim, claim))
            if cursor.rowcount == 0:
                row = conn.execute(
                    "SELECT status, claim FROM work_items WHERE id=?",
                    (item_id,)).fetchone()
                _require_in_progress(item_id, row, claim)

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
        output=row.get("output") or "", claim=int(row.get("claim") or 0))
