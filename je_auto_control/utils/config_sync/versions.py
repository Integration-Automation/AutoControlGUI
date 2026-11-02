"""Causal entry versions and explicit conflict preservation without wall-clock winners."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Iterable, Literal, Optional, cast

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _identifier, _revision, _schema_one

_WIRE_FIELDS = {"schema_version", "section", "entry_id", "value", "version", "operation_id", "origin", "is_deleted"}


def _key_text(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 512 or not value.isprintable():
        raise ConfigSyncError("sync entry keys must be nonempty printable text up to 512 characters")


def _version(value: dict[str, int], origin: str) -> None:
    if not isinstance(value, dict) or not value or len(value) > 128 or origin not in value:
        raise ConfigSyncError("sync version must include its origin and at most 128 devices")
    for peer, counter in value.items():
        _identifier(peer, "version device")
        _revision(counter)
        if counter == 0:
            raise ConfigSyncError("version counters must be positive")


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: seven independent entry values plus a private integrity seal
class SyncEntry:
    """One causal value or tombstone; timestamps inside value do not choose a winner.

    The constructor copies JSON inputs, while later mutation of exposed mappings
    is rejected when serializing or merging. A tombstone may retain its previous
    value until acknowledged collection; is_deleted determines application behavior.
    """

    section: str
    entry_id: str
    value: dict[str, object]
    version: dict[str, int]
    operation_id: str
    origin: str
    is_deleted: bool = False
    _seal: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _key_text(self.section)
        _key_text(self.entry_id)
        _identifier(self.operation_id, "entry operation_id")
        _identifier(self.origin, "entry origin")
        _version(self.version, self.origin)
        if not isinstance(self.value, dict) or not isinstance(self.is_deleted, bool):
            raise ConfigSyncError("entry value must be an object and deletion a boolean")
        encoded = _encoded(self._wire())
        cloned = json.loads(encoded)
        if cloned != self._wire():
            raise ConfigSyncError("sync entry keys must retain JSON identity")
        object.__setattr__(self, "value", cloned["value"])
        object.__setattr__(self, "version", cloned["version"])
        object.__setattr__(self, "_seal", sha256(encoded.encode("ascii")).hexdigest())

    @property
    def key(self) -> tuple[str, str]:
        """Section and entry ID jointly identify the merge domain."""
        return self.section, self.entry_id

    @property
    def change_id(self) -> str:
        """Identify causal change metadata independently of payload reclamation or wire ordering."""
        self.to_dict()
        metadata = {"section": self.section, "entry_id": self.entry_id, "version": self.version,
                    "operation_id": self.operation_id, "origin": self.origin, "is_deleted": self.is_deleted}
        return sha256(_encoded(metadata).encode("ascii")).hexdigest()

    def _wire(self) -> dict[str, object]:
        return {"schema_version": 1, "section": self.section, "entry_id": self.entry_id,
                "value": self.value, "version": self.version, "operation_id": self.operation_id,
                "origin": self.origin, "is_deleted": self.is_deleted}

    def to_dict(self) -> dict[str, object]:
        """Return an independent bounded JSON snapshot, rejecting changed causal evidence."""
        encoded = _encoded(self._wire())
        if sha256(encoded.encode("ascii")).hexdigest() != self._seal:
            raise ConfigSyncError("sync entry changed after construction")
        return cast(dict[str, object], json.loads(encoded))

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> SyncEntry:
        """Validate the exact version-one entry schema without evaluating payload values."""
        if (not isinstance(body, dict) or set(body) != _WIRE_FIELDS
                or not _schema_one(body["schema_version"])):
            raise ConfigSyncError("invalid causal entry schema")
        return cls(cast(str, body["section"]), cast(str, body["entry_id"]), cast(dict[str, object], body["value"]),
                   cast(dict[str, int], body["version"]), cast(str, body["operation_id"]),
                   cast(str, body["origin"]), cast(bool, body["is_deleted"]))

    def evolve(self, value: dict[str, object], *, origin: str, operation_id: str, is_deleted: bool = False,
                 observed: Iterable[SyncEntry] = ()) -> SyncEntry:
        """Create a new operation that causally follows this entry and explicitly observed alternatives."""
        self.to_dict()
        version = dict(self.version)
        for other in observed:
            other.to_dict()
            if other.key != self.key:
                raise ConfigSyncError("cannot resolve entries from different keys")
            for peer, counter in other.version.items():
                version[peer] = max(version.get(peer, 0), counter)
        version[origin] = version.get(origin, 0) + 1
        return SyncEntry(self.section, self.entry_id, value, version, operation_id, origin, is_deleted)


@dataclass(frozen=True)
class SyncConflict:
    """Both independently snapshotted alternatives remain available for explicit resolution."""

    local: SyncEntry
    remote: SyncEntry
    reason: Literal["concurrent_edits", "version_fork"] = "concurrent_edits"


@dataclass(frozen=True)
class MergeDecision:
    """A causal winner or an unresolved pair; never a timestamp-based silent replacement."""

    relation: Literal["same", "left", "right", "conflict"]
    entry: Optional[SyncEntry] = None
    conflict: Optional[SyncConflict] = None


def dominates(left: dict[str, int], right: dict[str, int]) -> bool:
    """Whether left strictly follows right, treating an unseen device counter as zero."""
    peers = left.keys() | right.keys()
    return (all(left.get(peer, 0) >= right.get(peer, 0) for peer in peers)
            and any(left.get(peer, 0) > right.get(peer, 0) for peer in peers))


def merge_entries(left: SyncEntry, right: SyncEntry) -> MergeDecision:
    """Preserve concurrent/forked input; only provable version-vector dominance selects a value."""
    left, right = SyncEntry.from_dict(left.to_dict()), SyncEntry.from_dict(right.to_dict())
    if left.key != right.key:
        raise ConfigSyncError("cannot merge entries from different keys")
    if left == right:
        return MergeDecision("same", left)
    if left.origin == right.origin and left.operation_id == right.operation_id:
        raise ConfigSyncError("entry operation_id identifies different causal data")
    if dominates(left.version, right.version):
        return MergeDecision("left", left)
    if dominates(right.version, left.version):
        return MergeDecision("right", right)
    reason: Literal["concurrent_edits", "version_fork"] = (
        "version_fork" if left.version == right.version else "concurrent_edits"
    )
    return MergeDecision("conflict", conflict=SyncConflict(left, right, reason))
