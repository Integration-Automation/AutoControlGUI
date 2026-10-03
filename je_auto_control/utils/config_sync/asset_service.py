"""Scoped file-backed asset transport shared by executor, MCP and GUI callers."""
from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any, Dict, Iterator, Optional

from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.utils.rbac.authorization import require_command

from .assets import AssetManifest, AssetSpec, AssetSyncError, sync_assets
from .definition_files import read_object


class DirectoryAssetTransport:  # pylint: disable=too-few-public-methods  # reason: single-method transport protocol
    """Read relative source bytes beneath an authorized directory without following links."""

    def __init__(self, root: Path) -> None:
        self._root = scoped_path(root, operation='read')

    def iter_chunks(self, asset: AssetSpec) -> Iterator[bytes]:
        """Stream the named asset; the receiver verifies its manifest identity."""
        path = self._root / asset.path
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise AssetSyncError('asset source cannot traverse a symlink')
        checked = scoped_path(path, operation='read')
        if not checked.resolve().is_relative_to(self._root.resolve()):
            raise AssetSyncError('asset source escapes its authorized directory')
        with checked.open('rb') as stream:
            yield from iter(lambda: stream.read(65536), b'')


def config_sync_assets(manifest_path: str, source_root: str, destination_root: str, *,
                       cancel: Optional[Event] = None) -> Dict[str, Any]:
    """Receive a local asset bundle using hash/size checks and atomic per-file publication."""
    require_command('AC_config_sync_assets')
    document = read_object(Path(manifest_path))
    try:
        assets = tuple(AssetSpec(**item) for item in document['assets'])
    except (KeyError, TypeError) as error:
        raise AssetSyncError('manifest requires an assets array of path/sha256/size objects') from error
    root = scoped_path(destination_root, operation='write')
    for asset in assets:
        scoped_path(root / asset.path, operation='write')
    result = sync_assets(AssetManifest(root, assets), DirectoryAssetTransport(Path(source_root)), cancel=cancel)
    return {'saved': list(result.saved), 'cancelled': result.cancelled}
