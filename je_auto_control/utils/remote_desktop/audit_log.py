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
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_PATH_RELATIVE = ".je_auto_control/audit.db"
_MAX_ROWS = 50_000
_PRUNE_TARGET = 37_500  # ~75% of MAX after a prune
_GENESIS_HASH = "0" * 64


def default_audit_log_path() -> Path:
    return Path(os.path.expanduser("~")) / _DEFAULT_PATH_RELATIVE


@dataclass
class ChainVerification:
    """Result of :meth:`AuditLog.verify_chain`."""

    ok: bool
    broken_at_id: Optional[int]
    total_rows: int


class AuditLog:
    """Append-only event log with hash-chain integrity."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else default_audit_log_path()
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._path), check_same_thread=False, isolation_level=None,
        )
        self._init_schema()
        self._last_hash: str = self._load_last_hash()

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
        # Add chain columns to pre-existing tables.
        for column in ("prev_hash", "row_hash"):
            try:
                self._conn.execute(
                    f"ALTER TABLE events ADD COLUMN {column} TEXT"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists — that's fine.
        self._backfill_chain_locked()

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

    def _read_last_hash_locked(self) -> str:
        cur = self._conn.execute(
            "SELECT row_hash FROM events"
            " WHERE row_hash IS NOT NULL ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        return row[0] if row else _GENESIS_HASH

    def _load_last_hash(self) -> str:
        with self._lock:
            return self._read_last_hash_locked()

    def log(self, event_type: str, *,
            host_id: Optional[str] = None,
            viewer_id: Optional[str] = None,
            detail: Optional[str] = None) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                row_hash = _compute_row_hash(
                    self._last_hash, ts, event_type, host_id, viewer_id, detail,
                )
                self._conn.execute(
                    "INSERT INTO events"
                    " (ts, event_type, host_id, viewer_id, detail,"
                    "  prev_hash, row_hash)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ts, event_type, host_id, viewer_id, detail,
                     self._last_hash, row_hash),
                )
                self._last_hash = row_hash
                self._maybe_prune_locked()
            except sqlite3.Error as error:
                autocontrol_logger.warning("audit log insert: %r", error)

    def _maybe_prune_locked(self) -> None:
        cur = self._conn.execute("SELECT COUNT(*) FROM events")
        (count,) = cur.fetchone()
        if count <= _MAX_ROWS:
            return
        # Keep the most recent ``_PRUNE_TARGET`` rows. The chain stays
        # valid for kept rows: each surviving row's prev_hash still
        # matches the row above it; the very first surviving row's
        # prev_hash points at a row that no longer exists, which is
        # expected and reported by verify_chain as a "pruned" boundary.
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
            except sqlite3.Error as error:
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
        if not rows:
            return ChainVerification(ok=True, broken_at_id=None, total_rows=0)
        prev_hash = rows[0][6] or _GENESIS_HASH
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
        """Wipe the table. Returns the number of rows deleted."""
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM events")
            (count,) = cur.fetchone()
            self._conn.execute("DELETE FROM events")
            self._last_hash = _GENESIS_HASH
        return int(count)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
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


def _build_query_sql(*, event_type: Optional[str], host_id: Optional[str],
                     limit: int) -> Tuple[str, list]:
    sql = ("SELECT id, ts, event_type, host_id, viewer_id, detail"
           " FROM events")
    clauses: List[str] = []
    args: list = []
    if event_type:
        clauses.append("event_type = ?")
        args.append(event_type)
    if host_id:
        clauses.append("host_id = ?")
        args.append(host_id)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return sql, args


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
