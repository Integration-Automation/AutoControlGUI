"""Sealed peer-control intents and bounded drain results without changing version-one edit wires."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Literal, Optional, cast

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _identifier, _revision, _schema_one
from je_auto_control.utils.config_sync.outbox_models import SyncLocalIdentity, _prepared, normalize_sync_endpoint
from je_auto_control.utils.logging.secret_scope import scrub_secret_data

ControlKind = Literal["register", "ack", "retire", "collect", "full_resync"]


@dataclass(frozen=True)
class SyncControlRequest:
    """Caller-owned logical metadata identity; keep operation_id stable when retrying a completed RPC result."""

    kind: ControlKind
    operation_id: Optional[str] = None
    peer_id: Optional[str] = None
    discard_pending: bool = False

    def __post_init__(self) -> None:
        _intent(self.kind, self.peer_id, self.discard_pending)
        if self.operation_id is not None:
            _identifier(self.operation_id, "control operation_id")


@dataclass(frozen=True)
class SyncControlOperation:
    """One durable metadata intent; prepared requests freeze the exact snapshot and actor before HTTP."""

    operation_id: str
    identity: SyncLocalIdentity
    kind: ControlKind
    peer_id: Optional[str] = None
    discard_pending: bool = False
    prepared: Optional[dict[str, object]] = field(default=None, repr=False)
    _seal: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _identifier(self.operation_id, "control operation_id")
        _identity(self.identity)
        _intent(self.kind, self.peer_id, self.discard_pending)
        _prepared(self.prepared, self.identity.user_id)
        if self.prepared is not None:
            object.__setattr__(self, "prepared", json.loads(_encoded(self.prepared)))
        object.__setattr__(self, "_seal", sha256(self._encode().encode("ascii")).hexdigest())

    def _encode(self) -> str:
        body = {"schema_version": 1, "operation_id": self.operation_id, "identity": asdict(self.identity),
                "kind": self.kind, "peer_id": self.peer_id, "discard_pending": self.discard_pending,
                "prepared": self.prepared}
        if _encoded(cast(dict[str, object], scrub_secret_data(body))) != _encoded(body):
            raise ConfigSyncError("resolved credentials cannot be persisted in a peer control")
        return _encoded(body, max_bytes=2 * 1024 * 1024)

    def to_dict(self) -> dict[str, object]:
        """Copy a sealed finite JSON intent; no live credential or callback is serialized."""
        encoded = self._encode()
        if sha256(encoded.encode("ascii")).hexdigest() != self._seal:
            raise ConfigSyncError("peer control changed after construction")
        return cast(dict[str, object], json.loads(encoded))

    @property
    def delivery_id(self) -> str:
        """Scope server receipt identity to the local generation and logical metadata operation."""
        self.to_dict()
        local = self.identity
        body = {"endpoint": local.endpoint, "user_id": local.user_id, "origin": local.origin,
                "epoch": local.epoch, "operation_id": self.operation_id}
        return "control-" + sha256(_encoded(body).encode("ascii")).hexdigest()

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> SyncControlOperation:
        """Validate the complete control wire when recovering a persistent request."""
        fields = {"schema_version", "operation_id", "identity", "kind", "peer_id", "discard_pending", "prepared"}
        if not isinstance(body, dict) or set(body) != fields or not _schema_one(body["schema_version"]):
            raise ConfigSyncError("invalid peer control schema")
        return cls(cast(str, body["operation_id"]), _parse_identity(body["identity"]),
                   cast(ControlKind, body["kind"]), cast(Optional[str], body["peer_id"]),
                   cast(bool, body["discard_pending"]), cast(Optional[dict[str, object]], body["prepared"]))


@dataclass(frozen=True)
class SyncControlResult:
    """One control drain's durable completion, retry count and original receipt revision."""

    operation_id: Optional[str]
    kind: Optional[str]
    delivered: int
    pending: int
    failed: int
    revision: Optional[int] = None
    cancelled: bool = False


def _identity(value: SyncLocalIdentity) -> None:
    if not isinstance(value, SyncLocalIdentity) or normalize_sync_endpoint(value.endpoint) != value.endpoint:
        raise ConfigSyncError("control requires a canonical local identity")
    _identifier(value.user_id, "user_id")
    _identifier(value.origin, "origin")
    _revision(value.epoch)
    _revision(value.confirmed_revision)


def _parse_identity(raw: object) -> SyncLocalIdentity:
    if (not isinstance(raw, dict)
            or set(raw) != {"endpoint", "user_id", "origin", "epoch", "confirmed_revision"}):
        raise ConfigSyncError("invalid peer-control identity")
    return SyncLocalIdentity(cast(str, raw["endpoint"]), cast(str, raw["user_id"]), cast(str, raw["origin"]),
                             cast(int, raw["epoch"]), cast(int, raw["confirmed_revision"]))


def _intent(kind: str, peer_id: Optional[str], discard_pending: bool) -> None:
    if not isinstance(kind, str) or kind not in {"register", "ack", "retire", "collect", "full_resync"}:
        raise ConfigSyncError("unknown peer control kind")
    if not isinstance(discard_pending, bool) or discard_pending and kind != "full_resync":
        raise ConfigSyncError("discard_pending is an explicit full-resync option")
    if kind == "retire":
        if peer_id is None:
            raise ConfigSyncError("retirement requires a target peer_id")
        _identifier(peer_id, "retired peer_id")
    elif peer_id is not None:
        raise ConfigSyncError("only retirement takes a target peer_id")
