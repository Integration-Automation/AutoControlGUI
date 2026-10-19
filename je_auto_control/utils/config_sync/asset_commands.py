"""Private local asset-manifest and verified-generation commands share live path and cancellation authority."""
from concurrent.futures import CancelledError
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from je_auto_control.utils.config_sync.asset_models import AssetManifest
from je_auto_control.utils.config_sync.assets import DirectoryAssetTransport, build_asset_manifest, sync_assets
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.path_guard import PathPolicy, validate_path

_Cancelled = Optional[Callable[[], bool]]


def _root(path: str | Path, policy: Optional[PathPolicy]) -> Path:
    candidate = validate_path(path)
    return policy.validate(candidate, operation='sync assets') if policy is not None else candidate


def _checkpoint(roots: tuple[Path, ...], policy: Optional[PathPolicy], cancelled: _Cancelled) -> bool:
    if cancelled is not None and cancelled():
        raise CancelledError()
    for root in roots:
        if _root(root, policy) != root:
            raise ConfigSyncError('asset root changed during transfer')
    return False


def _build_sync_asset_manifest(source_root: str, paths: list[str], *,
                                path_policy: Optional[PathPolicy] = None,
                                cancelled: _Cancelled = None) -> dict[str, object]:
    """Read an explicit confined local selection into a portable content-addressed manifest."""
    _checkpoint((), path_policy, cancelled)
    if not isinstance(paths, list):
        raise ConfigSyncError('asset paths must be a JSON array')
    source = _root(source_root, path_policy)
    manifest = build_asset_manifest(source, paths, cancelled=lambda: _checkpoint((source,), path_policy, cancelled))
    return {'manifest': manifest.to_dict(), 'digest': manifest.digest}


def _sync_asset_generation(manifest: dict[str, object], source_root: str, target_root: str, *,
                            path_policy: Optional[PathPolicy] = None,
                            cancelled: _Cancelled = None) -> dict[str, object]:
    """Copy an explicit local selection into one verified immutable generation without executing its data."""
    _checkpoint((), path_policy, cancelled)
    value = AssetManifest.from_dict(manifest)
    source, target = _root(source_root, path_policy), _root(target_root, path_policy)
    transport = DirectoryAssetTransport(source, target)
    result = sync_assets(value, transport, cancelled=lambda: _checkpoint((source, target), path_policy, cancelled))
    reply = asdict(result)
    reply['directory'] = str(result.directory)
    return reply
