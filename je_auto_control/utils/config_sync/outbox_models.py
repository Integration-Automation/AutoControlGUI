"""Bounded durable sync operations, retry budgets and account/endpoint identities."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Optional, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _identifier, _revision, _schema_one
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.logging.secret_scope import scrub_secret_data


def normalize_sync_endpoint(value: str) -> str:
    """Canonicalize an HTTP namespace without persisting URL credentials, query strings or fragments."""
    try:
        parts = _endpoint_parts(value)
        return urlunsplit((parts.scheme.lower(), _authority(parts), parts.path.rstrip("/"), "", ""))
    except (ValueError, UnicodeError, AttributeError):
        raise ConfigSyncError("sync endpoint must be an HTTP URL without credentials, query or fragment") from None


def _endpoint_parts(value: str) -> SplitResult:
    if not isinstance(value, str) or len(value) > 4096 or any(character.isspace() for character in value):
        raise ValueError("endpoint must be URL text")
    parts = urlsplit(value)
    if not _allowed_endpoint(parts):
        raise ValueError("unsupported endpoint")
    return parts


def _allowed_endpoint(parts: SplitResult) -> bool:
    return (parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)
            and parts.username is None and parts.password is None and not parts.query and not parts.fragment)


def _authority(parts: SplitResult) -> str:
    host = cast(str, parts.hostname).encode("idna").decode("ascii").lower()
    host = f"[{host}]" if ":" in host else host
    port = parts.port
    if port is not None and port != (443 if parts.scheme.lower() == "https" else 80):
        host = f"{host}:{port}"
    return host


def _prepared(value: Optional[dict[str, object]], user_id: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {"base_revision", "bucket"}:
        raise ConfigSyncError("prepared delivery must contain base_revision and bucket")
    _revision(cast(int, value["base_revision"]))
    if not isinstance(value["bucket"], dict) or value["bucket"].get("user_id") != user_id:
        raise ConfigSyncError("prepared bucket must be an object")
    _encoded(value)


def _copy_entries(entries: tuple[SyncEntry, ...], origin: str) -> tuple[SyncEntry, ...]:
    if not isinstance(entries, tuple) or not 1 <= len(entries) <= 1000:
        raise ConfigSyncError("sync operation requires 1–1000 immutable entries")
    copied, size = [], 0
    for entry in entries:
        if not isinstance(entry, SyncEntry):
            raise ConfigSyncError("operation entries must be SyncEntry values")
        wire = entry.to_dict()
        size += len(_encoded(wire))
        if size > 1024 * 1024:
            raise ConfigSyncError("operation entry data exceeds 1 MiB")
        copied.append(SyncEntry.from_dict(wire))
    if len({entry.key for entry in copied}) != len(copied) or any(entry.origin != origin for entry in copied):
        raise ConfigSyncError("operation entries must have unique keys and the operation's origin")
    return tuple(copied)


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: independent durable operation values and a private seal
class SyncOperation:
    """One logical local edit plus an optional exact prepared request for uncertain-result retries.

    Credentials belong to the live client, not this operation. Endpoints/accounts
    isolate queue identity; the same operation ID cannot silently change payload.
    """

    operation_id: str
    endpoint: str
    user_id: str
    origin: str
    entries: tuple[SyncEntry, ...]
    epoch: int = 0
    prepared: Optional[dict[str, object]] = field(default=None, repr=False)
    _seal: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _identifier(self.operation_id, "delivery operation_id")
        _identifier(self.user_id, "user_id")
        _identifier(self.origin, "origin")
        _revision(self.epoch)
        object.__setattr__(self, "endpoint", normalize_sync_endpoint(self.endpoint))
        object.__setattr__(self, "entries", _copy_entries(self.entries, self.origin))
        _prepared(self.prepared, self.user_id)
        if self.prepared is not None:
            object.__setattr__(self, "prepared", json.loads(_encoded(self.prepared)))
        encoded = self._encode()
        object.__setattr__(self, "_seal", sha256(encoded.encode("ascii")).hexdigest())

    def _encode(self) -> str:
        body = {"schema_version": 1, "operation_id": self.operation_id, "endpoint": self.endpoint,
                "user_id": self.user_id, "origin": self.origin, "epoch": self.epoch,
                "entries": [entry.to_dict() for entry in self.entries], "prepared": self.prepared}
        if scrub_secret_data(body) != body:
            raise ConfigSyncError("resolved secret values cannot be persisted in the sync outbox")
        return _encoded(body, max_bytes=4 * 1024 * 1024)

    def to_dict(self) -> dict[str, object]:
        """Return an independent sealed snapshot, never serializing callables or credential headers."""
        encoded = self._encode()
        if sha256(encoded.encode("ascii")).hexdigest() != self._seal:
            raise ConfigSyncError("sync operation changed after construction")
        return cast(dict[str, object], json.loads(encoded))

    @property
    def delivery_id(self) -> str:
        """Stable server receipt identity, including device epoch and namespace to prevent cross-device collisions."""
        self.to_dict()
        identity = [self.endpoint, self.user_id, self.origin, self.epoch, self.operation_id]
        return "sync-" + sha256(json.dumps(identity, ensure_ascii=True).encode("ascii")).hexdigest()

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> SyncOperation:
        """Validate the complete version-one operation before recovering pending work."""
        fields = {"schema_version", "operation_id", "endpoint", "user_id", "origin", "entries", "epoch", "prepared"}
        if not isinstance(body, dict) or set(body) != fields or not _schema_one(body["schema_version"]):
            raise ConfigSyncError("invalid durable sync operation schema")
        raw = body["entries"]
        if not isinstance(raw, list):
            raise ConfigSyncError("operation entries must be a list")
        return cls(cast(str, body["operation_id"]), cast(str, body["endpoint"]), cast(str, body["user_id"]),
                   cast(str, body["origin"]), tuple(SyncEntry.from_dict(entry) for entry in raw),
                   cast(int, body["epoch"]), cast(Optional[dict[str, object]], body["prepared"]))


@dataclass(frozen=True)
class SyncRetryPolicy:
    """One bounded drain budget; persisted backoff schedules retries without blocking a worker."""

    max_attempts: int = 3
    backoff: float = 0.25
    max_delay: float = 5.0
    max_batch: int = 100
    lease_seconds: float = 30.0

    def __post_init__(self) -> None:
        _revision(self.max_attempts)
        _revision(self.max_batch)
        if not 1 <= self.max_attempts <= 10 or not 1 <= self.max_batch <= 1000:
            raise ConfigSyncError("retry budget allows 1–10 attempts and 1–1000 queued operations")
        for value in (self.backoff, self.max_delay, self.lease_seconds):
            _finite_delay(value)
        if not 0 <= self.backoff <= self.max_delay <= 30 or not 1 <= self.lease_seconds <= 300:
            raise ConfigSyncError("backoff must be bounded to 30 seconds and leases to 1–300 seconds")


def _finite_delay(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigSyncError("retry delays must be finite numbers")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ConfigSyncError("retry delays must be finite numbers")


@dataclass(frozen=True)
class SyncDrainResult:
    """One drain's successful sends and remaining durable work, including cancellation/offline state."""

    delivered: int
    pending: int
    failed: int
    cancelled: bool = False


@dataclass(frozen=True)
class SyncLocalIdentity:
    """Durable device identity and confirmed delivery revision within one account/endpoint namespace."""

    endpoint: str
    user_id: str
    origin: str
    epoch: int = 0
    confirmed_revision: int = 0
