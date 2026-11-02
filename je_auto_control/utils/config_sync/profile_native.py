"""Validate complete native profile generations against sealed portable heads before native working-copy loading."""
import json
from pathlib import Path
from typing import Optional, cast

from je_auto_control.utils.config_sync.adapter_ledger import MAX_HEAD_BYTES
from je_auto_control.utils.config_sync.adapter_profiles import profile_files
from je_auto_control.utils.config_sync.adapter_schema import AdapterKind, KINDS, validate_record
from je_auto_control.utils.config_sync.adapter_state import _validate_incoming
from je_auto_control.utils.config_sync.adapters import _disabled
from je_auto_control.utils.config_sync.asset_models import AssetManifest, MAX_FILE_BYTES
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _schema_one
from je_auto_control.utils.config_sync.profile_bindings import ProfileBindings
from je_auto_control.utils.config_sync.profile_models import ProfileRecords
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.config_sync.workspace_preferences import _DEFAULTS, _read_workspace_preferences
from je_auto_control.utils.path_guard import PathPolicy


def native_profile(files: Path, manifest: AssetManifest, root: Path, policy: Optional[PathPolicy]
                   ) -> tuple[ProfileRecords, dict[str, bytes]]:
    """Return rebound native snapshots and replacement files only after all source formats agree with their heads."""
    selections = [item.path for item in manifest.files if item.path.startswith('profile/')]
    if not 1 <= len(selections) <= len(KINDS):
        raise ConfigSyncError('native profile requires one metadata file per selected kind')
    records: ProfileRecords = {}
    replacements: dict[str, bytes] = {}
    expected: set[str] = set()
    bindings = ProfileBindings(root, manifest, policy)
    for name in selections:
        kind = _metadata_kind(name)
        heads = _heads(files / name, kind)
        originals = _native_records(files, kind, heads)
        expected.update(_canonical_files(files, kind, originals, heads))
        values = _bind_records(kind, originals, heads, bindings)
        records[kind] = values
        replacements.update(profile_files(kind, values, heads))
    if {item.path for item in manifest.files} != expected | bindings.assets:
        raise ConfigSyncError('native profile contains missing or unreferenced generation files')
    return records, replacements


def _metadata_kind(name: str) -> AdapterKind:
    kind = cast(AdapterKind, Path(name).stem)
    if kind not in KINDS or name != 'profile/' + kind + '.json':
        raise ConfigSyncError('unknown native profile metadata')
    return kind


def _canonical_files(files: Path, kind: AdapterKind, originals: dict[str, dict[str, object]],
                        heads: dict[str, SyncEntry]) -> dict[str, bytes]:
    canonical = profile_files(kind, originals, heads)
    for path, body in canonical.items():
        if not (files / path).is_file() or (files / path).read_bytes() != body:
            raise ConfigSyncError('native profile files differ from their canonical definitions')
    return canonical


def _read(path: Path) -> object:
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ConfigSyncError('native profile document is missing or oversized')
    raw = json.loads(path.read_text(encoding='utf-8'))
    _encoded({'data': raw}, max_bytes=MAX_FILE_BYTES + 32)
    return raw


def _head_body(path: Path, kind: AdapterKind) -> dict[str, object]:
    body = _read(path)
    if not isinstance(body, dict) or set(body) != {'schema_version', 'kind', 'heads'}:
        raise ConfigSyncError('invalid native profile head metadata')
    if (not _schema_one(body['schema_version']) or body['kind'] != kind
            or not isinstance(body['heads'], dict) or len(body['heads']) > 10000):
        raise ConfigSyncError('invalid native profile head metadata')
    return cast(dict[str, object], body['heads'])


def _heads(path: Path, kind: AdapterKind) -> dict[str, SyncEntry]:
    raw = _head_body(path, kind)
    heads = {key: SyncEntry.from_dict(cast(dict[str, object], value)) for key, value in raw.items()}
    size = 0
    seen = set()
    for key, entry in heads.items():
        _validate_incoming(kind, {key: entry})
        size += len(_encoded(entry.to_dict()))
        if entry.entry_id in seen:
            raise ConfigSyncError('native profile retains unresolved causal alternatives')
        seen.add(entry.entry_id)
    if size > MAX_HEAD_BYTES:
        raise ConfigSyncError('native profile head metadata exceeds sixteen MiB')
    return heads


def _native_records(files: Path, kind: AdapterKind, heads: dict[str, SyncEntry]) -> dict[str, dict[str, object]]:
    active = sorted(entry.entry_id for entry in heads.values() if not entry.is_deleted)
    if kind == 'scripts':
        return {name: {'actions': _read(files / 'scripts' / name)} for name in active}
    if kind == 'workspace':
        return _workspace_records(files)
    raw = _read(files / (kind + '.json'))
    if kind in {'locators', 'settings'}:
        return _native_map(kind, raw, active)
    return _native_array(kind, raw, active)


def _workspace_records(files: Path) -> dict[str, dict[str, object]]:
    values = dict(_DEFAULTS)
    stored = _read_workspace_preferences(files / 'workspace.ini')
    values.update({name: value['value'] for name, value in stored.items()})
    return {name: {'value': value} for name, value in values.items()}


def _native_map(kind: AdapterKind, raw: object, active: list[str]) -> dict[str, dict[str, object]]:
    if not isinstance(raw, dict) or set(raw) != set(active):
        raise ConfigSyncError('native map differs from the selected head identifiers')
    return {name: {'value': value} if kind == 'settings' else _record(value) for name, value in raw.items()}


def _native_array(kind: AdapterKind, raw: object, active: list[str]) -> dict[str, dict[str, object]]:
    if not isinstance(raw, dict):
        raise ConfigSyncError('native record file must be an object')
    if kind == 'address_book':
        return _addresses(raw, active)
    return _bindings(kind, raw, active)


def _addresses(raw: dict[str, object], active: list[str]) -> dict[str, dict[str, object]]:
    if set(raw) != {'entries'} or not isinstance(raw['entries'], list) or len(raw['entries']) != len(active):
        raise ConfigSyncError('native address book differs from the selected heads')
    return {name: _record(value) for name, value in zip(active, raw['entries'])}


def _bindings(kind: AdapterKind, raw: dict[str, object], active: list[str]) -> dict[str, dict[str, object]]:
    if (set(raw) != {'schema_version', kind} or not _schema_one(raw['schema_version'])
            or not isinstance(raw[kind], list)):
        raise ConfigSyncError('invalid native binding/trigger envelope')
    id_field = 'binding_id' if kind == 'hotkeys' else 'trigger_id'
    result = {}
    for item in cast(list[object], raw[kind]):
        value = _record(item)
        identifier = value.pop(id_field, None)
        if not isinstance(identifier, str) or identifier in result:
            raise ConfigSyncError('invalid or duplicate native definition identifier')
        result[identifier] = value
    if set(result) != set(active):
        raise ConfigSyncError('native definitions differ from the selected heads')
    return result


def _record(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigSyncError('native definition requires an object')
    return dict(value)


def _bind_records(kind: AdapterKind, originals: dict[str, dict[str, object]], heads: dict[str, SyncEntry],
                    bindings: ProfileBindings) -> dict[str, dict[str, object]]:
    result = {}
    active = {entry.entry_id: entry for entry in heads.values() if not entry.is_deleted}
    if kind == 'workspace':
        for name in _DEFAULTS.keys() - active.keys():
            if originals[name] != {'value': _DEFAULTS[name]}:
                raise ConfigSyncError('absent workspace preferences must use native safe defaults')
            result[name] = originals[name]
    for name, entry in active.items():
        original = _strip_disabled(originals[name]) if kind in {'hotkeys', 'triggers'} else originals[name]
        validate_record(kind, name, original)
        value = cast(dict[str, object], bindings.value(entry.value, original))
        value = bindings.native_paths(kind, value)
        validate_record(kind, name, value)
        result[name] = _disabled(value) if kind in {'hotkeys', 'triggers'} else value
    return result


def _strip_disabled(value: dict[str, object], depth: int = 0) -> dict[str, object]:
    if depth > 16 or value.get('enabled') is not False:
        raise ConfigSyncError('every loaded hotkey/trigger node must be disabled')
    result = dict(value)
    del result['enabled']
    if 'children' in result:
        children = result['children']
        if not isinstance(children, list):
            raise ConfigSyncError('invalid native composite children')
        result['children'] = [_strip_disabled(_record(child), depth + 1) for child in children]
    return result
