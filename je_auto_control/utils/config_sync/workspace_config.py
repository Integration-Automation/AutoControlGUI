"""Validate private multi-domain workspace descriptors without opening source files, credentials or databases."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Callable, Optional, cast

from je_auto_control.utils.config_sync.adapter_factory import adapter_from_profile
from je_auto_control.utils.config_sync.adapter_ledger import fingerprint
from je_auto_control.utils.config_sync.adapter_schema import KINDS
from je_auto_control.utils.config_sync.asset_commands import _root
from je_auto_control.utils.config_sync.asset_models import AssetFile
from je_auto_control.utils.config_sync.assets import _asset_path
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _identifier, _schema_one
from je_auto_control.utils.config_sync.outbox_models import normalize_sync_endpoint
from je_auto_control.utils.path_guard import PathPolicy


@dataclass(frozen=True)
class WorkspaceSpec:
    """Owned private descriptor values; public reports never expose local configuration or inline source values."""

    endpoint: str
    user_id: str
    outbox_path: Path
    asset_cache_path: Path
    profiles: tuple[dict[str, object], ...]
    roots: tuple[Path, ...]


def parse_workspace(value: dict[str, object], policy: Optional[PathPolicy],
                      cancelled: Optional[Callable[[], bool]]) -> WorkspaceSpec:
    """Resolve and authorize every configured source/state path before opening an owned workspace database."""
    body = _workspace_body(value)
    endpoint = normalize_sync_endpoint(cast(str, body['endpoint']))
    user_id = cast(str, body['user_id'])
    _identifier(user_id, 'workspace user_id')
    path = _root(_path(body['outbox_path']), policy)
    cache = _root(_path(body.get('asset_cache_path', str(path) + '.assets.sqlite3')), policy)
    profiles = _profiles(body['profiles'])
    for profile in profiles:
        profile['asset_cache_path'] = str(cache)
    identity: dict[str, object] = {'endpoint': endpoint, 'user_id': user_id, 'origin': 'validation'}
    roots = [path, cache, *_profile_roots(profiles, identity, policy, cancelled)]
    _disjoint_roles(path, cache, profiles)
    return WorkspaceSpec(endpoint, user_id, path, cache, profiles, tuple(roots))


def _workspace_body(value: dict[str, object]) -> dict[str, object]:
    required = {'schema_version', 'endpoint', 'user_id', 'outbox_path', 'profiles'}
    if (not isinstance(value, dict) or not required <= set(value)
            or not set(value) <= required | {'asset_cache_path'} or not _schema_one(value.get('schema_version'))):
        raise ConfigSyncError('invalid private workspace descriptor')
    return cast(dict[str, object], json.loads(_encoded(value)))


def _profiles(raw: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= len(KINDS):
        raise ConfigSyncError('workspace requires 1–7 explicit distinct profile kinds')
    profiles = tuple(_profile(item) for item in raw)
    if len({profile['kind'] for profile in profiles}) != len(profiles):
        raise ConfigSyncError('workspace cannot bind multiple profiles to the same kind')
    return profiles


def _profile_roots(profiles: tuple[dict[str, object], ...], identity: dict[str, object],
                     policy: Optional[PathPolicy], cancelled: Optional[Callable[[], bool]]) -> list[Path]:
    roots = []
    for profile in profiles:
        adapter_from_profile(dict(profile, schema_version=1, identity=identity),
                             path_policy=policy, cancelled=cancelled)
        state_path = _root(cast(str, profile['state_path']), policy)
        profile['state_path'] = str(state_path)
        roots.append(state_path)
        source = cast(dict[str, object], profile['source'])
        bindings = cast(dict[str, object], profile.get('bindings', {}))
        local = cast(dict[str, object], bindings.get('local_values', {}))
        for name in cast(dict[str, object], bindings.get('assets', {})):
            selected = _root(cast(str, local[name]), policy)
            local[name] = str(selected)
            roots.append(selected)
        if 'path' in source:
            source_path = _root(cast(str, source['path']), policy)
            source['path'] = str(source_path)
            roots.append(source_path)
    return roots


def _disjoint_roles(outbox: Path, cache: Path, profiles: tuple[dict[str, object], ...]) -> None:
    storage = {Path(cast(str, item['state_path'])) for item in profiles}
    if outbox in storage or cache in storage or outbox == cache:
        raise ConfigSyncError('workspace outbox and adapter storage paths overlap')
    storage.add(outbox)
    storage.add(cache)
    for profile in profiles:
        if _profile_sources(profile) & storage:
            raise ConfigSyncError('workspace source and storage paths overlap')


def _profile_sources(profile: dict[str, object]) -> set[Path]:
    source = cast(dict[str, object], profile['source'])
    bindings = cast(dict[str, object], profile.get('bindings', {}))
    local = cast(dict[str, object], bindings.get('local_values', {}))
    selected = {Path(cast(str, local[name])) for name in cast(dict[str, object], bindings.get('assets', {}))}
    if 'path' in source:
        root = Path(cast(str, source['path']))
        selected.add(root)
        if profile['kind'] == 'scripts':
            selected.update(_asset_path(root, AssetFile(name, '0' * 64, 0))
                            for name in cast(list[str], source.get('paths', [])))
    return selected


def _profile(raw: object) -> dict[str, object]:
    required = {'kind', 'state_path', 'source'}
    if (not isinstance(raw, dict) or not required <= set(raw)
            or not set(raw) <= required | {'profile_id', 'bindings'}):
        raise ConfigSyncError('workspace profiles require kind/state_path/source without a separate identity')
    if not isinstance(raw['kind'], str) or raw['kind'] not in KINDS:
        raise ConfigSyncError('unsupported workspace profile kind')
    return dict(raw)


def _path(raw: object) -> str:
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 4096 or not raw.isprintable():
        raise ConfigSyncError('workspace outbox path must be bounded printable text')
    return raw


def profile_binding(profile: dict[str, object]) -> str:
    """Pin one kind to stable adapter state instead of silently forking its actor counters on another database."""
    return fingerprint({'kind': profile['kind'], 'path': os.path.normcase(cast(str, profile['state_path'])),
                        'profile_id': profile.get('profile_id', 'main')})


def source_configuration(profile: dict[str, object]) -> str:
    """Bind reset fingerprints to source/reference rules without hashing raw definitions or local values."""
    source = cast(dict[str, object], profile['source'])
    selector = {'path': os.path.normcase(cast(str, source['path']))} if 'path' in source else {'inline': True}
    bindings = cast(dict[str, object], profile.get('bindings', {}))
    body = {'binding': profile_binding(profile), 'source': selector, 'fields': bindings.get('fields', {})}
    if bindings.get('assets'):
        body['assets'] = bindings['assets']
    return fingerprint(body)


def asset_cache_binding(path: Path) -> str:
    """Pin the new cache role independently so existing adapter state bindings and reset baseline hashes stay valid."""
    return fingerprint({'path': os.path.normcase(str(path))})
