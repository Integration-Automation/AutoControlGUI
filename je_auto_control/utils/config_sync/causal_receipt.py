"""Complete server snapshot receipts for atomic durable outbox confirmation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _revision
from je_auto_control.utils.logging.secret_scope import scrub_secret_data


def _server_snapshot(snapshot: CausalBucket) -> CausalBucket:
    body = snapshot.to_dict()
    if _encoded(cast(dict[str, object], scrub_secret_data(body))) != _encoded(body):
        raise ConfigSyncError("server snapshot cannot persist resolved credentials")
    copied = CausalBucket.from_dict(body)
    if set(copied.committed) != {node.change_id for node in copied.nodes}:
        raise ConfigSyncError("server snapshot must assign every change a committed revision")
    records = cast(list[dict[str, object]], copied.peer_state["peers"])
    if any(cast(int, record["acknowledged_revision"]) > copied.revision for record in records):
        raise ConfigSyncError("server snapshot contains a future acknowledgement")
    return copied


@dataclass(frozen=True)
class CausalReceipt:
    """An operation's original receipt and the latest complete snapshot, which can have a newer revision."""

    revision: int
    snapshot: CausalBucket

    def __post_init__(self) -> None:
        _revision(self.revision)
        snapshot = _server_snapshot(self.snapshot)
        if not 0 < self.revision <= snapshot.revision:
            raise ConfigSyncError("causal receipt must identify a committed revision within its snapshot")
        object.__setattr__(self, "snapshot", snapshot)
