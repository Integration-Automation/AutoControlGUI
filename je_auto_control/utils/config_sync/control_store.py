"""Durable singleton peer controls share the edit outbox database and short lease ownership."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from typing import TYPE_CHECKING, Callable, Optional, cast
from uuid import uuid4

from je_auto_control.utils.config_sync.causal_receipt import CausalReceipt
from je_auto_control.utils.config_sync.contract import (
    ConfigRevisionConflict, ConfigStoreError, ConfigSyncError, _encoded,
)
from je_auto_control.utils.config_sync.control_adoption import SnapshotSaver, apply_control_receipt
from je_auto_control.utils.config_sync.control_models import ControlKind, SyncControlOperation
from je_auto_control.utils.config_sync.database import SyncDatabase
from je_auto_control.utils.config_sync.outbox_lease import due
from je_auto_control.utils.config_sync.outbox_models import SyncLocalIdentity, SyncRetryPolicy
from je_auto_control.utils.config_sync.peers import FullResyncRequired
from je_auto_control.utils.logging.secret_scope import scrub_secret_text

if TYPE_CHECKING:
    from sqlite3 import Connection

_SELECT = "SELECT wire,digest,prepared FROM sync_controls WHERE endpoint=? AND user_id=?"
_Scope = tuple[str, str]


def _logical(operation: SyncControlOperation) -> tuple[str, str]:
    body = operation.to_dict()
    body["prepared"] = None
    wire = _encoded(body)
    return wire, sha256(wire.encode("ascii")).hexdigest()


def _operation(row: tuple[object, ...]) -> SyncControlOperation:
    wire, digest, prepared = cast(tuple[str, str, Optional[str]], row)
    if len(wire) > 2 * 1024 * 1024 or sha256(wire.encode("ascii")).hexdigest() != digest:
        raise ConfigStoreError("peer-control integrity failed")
    try:
        operation = SyncControlOperation.from_dict(json.loads(wire))
        return replace(operation, prepared=json.loads(prepared)) if prepared is not None else operation
    except (ValueError, TypeError, RecursionError):
        raise ConfigStoreError("invalid durable peer control") from None


class ControlStore:
    """One outstanding control per endpoint/account, with idempotent recovery and atomic generation adoption."""

    def __init__(self, database: SyncDatabase, clock: Callable[[], float], save_snapshot: SnapshotSaver) -> None:
        self._database = database
        self._clock = clock
        self._save_snapshot = save_snapshot

    def enqueue(self, identity: SyncLocalIdentity, kind: ControlKind, *, peer_id: Optional[str] = None,
                 discard_pending: bool = False, operation_id: Optional[str] = None,
                 prepare: Optional[Callable[[Connection, SyncControlOperation], None]] = None) -> SyncControlOperation:
        """Persist a control intent once; a matching open intent is resumed instead of creating another request ID."""
        candidate = SyncControlOperation(uuid4().hex if operation_id is None else operation_id,
                                          identity, kind, peer_id, discard_pending)
        scope = identity.endpoint, identity.user_id
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            historical = _historical(connection, candidate)
            if historical is not None:
                connection.execute("COMMIT")
                return historical
            _local_generation(connection, identity)
            previous = _resumable(connection, candidate, operation_id is not None)
            if previous is not None:
                connection.execute("COMMIT")
                return previous
            _retirement_consent(connection, candidate)
            if prepare is not None:
                prepare(connection, candidate)
            wire, digest = _logical(candidate)
            connection.execute("DELETE FROM sync_controls WHERE endpoint=? AND user_id=?", scope)
            connection.execute("INSERT INTO sync_controls (endpoint,user_id,operation_id,kind,wire,digest) "
                               "VALUES (?,?,?,?,?,?)", (*scope, candidate.operation_id, kind, wire, digest))
            connection.execute("COMMIT")
        return candidate

    def receipt(self, scope: _Scope, operation_id: str) -> Optional[int]:
        """Return a durable original receipt across later controls and local generation changes."""
        with self._database.connection() as connection:
            row = connection.execute("SELECT revision FROM sync_control_receipts WHERE endpoint=? AND user_id=? "
                                     "AND operation_id=?", (*scope, operation_id)).fetchone()
        return int(row[0]) if row is not None else None

    def status(self, scope: _Scope) -> dict[str, object]:
        """Return bounded metadata without exposing a prepared snapshot or live credentials."""
        with self._database.connection() as connection:
            row = connection.execute("SELECT operation_id,kind,status,attempts,next_attempt,error,receipt_revision "
                                     "FROM sync_controls WHERE endpoint=? AND user_id=?", scope).fetchone()
        if row is None:
            return {"state": "idle", "pending": 0, "operation_id": None, "kind": None, "attempts": 0,
                    "next_attempt": None, "error": "", "revision": None}
        return {"operation_id": row[0], "kind": row[1], "state": row[2], "attempts": row[3],
                "next_attempt": row[4], "error": scrub_secret_text(row[5]), "revision": row[6],
                "pending": int(row[2] != "delivered")}

    def claim(self, scope: _Scope, owner: str, policy: SyncRetryPolicy) -> Optional[SyncControlOperation]:
        """Claim due metadata work without holding a database lock around HTTP callbacks."""
        now = self._clock()
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status,next_attempt,last_attempt,lease_owner,lease_until "
                                     "FROM sync_controls WHERE endpoint=? AND user_id=?", scope).fetchone()
            if row is None or not due(row, now):
                connection.execute("COMMIT")
                return None
            connection.execute("UPDATE sync_controls SET status='sending',attempts=attempts+1,last_attempt=?,"
                               "lease_owner=?,lease_until=? WHERE endpoint=? AND user_id=?",
                               (now, owner, now + policy.lease_seconds, *scope))
            operation = _operation(connection.execute(_SELECT, scope).fetchone())
            _local_generation(connection, operation.identity)
            connection.execute("COMMIT")
        return operation

    def prepare(self, operation: SyncControlOperation, owner: str, bucket: dict[str, object]) -> SyncControlOperation:
        """Freeze a complete actor request before sending; an uncertain request cannot be overwritten."""
        prepared = {"base_revision": bucket.get("revision"), "bucket": bucket}
        candidate = replace(operation, prepared=prepared)
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = _owned(connection, operation, owner)
            if current.prepared is not None and _encoded(current.prepared) != _encoded(prepared):
                raise ConfigSyncError("uncertain peer control cannot be replaced")
            connection.execute("UPDATE sync_controls SET prepared=? WHERE endpoint=? AND user_id=?",
                               (_encoded(prepared), operation.identity.endpoint, operation.identity.user_id))
            connection.execute("COMMIT")
        return candidate

    def reject(self, operation: SyncControlOperation, owner: str) -> SyncControlOperation:
        """Clear only the current owner's definitely rejected frozen request before bounded rebasing."""
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = _owned(connection, operation, owner)
            if (current.prepared is None or operation.prepared is None
                    or _encoded(current.prepared) != _encoded(operation.prepared)):
                raise ConfigSyncError("stale rejection does not identify the frozen control")
            connection.execute("UPDATE sync_controls SET prepared=NULL WHERE endpoint=? AND user_id=?",
                               (operation.identity.endpoint, operation.identity.user_id))
            connection.execute("COMMIT")
        return replace(operation, prepared=None)

    def complete(self, operation: SyncControlOperation, owner: str, receipt: CausalReceipt) -> bool:
        """Confirm the original receipt, authoritative snapshot and any generation adoption in one transaction."""
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            scope = operation.identity.endpoint, operation.identity.user_id
            row = connection.execute("SELECT operation_id,lease_owner FROM sync_controls "
                                     "WHERE endpoint=? AND user_id=?", scope).fetchone()
            if row != (operation.operation_id, owner):
                connection.execute("COMMIT")
                return False
            current = _owned(connection, operation, owner)
            apply_control_receipt(connection, current, receipt, self._save_snapshot)
            wire, digest = _logical(current)
            connection.execute("INSERT INTO sync_control_receipts VALUES (?,?,?,?,?,?)",
                               (*scope, current.operation_id, wire, digest, receipt.revision))
            connection.execute("UPDATE sync_controls SET status='delivered',receipt_revision=?,error='',"
                               "lease_owner='',lease_until=0 WHERE endpoint=? AND user_id=?",
                               (receipt.revision, *scope))
            connection.execute("COMMIT")
        return True

    def failed(self, operation: SyncControlOperation, owner: str, error: Exception, policy: SyncRetryPolicy) -> None:
        """Persist bounded retry/error state; definite generation failures block until explicit recovery."""
        state = ("blocked" if isinstance(error, FullResyncRequired) else
                 "conflict" if isinstance(error, ConfigRevisionConflict) else "offline")
        scope = operation.identity.endpoint, operation.identity.user_id
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT attempts FROM sync_controls WHERE endpoint=? AND user_id=? "
                                     "AND operation_id=? AND lease_owner=?",
                                     (*scope, operation.operation_id, owner)).fetchone()
            if row is not None:
                delay = min(policy.max_delay, policy.backoff * 2 ** min(row[0] - 1, 16))
                connection.execute("UPDATE sync_controls SET status=?,next_attempt=?,error=?,lease_owner='',"
                                   "lease_until=0 WHERE endpoint=? AND user_id=?",
                                   (state, self._clock() + delay, scrub_secret_text(str(error))[:2048], *scope))
            connection.execute("COMMIT")

    def release(self, operation: SyncControlOperation, owner: str) -> None:
        """Release only an owned lease, retaining exact requests on cancellation or hard interruption."""
        with self._database.connection() as connection:
            connection.execute("UPDATE sync_controls SET status=CASE WHEN status='sending' "
                               "THEN 'pending' ELSE status END,"
                               "lease_owner='',lease_until=0 WHERE endpoint=? AND user_id=? AND operation_id=? "
                               "AND lease_owner=?", (operation.identity.endpoint, operation.identity.user_id,
                                                    operation.operation_id, owner))


def _owned(connection: Connection, operation: SyncControlOperation, owner: str) -> SyncControlOperation:
    scope = operation.identity.endpoint, operation.identity.user_id
    row = connection.execute("SELECT wire,digest,prepared,lease_owner FROM sync_controls "
                             "WHERE endpoint=? AND user_id=?", scope).fetchone()
    if row is None or row[3] != owner or _logical(_operation(row[:3])) != _logical(operation):
        raise ConfigStoreError("peer-control lease is no longer owned")
    return _operation(row[:3])


def _local_generation(connection: Connection, identity: SyncLocalIdentity) -> None:
    row = connection.execute("SELECT origin,epoch FROM sync_namespaces WHERE endpoint=? AND user_id=?",
                             (identity.endpoint, identity.user_id)).fetchone()
    if row != (identity.origin, identity.epoch):
        raise FullResyncRequired("peer-control belongs to an obsolete local generation")


def _retirement_consent(connection: Connection, operation: SyncControlOperation) -> None:
    if operation.kind != "full_resync" or operation.discard_pending:
        return
    count = connection.execute("SELECT count(*) FROM sync_operations WHERE endpoint=? AND user_id=? "
                               "AND status NOT IN ('delivered','retired')",
                               (operation.identity.endpoint, operation.identity.user_id)).fetchone()[0]
    if count:
        raise ConfigSyncError("full resync requires explicit discard_pending before retiring pending edits")


def _same_intent(left: SyncControlOperation, right: SyncControlOperation) -> bool:
    return (left.kind, left.peer_id, left.discard_pending) == (right.kind, right.peer_id, right.discard_pending)


def _require_same_intent(left: SyncControlOperation, right: SyncControlOperation) -> None:
    if not _same_intent(left, right):
        raise ConfigSyncError("operation_id already identifies another peer-control intent")


def _historical(connection: Connection, candidate: SyncControlOperation) -> Optional[SyncControlOperation]:
    scope = candidate.identity.endpoint, candidate.identity.user_id
    row = connection.execute("SELECT wire,digest FROM sync_control_receipts WHERE endpoint=? AND user_id=? "
                             "AND operation_id=?", (*scope, candidate.operation_id)).fetchone()
    if row is None:
        return None
    previous = _operation((*row, None))
    _require_same_intent(previous, candidate)
    return previous


def _resumable(connection: Connection, candidate: SyncControlOperation,
                explicit: bool) -> Optional[SyncControlOperation]:
    scope = candidate.identity.endpoint, candidate.identity.user_id
    row = connection.execute("SELECT wire,digest,prepared,status FROM sync_controls WHERE endpoint=? AND user_id=?",
                             scope).fetchone()
    if row is None or row[3] == "delivered":
        return None
    previous = _operation(row[:3])
    if explicit and candidate.operation_id == previous.operation_id:
        _require_same_intent(previous, candidate)
        return previous
    if _same_intent(previous, candidate) and not explicit and row[3] not in {"blocked", "conflict"}:
        return previous
    if not _recoverable(row[3], candidate.kind):
        raise ConfigSyncError("an outstanding peer control must be resumed before another kind")
    return None


def _recoverable(state: str, kind: ControlKind) -> bool:
    if state == "blocked":
        return kind in {"register", "full_resync"}
    return state == "conflict" and kind == "full_resync"
