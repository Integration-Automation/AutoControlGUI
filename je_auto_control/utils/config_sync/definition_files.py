"""Strict local definition documents and portable causal snapshot persistence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.path_guard.policy import scoped_path

from .causal_bucket import _decode, _encode
from .definition_adapter import JsonDefinitionAdapter
from .definition_privacy import portable_definition
from .models import ConfigBucket, ConfigSyncError

SECTIONS = frozenset({'scripts', 'locators', 'hotkeys', 'triggers', 'address_book'})


def read_object(path: Path, *, missing: bool = False) -> Dict[str, Any]:
    """Read strict finite JSON; damaged state is never silently overwritten."""
    checked = scoped_path(path, operation='read')
    try:
        if missing and not checked.exists():
            return {}
        value = json.loads(checked.read_text(encoding='utf-8'),
                           parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        if not isinstance(value, dict):
            raise ConfigSyncError('definition document must be an object')
        return value
    except (OSError, ValueError) as error:
        raise ConfigSyncError('cannot read the definition document') from error


def write_object(path: Path, value: Mapping[str, Any]) -> None:
    """Write an authorized document atomically using the shared private-file writer."""
    checked = scoped_path(path, operation='write')
    try:
        checked.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(checked, json.dumps(dict(value), indent=2, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError) as error:
        raise ConfigSyncError('cannot persist the synchronization document') from error


def definition_hash(path: Path) -> str:
    """Hash the exact local bytes which an explicit apply must still match."""
    try:
        return hashlib.sha256(scoped_path(path, operation='read').read_bytes()).hexdigest()
    except OSError as error:
        raise ConfigSyncError('cannot snapshot the local definition file') from error


def checked_sections(document: Mapping[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Reject unknown sections and non-definition values before any local write."""
    if set(document) - SECTIONS:
        raise ConfigSyncError('definition document contains an unsupported section')
    result = {}
    for section, entries in document.items():
        if not isinstance(entries, dict) or not all(isinstance(key, str) and isinstance(value, dict)
                                                   for key, value in entries.items()):
            raise ConfigSyncError('each definition section must map identifiers to objects')
        result[section] = entries
    return result


def inactive_definition(section: str, value: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep activation and transient counters out of synchronized hotkey/trigger definitions."""
    result = dict(value)
    if section in {'hotkeys', 'triggers'}:
        result = {key: item for key, item in result.items()
                  if key not in {'enabled', 'fired'} and not key.startswith('_')}
        if 'children' in result:
            result['children'] = [inactive_definition(section, child) for child in result['children']]
    return result


def snapshot_definitions(definitions_path: Path, state_path: Path, user_id: str, device_id: str
                         ) -> Tuple[ConfigBucket, str]:
    """Persist only portable causal state, retaining operation IDs after reopening."""
    digest = definition_hash(definitions_path)
    definitions = checked_sections(read_object(definitions_path))
    stored = read_object(state_path, missing=True)
    bucket = ConfigBucket.from_dict(stored) if stored else ConfigBucket(user_id)
    if bucket.user_id != user_id:
        raise ConfigSyncError('local synchronization state belongs to another account')
    ensure_portable_bucket(bucket)
    for section in SECTIONS:
        previous = bucket.sections.get(section, {})
        if any('sync_conflict' in value for value in previous.values()):
            raise ConfigSyncError('local conflicts require an explicit resolution before another exchange')
        state = {key: _decode(value) for key, value in previous.items()}
        values = {key: inactive_definition(section, value) for key, value in definitions.get(section, {}).items()}
        entries = JsonDefinitionAdapter(section, values, device_id=device_id, state=state).snapshot()
        bucket.sections[section] = {key: _encode(value) for key, value in entries.items()}
    if definition_hash(definitions_path) != digest:
        raise ConfigSyncError('local definitions changed during snapshot')
    write_object(state_path, bucket.to_dict())
    return bucket, digest


def ensure_portable_bucket(bucket: ConfigBucket) -> None:
    """Reject confidential incoming literals before preview persistence or command output."""
    if set(bucket.sections) - (SECTIONS | {'__sync_devices__'}):
        raise ConfigSyncError('server bucket contains an unsupported definition section')
    for section in bucket.sections:
        for entry in bucket.sections.get(section, {}).values():
            alternatives = entry.get('sync_conflict', [entry])
            for alternative in alternatives:
                value = _decode(alternative).value
                if portable_definition(value) != dict(value):
                    raise ConfigSyncError('server definition contains confidential local data')
