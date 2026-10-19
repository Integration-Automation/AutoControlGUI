"""Stage and verify complete content-addressed asset generations before one atomic directory publication."""
from __future__ import annotations

from concurrent.futures import CancelledError
import errno
from hashlib import sha256
from itertools import islice
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Callable, Iterable, Optional, Protocol

from je_auto_control.utils.config_sync.asset_models import (
    MAX_ASSETS, MAX_BUNDLE_BYTES, MAX_FILE_BYTES, AssetFile, AssetManifest, AssetSyncResult,
)
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.path_guard import validate_path
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption

_CHUNK_BYTES = 64 * 1024
_Cancelled = Optional[Callable[[], bool]]


class AssetTransport(Protocol):
    """Read-only bounded asset source plus a local cache root; no runtime activation hook is provided."""

    @property
    def target_root(self) -> Path:
        """Return the explicit local generation-cache root."""

    def open(self, asset: AssetFile) -> BinaryIO:
        """Open a context-managed binary asset stream; the caller verifies every byte."""


class DirectoryAssetTransport:
    """Supply explicitly selected files from one local root to another without opening either on construction."""

    def __init__(self, source_root: str | Path, target_root: str | Path) -> None:
        self._source_root = Path(source_root).resolve()
        self._target_root = Path(target_root).resolve()

    @property
    def target_root(self) -> Path:
        """Return the generation root; it is created only by an uncancelled transfer."""
        return self._target_root

    def open(self, asset: AssetFile) -> BinaryIO:
        """Open a confined regular source file, refusing symlink components."""
        return _source_file(self._source_root, asset).open('rb')


def build_asset_manifest(source_root: str | Path, paths: Iterable[str], *,
                           cancelled: _Cancelled = None) -> AssetManifest:
    """Hash a bounded explicit file selection without recording machine roots or modifying sources."""
    _check(cancelled)
    if isinstance(paths, (str, bytes)):
        raise ConfigSyncError('asset selection requires an iterable of paths, not one string')
    selected = tuple(islice(paths, MAX_ASSETS + 1))
    if not 1 <= len(selected) <= MAX_ASSETS:
        raise ConfigSyncError('select 1–1024 asset paths')
    root = Path(source_root).resolve()
    assets = []
    remaining = MAX_BUNDLE_BYTES
    try:
        for name in selected:
            _check(cancelled)
            descriptor = AssetFile(name, '0' * 64, 0)
            with _source_file(root, descriptor).open('rb') as stream:
                digest, size = _hash_stream(stream, cancelled, min(remaining, MAX_FILE_BYTES))
            assets.append(AssetFile(name, digest, size))
            remaining -= size
    except (OSError, ConfigSyncError) as error:
        raise_caused_run_interruption(error)
        if isinstance(error, ConfigSyncError):
            raise
        raise ConfigSyncError('cannot read selected asset files') from error
    return AssetManifest(tuple(assets))


def sync_assets(manifest: AssetManifest, transport: AssetTransport, *,
                cancelled: _Cancelled = None) -> AssetSyncResult:
    """Publish all verified assets together, or leave previous generations intact; never run a synced script."""
    _check(cancelled)
    if not isinstance(manifest, AssetManifest):
        raise ConfigSyncError('asset transfer requires a validated manifest')
    root = Path(transport.target_root).resolve()
    destination = root / ('generation-' + manifest.digest)
    try:
        if destination.exists() or destination.is_symlink():
            return _verified_result(destination, manifest, True, cancelled)
        root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.incoming-', dir=root) as temporary:
            staging = Path(temporary)
            files = staging / 'files'
            files.mkdir()
            for asset in manifest.files:
                _check(cancelled)
                path = _asset_path(files, asset)
                path.parent.mkdir(parents=True, exist_ok=True)
                _copy_asset(transport, asset, path, cancelled)
            with (staging / 'manifest.json').open('wb') as output:
                output.write(_encoded(manifest.to_dict()).encode('ascii'))
                output.flush()
                os.fsync(output.fileno())
            _check(cancelled)
            validate_path(destination, allowed_roots=[root])
            reused = _publish(staging, destination)
        return _verified_result(destination, manifest, reused, cancelled=None)
    except (OSError, ConfigSyncError) as error:
        raise_caused_run_interruption(error)
        if isinstance(error, ConfigSyncError):
            raise
        raise ConfigSyncError('asset transfer could not publish a complete generation') from error


def _copy_asset(transport: AssetTransport, asset: AssetFile, path: Path, cancelled: _Cancelled) -> None:
    with transport.open(asset) as source:
        _check(cancelled)
        _copy_stream(source, asset, path, cancelled)


def _copy_stream(source: BinaryIO, asset: AssetFile, path: Path, cancelled: _Cancelled) -> None:
    digest, size = sha256(), 0
    with path.open('xb') as output:
        while True:
            _check(cancelled)
            chunk = source.read(_CHUNK_BYTES)
            _check(cancelled)
            if not isinstance(chunk, bytes):
                raise ConfigSyncError('asset transport must return binary chunks')
            if not chunk:
                break
            size += len(chunk)
            if size > asset.size or len(chunk) > _CHUNK_BYTES:
                raise ConfigSyncError('asset stream exceeds its declared size or chunk limit')
            output.write(chunk)
            digest.update(chunk)
        if size != asset.size or digest.hexdigest() != asset.sha256:
            raise ConfigSyncError('asset content does not match its declared size and SHA-256')
        output.flush()
        os.fsync(output.fileno())


def _publish(staging: Path, destination: Path) -> bool:
    try:
        os.rename(staging, destination)
    except OSError as error:
        if error.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
            raise
        return True  # Another sender may have published the same generation; the caller verifies it.
    return False


def _verified_result(directory: Path, manifest: AssetManifest, reused: bool,
                      cancelled: _Cancelled) -> AssetSyncResult:
    files = _generation_files(directory, manifest)
    _verify_layout(directory, manifest)
    for asset in manifest.files:
        _check(cancelled)
        with _source_file(files, asset).open('rb') as stream:
            digest, size = _hash_stream(stream, cancelled)
        if digest != asset.sha256 or size != asset.size:
            raise ConfigSyncError('cached asset generation failed integrity verification')
    return AssetSyncResult(files, manifest.digest, reused, len(manifest.files), sum(a.size for a in manifest.files))


def _generation_files(directory: Path, manifest: AssetManifest) -> Path:
    validate_path(directory, allowed_roots=[directory.parent])
    if directory.is_symlink() or not directory.is_dir():
        raise ConfigSyncError('asset generation is not an ordinary directory')
    stamp = directory / 'manifest.json'
    if stamp.is_symlink() or not stamp.is_file() or stamp.stat().st_size > 1024 * 1024:
        raise ConfigSyncError('invalid cached asset manifest')
    if stamp.read_bytes() != _encoded(manifest.to_dict()).encode('ascii'):
        raise ConfigSyncError('cached asset manifest differs from the requested generation')
    files = directory / 'files'
    validate_path(files, allowed_roots=[directory])
    if files.is_symlink() or not files.is_dir():
        raise ConfigSyncError('asset generation has no ordinary files directory')
    return files


def _hash_stream(stream: BinaryIO, cancelled: _Cancelled = None,
                   max_bytes: int = MAX_FILE_BYTES) -> tuple[str, int]:
    digest, size = sha256(), 0
    while True:
        _check(cancelled)
        chunk = stream.read(_CHUNK_BYTES)
        _check(cancelled)
        if not chunk:
            return digest.hexdigest(), size
        size += len(chunk)
        if size > max_bytes:
            raise ConfigSyncError('asset stream exceeds its byte budget')
        digest.update(chunk)


def _asset_path(root: Path, asset: AssetFile) -> Path:
    current = root
    for part in asset.path.split('/'):
        current = current / part
        if current.is_symlink():
            raise ConfigSyncError('asset paths cannot contain symbolic links')
    return validate_path(current, allowed_roots=[root])


def _source_file(root: Path, asset: AssetFile) -> Path:
    path = _asset_path(root, asset)
    if not path.is_file():
        raise ConfigSyncError('asset source must be an ordinary file')
    return path


def _verify_layout(directory: Path, manifest: AssetManifest) -> None:
    for item in directory.iterdir():
        if item.name not in {'files', 'manifest.json'}:
            raise ConfigSyncError('asset generation contains unmanifested metadata')
    _verify_file_tree(directory / 'files', {item.path for item in manifest.files})


def _verify_file_tree(files: Path, expected: set[str]) -> None:
    parents = {'/'.join(name.split('/')[:index]) for name in expected
               for index in range(1, len(name.split('/')))}
    for item in files.rglob('*'):
        name = item.relative_to(files).as_posix()
        if item.is_symlink():
            raise ConfigSyncError('asset generation contains a symbolic link')
        if item.is_dir() and name in parents:
            continue
        if not item.is_file() or name not in expected:
            raise ConfigSyncError('asset generation contains unmanifested files')


def _check(cancelled: _Cancelled) -> None:
    if cancelled is not None and cancelled():
        raise CancelledError()
