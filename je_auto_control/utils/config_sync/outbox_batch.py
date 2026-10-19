"""Atomically enqueue a bounded namespace batch while checking current generation and pending resync barriers."""
from __future__ import annotations

from hashlib import sha256
from itertools import islice
from typing import TYPE_CHECKING, Iterable

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.database import SyncDatabase
from je_auto_control.utils.config_sync.outbox_models import SyncOperation
from je_auto_control.utils.config_sync.peers import FullResyncRequired

if TYPE_CHECKING:
    from sqlite3 import Connection


def logical_operation(operation: SyncOperation) -> tuple[str, str]:
    """Seal only the logical edit; a prepared request remains a separately frozen transport artifact."""
    body = operation.to_dict()
    body['prepared'] = None
    wire = _encoded(body, max_bytes=2 * 1024 * 1024)
    return wire, sha256(wire.encode('ascii')).hexdigest()


def enqueue_batch(database: SyncDatabase, operations: Iterable[SyncOperation]) -> int:
    """Validate the complete batch before I/O and commit all new rows or none; equal retries insert nothing."""
    prepared = _prepare(operations)
    if not prepared:
        return 0
    first = prepared[0][0]
    with database.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        _namespace(connection, first)
        new = _new_rows(connection, prepared)
        scope = first.endpoint, first.user_id
        if new:
            _admit(connection, scope, len(new))
            for operation, wire, digest, request in new:
                connection.execute('INSERT INTO sync_operations '
                                   '(endpoint,user_id,operation_id,wire,digest,prepared) VALUES (?,?,?,?,?,?)',
                                   (*scope, operation.operation_id, wire, digest, request))
        connection.execute('COMMIT')
    return len(new)


def _prepare(operations: Iterable[SyncOperation]) -> list[tuple[SyncOperation, str, str, str | None]]:
    selected = tuple(islice(operations, 10001))
    if len(selected) > 10000:
        raise ConfigSyncError('outbox batch exceeds 10000 operations')
    result = []
    size = 0
    namespace = None
    identifiers: set[str] = set()
    for operation in selected:
        if not isinstance(operation, SyncOperation):
            raise ConfigSyncError('outbox batch requires sealed sync operations')
        operation = SyncOperation.from_dict(operation.to_dict())
        current = operation.endpoint, operation.user_id, operation.origin, operation.epoch
        namespace = current if namespace is None else namespace
        if current != namespace or operation.operation_id in identifiers:
            raise ConfigSyncError('outbox batch requires one generation and distinct operation IDs')
        identifiers.add(operation.operation_id)
        wire, digest = logical_operation(operation)
        request = _encoded(operation.prepared) if operation.prepared is not None else None
        size += len(wire) + (len(request) if request is not None else 0)
        if size > 16 * 1024 * 1024:
            raise ConfigSyncError('outbox batch exceeds sixteen MiB')
        result.append((operation, wire, digest, request))
    return result


def _namespace(connection: Connection, operation: SyncOperation) -> None:
    scope = operation.endpoint, operation.user_id
    connection.execute('INSERT OR IGNORE INTO sync_namespaces (endpoint,user_id,origin,epoch) VALUES (?,?,?,?)',
                       (*scope, operation.origin, operation.epoch))
    row = connection.execute('SELECT origin,epoch FROM sync_namespaces WHERE endpoint=? AND user_id=?',
                             scope).fetchone()
    if row[0] != operation.origin:
        raise ConfigSyncError('outbox namespace already belongs to another origin')
    if row[1] != operation.epoch:
        raise FullResyncRequired('operation belongs to an obsolete local peer epoch')


def _new_rows(connection: Connection, rows: list[tuple[SyncOperation, str, str, str | None]]
              ) -> list[tuple[SyncOperation, str, str, str | None]]:
    result = []
    for operation, wire, digest, prepared in rows:
        key = operation.endpoint, operation.user_id, operation.operation_id
        row = connection.execute('SELECT digest FROM sync_operations WHERE endpoint=? AND user_id=? AND operation_id=?',
                                 key).fetchone()
        if row is None:
            result.append((operation, wire, digest, prepared))
        elif row[0] != digest:
            raise ConfigSyncError('operation_id already identifies different queued data')
    return result


def _admit(connection: Connection, scope: tuple[str, str], count: int) -> None:
    control = connection.execute("SELECT 1 FROM sync_controls WHERE endpoint=? AND user_id=? "
                                 "AND kind='full_resync' AND status!='delivered'", scope).fetchone()
    if control is not None:
        raise FullResyncRequired('local full resync must complete before new edits are captured')
    pending = connection.execute("SELECT count(*) FROM sync_operations WHERE endpoint=? AND user_id=? "
                                 "AND status NOT IN ('delivered','retired')", scope).fetchone()[0]
    if pending + count > 10000:
        raise ConfigSyncError('outbox namespace exceeds 10000 pending edits')
