"""Data-only causal review and private local outbox adapters; no network delivery or configuration application."""
from dataclasses import asdict
from typing import Callable, Optional, cast

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _revision
from je_auto_control.utils.config_sync.outbox import SyncOutbox
from je_auto_control.utils.config_sync.outbox_models import SyncOperation
from je_auto_control.utils.config_sync.peers import SyncPeer, SyncPeers
from je_auto_control.utils.config_sync.versions import SyncEntry, merge_entries
from je_auto_control.utils.path_guard.path_guard import validate_path
from je_auto_control.utils.path_guard.policy import PathPolicy


def _merge_sync_entry(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    decision = merge_entries(SyncEntry.from_dict(left), SyncEntry.from_dict(right))
    conflict = decision.conflict
    return {"relation": decision.relation, "entry": decision.entry.to_dict() if decision.entry is not None else None,
            "conflict": {"local": conflict.local.to_dict(), "remote": conflict.remote.to_dict(),
                         "reason": conflict.reason} if conflict is not None else None}


def _queue(path: str, policy: Optional[PathPolicy]) -> SyncOutbox:
    candidate = validate_path(path)
    if policy is not None:
        candidate = policy.validate(candidate, operation="sync outbox")
    return SyncOutbox(candidate)


def _enqueue_sync_outbox(path: str, operation: dict[str, object], *,
                           path_policy: Optional[PathPolicy] = None) -> dict[str, object]:
    value = SyncOperation.from_dict(operation)
    queue = _queue(path, path_policy)
    queue.enqueue(value)
    return {"accepted": True, "state": queue.status(endpoint=value.endpoint, user_id=value.user_id)}


def _status_sync_outbox(path: str, endpoint: str, user_id: str, include_pending: bool = False, limit: int = 100, *,
                          path_policy: Optional[PathPolicy] = None) -> dict[str, object]:
    if not isinstance(include_pending, bool):
        raise ConfigSyncError("include_pending must be a boolean")
    _revision(limit)
    if not 1 <= limit <= 1000:
        raise ConfigSyncError("pending view limit must be 1–1000")
    queue = _queue(path, path_policy)
    state = queue.status(endpoint=endpoint, user_id=user_id)
    operations = queue.pending(endpoint=endpoint, user_id=user_id, limit=limit) if include_pending else ()
    return {"state": state, "operations": [value.to_dict() for value in operations],
            "truncated": include_pending and len(operations) < cast(int, state["pending"])}


def _required_peer(value: Optional[str]) -> str:
    if value is None:
        raise ConfigSyncError("this peer operation requires peer_id")
    return value


def _required_number(value: Optional[int]) -> int:
    if value is None:
        raise ConfigSyncError("this peer operation requires a revision/epoch")
    return value


def _sync_peer_state(state: dict[str, object], operation: str, peer_id: Optional[str] = None,
                      revision: Optional[int] = None, epoch: Optional[int] = None,
                      full_resync: bool = False) -> dict[str, object]:
    peers = SyncPeers.from_dict(state)
    handlers: dict[str, Callable[[], SyncPeer | bool]] = {
        "register": lambda: peers.register(_required_peer(peer_id), full_revision=_required_number(revision),
                                             full_resync=full_resync),
        "acknowledge": lambda: peers.acknowledge(_required_peer(peer_id), _required_number(revision),
                                                  epoch=_required_number(epoch)),
        "retire": lambda: peers.retire(_required_peer(peer_id)),
        "require_active": lambda: peers.require_active(_required_peer(peer_id), epoch=epoch),
        "can_collect": lambda: peers.can_collect(_required_number(revision)),
    }
    if operation not in handlers:
        raise ConfigSyncError("unknown peer-state operation")
    result = handlers[operation]()
    return {"state": peers.to_dict(), "result": result if isinstance(result, bool) else asdict(result)}
