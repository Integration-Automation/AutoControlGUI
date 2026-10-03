"""Compatible config bucket shapes and legacy timestamp editing helpers."""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping

from je_auto_control.utils.exception.exceptions import AutoControlException

#: Legacy timestamp-merge retention only. Protected causal synchronization
#: never uses elapsed wall-clock time to discard deletion evidence.
TOMBSTONE_RETENTION_S = 30 * 24 * 3600.0


def is_tombstone(entry: Mapping[str, Any]) -> bool:
    """Whether ``entry`` records a deletion rather than a value."""
    return entry.get("deleted") is True


class ConfigSyncError(AutoControlException, RuntimeError):
    """Raised on network errors or schema validation failures."""


@dataclass
class ConflictRecord:
    """One entry that lost a last-modified race during the merge."""
    section: str
    entry_id: str
    dropped: Dict[str, Any]
    kept: Dict[str, Any]


@dataclass
class ConfigBucket:
    """JSON-shaped bucket persisted on the sync server.

    Each section maps an opaque ``entry_id`` to a JSON object carrying legacy
    ``last_modified`` or causal ``_sync`` metadata. Unknown sections are passed
    through untouched so callers can extend the schema without
    touching the syncer.

    A removed entry stays in ``sections`` as a tombstone
    (``{"deleted": True, "last_modified": ...}``) so the deletion wins the
    merge against an older copy on another machine instead of being undone
    by it; :meth:`entries` excludes tombstones and unresolved causal conflicts.
    """
    user_id: str
    sections: Dict[str, Dict[str, Dict[str, Any]]] = field(
        default_factory=dict,
    )
    revision: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Return a copied JSON-shaped bucket including its committed revision."""
        return asdict(self)

    @classmethod
    def from_dict(cls, body: Mapping[str, Any]) -> "ConfigBucket":
        """Validate bucket mappings and legacy stamps while preserving causal wire data."""
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
        )

    def upsert(self, section: str, entry_id: str,
               entry: Mapping[str, Any]) -> None:
        """Add or replace an entry, stamping it with the current time.

        A ``last_modified`` already in ``entry`` is kept, so drop it when
        editing an entry read back from a bucket -- otherwise the edit keeps
        its old stamp and loses the merge to any newer remote copy.
        """
        body = dict(entry)
        body["last_modified"] = float(body.get("last_modified", time.time()))
        self.sections.setdefault(section, {})[entry_id] = body

    def remove(self, section: str, entry_id: str) -> bool:
        """Replace a live entry with a tombstone; False when there was none.

        Dropping the entry outright let the next sync bring it straight back
        from the server, where it still existed. The tombstone is stamped no
        earlier than the entry it deletes, so a clock running behind cannot
        make the deletion lose to the value it removed.
        """
        entry = self.sections.get(section, {}).get(entry_id)
        if entry is None or is_tombstone(entry):
            return False
        stamp = max(time.time(), float(entry.get("last_modified", 0)))
        self.sections[section][entry_id] = {"deleted": True, "last_modified": stamp}
        return True

    def entries(self, section: str) -> Dict[str, Dict[str, Any]]:
        """Return live definitions, excluding tombstones and unresolved conflicts."""
        return {entry_id: entry for entry_id, entry in self.sections.get(section, {}).items()
                if not is_tombstone(entry) and 'sync_conflict' not in entry}


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
    return entries
