"""Atomically adopt acknowledged peer generations and retire only explicitly abandoned old local work."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable, Optional, cast

from je_auto_control.utils.config_sync.causal_models import SyncActor
from je_auto_control.utils.config_sync.causal_receipt import CausalReceipt
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigStoreError, ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.control_models import SyncControlOperation
from je_auto_control.utils.config_sync.peers import FullResyncRequired

if TYPE_CHECKING:
    from sqlite3 import Connection

SnapshotSaver = Callable[["Connection", tuple[str, str], Optional[CausalBucket]], None]


def apply_control_receipt(connection: Connection, operation: SyncControlOperation, receipt: CausalReceipt,
                          save_snapshot: SnapshotSaver) -> None:
    """Run under the control lease/CAS transaction; failed adoption changes neither epoch nor pending edits."""
    local = operation.identity
    scope = local.endpoint, local.user_id
    row = connection.execute("SELECT origin,epoch,snapshot FROM sync_namespaces WHERE endpoint=? AND user_id=?",
                             scope).fetchone()
    if row is None:
        raise ConfigStoreError("peer-control namespace disappeared")
    if row[:2] != (local.origin, local.epoch):
        raise FullResyncRequired("control belongs to an obsolete local generation")
    if receipt.snapshot.user_id != local.user_id:
        raise ConfigSyncError("control receipt belongs to another account")
    claim = _claim(operation)
    if operation.kind in {"register", "full_resync"}:
        receipt.snapshot.peers.require_active(claim.origin, epoch=claim.epoch)
    changed = (claim.origin, claim.epoch) != row[:2]
    if changed:
        _adopt_generation(connection, operation, receipt, claim, row[2])
    else:
        save_snapshot(connection, scope, receipt.snapshot)
        connection.execute("UPDATE sync_namespaces SET confirmed_revision=max(confirmed_revision,?) "
                           "WHERE endpoint=? AND user_id=?", (receipt.revision, *scope))
        if operation.kind == "register":
            connection.execute("UPDATE sync_operations SET status='pending',next_attempt=0,error='' "
                               "WHERE endpoint=? AND user_id=? AND status='blocked'", scope)


def _claim(operation: SyncControlOperation) -> SyncActor:
    prepared = operation.prepared
    body = prepared.get("bucket") if prepared is not None else None
    raw = body.get("_actor") if isinstance(body, dict) else None
    if not isinstance(raw, dict):
        raise ConfigSyncError("control adoption requires its frozen actor")
    return SyncActor.from_dict(raw)


def _adopt_generation(connection: Connection, operation: SyncControlOperation, receipt: CausalReceipt,
                       claim: SyncActor, cached: Optional[str]) -> None:
    if operation.kind != "full_resync" or claim.mode != "full_sync":
        raise ConfigSyncError("only explicit full resync can change local generation")
    scope = operation.identity.endpoint, operation.identity.user_id
    pending = connection.execute("SELECT count(*) FROM sync_operations WHERE endpoint=? AND user_id=? "
                                 "AND status NOT IN ('delivered','retired')", scope).fetchone()[0]
    if pending and not operation.discard_pending:
        raise ConfigSyncError("full resync requires explicit discard_pending before retiring pending edits")
    snapshot = _adopted_snapshot(receipt.snapshot, claim, cached, operation.identity.origin)
    connection.execute("UPDATE sync_operations SET status='retired',lease_owner='',lease_until=0,error='' "
                       "WHERE endpoint=? AND user_id=? AND status NOT IN ('delivered','retired')", scope)
    connection.execute("UPDATE sync_namespaces SET origin=?,epoch=?,confirmed_revision=?,snapshot=? "
                       "WHERE endpoint=? AND user_id=?",
                       (claim.origin, claim.epoch, receipt.revision, _encoded(snapshot.to_dict()), *scope))


def _adopted_snapshot(snapshot: CausalBucket, claim: SyncActor, cached: Optional[str], old_origin: str) -> CausalBucket:
    if cached is None or claim.origin != old_origin:
        return snapshot
    previous = CausalBucket.from_dict(json.loads(cached))
    if previous.revision <= snapshot.revision:
        return snapshot
    records = cast(list[dict[str, object]], previous.peer_state["peers"])
    record = next((raw for raw in records if raw["peer_id"] == claim.origin), None)
    if record is None or cast(int, record["epoch"]) < claim.epoch:
        return snapshot
    previous.peers.require_active(claim.origin, epoch=claim.epoch)
    return previous
