"""Build private local adapter profiles from explicit JSON source descriptors with live path/cancellation authority."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional, cast

from je_auto_control.utils.config_sync.adapter_references import SyncBindings
from je_auto_control.utils.config_sync.adapter_protocol import SyncAdapter
from je_auto_control.utils.config_sync.adapter_schema import AdapterKind, KINDS
from je_auto_control.utils.config_sync.adapter_sources import address_record_values, read_json
from je_auto_control.utils.config_sync.adapter_state import SyncAdapterState
from je_auto_control.utils.config_sync.adapters import ScriptSyncAdapter, _DomainAdapter
from je_auto_control.utils.config_sync.asset_commands import _checkpoint, _root
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _schema_one
from je_auto_control.utils.config_sync.outbox_models import SyncLocalIdentity, normalize_sync_endpoint
from je_auto_control.utils.config_sync.workspace_preferences import _read_workspace_preferences
from je_auto_control.utils.path_guard import PathPolicy

_Cancelled = Optional[Callable[[], bool]]


def adapter_from_profile(profile: dict[str, object], *, path_policy: Optional[PathPolicy] = None,
                            cancelled: _Cancelled = None) -> SyncAdapter:
    """Construct a lazy adapter from private JSON configuration; no source, vault or database is opened here."""
    _checkpoint((), path_policy, cancelled)
    body = _profile(profile)
    identity = _identity(body['identity'])
    kind = cast(AdapterKind, body['kind'])
    source = cast(dict[str, object], body['source'])
    state_path = _root(cast(str, body['state_path']), path_policy)
    source_path = _source_path(source, path_policy)
    roots = (state_path,) if source_path is None else (state_path, source_path)

    def checkpoint() -> None:
        _checkpoint(roots, path_policy, cancelled)

    state = SyncAdapterState(state_path, identity, profile=cast(str, body.get('profile_id', 'main')),
                              checkpoint=checkpoint)
    bindings = SyncBindings.from_dict(cast(dict[str, object], body.get('bindings', {})))
    if kind == 'scripts' and source_path is not None:
        paths = source.get('paths', [])
        if not isinstance(paths, list):
            raise ConfigSyncError('script profile paths require a JSON array')
        return ScriptSyncAdapter(source_path, state, paths=paths, bindings=bindings)
    reader = _reader(kind, source, source_path)
    return _DomainAdapter(kind, reader, state, bindings)


def _profile(value: dict[str, object]) -> dict[str, object]:
    required = {'schema_version', 'kind', 'state_path', 'identity', 'source'}
    optional = {'profile_id', 'bindings'}
    if not isinstance(value, dict) or not required <= set(value) or not set(value) <= required | optional:
        raise ConfigSyncError('invalid private adapter profile fields')
    if not _schema_one(value['schema_version']) or not isinstance(value['kind'], str) or value['kind'] not in KINDS:
        raise ConfigSyncError('unsupported adapter profile schema or kind')
    if not isinstance(value['source'], dict):
        raise ConfigSyncError('adapter profile source must be an object')
    _path(value['state_path'])
    return cast(dict[str, object], json.loads(_encoded(value)))


def _identity(raw: object) -> SyncLocalIdentity:
    required = {'endpoint', 'user_id', 'origin'}
    if (not isinstance(raw, dict) or not required <= set(raw)
            or not set(raw) <= required | {'epoch', 'confirmed_revision'}):
        raise ConfigSyncError('invalid adapter identity descriptor')
    endpoint = normalize_sync_endpoint(cast(str, raw['endpoint']))
    return SyncLocalIdentity(endpoint, cast(str, raw['user_id']), cast(str, raw['origin']),
                             cast(int, raw.get('epoch', 0)), cast(int, raw.get('confirmed_revision', 0)))


def _source_path(source: dict[str, object], policy: Optional[PathPolicy]) -> Optional[Path]:
    if 'records' in source:
        if set(source) != {'records'}:
            raise ConfigSyncError('inline adapter sources cannot also select filesystem paths')
        return None
    if 'path' not in source or not set(source) <= {'path', 'paths'}:
        raise ConfigSyncError('adapter source requires an explicit path or inline records')
    return _root(_path(source['path']), policy)


def _path(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or not value.isprintable() or len(value) > 4096:
        raise ConfigSyncError('adapter paths require bounded printable text')
    return value


def _reader(kind: AdapterKind, source: dict[str, object], path: Optional[Path]
               ) -> Callable[[], dict[str, dict[str, object]]]:
    if path is None:
        records = _inline_records(kind, source['records'])
        return lambda: cast(dict[str, dict[str, object]], json.loads(_encoded(cast(dict[str, object], records))))
    if 'paths' in source:
        raise ConfigSyncError('only script-directory sources accept a paths selection')
    return lambda: _file_records(kind, path)


def _file_records(kind: AdapterKind, path: Path) -> dict[str, dict[str, object]]:
    if not path.parent.is_dir():
        raise ConfigSyncError('adapter source parent directory is unavailable')
    if kind == 'workspace':
        return _read_workspace_preferences(path)
    raw = read_json(path) if path.exists() else {}
    if kind == 'settings':
        return _settings_file(raw)
    if kind == 'address_book':
        return _address_file(raw)
    if kind in {'hotkeys', 'triggers'}:
        return _binding_file(kind, raw)
    return _inline_records(kind, raw)


def _settings_file(raw: object) -> dict[str, dict[str, object]]:
    if not isinstance(raw, dict):
        raise ConfigSyncError('working settings require a JSON object')
    return {name: {'value': value} for name, value in raw.items()}


def _address_file(raw: object) -> dict[str, dict[str, object]]:
    if not isinstance(raw, dict) or not isinstance(raw.get('entries', []), list):
        raise ConfigSyncError('address-book source requires the native entries array')
    return _addresses(raw.get('entries', []))


def _binding_file(kind: AdapterKind, raw: object) -> dict[str, dict[str, object]]:
    if raw == {}:
        return {}
    if (not isinstance(raw, dict) or set(raw) != {'schema_version', kind}
            or not _schema_one(raw['schema_version'])):
        raise ConfigSyncError('invalid local binding/trigger profile file')
    return _record_array(kind, raw[kind])


def _inline_records(kind: AdapterKind, raw: object) -> dict[str, dict[str, object]]:
    if kind == 'address_book' and isinstance(raw, list):
        return _addresses(raw)
    if kind in {'hotkeys', 'triggers'} and isinstance(raw, list):
        return _record_array(kind, raw)
    if not isinstance(raw, dict) or len(raw) > 1000:
        raise ConfigSyncError('adapter source records require a bounded object')
    result = {}
    for entry_id, value in raw.items():
        if not isinstance(value, dict):
            raise ConfigSyncError('adapter source values must be definition objects')
        result[entry_id] = _runtime_fields(value) if kind in {'hotkeys', 'triggers'} else dict(value)
    return result


def _record_array(kind: AdapterKind, raw: object) -> dict[str, dict[str, object]]:
    if not isinstance(raw, list) or len(raw) > 1000:
        raise ConfigSyncError('binding/trigger records require a bounded array')
    key = 'binding_id' if kind == 'hotkeys' else 'trigger_id'
    result = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get(key), str):
            raise ConfigSyncError('binding/trigger records need their native identifier')
        value = dict(item)
        entry_id = cast(str, value.pop(key))
        if entry_id in result:
            raise ConfigSyncError('duplicate binding/trigger definition ID')
        result[entry_id] = _runtime_fields(value)
    return result


def _runtime_fields(value: dict[str, object], depth: int = 0) -> dict[str, object]:
    if depth > 16:
        raise ConfigSyncError('trigger profiles exceed the nesting limit')
    result = _local_flags(value)
    if 'children' in result:
        children = result['children']
        if not isinstance(children, list) or not all(isinstance(child, dict) for child in children):
            raise ConfigSyncError('invalid local child-trigger data')
        result['children'] = [_runtime_fields(child, depth + 1) for child in children]
    return result


def _local_flags(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    enabled = result.pop('enabled', False)
    fired = result.pop('fired', 0)
    if not isinstance(enabled, bool) or isinstance(fired, bool) or not isinstance(fired, int) or fired < 0:
        raise ConfigSyncError('invalid local runtime flags')
    return result


def _addresses(raw: object) -> dict[str, dict[str, object]]:
    if not isinstance(raw, list) or len(raw) > 1000 or not all(isinstance(item, dict) for item in raw):
        raise ConfigSyncError('saved addresses require a bounded native entries array')
    return address_record_values(raw)
