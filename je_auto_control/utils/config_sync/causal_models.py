"""Typed causal actors and compact deletion fences without changing version-one entry wire data."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Literal, Optional, cast

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _identifier, _revision, _schema_one
from je_auto_control.utils.config_sync.versions import SyncEntry, _key_text, _version

ActorMode = Literal["edit", "full_sync", "ack", "retire", "collect"]


@dataclass(frozen=True)
class SyncActor:
    """One explicit peer/epoch operation; its revision is an acknowledgement claim checked by the server."""

    origin: str
    epoch: int
    mode: ActorMode = "edit"
    peer_id: Optional[str] = None
    revision: Optional[int] = None

    def __post_init__(self) -> None:
        _identifier(self.origin, "actor origin")
        _revision(self.epoch)
        allowed = {"edit", "full_sync", "ack", "retire", "collect"}
        if not isinstance(self.mode, str) or self.mode not in allowed:
            raise ConfigSyncError("unknown causal actor mode")
        _actor_fields(self.mode, self.peer_id, self.revision)

    def to_dict(self) -> dict[str, object]:
        """Return the exact actor envelope without credentials or executable values."""
        return asdict(self)

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> SyncActor:
        """Validate every actor field before storage or membership changes."""
        if not isinstance(body, dict) or set(body) != {"origin", "epoch", "mode", "peer_id", "revision"}:
            raise ConfigSyncError("invalid causal actor schema")
        return cls(cast(str, body["origin"]), cast(int, body["epoch"]), cast(ActorMode, body["mode"]),
                   cast(Optional[str], body["peer_id"]), cast(Optional[int], body["revision"]))


def _actor_fields(mode: str, peer_id: Optional[str], revision: Optional[int]) -> None:
    if mode == "retire":
        if peer_id is None or revision is not None:
            raise ConfigSyncError("retirement requires only a target peer_id")
        _identifier(peer_id, "retired peer_id")
        return
    if peer_id is not None:
        raise ConfigSyncError("this actor mode does not take a target peer_id")
    if mode in {"ack", "full_sync"}:
        if revision is None:
            raise ConfigSyncError("acknowledgement/full sync requires a revision")
        _revision(revision)
    elif revision is not None:
        raise ConfigSyncError("this actor mode does not take an acknowledgement revision")


@dataclass(frozen=True)
class DeletionFence:
    """Minimal acknowledged deletion evidence; old values cannot return after their payload is reclaimed."""

    section: str
    entry_id: str
    version: dict[str, int]
    operation_id: str
    origin: str
    deletion_revision: int
    _seal: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _key_text(self.section)
        _key_text(self.entry_id)
        _identifier(self.operation_id, "deleted operation_id")
        _identifier(self.origin, "deleted origin")
        _version(self.version, self.origin)
        _revision(self.deletion_revision)
        if self.deletion_revision == 0:
            raise ConfigSyncError("a deletion fence requires a committed revision")
        copied = json.loads(_encoded(self._wire()))
        object.__setattr__(self, "version", copied["version"])
        object.__setattr__(self, "_seal", sha256(_encoded(copied).encode("ascii")).hexdigest())

    @property
    def key(self) -> tuple[str, str]:
        """Return the same merge domain used by entry snapshots."""
        return self.section, self.entry_id

    @property
    def change_id(self) -> str:
        """Match the original tombstone without retaining its old value."""
        self.to_dict()
        metadata = {"section": self.section, "entry_id": self.entry_id, "version": self.version,
                    "operation_id": self.operation_id, "origin": self.origin, "is_deleted": True}
        return sha256(_encoded(metadata).encode("ascii")).hexdigest()

    def _wire(self) -> dict[str, object]:
        return {"schema_version": 1, "kind": "deletion-fence", "section": self.section, "entry_id": self.entry_id,
                "version": self.version, "operation_id": self.operation_id, "origin": self.origin,
                "deletion_revision": self.deletion_revision}

    def to_dict(self) -> dict[str, object]:
        """Copy and validate the compact evidence before a merge or commit."""
        encoded = _encoded(self._wire())
        if sha256(encoded.encode("ascii")).hexdigest() != self._seal:
            raise ConfigSyncError("deletion fence changed after construction")
        return cast(dict[str, object], json.loads(encoded))

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> DeletionFence:
        """Reject incomplete or foreign fence data rather than treating it as a live value."""
        fields = {"schema_version", "kind", "section", "entry_id", "version", "operation_id", "origin",
                  "deletion_revision"}
        if (not isinstance(body, dict) or set(body) != fields or not _schema_one(body["schema_version"])
                or body["kind"] != "deletion-fence"):
            raise ConfigSyncError("invalid deletion fence schema")
        return cls(cast(str, body["section"]), cast(str, body["entry_id"]), cast(dict[str, int], body["version"]),
                   cast(str, body["operation_id"]), cast(str, body["origin"]), cast(int, body["deletion_revision"]))

    @classmethod
    def from_entry(cls, entry: SyncEntry, revision: int) -> DeletionFence:
        """Compact only a tombstone, preserving its original change identity and causal counter floor."""
        entry.to_dict()
        if not entry.is_deleted:
            raise ConfigSyncError("a live value cannot become a deletion fence")
        return cls(entry.section, entry.entry_id, entry.version, entry.operation_id, entry.origin, revision)


CausalNode = SyncEntry | DeletionFence


@dataclass(frozen=True)
class CausalConflict:
    """Every unresolved frontier alternative, including a compacted deletion with no recoverable old payload."""

    key: tuple[str, str]
    alternatives: tuple[CausalNode, ...]

    @property
    def origins(self) -> tuple[str, ...]:
        """Expose actual origins for evidence without selecting an arbitrary alternative."""
        return tuple(node.origin for node in self.alternatives)
