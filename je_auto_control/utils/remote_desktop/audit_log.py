"""SQLite-backed, hash-chained audit log for remote-desktop sessions.

Captures connection lifecycle, auth outcomes, file transfers, and rate-limit
warnings. Schema is one ``events`` table with ``ts/event_type/host_id/
viewer_id/detail`` plus ``prev_hash`` and ``row_hash`` columns that form a
tamper-evident chain — each row's hash covers the previous hash so editing
any past row breaks every subsequent hash. Rotation is by row count
(oldest 25% pruned when threshold exceeded), so no external cron needed.

The store is thread-safe via ``check_same_thread=False`` plus a per-instance
lock; SQLite handles concurrent readers fine.

The chain is "trust on first use": rows that existed before this code was
deployed are backfilled at init, so the chain attests only to write order
*from that point forward*. Pre-existing rows could have been tampered
before backfill ran.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.sqlite_support import (
    SQLITE_ERRORS, SQLITE_OPERATIONAL_ERRORS, require_sqlite3,
)


_DEFAULT_PATH_RELATIVE = ".je_auto_control/audit.db"
_MAX_ROWS = 50_000
_PRUNE_TARGET = 37_500  # ~75% of MAX after a prune
_GENESIS_HASH = "0" * 64
#: ``PRAGMA user_version`` once the one-off backfill and the anchor exist.
_CHAIN_SCHEMA_VERSION = 1
_CLEARED_EVENT = "audit_log_cleared"


def default_audit_log_path() -> Path:
    return Path(os.path.expanduser("~")) / _DEFAULT_PATH_RELATIVE


@dataclass
class ChainVerification:
    """Result of :meth:`AuditLog.verify_chain`."""

    ok: bool
    broken_at_id: Optional[int]
    total_rows: int


class AuditLogError(AutoControlException):
    """The audit database could not be opened (corrupt file, lock timeout...)."""


class AuditLog:
    """Append-only event log with hash-chain integrity.

    Several processes may share one file (the host service and the GUI): each
    ``log`` reads the chain head inside its own write transaction, so a
    per-instance cache cannot link a row to a stale predecessor.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else default_audit_log_path()
        self._lock = threading.Lock()
        # Asked for before the directory is made, so a Python without
        # sqlite3 does not leave an empty ~/.je_auto_control behind.
        driver = require_sqlite3()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = driver.connect(
            str(self._path), check_same_thread=False, isolation_level=None,
        )
        try:
            self._init_schema()
        except SQLITE_ERRORS as error:
            # A corrupt file raised sqlite3.DatabaseError, outside the
            # family every caller's boundary contains.
            self._conn.close()
            raise AuditLogError(f"cannot open audit log {self._path}: {error}") from error

    def _init_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts TEXT NOT NULL,"
            " event_type TEXT NOT NULL,"
            " host_id TEXT,"
            " viewer_id TEXT,"
            " detail TEXT,"
            " prev_hash TEXT,"
            " row_hash TEXT)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)"
        )
        # Add chain columns to pre-existing tables. Column names are
        # split out as explicit literal SQL statements rather than
        # interpolated, so the SQL strings here are fully static —
        # this is the form that satisfies Semgrep / Sonar's
        # raw-SQL-construction rules without resorting to suppressions.
        try:
            self._conn.execute("ALTER TABLE events ADD COLUMN prev_hash TEXT")
        except SQLITE_OPERATIONAL_ERRORS:
            pass  # Column already exists — that's fine.
        try:
            self._conn.execute("ALTER TABLE events ADD COLUMN row_hash TEXT")
        except SQLITE_OPERATIONAL_ERRORS:
            pass  # Column already exists — that's fine.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS chain_meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        (version,) = self._conn.execute("PRAGMA user_version").fetchone()
        if int(version) < _CHAIN_SCHEMA_VERSION:
            self._migrate_chain_locked()

    def _migrate_chain_locked(self) -> None:
        """Chain the rows written before the hash columns existed -- once.

        The backfill used to run on every open and re-hash any row whose
        ``row_hash`` was NULL, so forging a row and clearing its hash made
        the next open bless the forgery. It runs once now; afterwards a
        NULL hash is a broken link. A table that was pruned before the
        anchor existed keeps its first row's ``prev_hash`` as the anchor.
        """
        first = self._conn.execute(
            "SELECT prev_hash FROM events WHERE row_hash IS NOT NULL ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if first is not None and first[0]:
            self._set_anchor_locked(first[0])
        self._backfill_chain_locked()
        # PRAGMA takes no bound parameters; the literal is _CHAIN_SCHEMA_VERSION.
        self._conn.execute("PRAGMA user_version = 1")

    def _backfill_chain_locked(self) -> None:
        cur = self._conn.execute(
            "SELECT id, ts, event_type, host_id, viewer_id, detail,"
            " prev_hash, row_hash FROM events"
            " WHERE row_hash IS NULL ORDER BY id ASC"
        )
        rows = cur.fetchall()
        if not rows:
            return
        prev_hash = self._read_last_hash_locked()
        for row in rows:
            row_id, ts, event_type, host_id, viewer_id, detail, _ph, _rh = row
            row_hash = _compute_row_hash(
                prev_hash, ts, event_type, host_id, viewer_id, detail,
            )
            self._conn.execute(
                "UPDATE events SET prev_hash = ?, row_hash = ? WHERE id = ?",
                (prev_hash, row_hash, row_id),
            )
            prev_hash = row_hash

    def _read_anchor_locked(self) -> str:
        """The hash the first row must point at: genesis, or the last pruned row."""
        row = self._conn.execute(
            "SELECT value FROM chain_meta WHERE key = 'anchor'"
        ).fetchone()
        return row[0] if row and row[0] else _GENESIS_HASH

    def _set_anchor_locked(self, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO chain_meta (key, value) VALUES ('anchor', ?)",
            (value,),
        )

    def _read_last_hash_locked(self) -> str:
        cur = self._conn.execute(
            "SELECT row_hash FROM events"
            " WHERE row_hash IS NOT NULL ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        return row[0] if row else _GENESIS_HASH

    def log(self, event_type: str, *,
            host_id: Optional[str] = None,
            viewer_id: Optional[str] = None,
            detail: Optional[str] = None) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                prev_hash = self._read_last_hash_locked()
                row_hash = _compute_row_hash(
                    prev_hash, ts, event_type, host_id, viewer_id, detail,
                )
                self._conn.execute(
                    "INSERT INTO events"
                    " (ts, event_type, host_id, viewer_id, detail,"
                    "  prev_hash, row_hash)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ts, event_type, host_id, viewer_id, detail,
                     prev_hash, row_hash),
                )
                self._conn.execute("COMMIT")
                self._maybe_prune_locked()
            except SQLITE_ERRORS as error:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                autocontrol_logger.warning("audit log insert: %r", error)

    def _maybe_prune_locked(self) -> None:
        cur = self._conn.execute("SELECT COUNT(*) FROM events")
        (count,) = cur.fetchone()
        if count <= _MAX_ROWS:
            return
        # Keep the most recent ``_PRUNE_TARGET`` rows. The chain stays
        # valid for kept rows: each surviving row's prev_hash still
        # matches the row above it. The first survivor's prev_hash names a
        # row that no longer exists, so it becomes the anchor verify_chain
        # starts from -- deleting rows from the top by hand does not.
        boundary = self._conn.execute(
            "SELECT row_hash FROM events WHERE id = ("
            "SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?)",
            (_PRUNE_TARGET,),
        ).fetchone()
        if boundary is not None and boundary[0]:
            self._set_anchor_locked(boundary[0])
        self._conn.execute(
            "DELETE FROM events WHERE id <= ("
            "SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?)",
            (_PRUNE_TARGET,),
        )

    def query(self, *,
              event_type: Optional[str] = None,
              host_id: Optional[str] = None,
              limit: int = 500) -> List[dict]:
        sql, args = _build_query_sql(
            event_type=event_type, host_id=host_id, limit=int(limit),
        )
        with self._lock:
            try:
                cur = self._conn.execute(sql, args)
                rows = cur.fetchall()
            except SQLITE_ERRORS as error:
                autocontrol_logger.warning("audit log query: %r", error)
                return []
        return [
            {"id": r[0], "ts": r[1], "event_type": r[2], "host_id": r[3],
             "viewer_id": r[4], "detail": r[5]}
            for r in rows
        ]

    def verify_chain(self) -> ChainVerification:
        """Walk the chain top-to-bottom; return the first broken link."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, ts, event_type, host_id, viewer_id, detail,"
                " prev_hash, row_hash FROM events ORDER BY id ASC"
            )
            rows = cur.fetchall()
            anchor = self._read_anchor_locked()
        if not rows:
            return ChainVerification(ok=True, broken_at_id=None, total_rows=0)
        prev_hash = anchor
        for row in rows:
            row_id, ts, event_type, host_id, viewer_id, detail, ph, rh = row
            if ph != prev_hash:
                return ChainVerification(
                    ok=False, broken_at_id=row_id, total_rows=len(rows),
                )
            expected = _compute_row_hash(
                ph, ts, event_type, host_id, viewer_id, detail,
            )
            if expected != rh:
                return ChainVerification(
                    ok=False, broken_at_id=row_id, total_rows=len(rows),
                )
            prev_hash = rh
        return ChainVerification(ok=True, broken_at_id=None, total_rows=len(rows))

    def clear(self) -> int:
        """Wipe the table, leaving one ``audit_log_cleared`` event. Returns the rows deleted.

        A clear used to leave nothing behind, so a wiped log verified as a
        clean empty one. The new chain starts with the event that says so.
        """
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM events")
            (count,) = cur.fetchone()
            self._conn.execute("DELETE FROM events")
            self._set_anchor_locked(_GENESIS_HASH)
        self.log(_CLEARED_EVENT, detail=f"{int(count)} rows deleted")
        return int(count)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except SQLITE_ERRORS:
                pass


def _compute_row_hash(prev_hash: Optional[str], ts: str, event_type: str,
                      host_id: Optional[str], viewer_id: Optional[str],
                      detail: Optional[str]) -> str:
    canonical = json.dumps(
        [prev_hash or _GENESIS_HASH, ts, event_type,
         host_id, viewer_id, detail],
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_QUERY_SQL = (
    "SELECT id, ts, event_type, host_id, viewer_id, detail"
    " FROM events"
    " WHERE (? IS NULL OR event_type = ?)"
    " AND (? IS NULL OR host_id = ?)"
    " ORDER BY id DESC LIMIT ?"
)


def _build_query_sql(*, event_type: Optional[str], host_id: Optional[str],
                     limit: int) -> Tuple[str, list]:
    """Return a static SQL string + bound args for an audit-log query.

    The SQL is a single fixed template; optional filters are toggled
    by passing ``None`` to the matching parameters. Keeping the SQL
    literal-only means there is no string concatenation for static
    analysers to mistake for SQL injection.
    """
    args: list = [event_type, event_type, host_id, host_id, int(limit)]
    return _QUERY_SQL, args


_default_audit_log: Optional[AuditLog] = None
_default_lock = threading.Lock()


def default_audit_log() -> AuditLog:
    """Process-wide singleton on the default path."""
    global _default_audit_log
    with _default_lock:
        if _default_audit_log is None:
            _default_audit_log = AuditLog()
        return _default_audit_log


__all__ = [
    "AuditLog", "ChainVerification",
    "default_audit_log", "default_audit_log_path",
]
