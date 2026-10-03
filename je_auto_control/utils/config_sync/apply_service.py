"""Explicit conflict resolution and inert definition publication after asset verification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Union, cast

from je_auto_control.utils.json_store.json_store import _file_lock
from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.utils.rbac.authorization import require_command

from .assets import AssetSpec
from .causal_bucket import _decode, causal_remove, causal_upsert
from .definition_adapter import JsonDefinitionAdapter
from .definition_files import (
    SECTIONS, checked_sections, definition_hash, ensure_portable_bucket, inactive_definition, read_object, write_object,
)
from .models import ConfigBucket, ConfigSyncError
from .versions import SyncEntry

Choices = Union[Mapping[str, int], str]


def _resolve_choices(bucket: ConfigBucket, choices: Choices, device_id: str) -> None:
    selected = json.loads(choices) if isinstance(choices, str) else dict(choices)
    if not isinstance(selected, dict):
        raise ConfigSyncError('conflict choices must map section/identifier to an alternative index')
    for identity, index in selected.items():
        if not isinstance(identity, str):
            raise ConfigSyncError('conflict choice identity must be a string')
        section, separator, entry_id = identity.partition('/')
        if section not in SECTIONS or not separator:
            raise ConfigSyncError('invalid conflict choice identity')
        alternatives = bucket.sections.get(section, {}).get(entry_id, {}).get('sync_conflict')
        if not _valid_choice(alternatives, index):
            raise ConfigSyncError('conflict choice must select an existing alternative')
        chosen = _decode(cast(List[Dict[str, Any]], alternatives)[index])
        if chosen.is_deleted:
            causal_remove(bucket, section, entry_id, device_id=device_id)
        else:
            causal_upsert(bucket, section, entry_id, chosen.value, device_id=device_id)


def _valid_choice(alternatives: Any, index: Any) -> bool:
    return (isinstance(alternatives, list) and isinstance(index, int) and not isinstance(index, bool)
            and 0 <= index < len(alternatives))


def _asset_matches(root: Path, asset: AssetSpec) -> bool:
    original = root / asset.path
    if any(part.is_symlink() for part in (original, *original.parents)):
        return False
    path = scoped_path(original, operation='read')
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        return False
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return path.stat().st_size == asset.size and digest.hexdigest() == asset.sha256


def _assets_ready(root: Path, entry: SyncEntry) -> bool:
    manifest = entry.value.get('assets', [])
    if not isinstance(manifest, list):
        return False
    try:
        for definition in manifest:
            asset = AssetSpec(**definition)
            if not _asset_matches(root, asset):
                return False
    except (OSError, TypeError, ConfigSyncError):
        return False
    return True


def _apply_section(section: str, local: Dict[str, Dict[str, Any]], bucket: ConfigBucket,
                   root: Path, device_id: str) -> tuple[List[str], List[str]]:
    entries, blocked = {}, []
    for entry_id, value in bucket.sections.get(section, {}).items():
        if 'sync_conflict' in value:
            blocked.append(entry_id)
            continue
        entry = _decode(value)
        if not entry.is_deleted and not _assets_ready(root, entry):
            blocked.append(entry_id)
        else:
            entries[entry_id] = entry
    report = JsonDefinitionAdapter(section, local, device_id=device_id).apply(entries)
    for entry_id in report.applied:
        if section in {'hotkeys', 'triggers'} and entry_id in local:
            local[entry_id] = {**inactive_definition(section, local[entry_id]), 'enabled': False}
    return list(report.applied), blocked + list(report.unresolved)


def _apply_locked(destination: Path, preview_path: Path, state_path: Path, device_id: str,
                  choices: Choices) -> Dict[str, Any]:
    preview = read_object(preview_path)
    if preview.get('definitions_sha256') != definition_hash(destination):
        raise ConfigSyncError('local definitions changed since the synchronization preview')
    if preview.get('device_id') != device_id:
        raise ConfigSyncError('preview belongs to another device')
    bucket = ConfigBucket.from_dict(preview.get('bucket', {}))
    ensure_portable_bucket(bucket)
    _resolve_choices(bucket, choices, device_id)
    definitions = checked_sections(read_object(destination))
    applied: List[str] = []
    unresolved: List[str] = []
    for section in sorted(SECTIONS):
        written, blocked = _apply_section(section, definitions.setdefault(section, {}), bucket,
                                         destination.parent, device_id)
        applied.extend(f'{section}/{key}' for key in written)
        unresolved.extend(f'{section}/{key}' for key in blocked)
    if definition_hash(destination) != preview['definitions_sha256']:
        raise ConfigSyncError('local definitions changed during application')
    state = _applied_state(state_path, bucket, unresolved)
    write_object(destination, definitions)
    write_object(state_path, state.to_dict())
    return {'applied': applied, 'unresolved': unresolved,
            'conflicts': sum('sync_conflict' in value for section in SECTIONS
                             for value in bucket.sections.get(section, {}).values())}


def _applied_state(path: Path, bucket: ConfigBucket, unresolved: List[str]) -> ConfigBucket:
    previous = read_object(path, missing=True)
    state = ConfigBucket.from_dict(previous) if previous else ConfigBucket(bucket.user_id)
    if state.user_id != bucket.user_id:
        raise ConfigSyncError('preview and applied state belong to different accounts')
    state.revision = bucket.revision
    state.sections['__sync_devices__'] = bucket.sections.get('__sync_devices__', {})
    for section in SECTIONS:
        for key, value in bucket.sections.get(section, {}).items():
            if f'{section}/{key}' not in unresolved:
                state.sections.setdefault(section, {})[key] = value
    return state


def config_sync_apply(definitions_path: str, preview_path: str, state_path: str, device_id: str, *,
                      choices: Choices = '{}') -> Dict[str, Any]:
    """Apply reviewed entries against an unchanged baseline; explicit choices resolve concurrent versions.

    Missing local references/assets remain unresolved. Choices index the preserved
    ``sync_conflict`` array in the preview. Files are published atomically one at
    a time; local definitions remain inert and are never loaded into a runtime.
    """
    require_command('AC_config_sync_apply')
    destination = scoped_path(definitions_path, operation='write')
    try:
        with _file_lock(destination):
            return _apply_locked(destination, Path(preview_path), Path(state_path), device_id, choices)
    except (ValueError, OSError) as error:
        if isinstance(error, ConfigSyncError):
            raise
        raise ConfigSyncError('definition apply failed without activating any runtime') from error
