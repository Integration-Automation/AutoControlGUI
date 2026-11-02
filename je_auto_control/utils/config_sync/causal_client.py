"""Explicit causal HTTP snapshots and durable outbox delivery with bounded, definite-rejection rebasing."""
from __future__ import annotations

from concurrent.futures import CancelledError
from typing import Callable, Optional, cast

from je_auto_control.utils.config_sync.causal_models import SyncActor
from je_auto_control.utils.config_sync.causal_receipt import CausalReceipt, _server_snapshot
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.causal_wire import CausalWire
from je_auto_control.utils.config_sync.contract import ConfigRevisionConflict, ConfigSyncError, _encoded, _identifier
from je_auto_control.utils.config_sync.control_delivery import drain_control
from je_auto_control.utils.config_sync.control_models import ControlKind, SyncControlRequest, SyncControlResult
from je_auto_control.utils.config_sync.outbox import SyncOutbox
from je_auto_control.utils.config_sync.outbox_models import (
    SyncDrainResult, SyncOperation, SyncRetryPolicy, normalize_sync_endpoint,
)
from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope

_Cancelled = Optional[Callable[[], bool]]


class CausalSyncClient:
    """Use explicit peer-control commits and flush already durable edits; synced scripts never execute.

    A caller must register a complete peer snapshot before incremental delivery.
    Unknown/retired epochs remain blocked until explicit full sync. Credentials
    remain live-client state and are never part of queue operations or snapshots.
    """

    def __init__(self, server_url: str, *, user_id: str, secret: Optional[str] = None,
                 timeout_s: float = 5.0, snapshot_validator: Optional[Callable[[CausalBucket], None]] = None) -> None:
        self._wire = CausalWire(server_url, user_id, secret, timeout_s)
        self._endpoint = normalize_sync_endpoint(server_url)
        self._user_id = user_id
        self._secret = secret
        self._snapshot_validator = snapshot_validator

    def _request(self, method: str, body: Optional[dict[str, object]] = None) -> dict[str, object]:
        return self._wire.request(method) if body is None else self._wire.request(method, body)

    def _validate_snapshot(self, snapshot: CausalBucket) -> None:
        if self._snapshot_validator is not None:
            self._snapshot_validator(snapshot)
            snapshot.to_dict()

    def fetch(self) -> CausalBucket:
        """Fetch a complete server snapshot; unsupported older endpoints fail without any write."""
        with secret_log_scope():
            remember_secret(self._secret or "")
            reply = self._request("GET")
            if set(reply) != {"version", "bucket"}:
                raise ConfigSyncError("invalid causal snapshot reply")
            return self._snapshot(reply)

    def push(self, bucket: CausalBucket, *, actor: SyncActor, operation_id: str,
             base_revision: Optional[int] = None) -> CausalReceipt:
        """Commit an exact explicit actor request; callers must retain its identity across uncertain results."""
        _identifier(operation_id, "operation_id")
        if bucket.user_id != self._user_id:
            raise ConfigSyncError("causal bucket/client account mismatch")
        base = bucket.revision if base_revision is None else base_revision
        if base != bucket.revision or isinstance(base, bool):
            raise ConfigSyncError("causal request must retain its snapshot base revision")
        self._validate_snapshot(bucket)
        with secret_log_scope():
            remember_secret(self._secret or "")
            body = bucket.to_dict()
            body["_actor"] = actor.to_dict()
            envelope = {"version": 3, "base_revision": base, "operation_id": operation_id, "bucket": body}
            _encoded(envelope)
            reply = self._request("PUT", envelope)
            if set(reply) != {"version", "revision", "bucket"} or reply["revision"] != base + 1:
                raise ConfigSyncError("server returned an invalid causal commit receipt")
            return CausalReceipt(reply["revision"], self._snapshot(reply))

    def flush(self, outbox: SyncOutbox, *, policy: Optional[SyncRetryPolicy] = None,
              max_rebases: int = 3, cancelled: _Cancelled = None) -> SyncDrainResult:
        """Deliver bounded durable work; retry frozen uncertain requests before fetching or changing their base."""
        if isinstance(max_rebases, bool) or not isinstance(max_rebases, int) or not 0 <= max_rebases <= 10:
            raise ConfigSyncError("causal rebasing allows 0–10 definite stale-base retries per attempt")
        if cancelled is not None and cancelled():
            pending_data = cast(int, outbox.status(endpoint=self._endpoint, user_id=self._user_id)["pending"])
            status = outbox.control_status(endpoint=self._endpoint, user_id=self._user_id)
            pending_control = cast(int, status["pending"])
            return SyncDrainResult(0, pending_data + pending_control, 0, True)
        with secret_log_scope():
            remember_secret(self._secret or "")
            control = self._drain_control(outbox, policy or SyncRetryPolicy(), cancelled)
            if control.pending:
                pending = cast(int, outbox.status(endpoint=self._endpoint, user_id=self._user_id)["pending"])
                return SyncDrainResult(control.delivered, pending + control.pending, control.failed)
            data = outbox.flush(lambda operation: self._deliver(outbox, operation, max_rebases, cancelled),
                                 endpoint=self._endpoint, user_id=self._user_id, policy=policy, cancelled=cancelled)
            return SyncDrainResult(control.delivered + data.delivered, data.pending,
                                    control.failed + data.failed, data.cancelled)

    def control(self, outbox: SyncOutbox, kind: ControlKind | SyncControlRequest, *, peer_id: Optional[str] = None,
                  discard_pending: bool = False, policy: Optional[SyncRetryPolicy] = None,
                  cancelled: _Cancelled = None) -> SyncControlResult:
        """Durably register/ack/retire/collect or explicitly adopt a full snapshot and retire pending old edits."""
        _check_cancelled(cancelled)
        request = _control_request(kind, peer_id, discard_pending)
        with secret_log_scope():
            remember_secret(self._secret or "")
            operation = outbox.request_control(self._endpoint, self._user_id, request.kind,
                                                peer_id=request.peer_id, discard_pending=request.discard_pending,
                                                operation_id=request.operation_id)
            receipt = outbox.control_receipt(self._endpoint, self._user_id, operation.operation_id)
            if receipt is not None:
                return SyncControlResult(operation.operation_id, operation.kind, 0, 0, 0, receipt)
            return self._drain_control(outbox, policy or SyncRetryPolicy(), cancelled)

    def _drain_control(self, outbox: SyncOutbox, policy: SyncRetryPolicy, cancelled: _Cancelled) -> SyncControlResult:
        # pylint: disable-next=protected-access  # reason: one package shares the outbox's atomic control/CAS owner
        return drain_control(self, outbox._controls(), (self._endpoint, self._user_id), policy, cancelled)

    def _snapshot(self, reply: dict[str, object]) -> CausalBucket:
        body = reply.get("bucket")
        if not isinstance(body, dict):
            raise ConfigSyncError("causal server snapshot must be an object")
        snapshot = _server_snapshot(CausalBucket.from_dict(body))
        if snapshot.user_id != self._user_id:
            raise ConfigSyncError("causal server snapshot/client account mismatch")
        self._validate_snapshot(snapshot)
        return snapshot

    def _deliver(self, outbox: SyncOutbox, operation: SyncOperation, max_rebases: int,
                 cancelled: _Cancelled) -> CausalReceipt:
        if (operation.endpoint, operation.user_id) != (self._endpoint, self._user_id):
            raise ConfigSyncError("queued operation belongs to another client namespace")
        for attempt in range(max_rebases + 1):
            _check_cancelled(cancelled)
            if operation.prepared is None:
                current = self.fetch()
                current.peers.require_active(operation.origin, epoch=operation.epoch)
                candidate = current.with_entries(operation.entries)
                self._validate_snapshot(candidate)
                body = candidate.to_dict()
                body["_actor"] = SyncActor(operation.origin, operation.epoch).to_dict()
                operation = outbox.prepare(operation, base_revision=current.revision, bucket=body)
            _check_cancelled(cancelled)
            try:
                return self._send_prepared(operation)
            except ConfigRevisionConflict as error:
                if error.code != "stale_revision":
                    raise
                operation = _rebase(outbox, operation)
                if attempt == max_rebases:
                    message = "causal stale-base retry budget exhausted; logical edit remains queued"
                    raise ConfigSyncError(message) from error
        raise ConfigSyncError("causal delivery did not produce a receipt")

    def _send_prepared(self, operation: SyncOperation) -> CausalReceipt:
        prepared = operation.prepared
        if prepared is None:
            raise ConfigSyncError("causal delivery requires a durable prepared request")
        body = dict(cast(dict[str, object], prepared["bucket"]))
        actor = body.pop("_actor", None)
        if not isinstance(actor, dict):
            raise ConfigSyncError("prepared causal request requires an actor")
        claim = SyncActor.from_dict(actor)
        if claim != SyncActor(operation.origin, operation.epoch):
            raise ConfigSyncError("prepared request actor must match its logical edit and epoch")
        snapshot = CausalBucket.from_dict(body)
        logical_ids = {entry.change_id for entry in operation.entries}
        uncommitted = (node for node in snapshot.nodes if node.change_id not in snapshot.committed)
        if any(node.change_id not in logical_ids for node in uncommitted):
            raise ConfigSyncError("prepared causal request includes changes outside its logical operation")
        merged = snapshot.with_entries(operation.entries)
        if _encoded(merged.to_dict()) != _encoded(snapshot.to_dict()):
            raise ConfigSyncError("prepared causal snapshot omits its logical edits")
        return self.push(snapshot, actor=claim, operation_id=operation.delivery_id,
                         base_revision=cast(int, prepared["base_revision"]))


def _check_cancelled(cancelled: _Cancelled) -> None:
    if cancelled is not None and cancelled():
        raise CancelledError()


def _rebase(outbox: SyncOutbox, operation: SyncOperation) -> SyncOperation:
    if operation.prepared is None:
        raise ConfigSyncError("cannot rebase an unprepared operation")
    outbox.reject_prepared(operation, rejected_base=cast(int, operation.prepared["base_revision"]))
    body = operation.to_dict()
    body["prepared"] = None
    return SyncOperation.from_dict(body)


def _control_request(kind: ControlKind | SyncControlRequest, peer_id: Optional[str],
                      discard: bool) -> SyncControlRequest:
    if isinstance(kind, SyncControlRequest):
        if peer_id is not None or discard:
            raise ConfigSyncError("a typed control request cannot be overridden by separate options")
        return kind
    return SyncControlRequest(kind, peer_id=peer_id, discard_pending=discard)
