"""Cancellable peer-control delivery freezes complete snapshots and retries only definite stale-base refusals."""
from __future__ import annotations

from concurrent.futures import CancelledError
from hashlib import sha256
from typing import Callable, Optional, Protocol, cast
from uuid import uuid4

from je_auto_control.utils.config_sync.causal_models import SyncActor
from je_auto_control.utils.config_sync.causal_receipt import CausalReceipt
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigRevisionConflict, ConfigStoreError, ConfigSyncError
from je_auto_control.utils.config_sync.control_models import SyncControlOperation, SyncControlResult
from je_auto_control.utils.config_sync.control_store import ControlStore
from je_auto_control.utils.config_sync.outbox_models import SyncRetryPolicy
from je_auto_control.utils.config_sync.peers import FullResyncRequired
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption

_Cancelled = Optional[Callable[[], bool]]


class _Client(Protocol):
    """Minimal transport seam; peer control storage never imports the orchestration client."""

    def fetch(self) -> CausalBucket:
        """Fetch one complete causal snapshot."""

    def push(self, bucket: CausalBucket, *, actor: SyncActor, operation_id: str,
             base_revision: Optional[int] = None) -> CausalReceipt:
        """Commit an exact actor request and return its complete receipt."""


def drain_control(client: _Client, store: ControlStore, scope: tuple[str, str],
                   policy: SyncRetryPolicy, cancelled: _Cancelled = None) -> SyncControlResult:
    """Attempt one durable intent with the existing retry/backoff/lease budget and preserve successful receipts."""
    failed, delivered, revision = 0, 0, None
    owner = uuid4().hex
    for _ in range(policy.max_attempts):
        _check(cancelled)
        operation = store.claim(scope, owner, policy)
        if operation is None:
            break
        try:
            receipt = _deliver(client, store, operation, owner, cancelled)
            delivered = int(store.complete(operation, owner, receipt))
            revision = receipt.revision if delivered else None
            break
        except (OSError, ConfigSyncError, ConfigStoreError, ConfigRevisionConflict, FullResyncRequired) as error:
            raise_caused_run_interruption(error)
            store.failed(operation, owner, error, policy)
            failed += 1
        finally:
            store.release(operation, owner)
    status = store.status(scope)
    return SyncControlResult(cast(Optional[str], status["operation_id"]), cast(Optional[str], status["kind"]),
                             delivered, cast(int, status["pending"]), failed, revision)


def _deliver(client: _Client, store: ControlStore, operation: SyncControlOperation, owner: str,
              cancelled: _Cancelled) -> CausalReceipt:
    for attempt in range(4):
        _check(cancelled)
        if operation.prepared is None:
            state = client.fetch()
            body = _request(state, operation)
            _check(cancelled)
            operation = store.prepare(operation, owner, body)
        _check(cancelled)
        try:
            return _send(client, operation)
        except ConfigRevisionConflict as error:
            if error.code != "stale_revision":
                raise
            operation = store.reject(operation, owner)
            if attempt == 3:
                raise ConfigSyncError("peer-control stale-base retry budget exhausted") from error
    raise ConfigSyncError("peer control did not produce a receipt")


def _request(state: CausalBucket, operation: SyncControlOperation) -> dict[str, object]:
    local = operation.identity
    if operation.kind in {"register", "full_resync"}:
        candidate, actor = _registration(state, operation)
    else:
        previous = state.peers.require_active(local.origin, epoch=local.epoch)
        peers = state.peers
        if operation.kind == "ack":
            revision = max(previous.acknowledged_revision, max(state.committed.values(), default=0))
            peers.acknowledge(local.origin, revision, epoch=local.epoch)
            actor = SyncActor(local.origin, local.epoch, "ack", revision=revision)
        elif operation.kind == "retire":
            peers.retire(cast(str, operation.peer_id))
            actor = SyncActor(local.origin, local.epoch, "retire", peer_id=operation.peer_id)
        else:
            state = state.collect()
            actor = SyncActor(local.origin, local.epoch, "collect")
        candidate = state.with_peers(peers)
    body = candidate.to_dict()
    body["_actor"] = actor.to_dict()
    return body


def _registration(state: CausalBucket, operation: SyncControlOperation) -> tuple[CausalBucket, SyncActor]:
    local, peers = operation.identity, state.peers
    records = cast(list[dict[str, object]], state.peer_state["peers"])
    previous = next((record for record in records if record["peer_id"] == local.origin), None)
    if operation.kind == "register" and previous is not None:
        peers.require_active(local.origin, epoch=local.epoch)
        peers.acknowledge(local.origin, state.revision, epoch=local.epoch)
        return state.with_peers(peers), SyncActor(local.origin, local.epoch, "ack", revision=state.revision)
    if operation.kind == "register":
        if local.epoch != 0 or local.confirmed_revision:
            raise FullResyncRequired("unknown historical peer requires explicit full resync")
        record = peers.register(local.origin, full_revision=state.revision)
    elif previous is None or cast(int, previous["epoch"]) < local.epoch:
        fresh = "peer-" + sha256(operation.delivery_id.encode("ascii")).hexdigest()
        record = peers.register(fresh, full_revision=state.revision)
    else:
        record = peers.register(local.origin, full_revision=state.revision, full_resync=True)
    return state.with_peers(peers), SyncActor(record.peer_id, record.epoch, "full_sync", revision=state.revision)


def _send(client: _Client, operation: SyncControlOperation) -> CausalReceipt:
    prepared = operation.prepared
    if prepared is None or not isinstance(prepared.get("bucket"), dict):
        raise ConfigSyncError("peer control requires a frozen request")
    body = dict(cast(dict[str, object], prepared["bucket"]))
    raw_actor = body.pop("_actor", None)
    if not isinstance(raw_actor, dict):
        raise ConfigSyncError("prepared peer control requires its explicit actor")
    actor = SyncActor.from_dict(raw_actor)
    state = CausalBucket.from_dict(body)
    if state.user_id != operation.identity.user_id:
        raise ConfigSyncError("prepared peer control belongs to another account")
    _prepared_actor(operation, actor)
    return client.push(state, actor=actor, operation_id=operation.delivery_id,
                        base_revision=cast(int, prepared["base_revision"]))


def _prepared_actor(operation: SyncControlOperation, actor: SyncActor) -> None:
    local = operation.identity
    if operation.kind == "full_resync":
        fresh = "peer-" + sha256(operation.delivery_id.encode("ascii")).hexdigest()
        if actor.mode != "full_sync" or actor.origin not in {local.origin, fresh}:
            raise ConfigSyncError("full-resync actor does not match its logical control")
        return
    modes = {"ack", "full_sync"} if operation.kind == "register" else {operation.kind}
    if actor.origin != local.origin or actor.epoch != local.epoch or actor.mode not in modes:
        raise ConfigSyncError("peer-control actor does not match its logical intent")
    if actor.peer_id != operation.peer_id:
        raise ConfigSyncError("peer retirement target changed after preparation")


def _check(cancelled: _Cancelled) -> None:
    if cancelled is not None and cancelled():
        raise CancelledError()
