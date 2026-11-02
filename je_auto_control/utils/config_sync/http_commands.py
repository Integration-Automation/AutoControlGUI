"""Private causal HTTP adapters use live credential references and durable, path-confined outboxes."""
from concurrent.futures import CancelledError
from dataclasses import asdict
import os
import re
from typing import Callable, Optional, cast

from je_auto_control.utils.config_sync.causal_client import CausalSyncClient
from je_auto_control.utils.config_sync.causal_commands import _queue
from je_auto_control.utils.config_sync.causal_models import SyncActor
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.control_models import ControlKind, SyncControlRequest
from je_auto_control.utils.config_sync.outbox import SyncOutbox
from je_auto_control.utils.config_sync.outbox_models import SyncRetryPolicy
from je_auto_control.utils.path_guard.policy import PathPolicy

_Cancelled = Optional[Callable[[], bool]]


def _options(value: Optional[dict[str, object]], extra: tuple[str, ...] = ()) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not set(value) <= {"secret_env", "timeout_s", *extra}:
        raise ConfigSyncError("unknown causal HTTP options")
    return dict(value)


def _client(endpoint: str, user_id: str, options: dict[str, object]) -> CausalSyncClient:
    environment = options.get("secret_env")
    secret = None
    if environment is not None:
        if not isinstance(environment, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", environment):
            raise ConfigSyncError("secret_env must name one environment variable")
        secret = os.environ.get(environment)
        if not secret:
            raise ConfigSyncError("configured causal credential environment variable is unset or empty")
    return CausalSyncClient(endpoint, user_id=user_id, secret=secret,
                            timeout_s=cast(float, options.get("timeout_s", 5.0)))


def _check(cancelled: _Cancelled) -> None:
    if cancelled is not None and cancelled():
        raise CancelledError()


def _fetch_causal_config(endpoint: str, user_id: str, options: Optional[dict[str, object]] = None, *,
                         cancelled: _Cancelled = None) -> dict[str, object]:
    _check(cancelled)
    snapshot = _client(endpoint, user_id, _options(options)).fetch()
    return {"version": 3, "bucket": snapshot.to_dict()}


def _commit_causal_config(endpoint: str, user_id: str, bucket: dict[str, object], actor: dict[str, object],
                          operation_id: str, options: Optional[dict[str, object]] = None, *,
                          cancelled: _Cancelled = None) -> dict[str, object]:
    _check(cancelled)
    client = _client(endpoint, user_id, _options(options))
    receipt = client.push(CausalBucket.from_dict(bucket), actor=SyncActor.from_dict(actor), operation_id=operation_id)
    return {"version": 3, "revision": receipt.revision, "bucket": receipt.snapshot.to_dict()}


def _flush_sync_outbox(path: str, endpoint: str, user_id: str, options: Optional[dict[str, object]] = None, *,
                        path_policy: Optional[PathPolicy] = None, cancelled: _Cancelled = None) -> dict[str, object]:
    _check(cancelled)
    settings = _options(options, ("policy", "max_rebases"))
    client = _client(endpoint, user_id, settings)
    policy = _retry_policy(settings.get("policy"))
    queue = _queue(path, path_policy)
    report = client.flush(queue, policy=policy, max_rebases=cast(int, settings.get("max_rebases", 3)),
                          cancelled=cancelled)
    snapshot = queue.snapshot(endpoint=endpoint, user_id=user_id)
    return {"report": asdict(report), "state": queue.status(endpoint=endpoint, user_id=user_id),
            "snapshot": snapshot.to_dict() if snapshot is not None else None}


def _retry_policy(raw: object) -> SyncRetryPolicy:
    if raw is None:
        return SyncRetryPolicy()
    fields = {"max_attempts", "max_batch", "backoff", "max_delay", "lease_seconds"}
    if not isinstance(raw, dict) or not set(raw) <= fields:
        raise ConfigSyncError("invalid causal delivery retry policy")
    return SyncRetryPolicy(max_attempts=cast(int, raw.get("max_attempts", 3)),
                           backoff=cast(float, raw.get("backoff", 0.25)),
                           max_delay=cast(float, raw.get("max_delay", 5.0)),
                           max_batch=cast(int, raw.get("max_batch", 100)),
                           lease_seconds=cast(float, raw.get("lease_seconds", 30.0)))


def _control_sync_peer(path: str, endpoint: str, user_id: str, operation: str = "status",
                        options: Optional[dict[str, object]] = None, *, path_policy: Optional[PathPolicy] = None,
                        cancelled: _Cancelled = None) -> dict[str, object]:
    _check(cancelled)
    settings = _options(options, ("policy", "peer_id", "discard_pending", "operation_id"))
    queue = _queue(path, path_policy)
    if operation == "status":
        return _control_reply(queue, endpoint, user_id, None)
    request = SyncControlRequest(cast(ControlKind, operation),
                                  operation_id=cast(Optional[str], settings.get("operation_id")),
                                  peer_id=cast(Optional[str], settings.get("peer_id")),
                                  discard_pending=cast(bool, settings.get("discard_pending", False)))
    policy = _retry_policy(settings.get("policy"))
    client = _client(endpoint, user_id, settings)
    report = client.control(queue, request, policy=policy, cancelled=cancelled)
    return _control_reply(queue, endpoint, user_id, asdict(report))


def _control_reply(queue: SyncOutbox, endpoint: str, user_id: str,
                    report: Optional[dict[str, object]]) -> dict[str, object]:
    snapshot = queue.snapshot(endpoint=endpoint, user_id=user_id)
    return {"report": report, "state": queue.status(endpoint=endpoint, user_id=user_id),
            "control": queue.control_status(endpoint=endpoint, user_id=user_id),
            "snapshot": snapshot.to_dict() if snapshot is not None else None}
