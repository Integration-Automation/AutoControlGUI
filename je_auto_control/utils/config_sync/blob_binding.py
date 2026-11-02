"""Capture explicitly named source assets and stream complete inert profile bundles from verified content caches."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, Callable, Mapping, Optional, cast

from je_auto_control.utils.config_sync.asset_models import AssetFile, MAX_FILE_BYTES
from je_auto_control.utils.config_sync.assets import DirectoryAssetTransport, _source_file
from je_auto_control.utils.config_sync.blob_models import ASSET_TAG, CHUNK_BYTES, SyncAssetBlob, SyncAssetReference
from je_auto_control.utils.config_sync.blob_store import SyncAssetStore
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption


def asset_reference(value: object) -> Optional[SyncAssetReference]:
    """Recognize only an exact reserved asset marker; malformed markers never become generic application data."""
    if isinstance(value, dict) and ASSET_TAG in value:
        return SyncAssetReference.from_dict(value)
    return None


def asset_references(value: object, depth: int = 0) -> tuple[SyncAssetReference, ...]:
    """Collect a bounded portable reference set without reading machine paths or resolving any secret."""
    if depth > 32:
        raise ConfigSyncError('asset reference traversal exceeds the nesting limit')
    reference = asset_reference(value)
    if reference is not None:
        return (reference,)
    values = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    result = {item for child in values for item in asset_references(child, depth + 1)}
    return tuple(sorted(result, key=lambda item: (item.path, item.blob.sha256)))


def convert_asset_bindings(value: object, aliases: Mapping[str, str],
                           resolver: Optional[Callable[[str], SyncAssetReference]], depth: int = 0) -> object:
    """Replace only explicitly designated local aliases with frozen content references after private source export."""
    if depth > 32:
        raise ConfigSyncError('asset binding traversal exceeds the nesting limit')
    if isinstance(value, dict):
        raw = value.get('$autocontrol_ref')
        if isinstance(raw, dict) and raw.get('kind') == 'local' and raw.get('name') in aliases:
            if resolver is None:
                raise ConfigSyncError('asset source capture requires a configured content cache')
            return resolver(cast(str, raw['name'])).to_dict()
        return {key: convert_asset_bindings(item, aliases, resolver, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [convert_asset_bindings(item, aliases, resolver, depth + 1) for item in value]
    return value


def capture_asset(source: str, target: str, store: SyncAssetStore, user_id: str,
                   checkpoint: Callable[[], None]) -> SyncAssetReference:
    """Freeze selected raw bytes into bounded immutable chunks before recording a source's causal fingerprint."""
    try:
        return _capture_asset(source, target, store, user_id, checkpoint)
    except (OSError, AutoControlException) as error:
        raise_caused_run_interruption(error)
        if isinstance(error, AutoControlException):
            raise
        raise ConfigSyncError('cannot capture selected profile asset') from error


def _capture_asset(source: str, target: str, store: SyncAssetStore, user_id: str,
                    checkpoint: Callable[[], None]) -> SyncAssetReference:
    checkpoint()
    path = Path(source).expanduser().resolve()
    selected = _source_file(path.parent, AssetFile(path.name, '0' * 64, 0))
    if selected.stat().st_size > MAX_FILE_BYTES:
        raise ConfigSyncError('selected profile asset exceeds 64 MiB')
    digest = sha256()
    size = 0
    chunks = []
    with selected.open('rb') as stream:
        while True:
            checkpoint()
            body = stream.read(CHUNK_BYTES)
            if not body:
                break
            size += len(body)
            if size > MAX_FILE_BYTES:
                raise ConfigSyncError('selected profile asset exceeds 64 MiB')
            chunk_id = sha256(body).hexdigest()
            store.put_chunk(user_id, chunk_id, body)
            chunks.append(chunk_id)
            digest.update(body)
    blob = SyncAssetBlob(digest.hexdigest(), size, tuple(chunks))
    checkpoint()
    store.commit(user_id, blob)
    return SyncAssetReference(target, blob)


@dataclass(frozen=True)
class BoundProfileAsset:
    """A private read capability for one portable reference, retained only while publishing an inert generation."""

    reference: SyncAssetReference
    store: SyncAssetStore
    user_id: str
    checkpoint: Callable[[], None]

    def open(self) -> BinaryIO:
        """Verify cached bytes before handing an owned stream to the generation publisher."""
        self.checkpoint()
        stream = self.store.open(self.user_id, self.reference.blob)
        try:
            self.checkpoint()
            return stream
        except BaseException:  # reason: close the newly owned stream before preserving any cancellation or hard signal
            stream.close()
            raise


@dataclass(frozen=True)
class ProfileBundle:
    """One consistent adapter head view produces native metadata and exact associated asset capabilities together."""

    files: Mapping[str, bytes]
    assets: tuple[BoundProfileAsset, ...] = ()


class ProfileAssetTransport(DirectoryAssetTransport):
    """Stream generated metadata and verified cached blobs into the existing all-or-none asset publisher."""

    def __init__(self, source_root: str | Path, assets: Mapping[str, BoundProfileAsset],
                   target_root: str | Path) -> None:
        super().__init__(source_root, target_root)
        self._assets = assets

    def open(self, asset: AssetFile) -> BinaryIO:
        """Open only the exact descriptor selected before generation staging."""
        bound = self._assets.get(asset.path)
        if bound is None:
            return super().open(asset)
        if bound.reference.file != asset:
            raise ConfigSyncError('profile asset changed after generation planning')
        return bound.open()
