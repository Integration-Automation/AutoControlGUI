"""Resolve canonical workspace preferences only from the exact conflict-free heads explicitly reviewed."""
from itertools import islice
from typing import Iterable, Mapping

from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.config_sync.workspace_preferences import _DEFAULTS, _validate_workspace_record


def reviewed_ids(observed: Iterable[str]) -> frozenset[str]:
    """Validate a bounded review before opening any workspace storage."""
    if isinstance(observed, (str, bytes)) or not isinstance(observed, Iterable):
        raise ConfigSyncError('workspace preferences require reviewed change identifiers')
    values = list(islice(observed, 1025))
    if len(values) > 1024 or any(not isinstance(value, str) or not value or len(value) > 128 for value in values):
        raise ConfigSyncError('invalid workspace preference review identifiers')
    if len(set(values)) != len(values):
        raise ConfigSyncError('duplicate workspace preference review identifiers')
    return frozenset(values)


def reviewed_preferences(heads: Mapping[str, SyncEntry], observed: frozenset[str]) -> dict[str, object]:
    """Return four validated native values; deletions and missing keys use safe defaults."""
    if set(heads) != observed:
        raise ConfigSyncError('workspace preferences changed after review')
    resolved = dict(_DEFAULTS)
    seen: set[str] = set()
    for entry in heads.values():
        if entry.entry_id in seen:
            raise ConfigSyncError('workspace preferences contain an unresolved conflict')
        seen.add(entry.entry_id)
        _validate_workspace_record(entry.entry_id, entry.value, deleted=entry.is_deleted)
        if not entry.is_deleted:
            resolved[entry.entry_id] = entry.value['value']
    return resolved
