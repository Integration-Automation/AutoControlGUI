"""Durable workspace leases and pre-resync fingerprints share the outbox's atomic control-intent transaction."""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import TYPE_CHECKING, Callable, Mapping, cast
from uuid import uuid4

from je_auto_control.utils.config_sync.contract import ConfigStoreError, ConfigSyncError, _encoded, _revision
from je_auto_control.utils.config_sync.causal_merge import frontier
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.control_models import SyncControlOperation
from je_auto_control.utils.config_sync.control_store import _operation
from je_auto_control.utils.config_sync.database import SyncDatabase
from je_auto_control.utils.config_sync.outbox import _operation as _edit_operation
from je_auto_control.utils.config_sync.outbox_models import SyncOperation
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.config_sync.workspace_models import SyncWorkspaceError, validate_workspace_snapshot

if TYPE_CHECKING:
    from sqlite3 import Connection


class WorkspaceStore:
    """Fence mutating coordinators while leaving status local, bounded and free of source/credential reads."""

    def __init__(self, database: SyncDatabase, scope: tuple[str, str], clock: Callable[[], float]) -> None:
        self._database = database
        self._scope = scope
        self._clock = clock

    def _now(self) -> float:
        try:
            value = float(self._clock())
        except (ValueError, TypeError, OverflowError) as error:
            raise ConfigSyncError('workspace clock must return a finite number') from error
        if not math.isfinite(value):
            raise ConfigSyncError('workspace clock must return a finite number')
        return value

    def claim(self, bindings: Mapping[str, str], seconds: float) -> str:
        """Claim one namespace and pin adapter state bindings before any source edits or RPCs."""
        now, owner = self._now(), uuid4().hex
        with self._database.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT owner,lease_until,last_attempt FROM sync_workspace_leases '
                                     'WHERE endpoint=? AND user_id=?', self._scope).fetchone()
            if row and row[0] and row[2] <= now < row[1]:
                raise SyncWorkspaceError('another workspace operation is active', code='busy')
            _bind(connection, self._scope, bindings)
            connection.execute('INSERT INTO sync_workspace_leases '
                               '(endpoint,user_id,owner,lease_until,last_attempt) VALUES (?,?,?,?,?) '
                               'ON CONFLICT(endpoint,user_id) DO UPDATE SET owner=excluded.owner,'
                               'lease_until=excluded.lease_until,last_attempt=excluded.last_attempt',
                               (*self._scope, owner, now + seconds, now))
            connection.execute('COMMIT')
        return owner

    def check(self, owner: str) -> None:
        """Read-only checkpoints remain safe inside the control-preparation write transaction."""
        with self._database.connection() as connection:
            row = connection.execute('SELECT owner,lease_until FROM sync_workspace_leases '
                                     'WHERE endpoint=? AND user_id=?', self._scope).fetchone()
        _owned(row, owner, self._now())

    def renew(self, owner: str, seconds: float) -> None:
        """Refresh before bounded steps/RPCs without holding a database lock around network I/O."""
        now = self._now()
        with self._database.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT owner,lease_until FROM sync_workspace_leases '
                                     'WHERE endpoint=? AND user_id=?', self._scope).fetchone()
            _owned(row, owner, now)
            connection.execute('UPDATE sync_workspace_leases SET lease_until=?,last_attempt=? '
                               'WHERE endpoint=? AND user_id=? AND owner=?', (now + seconds, now, *self._scope, owner))
            connection.execute('COMMIT')

    def release(self, owner: str) -> None:
        """A stale coordinator cannot release its successor's lease."""
        with self._database.connection() as connection:
            connection.execute("UPDATE sync_workspace_leases SET owner='',lease_until=0 "
                               'WHERE endpoint=? AND user_id=? AND owner=?', (*self._scope, owner))

    def note_error(self, owner: str, code: str) -> None:
        """Retain only a fixed diagnostic code, never a network payload or credential-bearing exception."""
        with self._database.connection() as connection:
            connection.execute('UPDATE sync_workspace_leases SET error_code=? '
                               'WHERE endpoint=? AND user_id=? AND owner=?', (code, *self._scope, owner))

    def info(self) -> dict[str, object]:
        """Read bounded ownership/error metadata without a source or credential lookup."""
        with self._database.connection() as connection:
            row = connection.execute('SELECT owner,lease_until,last_attempt,error_code FROM sync_workspace_leases '
                                     'WHERE endpoint=? AND user_id=?', self._scope).fetchone()
        now = self._now()
        if row is None:
            return {'active': False, 'lease_until': 0, 'error': ''}
        return {'active': bool(row[0] and row[2] <= now < row[1]), 'lease_until': row[1], 'error': row[3]}

    def pending_control(self) -> SyncControlOperation | None:
        """Inspect the exact durable metadata intent so a coordinator never drains an unprepared reset implicitly."""
        with self._database.connection() as connection:
            row = connection.execute('SELECT wire,digest,prepared,status FROM sync_controls '
                                     'WHERE endpoint=? AND user_id=?', self._scope).fetchone()
        return _load(row[:3], self._scope) if row and row[3] != 'delivered' else None

    def pending_entries(self) -> tuple[SyncEntry, ...]:
        """Read a bounded frontier of every pending edit, so restart/import cannot fork unseen local actor counters."""
        groups: dict[tuple[str, str], tuple[SyncEntry, ...]] = {}
        size = 0
        with self._database.connection() as connection:
            identity = connection.execute('SELECT origin,epoch FROM sync_namespaces WHERE endpoint=? AND user_id=?',
                                          self._scope).fetchone()
            rows = connection.execute("SELECT wire,digest,NULL FROM sync_operations WHERE endpoint=? AND user_id=? "
                                      "AND status NOT IN ('delivered','retired') ORDER BY sequence", self._scope)
            for row in rows:
                operation = _load_edit(row)
                if (operation.endpoint, operation.user_id) != self._scope or identity != (
                        operation.origin, operation.epoch):
                    raise ConfigStoreError('pending workspace edit belongs to another namespace or generation')
                size += _add_pending(groups, operation)
                if size > 16 * 1024 * 1024:
                    raise SyncWorkspaceError('pending workspace frontier exceeds its bound', code='invalid_pending')
        return tuple(item for values in groups.values() for item in values)

    def latest_reset(self) -> tuple[SyncControlOperation, int] | None:
        """Find the latest completed reset across later ack/control receipts, including pre-workspace databases."""
        with self._database.connection() as connection:
            row = connection.execute('SELECT wire,digest,revision FROM sync_control_receipts '
                                     'WHERE endpoint=? AND user_id=? AND instr(wire,?)>0 ORDER BY rowid DESC LIMIT 1',
                                     (*self._scope, '"kind":"full_resync"')).fetchone()
        if row is None:
            return None
        operation = _load((row[0], row[1], None), self._scope)
        _revision(row[2])
        if operation.kind != 'full_resync' or row[2] == 0:
            raise ConfigStoreError('invalid completed workspace reset receipt')
        return operation, row[2]

    def save_baseline(self, connection: Connection, operation: SyncControlOperation, kind: str,
                      configuration: str, values: Mapping[str, str]) -> None:
        """Run inside control enqueue: source fingerprints and the reset barrier commit or roll back together."""
        wire = _encoded({'sources': dict(values)}, max_bytes=16 * 1024 * 1024)
        digest = sha256(wire.encode('ascii')).hexdigest()
        connection.execute('INSERT INTO sync_workspace_baselines VALUES (?,?,?,?,?,?,?)',
                           (*self._scope, operation.operation_id, kind, configuration, wire, digest))

    def baseline(self, operation_id: str, kind: str, configuration: str) -> dict[str, str]:
        """Load sealed pre-reset fingerprints or require explicit coordinated recovery."""
        with self._database.connection() as connection:
            row = connection.execute('SELECT configuration,wire,digest FROM sync_workspace_baselines '
                                     'WHERE endpoint=? AND user_id=? AND operation_id=? AND kind=?',
                                     (*self._scope, operation_id, kind)).fetchone()
        if row is None or row[0] != configuration:
            raise SyncWorkspaceError('full resync lacks a matching prepared source baseline', code='missing_baseline')
        return _decode_baseline(row[1], row[2])


def _owned(row: tuple[object, ...] | None, owner: str, now: float) -> None:
    if row is None or row[0] != owner or cast(float, row[1]) <= now:
        raise SyncWorkspaceError('workspace operation lost its lease', code='lease_lost')


def _bind(connection: Connection, scope: tuple[str, str], bindings: Mapping[str, str]) -> None:
    for kind, binding in bindings.items():
        row = connection.execute('SELECT binding FROM sync_workspace_bindings '
                                 'WHERE endpoint=? AND user_id=? AND kind=?', (*scope, kind)).fetchone()
        if row is not None and row[0] != binding:
            raise SyncWorkspaceError('workspace kind is already bound to another adapter state',
                                     code='configuration_changed')
        connection.execute('INSERT OR IGNORE INTO sync_workspace_bindings VALUES (?,?,?,?)', (*scope, kind, binding))


def _load(row: tuple[object, ...], scope: tuple[str, str]) -> SyncControlOperation:
    try:
        operation = _operation(row)
    except (UnicodeError, ValueError, TypeError, RecursionError, ConfigSyncError) as error:
        raise ConfigStoreError('invalid workspace control evidence') from error
    if (operation.identity.endpoint, operation.identity.user_id) != scope:
        raise ConfigStoreError('workspace control evidence belongs to another namespace')
    return operation


def _decode_baseline(wire: str, digest: str) -> dict[str, str]:
    if not isinstance(wire, str) or not wire.isascii() or len(wire) > 16 * 1024 * 1024:
        raise ConfigStoreError('invalid workspace baseline wire')
    if sha256(wire.encode('ascii')).hexdigest() != digest:
        raise ConfigStoreError('workspace baseline integrity failed')
    try:
        body = json.loads(wire)
        values = _baseline_values(body)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ConfigStoreError('invalid workspace source fingerprints') from error
    return values


def _baseline_values(body: object) -> dict[str, str]:
    if not isinstance(body, dict) or set(body) != {'sources'}:
        raise ValueError('invalid source fingerprint fields')
    values = body['sources']
    if not isinstance(values, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in values.items()):
        raise ValueError('invalid source fingerprint map')
    return values


def _load_edit(row: tuple[object, ...]) -> SyncOperation:
    try:
        return _edit_operation(row)
    except ConfigSyncError as error:
        raise SyncWorkspaceError('queued workspace edit violates portable boundaries',
                                 code='invalid_pending') from error
    except UnicodeError as error:
        raise ConfigStoreError('invalid workspace edit evidence') from error


def _add_pending(groups: dict[tuple[str, str], tuple[SyncEntry, ...]], operation: SyncOperation) -> int:
    validate_workspace_snapshot(CausalBucket(operation.user_id, entries=operation.entries))
    delta = 0
    for entry in operation.entries:
        previous = groups.get(entry.key, ())
        values = cast(tuple[SyncEntry, ...], frontier((*previous, entry)))
        if len(values) > 128:
            raise SyncWorkspaceError('pending workspace frontier exceeds its bound', code='invalid_pending')
        delta += sum(len(_encoded(item.to_dict())) for item in values)
        delta -= sum(len(_encoded(item.to_dict())) for item in previous)
        groups[entry.key] = values
    return delta
