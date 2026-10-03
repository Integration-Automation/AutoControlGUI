"""Durable account/endpoint-scoped config retries and device acknowledgements."""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, Literal, Mapping, Optional, Tuple

from je_auto_control.utils.sqlite_support import sqlite_errors_as

from .database import LazyConfigDatabase
from .models import ConfigSyncError
from .store import ConfigRevisionConflict, StorePath, validate_operation_id, validate_revision
from .versions import PeerState

if TYPE_CHECKING:
    import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_outbox (
    endpoint TEXT NOT NULL, user_id TEXT NOT NULL, operation_id TEXT NOT NULL,
    payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY(endpoint,user_id,operation_id)
);
CREATE TABLE IF NOT EXISTS sync_peers (
    endpoint TEXT NOT NULL, user_id TEXT NOT NULL, peer_id TEXT NOT NULL,
    revision INTEGER NOT NULL, retired INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(endpoint,user_id,peer_id)
);
CREATE TABLE IF NOT EXISTS sync_device_ids (
    endpoint TEXT NOT NULL, user_id TEXT NOT NULL, device_id TEXT NOT NULL,
    PRIMARY KEY(endpoint,user_id)
);
"""


def normalize_endpoint(value: str) -> str:
    """Validate a credential-free HTTP endpoint before persisting its namespace."""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ConfigSyncError('sync endpoint must be an HTTP URL with a hostname')
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ConfigSyncError('sync endpoint must be an HTTP URL without credentials, query or fragment')
    return value.rstrip('/')


@dataclass(frozen=True)
class SyncOperation:
    """An exact protected write envelope; authentication is supplied only at dispatch."""
    endpoint: str
    user_id: str
    operation_id: str
    base_revision: int
    bucket: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'endpoint', normalize_endpoint(self.endpoint))
        validate_revision(self.base_revision)
        validate_operation_id(self.operation_id)
        if not self.user_id or self.bucket.get('user_id') != self.user_id:
            raise ConfigSyncError('operation account does not match bucket')
        try:
            snapshot = json.loads(json.dumps(dict(self.bucket), allow_nan=False))
        except (TypeError, ValueError) as error:
            raise ConfigSyncError('operation bucket must contain finite JSON data') from error
        object.__setattr__(self, 'bucket', snapshot)

    def envelope(self) -> Dict[str, object]:
        """Build the version-2 request without adding credentials or new operation IDs."""
        return {'schema_version': 2, 'base_revision': self.base_revision,
                'operation_id': self.operation_id, 'bucket': dict(self.bucket)}


@dataclass(frozen=True)
class OutboxReport:
    """One bounded drain's deliveries, outstanding data, failures and cancellation."""
    sent: int
    pending: int
    conflicts: int = 0
    failed: int = 0
    cancelled: bool = False


class SyncOutbox:
    """Persist exact write envelopes before dispatch, with bounded retries and scoped peers."""

    def __init__(self, path: StorePath, *, endpoint: str, user_id: str) -> None:
        self._database = LazyConfigDatabase(path, _SCHEMA)
        self._endpoint = normalize_endpoint(endpoint)
        if not user_id:
            raise ConfigSyncError('outbox requires a user_id')
        self._user_id = user_id
        self._lock = threading.RLock()

    def _connection(self) -> sqlite3.Connection:
        return self._database.connection()

    @sqlite_errors_as(ConfigSyncError)
    def enqueue(self, operation: SyncOperation, *, superseded: Tuple[str, ...] = ()) -> None:
        """Atomically replace only unsent intents or server-confirmed stale envelopes."""
        self._enqueue(operation, 'pending', superseded)

    @sqlite_errors_as(ConfigSyncError)
    def enqueue_intent(self, operation: SyncOperation) -> None:
        """Persist a local publication intent; it must never be dispatched as an exact envelope."""
        self._enqueue(operation, 'intent', ())

    def _enqueue(self, operation: SyncOperation, state: str, superseded: Tuple[str, ...]) -> None:
        if operation.endpoint != self._endpoint or operation.user_id != self._user_id:
            raise ConfigSyncError('operation belongs to another outbox namespace')
        payload = json.dumps(operation.envelope(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        with self._lock:
            conn = self._connection()
            conn.execute('BEGIN IMMEDIATE')
            try:
                self._check_superseded(conn, superseded)
                row = conn.execute('SELECT payload FROM sync_outbox WHERE endpoint=? AND user_id=? '
                                   'AND operation_id=?', self._key(operation.operation_id)).fetchone()
                if row is not None and row[0] != payload:
                    raise ConfigSyncError('operation ID reused with a different envelope')
                conn.execute('INSERT OR IGNORE INTO sync_outbox(endpoint,user_id,operation_id,payload,state) '
                             'VALUES(?,?,?,?,?)', (*self._key(operation.operation_id), payload, state))
                conn.executemany('DELETE FROM sync_outbox WHERE endpoint=? AND user_id=? AND operation_id=?',
                                 [self._key(identifier) for identifier in superseded])
                conn.commit()
            finally:
                if conn.in_transaction:
                    conn.rollback()

    def _check_superseded(self, conn: sqlite3.Connection, identifiers: Tuple[str, ...]) -> None:
        for identifier in identifiers:
            row = conn.execute('SELECT state FROM sync_outbox WHERE endpoint=? AND user_id=? AND operation_id=?',
                               self._key(identifier)).fetchone()
            if row is None or row[0] not in ('intent', 'conflict'):
                raise ConfigSyncError('cannot replace an operation with an uncertain delivery outcome')

    def _key(self, operation_id: str) -> Tuple[str, str, str]:
        return self._endpoint, self._user_id, operation_id

    @sqlite_errors_as(ConfigSyncError)
    def device_id(self) -> str:
        """Read or create the stable local device origin for this account/endpoint."""
        with self._lock:
            conn = self._connection()
            conn.execute('INSERT OR IGNORE INTO sync_device_ids VALUES(?,?,?)',
                         (self._endpoint, self._user_id, uuid.uuid4().hex))
            row = conn.execute('SELECT device_id FROM sync_device_ids WHERE endpoint=? AND user_id=?',
                               (self._endpoint, self._user_id)).fetchone()
            return str(row[0])

    @sqlite_errors_as(ConfigSyncError)
    def confirm(self, operation_id: str, *, revision: int) -> None:
        """Remove a delivered operation only after a positive committed revision is confirmed."""
        if validate_revision(revision) == 0:
            raise ConfigSyncError('a committed revision must be positive')
        with self._lock:
            self._connection().execute('DELETE FROM sync_outbox WHERE endpoint=? AND user_id=? AND operation_id=?',
                                       self._key(operation_id))

    @sqlite_errors_as(ConfigSyncError)
    def mark_conflict(self, operation_id: str) -> None:
        """Stop resending a server-confirmed stale write while preserving its data."""
        with self._lock:
            self._connection().execute("UPDATE sync_outbox SET state='conflict' "
                                       'WHERE endpoint=? AND user_id=? AND operation_id=?', self._key(operation_id))

    @sqlite_errors_as(ConfigSyncError)
    def drop_conflict(self, operation_id: str) -> None:
        """Remove only a confirmed stale envelope after its merged replacement was enqueued."""
        with self._lock:
            self._connection().execute("DELETE FROM sync_outbox WHERE state='conflict' "
                                       'AND endpoint=? AND user_id=? AND operation_id=?', self._key(operation_id))

    def _operation(self, payload: str) -> SyncOperation:
        body = json.loads(payload)
        return SyncOperation(self._endpoint, self._user_id, body['operation_id'], body['base_revision'], body['bucket'])

    @sqlite_errors_as(ConfigSyncError)
    def pending(self) -> Tuple[SyncOperation, ...]:
        """Read all outstanding operations, including bounded failures awaiting a decision."""
        with self._lock:
            rows = self._connection().execute('SELECT payload FROM sync_outbox WHERE endpoint=? AND user_id=? '
                                              'ORDER BY rowid', (self._endpoint, self._user_id)).fetchall()
            return tuple(self._operation(row[0]) for row in rows)

    @sqlite_errors_as(ConfigSyncError)
    def recoverable(self, *, state: Optional[Literal['intent', 'conflict']] = None) -> Tuple[SyncOperation, ...]:
        """Read only never-dispatched intents and confirmed stale writes for fresh causal merging."""
        with self._lock:
            rows = self._connection().execute('SELECT payload,state FROM sync_outbox WHERE endpoint=? AND user_id=? '
                                              "AND state IN ('intent','conflict') ORDER BY rowid",
                                              (self._endpoint, self._user_id)).fetchall()
            return tuple(self._operation(row[0]) for row in rows if state is None or row[1] == state)

    @sqlite_errors_as(ConfigSyncError)
    def restart_failed(self) -> None:
        """Explicitly renew exhausted retries without changing their payload or operation ID."""
        with self._lock:
            self._connection().execute("UPDATE sync_outbox SET state='pending',attempts=0,next_at=0 "
                                       "WHERE endpoint=? AND user_id=? AND state='failed'",
                                       (self._endpoint, self._user_id))

    @sqlite_errors_as(ConfigSyncError)
    def state_counts(self) -> Dict[str, int]:
        """Expose actionable recovery conditions without disclosing payloads or credentials."""
        with self._lock:
            rows = self._connection().execute('SELECT state,COUNT(*) FROM sync_outbox WHERE endpoint=? AND user_id=? '
                                              'GROUP BY state', (self._endpoint, self._user_id)).fetchall()
            return {str(state): int(count) for state, count in rows}

    @sqlite_errors_as(ConfigSyncError)
    def drain(self, sender: Callable[[SyncOperation], int], *, cancel: Optional[threading.Event] = None,
              now: Optional[float] = None, max_attempts: int = 5) -> OutboxReport:
        """Attempt each currently due operation once; cancellation and retry limits retain data."""
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ConfigSyncError('max_attempts must be positive')
        moment = time.time() if now is None else now
        sent = conflicts = failed = 0
        with self._lock:
            conn = self._connection()
            rows = conn.execute('SELECT operation_id,payload,attempts FROM sync_outbox '
                                "WHERE endpoint=? AND user_id=? AND state='pending' AND next_at<=? ORDER BY rowid",
                                (self._endpoint, self._user_id, moment)).fetchall()
            for operation_id, payload, attempts in rows:
                if cancel is not None and cancel.is_set():
                    break
                state = self._deliver(conn, (operation_id, payload, attempts), sender, moment, max_attempts)
                sent += int(state == 'sent')
                conflicts += int(state == 'conflict')
                failed += int(state == 'failed')
            return OutboxReport(sent, len(self.pending()), conflicts, failed,
                                cancel is not None and cancel.is_set())

    def _deliver(self, conn: sqlite3.Connection, row: Tuple[str, str, int], sender: Callable[[SyncOperation], int],
                 moment: float, max_attempts: int) -> str:
        operation_id, payload, attempts = row
        state = self._send(sender, self._operation(payload))
        if state == 'sent':
            conn.execute('DELETE FROM sync_outbox WHERE endpoint=? AND user_id=? AND operation_id=?',
                         self._key(operation_id))
            return state
        count = attempts + 1
        state = 'failed' if state == 'pending' and count >= max_attempts else state
        conn.execute('UPDATE sync_outbox SET attempts=?,next_at=?,state=? '
                     'WHERE endpoint=? AND user_id=? AND operation_id=?',
                     (count, moment + min(300, 2 ** min(count, 8)), state, *self._key(operation_id)))
        return state

    @staticmethod
    def _send(sender: Callable[[SyncOperation], int], operation: SyncOperation) -> str:
        try:
            revision = validate_revision(sender(operation))
            if revision == 0:
                raise ConfigSyncError('sender did not confirm a committed revision')
        except ConfigRevisionConflict:
            return 'conflict'
        except (OSError, ConfigSyncError):
            return 'pending'
        return 'sent'

    @sqlite_errors_as(ConfigSyncError)
    def acknowledge_peer(self, peer_id: str, *, revision: int) -> None:
        """Advance a device acknowledgement without silently reactivating a retired device."""
        PeerState(peer_id, validate_revision(revision))
        with self._lock:
            self._connection().execute('INSERT INTO sync_peers(endpoint,user_id,peer_id,revision) VALUES(?,?,?,?) '
                                       'ON CONFLICT(endpoint,user_id,peer_id) DO UPDATE SET '
                                       'revision=MAX(revision,excluded.revision)', (*self._key(peer_id), revision))

    @sqlite_errors_as(ConfigSyncError)
    def retire_peer(self, peer_id: str) -> None:
        """Persist retirement so the device must obtain a full snapshot before rejoining."""
        self.acknowledge_peer(peer_id, revision=0)
        with self._lock:
            self._connection().execute('UPDATE sync_peers SET retired=1 WHERE endpoint=? AND user_id=? AND peer_id=?',
                                       self._key(peer_id))

    @sqlite_errors_as(ConfigSyncError)
    def peers(self) -> Tuple[PeerState, ...]:
        """Read the durable device acknowledgement set for this namespace."""
        with self._lock:
            rows = self._connection().execute('SELECT peer_id,revision,retired FROM sync_peers '
                                              'WHERE endpoint=? AND user_id=?',
                                              (self._endpoint, self._user_id)).fetchall()
            return tuple(PeerState(row[0], int(row[1]), bool(row[2])) for row in rows)

    def requires_full_sync(self, peer_id: str) -> bool:
        """Whether a retired device is prohibited from incremental rejoining."""
        return any(peer.peer_id == peer_id and peer.retired for peer in self.peers())

    @sqlite_errors_as(ConfigSyncError)
    def complete_full_sync(self, peer_id: str, *, revision: int) -> None:
        """Reactivate a device only after the caller confirms a complete snapshot."""
        self.acknowledge_peer(peer_id, revision=revision)
        with self._lock:
            self._connection().execute('UPDATE sync_peers SET retired=0 WHERE endpoint=? AND user_id=? AND peer_id=?',
                                       self._key(peer_id))

    @sqlite_errors_as(ConfigSyncError)
    def close(self) -> None:
        """Release the SQLite connection without discarding outstanding operations."""
        with self._lock:
            self._database.close()
