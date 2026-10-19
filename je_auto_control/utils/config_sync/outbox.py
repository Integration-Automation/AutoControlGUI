"""Durable account/endpoint-scoped edits with leased, bounded and cancellable retry delivery."""
from __future__ import annotations

import json
import math
import time
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, cast
from uuid import uuid4

from je_auto_control.utils.config_sync.contract import (
    ConfigRevisionConflict, ConfigStoreError, ConfigSyncError, _encoded, _identifier, _revision,
)
from je_auto_control.utils.config_sync.database import SyncDatabase
from je_auto_control.utils.config_sync.causal_receipt import CausalReceipt, _server_snapshot
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.outbox_models import (
    SyncDrainResult, SyncLocalIdentity, SyncOperation, SyncRetryPolicy, normalize_sync_endpoint,
)
from je_auto_control.utils.config_sync.outbox_schema import initialize_outbox
from je_auto_control.utils.config_sync.peers import FullResyncRequired
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption as _raise_interruption

if TYPE_CHECKING:
    from sqlite3 import Connection

_Scope = tuple[str, str]
_Key = tuple[str, str, str]
_Clock = Callable[[], float]
_Sender = Callable[[SyncOperation], int | CausalReceipt]
_Cancelled = Optional[Callable[[], bool]]
_SELECT = "SELECT wire, digest, prepared FROM sync_operations WHERE endpoint = ? AND user_id = ? AND operation_id = ?"


def _scope(endpoint: str, user_id: str) -> _Scope:
    _identifier(user_id, "user_id")
    return normalize_sync_endpoint(endpoint), user_id


def _logical(operation: SyncOperation) -> tuple[str, str]:
    body = operation.to_dict()
    body["prepared"] = None
    wire = _encoded(body, max_bytes=2 * 1024 * 1024)
    return wire, sha256(wire.encode("ascii")).hexdigest()


def _operation(row: tuple[object, ...]) -> SyncOperation:
    wire, digest, prepared = cast(tuple[str, str, Optional[str]], row)
    if len(wire) > 2 * 1024 * 1024 or sha256(wire.encode("ascii")).hexdigest() != digest:
        raise ConfigStoreError("sync outbox operation integrity failed")
    try:
        value = SyncOperation.from_dict(json.loads(wire))
        return replace(value, prepared=json.loads(prepared)) if prepared is not None else value
    except (ValueError, TypeError, RecursionError):
        raise ConfigStoreError("invalid durable sync operation") from None


class SyncOutbox:
    """Keep logical edits and exact prepared requests across restart without persisting client credentials.

    Drains own short leases rather than holding SQLite locks around callbacks.
    Failed attempts remain pending/offline; a later drain may retry the same ID.
    At-least-once sinks must honor operation identity; the causal HTTP sender uses
    the durable prepared request and server receipts for that purpose.
    """

    def __init__(self, path: Optional[str | Path] = None, *, clock: _Clock = time.time) -> None:
        self._database = SyncDatabase(path, "AUTOCONTROL_SYNC_OUTBOX", "config-outbox.sqlite3", initialize_outbox)
        self._clock = clock

    def _now(self) -> float:
        try:
            value = float(self._clock())
        except (TypeError, ValueError, OverflowError):
            raise ConfigSyncError("outbox clock must return a finite number") from None
        if not math.isfinite(value):
            raise ConfigSyncError("outbox clock must return a finite number")
        return value

    def identity(self, endpoint: str, user_id: str, *, origin: Optional[str] = None,
                    epoch: Optional[int] = None) -> SyncLocalIdentity:
        """Load/create a stable local origin for precisely one canonical endpoint/account."""
        scope = _scope(endpoint, user_id)
        if origin is not None:
            _identifier(origin, "origin")
        if epoch is not None:
            _revision(epoch)
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT OR IGNORE INTO sync_namespaces (endpoint,user_id,origin,epoch) VALUES (?,?,?,?)",
                               (*scope, origin or uuid4().hex, epoch or 0))
            row = connection.execute("SELECT origin,epoch,confirmed_revision FROM sync_namespaces "
                                     "WHERE endpoint = ? AND user_id = ?", scope).fetchone()
            if origin is not None and row[0] != origin:
                raise ConfigSyncError("outbox namespace already belongs to another origin")
            if epoch is not None and row[1] != epoch:
                raise FullResyncRequired("operation belongs to an obsolete local peer epoch")
            connection.execute("COMMIT")
        return SyncLocalIdentity(*scope, row[0], row[1], row[2])

    def enqueue(self, operation: SyncOperation) -> None:
        """Persist once by namespace/ID; duplicate equal input is idempotent, changed input is refused."""
        wire, digest = _logical(operation)
        self.identity(operation.endpoint, operation.user_id, origin=operation.origin, epoch=operation.epoch)
        key = operation.endpoint, operation.user_id, operation.operation_id
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT digest FROM sync_operations WHERE endpoint = ? "
                                     "AND user_id = ? AND operation_id = ?", key).fetchone()
            if row is not None and row[0] != digest:
                raise ConfigSyncError("operation_id already identifies different queued data")
            if row is None:
                pending = connection.execute("SELECT count(*) FROM sync_operations WHERE endpoint = ? AND user_id = ? "
                                             "AND status NOT IN ('delivered','retired')", key[:2]).fetchone()[0]
                if pending >= 10000:
                    raise ConfigSyncError("outbox namespace exceeds 10000 pending edits")
                prepared = _encoded(operation.prepared) if operation.prepared is not None else None
                connection.execute("INSERT INTO sync_operations "
                                   "(endpoint,user_id,operation_id,wire,digest,prepared) VALUES (?,?,?,?,?,?)",
                                   (*key, wire, digest, prepared))
            connection.execute("COMMIT")

    def pending(self, *, endpoint: str, user_id: str, limit: int = 1000) -> tuple[SyncOperation, ...]:
        """Read a bounded prefix in enqueue order; status reports the full count even when this view is truncated."""
        _revision(limit)
        if not 1 <= limit <= 1000:
            raise ConfigSyncError("pending view limit must be 1–1000")
        scope = _scope(endpoint, user_id)
        values: list[SyncOperation] = []
        size = 0
        with self._database.connection() as connection:
            rows = connection.execute("SELECT wire,digest,prepared FROM sync_operations WHERE endpoint = ? "
                                      "AND user_id = ? AND status NOT IN ('delivered','retired') "
                                      "ORDER BY sequence LIMIT ?", (*scope, limit))
            for row in rows:
                size += len(row[0]) + len(row[2] or "")
                if size > 16 * 1024 * 1024:
                    if not values:
                        raise ConfigStoreError("oversized persisted outbox operation")
                    break
                values.append(_operation(row))
        return tuple(values)

    def status(self, *, endpoint: str, user_id: str) -> dict[str, object]:
        """Read aggregate queue state and bounded sanitized error previews without loading payload history."""
        scope = _scope(endpoint, user_id)
        with self._database.connection() as connection:
            connection.execute("BEGIN")
            rows = connection.execute("SELECT status,count(*) FROM sync_operations WHERE endpoint=? AND user_id=? "
                                      "GROUP BY status", scope).fetchall()
            totals = {name: int(count) for name, count in rows}
            local = connection.execute("SELECT origin,epoch,confirmed_revision FROM sync_namespaces "
                                       "WHERE endpoint=? AND user_id=?", scope).fetchone()
            due = connection.execute("SELECT min(next_attempt),sum(attempts) FROM sync_operations "
                                     "WHERE endpoint=? AND user_id=? AND status IN ('pending','offline','sending')",
                                     scope).fetchone()
            errors = connection.execute("SELECT error FROM sync_operations WHERE endpoint=? AND user_id=? "
                                        "AND error != '' ORDER BY sequence DESC LIMIT 10", scope).fetchall()
            connection.execute("COMMIT")
        pending = sum(count for name, count in totals.items() if name not in {"delivered", "retired"})
        result: dict[str, object] = {"endpoint": scope[0], "user_id": scope[1], "pending": pending,
                                     "origin": local[0] if local else None, "epoch": local[1] if local else 0,
                                     "confirmed_revision": local[2] if local else 0,
                                     "next_attempt": due[0], "attempts": due[1] or 0,
                                     "errors": [scrub_secret_text(row[0]) for row in errors]}
        for name in ("offline", "conflict", "blocked", "sending", "delivered", "retired"):
            result[name] = totals.get(name, 0)
        result["queued"] = totals.get("pending", 0)
        return result

    def prepare(self, operation: SyncOperation, *, base_revision: int, bucket: dict[str, object]) -> SyncOperation:
        """Durably freeze a request before sending; replacing an uncertain request is forbidden."""
        prepared = {"base_revision": base_revision, "bucket": bucket}
        candidate = replace(operation, prepared=prepared)
        encoded = _encoded(prepared)
        key = operation.endpoint, operation.user_id, operation.operation_id
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(_SELECT, key).fetchone()
            if row is None or _logical(_operation(row))[1] != _logical(operation)[1]:
                raise ConfigSyncError("cannot prepare an unknown or changed operation")
            if row[2] is not None and row[2] != encoded:
                raise ConfigSyncError("prepared request cannot change before an explicit rejection")
            connection.execute("UPDATE sync_operations SET prepared = ? WHERE endpoint = ? "
                               "AND user_id = ? AND operation_id = ?", (encoded, *key))
            connection.execute("COMMIT")
        return candidate

    def reject_prepared(self, operation: SyncOperation, *, rejected_base: int) -> None:
        """Clear a frozen request only after a definite stale-base rejection, retaining its logical edit."""
        _revision(rejected_base)
        key = operation.endpoint, operation.user_id, operation.operation_id
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(_SELECT, key).fetchone()
            if row is None or _logical(_operation(row))[1] != _logical(operation)[1]:
                raise ConfigSyncError("unknown or changed queued operation")
            prepared = _operation(row).prepared
            if prepared is None or prepared["base_revision"] != rejected_base:
                raise ConfigSyncError("rejected base does not identify the frozen request")
            connection.execute("UPDATE sync_operations SET prepared = NULL WHERE endpoint = ? "
                               "AND user_id = ? AND operation_id = ?", key)
            connection.execute("COMMIT")

    def snapshot(self, *, endpoint: str, user_id: str) -> Optional[CausalBucket]:
        """Read the latest complete server snapshot durably confirmed by a current delivery lease owner."""
        scope = _scope(endpoint, user_id)
        with self._database.connection() as connection:
            row = connection.execute("SELECT snapshot FROM sync_namespaces WHERE endpoint=? AND user_id=?",
                                     scope).fetchone()
        if row is None or row[0] is None:
            return None
        result = _server_snapshot(CausalBucket.from_dict(json.loads(row[0])))
        if result.user_id != user_id:
            raise ConfigStoreError("outbox snapshot belongs to another account")
        return result

    def flush(self, sender: _Sender, *, endpoint: str, user_id: str,
                 policy: Optional[SyncRetryPolicy] = None, cancelled: _Cancelled = None) -> SyncDrainResult:
        """Attempt bounded due work; backoff is persisted without sleeping and cancellation never discards edits."""
        policy = policy or SyncRetryPolicy()
        operations = self.pending(endpoint=endpoint, user_id=user_id, limit=policy.max_batch)
        delivered, failed, stopped = 0, 0, False
        for operation in operations:
            owner = uuid4().hex
            result = self._attempt(operation, sender, policy, owner, cancelled)
            delivered += result[0]
            failed += result[1]
            if result[2]:
                stopped = True
                break
        count = cast(int, self.status(endpoint=endpoint, user_id=user_id)["pending"])
        return SyncDrainResult(delivered, count, failed, stopped)

    def _attempt(self, operation: SyncOperation, sender: _Sender, policy: SyncRetryPolicy,
                    owner: str, cancelled: _Cancelled) -> tuple[int, int, bool]:
        failed = 0
        key = operation.endpoint, operation.user_id, operation.operation_id
        for _ in range(policy.max_attempts):
            if cancelled is not None and cancelled():
                return 0, failed, True
            claimed = self._claim(key, owner, policy)
            if claimed is None:
                break
            try:
                if cancelled is not None and cancelled():
                    return 0, failed, True
                receipt = sender(claimed)
                revision = receipt.revision if isinstance(receipt, CausalReceipt) else receipt
                _revision(revision)
                if revision == 0:
                    raise ConfigSyncError("delivery receipt must be a positive revision")
                return int(self._delivered(key, owner, receipt)), failed, False
            except (OSError, ConfigSyncError, ConfigStoreError, ConfigRevisionConflict, FullResyncRequired) as error:
                _raise_interruption(error)
                self._failed(key, owner, error, policy)
                failed += 1
            finally:
                self._release(key, owner)
        return 0, failed, False

    def _claim(self, key: _Key, owner: str, policy: SyncRetryPolicy) -> Optional[SyncOperation]:
        now = self._now()
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status,next_attempt,last_attempt,lease_owner,lease_until "
                                     "FROM sync_operations WHERE endpoint = ? AND user_id = ? AND operation_id = ?",
                                     key).fetchone()
            if row is None or not _due(row, now):
                connection.execute("COMMIT")
                return None
            connection.execute("UPDATE sync_operations SET status='sending', attempts=attempts+1, "
                               "last_attempt=?,lease_owner=?,lease_until=? WHERE endpoint=? AND user_id=? "
                               "AND operation_id=?", (now, owner, now + policy.lease_seconds, *key))
            value = _operation(connection.execute(_SELECT, key).fetchone())
            connection.execute("COMMIT")
            return value

    def _delivered(self, key: _Key, owner: str, receipt: int | CausalReceipt) -> bool:
        revision = receipt.revision if isinstance(receipt, CausalReceipt) else receipt
        snapshot = _receipt_snapshot(receipt, key[1])
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute("UPDATE sync_operations SET status='delivered',delivered_revision=?, "
                                         "error='',lease_owner='',lease_until=0 WHERE endpoint=? AND user_id=? "
                                         "AND operation_id=? AND lease_owner=?", (revision, *key, owner)).rowcount
            if changed:
                self._save_snapshot(connection, key[:2], snapshot)
                connection.execute("UPDATE sync_namespaces SET confirmed_revision=max(confirmed_revision,?) "
                                   "WHERE endpoint=? AND user_id=?", (revision, *key[:2]))
            connection.execute("COMMIT")
            return bool(changed)

    @staticmethod
    def _save_snapshot(connection: Connection, scope: _Scope, snapshot: Optional[CausalBucket]) -> None:
        if snapshot is None:
            return
        row = connection.execute("SELECT snapshot FROM sync_namespaces WHERE endpoint=? AND user_id=?",
                                 scope).fetchone()
        previous = CausalBucket.from_dict(json.loads(row[0])) if row and row[0] else None
        if previous is not None and snapshot.revision == previous.revision:
            if _encoded(snapshot.to_dict()) != _encoded(previous.to_dict()):
                raise ConfigSyncError("server snapshot fork at an already confirmed revision")
        if previous is None or snapshot.revision >= previous.revision:
            connection.execute("UPDATE sync_namespaces SET snapshot=? WHERE endpoint=? AND user_id=?",
                               (_encoded(snapshot.to_dict()), *scope))

    def _failed(self, key: _Key, owner: str, error: Exception, policy: SyncRetryPolicy) -> None:
        status = ("blocked" if isinstance(error, FullResyncRequired) else
                  "conflict" if isinstance(error, ConfigRevisionConflict) else "offline")
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT attempts FROM sync_operations WHERE endpoint=? AND user_id=? "
                                     "AND operation_id=? AND lease_owner=?", (*key, owner)).fetchone()
            if row is not None:
                delay = min(policy.max_delay, policy.backoff * 2 ** min(row[0] - 1, 16))
                connection.execute("UPDATE sync_operations SET status=?,next_attempt=?,error=?,lease_owner='', "
                                   "lease_until=0 WHERE endpoint=? AND user_id=? AND operation_id=? AND lease_owner=?",
                                   (status, self._now() + delay, scrub_secret_text(str(error))[:2048], *key, owner))
            connection.execute("COMMIT")

    def _release(self, key: _Key, owner: str) -> None:
        with self._database.connection() as connection:
            connection.execute("UPDATE sync_operations SET status=CASE WHEN status='sending' THEN 'pending' "
                               "ELSE status END,lease_owner='',lease_until=0 WHERE endpoint=? AND user_id=? "
                               "AND operation_id=? AND lease_owner=?", (*key, owner))


def _due(row: tuple[object, ...], now: float) -> bool:
    status, next_attempt, last_attempt, owner, lease_until = row
    if status not in {"pending", "offline", "sending"}:
        return False
    if cast(float, last_attempt) <= now:
        if owner and cast(float, lease_until) > now:
            return False
        if cast(float, next_attempt) > now:
            return False
    return True


def _receipt_snapshot(receipt: int | CausalReceipt, user_id: str) -> Optional[CausalBucket]:
    if not isinstance(receipt, CausalReceipt):
        return None
    snapshot = _server_snapshot(receipt.snapshot)
    if snapshot.user_id != user_id:
        raise ConfigSyncError("delivery receipt snapshot belongs to another account")
    return snapshot
