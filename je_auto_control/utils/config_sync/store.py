"""Persistent config buckets with atomic revision checks and operation deduplication."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, Union

from je_auto_control.utils.sqlite_support import SQLITE_ERRORS, require_sqlite3, sqlite_errors_as
from .client import ConfigBucket, ConfigSyncError

if TYPE_CHECKING:
    import sqlite3

StorePath = Union[str, Path, Callable[[], Path]]
_SCHEMA = """
CREATE TABLE IF NOT EXISTS config_buckets (
    user_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS config_operations (
    user_id TEXT NOT NULL, operation_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL, revision INTEGER NOT NULL,
    PRIMARY KEY (user_id, operation_id)
);
"""


class ConfigRevisionConflict(ConfigSyncError):
    """A write used a server revision superseded by another operation."""


class ConfigStoreCapacityError(ConfigSyncError):
    """Creating another account would exceed the configured bucket limit."""


def default_config_store_path() -> Path:
    """Resolve the host-owned database override or per-user default on first use."""
    override = os.environ.get('AC_CONFIG_STORE_PATH')
    return Path(override) if override else Path.home() / '.je_auto_control' / 'config_sync.sqlite'


def validate_revision(value: object) -> int:
    """Require a nonnegative SQLite integer without coercing floats or booleans."""
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < 2 ** 63 - 1:
        raise ConfigSyncError('base_revision must be a nonnegative integer')
    return value


def validate_operation_id(value: object) -> str:
    """Require a bounded printable operation identifier for stable retries."""
    if not isinstance(value, str) or not value or len(value) > 128 or not value.isprintable():
        raise ConfigSyncError('operation_id must be a printable string of 1-128 characters')
    return value


def _payload(user_id: str, bucket: ConfigBucket) -> str:
    if not user_id or len(user_id) > 128 or not user_id.isprintable() or '/' in user_id:
        raise ConfigSyncError('invalid user_id')
    if bucket.user_id != user_id:
        raise ConfigSyncError('bucket user_id mismatch')
    # Claimed bucket revision is not server state and is excluded from retry identity.
    body = bucket.to_dict()
    body['revision'] = 0
    ConfigBucket.from_dict(body)
    try:
        return json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ConfigSyncError('bucket must contain finite JSON data') from error


class ConfigStore:
    """Lazy SQLite store safe across threads and independent server processes.

    CAS, account-cap checks, writes and retry receipts share BEGIN IMMEDIATE.
    An idempotent retry returns its original revision even after later writes.
    """

    def __init__(self, path: StorePath = default_config_store_path, *, max_users: int = 1024) -> None:
        if not isinstance(max_users, int) or isinstance(max_users, bool) or max_users < 1:
            raise ConfigSyncError('max_users must be a positive integer')
        self._path_source = path
        self._resolved_path: Optional[str] = None
        self._max_users = max_users
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if self._resolved_path is None:
            source = self._path_source() if callable(self._path_source) else self._path_source
            self._resolved_path = str(source)
        if self._resolved_path != ':memory:':
            Path(self._resolved_path).parent.mkdir(parents=True, exist_ok=True)
        conn = require_sqlite3().connect(self._resolved_path, isolation_level=None, check_same_thread=False)
        try:
            conn.executescript(_SCHEMA)
        except SQLITE_ERRORS:
            conn.close()
            raise
        self._conn = conn
        return conn

    @sqlite_errors_as(ConfigSyncError)
    def get(self, user_id: str) -> Optional[ConfigBucket]:
        """Read a fresh bucket with the committed revision, or None for an unknown account."""
        with self._lock:
            row = self._connection().execute(
                'SELECT revision, payload FROM config_buckets WHERE user_id=?', (user_id,)).fetchone()
            if row is None:
                return None
            try:
                bucket = ConfigBucket.from_dict(json.loads(row[1]))
            except (ValueError, TypeError) as error:
                raise ConfigSyncError('stored config payload is invalid') from error
            bucket.revision = int(row[0])
            return bucket

    def commit(self, user_id: str, bucket: ConfigBucket, *, base_revision: int, operation_id: str) -> int:
        """Atomically commit if base_revision matches, or return an identical retry receipt."""
        return self._commit(user_id, bucket, validate_revision(base_revision), validate_operation_id(operation_id))

    def commit_legacy(self, user_id: str, bucket: ConfigBucket) -> int:
        """Explicit compatibility write using the current revision inside the transaction."""
        # This method is intentionally separate from the protected commit interface.
        return self._commit(user_id, bucket, None, uuid.uuid4().hex)

    @sqlite_errors_as(ConfigSyncError)
    def _commit(self, user_id: str, bucket: ConfigBucket, base: Optional[int], operation: str) -> int:
        payload = _payload(user_id, bucket)
        fingerprint = hashlib.sha256(f'{base}:{payload}'.encode('utf-8')).hexdigest()
        with self._lock:
            conn = self._connection()
            conn.execute('BEGIN IMMEDIATE')
            try:
                revision = self._write(conn, user_id, payload, base, operation, fingerprint)
                conn.commit()
                return revision
            finally:
                if conn.in_transaction:
                    conn.rollback()

    def _write(self, conn: sqlite3.Connection, user_id: str, payload: str,
               base: Optional[int], operation: str, fingerprint: str) -> int:
        receipt = conn.execute('SELECT fingerprint, revision FROM config_operations '
                               'WHERE user_id=? AND operation_id=?', (user_id, operation)).fetchone()
        if receipt is not None:
            if receipt[0] != fingerprint:
                raise ConfigSyncError('operation_id was reused for a different write')
            return int(receipt[1])
        row = conn.execute('SELECT revision FROM config_buckets WHERE user_id=?', (user_id,)).fetchone()
        current = int(row[0]) if row is not None else 0
        if base is not None and base != current:
            raise ConfigRevisionConflict('base_revision does not match the committed revision')
        if row is None:
            count = conn.execute('SELECT COUNT(*) FROM config_buckets').fetchone()[0]
            if count >= self._max_users:
                raise ConfigStoreCapacityError('too many users')
        revision = current + 1
        validate_revision(revision)
        conn.execute('INSERT INTO config_buckets VALUES (?,?,?) ON CONFLICT(user_id) '
                     'DO UPDATE SET revision=excluded.revision, payload=excluded.payload', (user_id, revision, payload))
        conn.execute('INSERT INTO config_operations VALUES (?,?,?,?)', (user_id, operation, fingerprint, revision))
        return revision

    @sqlite_errors_as(ConfigSyncError)
    def close(self) -> None:
        """Release the connection; a subsequent operation reopens the same resolved path."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
