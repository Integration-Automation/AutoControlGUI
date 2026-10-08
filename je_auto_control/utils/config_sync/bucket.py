"""The config-sync bucket: its JSON shape, validation and the error types.

:class:`ConfigBucket` is what the sync server stores per account and what
every machine merges into. The errors every other module of the package
raises live here too, so nothing has to import the HTTP client to name them.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

if TYPE_CHECKING:  # reason: versions imports this module for ConfigSyncError
    from je_auto_control.utils.config_sync.versions import PeerState, SyncEntry

#: The ``/config`` wire format: a PUT is an envelope naming the revision it
#: was built on and an operation id, and is refused when that revision is stale.
WIRE_VERSION = 2

#: How long an *unversioned* deletion is remembered. Entries written with a
#: device id carry a version vector instead, and their tombstones are never
#: dropped by age -- see :func:`~je_auto_control.utils.config_sync.versions.collect_tombstones`.
TOMBSTONE_RETENTION_S = 30 * 24 * 3600.0


def is_tombstone(entry: Mapping[str, Any]) -> bool:
    """Whether ``entry`` records a deletion rather than a value."""
    return entry.get("deleted") is True


class ConfigSyncError(AutoControlException, RuntimeError):
    """Raised on network errors or schema validation failures."""


class ConfigSyncConflict(ConfigSyncError):
    """The server refused a push built on a revision that is no longer current.

    ``revision`` is the server's current revision when it reported one.
    Nothing was written: fetch, merge and push again.
    """

    def __init__(self, message: str, revision: Optional[int] = None) -> None:
        super().__init__(message)
        self.revision = revision


class FullResyncRequired(ConfigSyncError):
    """This device was retired from the group and may not push its old state.

    While it was away the others stopped waiting for it and collected the
    tombstones it never saw, so merging its copy could bring deleted entries
    back. Call :meth:`ConfigSyncClient.full_resync` and replace the local
    state with what it returns.
    """


class OperationMismatchError(ConfigSyncError):
    """An ``operation_id`` was reused for a write with different content.

    An operation id names one write: repeating it is how a client asks "did
    my push arrive?", and the server answers with the revision of the first
    attempt. Sending the same id with another bucket (or another base
    revision) is a different write, and answering it the same way would
    report as committed something the server discarded. Nothing was written;
    push again under a fresh id. ``revision`` is the revision the id's first
    write produced, when the server reported it.

    Deliberately not a :class:`ConfigSyncConflict`: fetching and merging
    again does not help while the id stays the same.
    """

    def __init__(self, message: str, operation_id: str = "",
                 revision: Optional[int] = None) -> None:
        super().__init__(message)
        self.operation_id = operation_id
        self.revision = revision


def new_operation_id() -> str:
    """A fresh id for one push; reuse it when retrying that same push."""
    return uuid.uuid4().hex


@dataclass
class ConfigBucket:
    """JSON-shaped bucket persisted on the sync server.

    Each section maps an opaque ``entry_id`` to an entry. An entry written
    with an ``origin`` device id is *versioned*: it has the
    :class:`~je_auto_control.utils.config_sync.versions.SyncEntry` shape
    (``value`` / ``vector`` / ``origin`` / ``operation_id``) and merges by
    causality. An entry written without one is the older flat dict stamped
    with ``last_modified``, which merges by "later wins". Unknown sections
    are passed through untouched.

    A removed entry stays in ``sections`` as a tombstone (``"deleted": true``)
    so the deletion reaches the other machines; read entries through
    :meth:`entries` or :meth:`values`, which leave tombstones out. ``peers``
    records which devices take part and the revision each has merged.
    """
    user_id: str
    sections: Dict[str, Dict[str, Dict[str, Any]]] = field(
        default_factory=dict,
    )
    revision: int = 0
    peers: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, body: Mapping[str, Any]) -> "ConfigBucket":
        if not isinstance(body, Mapping):
            raise ConfigSyncError("bucket body must be a mapping")
        if not isinstance(body.get("user_id"), str):
            raise ConfigSyncError("bucket missing user_id")
        sections = body.get("sections") or {}
        if not isinstance(sections, Mapping):
            raise ConfigSyncError("bucket sections must be a mapping")
        # The server's reply is data, not trusted structure: a list where a
        # section belongs or a non-numeric stamp raised AttributeError or
        # ValueError here or later in merge_buckets.
        return cls(
            user_id=body["user_id"],
            sections={str(name): _section(name, sec) for name, sec in sections.items()},
            revision=int(_finite(body.get("revision", 0), "revision")),
            peers=_peers(body.get("peers") or {}),
        )

    def upsert(self, section: str, entry_id: str,
               entry: Mapping[str, Any], *, origin: Optional[str] = None) -> None:
        """Add or replace an entry.

        With ``origin`` (this device's id) the entry is versioned: the change
        is recorded as made by that device on top of whatever the bucket
        holds for ``entry_id``, and no clock decides later merges.

        Without it the entry is stamped with the current time, and a
        ``last_modified`` already in ``entry`` is kept -- so drop it when
        editing an entry read back from a bucket, otherwise the edit keeps
        its old stamp and loses the merge to any newer remote copy.
        """
        if origin is not None:
            from je_auto_control.utils.config_sync.versions import SyncEntry
            current = self.get_entry(section, entry_id)
            now = time.time()
            self.put_entry(section, (
                SyncEntry.create(entry_id, entry, origin, modified_at=now) if current is None
                else current.edited(entry, origin, modified_at=now)))
            return
        body = dict(entry)
        body["last_modified"] = float(body.get("last_modified", time.time()))
        self.sections.setdefault(section, {})[entry_id] = body

    def remove(self, section: str, entry_id: str, *, origin: Optional[str] = None) -> bool:
        """Replace a live entry with a tombstone; False when there was none.

        Dropping the entry outright let the next sync bring it straight back
        from the server, where it still existed. With ``origin`` (required
        for a versioned entry) the tombstone is a new version made by that
        device. Without it the tombstone is stamped no earlier than the entry
        it deletes, so a clock running behind cannot make the deletion lose
        to the value it removed.
        """
        entry = self.sections.get(section, {}).get(entry_id)
        if entry is None or is_tombstone(entry):
            return False
        versioned = self.get_entry(section, entry_id)
        if versioned is not None:
            if origin is None:
                raise ConfigSyncError(
                    f"{section}/{entry_id} is versioned: removing it needs origin=<device id>")
            self.put_entry(section, versioned.removed(origin, modified_at=time.time()))
            return True
        stamp = max(time.time(), float(entry.get("last_modified", 0)))
        self.sections[section][entry_id] = {"deleted": True, "last_modified": stamp}
        return True

    def entries(self, section: str) -> Dict[str, Dict[str, Any]]:
        """The live entries of ``section`` as stored: everything except tombstones."""
        return {entry_id: entry for entry_id, entry in self.sections.get(section, {}).items()
                if not is_tombstone(entry)}

    def values(self, section: str) -> Dict[str, Dict[str, Any]]:
        """The live values of ``section``, whichever shape they are stored in.

        A versioned entry yields its ``value``; an entry still in conflict is
        left out (see :meth:`conflicts`); a flat entry yields itself.
        """
        values: Dict[str, Dict[str, Any]] = {}
        for entry_id, entry in self.entries(section).items():
            if "vector" not in entry:
                values[entry_id] = entry
            elif isinstance(entry.get("value"), Mapping):
                values[entry_id] = dict(entry["value"])
        return values

    def get_entry(self, section: str, entry_id: str) -> Optional["SyncEntry"]:
        """The versioned entry stored for ``entry_id``; ``None`` if absent or flat."""
        from je_auto_control.utils.config_sync.versions import SyncEntry, is_versioned
        body = self.sections.get(section, {}).get(entry_id)
        if body is None or not is_versioned(body):
            return None
        return SyncEntry.from_dict(entry_id, body)

    def put_entry(self, section: str, entry: "SyncEntry") -> None:
        """Store a versioned entry under its key."""
        self.sections.setdefault(section, {})[entry.key] = entry.to_dict()

    def sync_entries(self, section: str) -> Dict[str, "SyncEntry"]:
        """Every versioned entry of ``section``, tombstones and conflicts included."""
        from je_auto_control.utils.config_sync.versions import SyncEntry, is_versioned
        return {entry_id: SyncEntry.from_dict(entry_id, body)
                for entry_id, body in self.sections.get(section, {}).items()
                if is_versioned(body)}

    def conflicts(self) -> List[Tuple[str, "SyncEntry"]]:
        """``(section, entry)`` for every entry still holding concurrent changes."""
        found: List[Tuple[str, "SyncEntry"]] = []
        for section in sorted(self.sections):
            found.extend((section, entry) for _key, entry in sorted(self.sync_entries(section).items())
                         if entry.in_conflict)
        return found

    def peer_states(self) -> Dict[str, "PeerState"]:
        """The devices taking part in this bucket, by device id."""
        from je_auto_control.utils.config_sync.versions import PeerState
        return {device: PeerState.from_dict(device, body) for device, body in self.peers.items()}


def _finite(value: Any, what: str) -> float:
    """``value`` as a finite float, or :class:`ConfigSyncError`."""
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigSyncError(f"{what} must be a number, got {value!r}") from error
    if not math.isfinite(number):
        raise ConfigSyncError(f"{what} must be finite, got {value!r}")
    return number


def _section(name: Any, section: Any) -> Dict[str, Dict[str, Any]]:
    from je_auto_control.utils.config_sync.versions import SyncEntry, is_versioned
    if not isinstance(section, Mapping):
        raise ConfigSyncError(f"section {name!r} must be a mapping")
    entries: Dict[str, Dict[str, Any]] = {}
    for entry_id, entry in section.items():
        if not isinstance(entry, Mapping):
            raise ConfigSyncError(f"entry {name!r}/{entry_id!r} must be a mapping")
        entries[str(entry_id)] = dict(entry)
        _finite(entry.get("last_modified", 0), f"{name}/{entry_id} last_modified")
        if not isinstance(entry.get("deleted", False), bool):
            raise ConfigSyncError(f"entry {name!r}/{entry_id!r} deleted must be a boolean")
        if is_versioned(entry):
            SyncEntry.from_dict(str(entry_id), entry)
    return entries


def _peers(peers: Any) -> Dict[str, Dict[str, Any]]:
    from je_auto_control.utils.config_sync.versions import PeerState
    if not isinstance(peers, Mapping):
        raise ConfigSyncError("bucket peers must be a mapping")
    return {str(device): PeerState.from_dict(str(device), body).to_dict()
            for device, body in peers.items()}


__all__ = [
    "ConfigBucket", "ConfigSyncConflict", "ConfigSyncError", "FullResyncRequired",
    "OperationMismatchError",
    "TOMBSTONE_RETENTION_S", "WIRE_VERSION", "is_tombstone", "new_operation_id",
]
