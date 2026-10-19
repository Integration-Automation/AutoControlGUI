"""Materialize complete inert adapter profiles through the verified asset-generation publisher."""
from __future__ import annotations

import json
from hashlib import sha256
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterable, Mapping, Optional

from je_auto_control.utils.config_sync.adapter_schema import AdapterKind, KINDS
from je_auto_control.utils.config_sync.adapter_protocol import SyncAdapter
from je_auto_control.utils.config_sync.asset_models import AssetFile, AssetManifest, AssetSyncResult
from je_auto_control.utils.config_sync.assets import _check, sync_assets
from je_auto_control.utils.config_sync.blob_binding import BoundProfileAsset, ProfileAssetTransport, ProfileBundle
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.config_sync.workspace_preferences import _workspace_ini
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption

def profile_files(kind: AdapterKind, values: Mapping[str, dict[str, object]],
                    heads: Mapping[str, SyncEntry]) -> dict[str, bytes]:
    """Build native data files and a portable version index from one consistent adapter head view."""
    files: dict[str, bytes] = {}
    if kind == 'scripts':
        files = {'scripts/' + name: _json(value['actions']) for name, value in values.items()}
    else:
        name, content = _native_file(kind, values)
        files[name] = content
    files['profile/' + kind + '.json'] = _json({'schema_version': 1, 'kind': kind,
                                              'heads': {key: item.to_dict() for key, item in heads.items()}})
    return files


def _native_file(kind: AdapterKind, values: Mapping[str, dict[str, object]]) -> tuple[str, bytes]:
    if kind == 'locators':
        return 'locators.json', _json(values)
    if kind == 'address_book':
        return 'address_book.json', _json({'entries': list(values.values())})
    if kind == 'settings':
        return 'settings.json', _json({name: value['value'] for name, value in values.items()})
    if kind == 'workspace':
        return 'workspace.ini', _workspace_ini(values)
    id_field = 'binding_id' if kind == 'hotkeys' else 'trigger_id'
    return kind + '.json', _json({'schema_version': 1, kind: [dict(value, **{id_field: name})
                                                            for name, value in values.items()]})


def _json(value: object) -> bytes:
    encoded = _encoded({'data': value}, max_bytes=64 * 1024 * 1024)
    text = json.dumps(json.loads(encoded)['data'], ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return text.encode('ascii')


def materialize_sync_profile(adapters: Iterable[SyncAdapter], target_root: str | Path, *,
                               cancelled: Optional[Callable[[], bool]] = None) -> AssetSyncResult:
    """Publish all selected resolved definitions together; never replace active source files or start a runtime."""
    _check(cancelled)
    selected = tuple(islice(adapters, len(KINDS) + 1))
    if not 1 <= len(selected) <= len(KINDS):
        raise ConfigSyncError(f'materialization requires 1–{len(KINDS)} explicit adapter profiles')

    def checkpoint() -> bool:
        _check(cancelled)
        for item in selected:
            item.checkpoint()
        return False

    try:
        files, assets = _collect_files(selected, checkpoint)
        return _publish_files(files, assets, target_root, checkpoint)
    except (OSError, ConfigSyncError) as error:
        raise_caused_run_interruption(error)
        if isinstance(error, ConfigSyncError):
            raise
        raise ConfigSyncError('could not materialize a complete adapter profile') from error


def _collect_files(selected: tuple[SyncAdapter, ...], checkpoint: Callable[[], bool]
                   ) -> tuple[dict[str, bytes], dict[str, BoundProfileAsset]]:
    files: dict[str, bytes] = {}
    assets: dict[str, BoundProfileAsset] = {}
    kinds = set()
    for adapter in selected:
        checkpoint()
        if adapter.kind not in KINDS or adapter.kind in kinds:
            raise ConfigSyncError('a materialized profile can contain only one adapter per kind')
        kinds.add(adapter.kind)
        builder = getattr(adapter, 'profile_bundle', None)
        bundle = builder() if callable(builder) else ProfileBundle(adapter.profile_files())
        if not isinstance(bundle, ProfileBundle):
            raise ConfigSyncError('invalid adapter profile bundle')
        files.update(bundle.files)
        _collect_assets(assets, bundle)
    if not files:
        raise ConfigSyncError('materialization requires at least one adapter')
    if any(not isinstance(name, str) or not isinstance(body, bytes) for name, body in files.items()):
        raise ConfigSyncError('adapter profile files require relative names and binary contents')
    return files, assets


def _collect_assets(assets: dict[str, BoundProfileAsset], bundle: ProfileBundle) -> None:
    for item in bundle.assets:
        path = item.reference.path
        if path in assets and assets[path].reference != item.reference:
            raise ConfigSyncError('profile assets have conflicting portable destinations')
        assets[path] = item


def _publish_files(files: dict[str, bytes], assets: dict[str, BoundProfileAsset],
                     target_root: str | Path, checkpoint: Callable[[], bool]) -> AssetSyncResult:
    entries = tuple(AssetFile(name, sha256(body).hexdigest(), len(body)) for name, body in files.items())
    manifest = AssetManifest(entries + tuple(item.reference.file for item in assets.values()))
    with TemporaryDirectory(prefix='autocontrol-profile-') as temporary:
        source = Path(temporary)
        for name, body in files.items():
            checkpoint()
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        return sync_assets(manifest, ProfileAssetTransport(source, assets, target_root), cancelled=checkpoint)
