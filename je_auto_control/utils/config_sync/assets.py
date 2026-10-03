"""Receive bounded, hash-checked assets as data; publish each completed file atomically."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from threading import Event
from typing import Iterator, List, Optional, Protocol, Tuple

from .models import ConfigSyncError

_MAX_ASSET_BYTES = 256 * 1024 * 1024
_DEVICE_NAMES = frozenset(['CON', 'PRN', 'AUX', 'NUL'] +
                          [f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in range(10)])


def _portable_filename(part: str) -> bool:
    return (part[-1] not in '. ' and part.split('.')[0].upper() not in _DEVICE_NAMES
            and not any(character in '<>:"|?*' or ord(character) < 32 for character in part))


def _relative_path(raw: str) -> bool:
    path = PurePosixPath(raw)
    normalized = bool(raw) and path.as_posix() == raw and raw != '.'
    rooted = path.is_absolute() or bool(PureWindowsPath(raw).drive)
    unsafe = '\\' in raw or '..' in path.parts or ':' in raw
    return normalized and not rooted and not unsafe and all(_portable_filename(part) for part in path.parts)


class AssetSyncError(ConfigSyncError):
    """An invalid manifest, interrupted transfer or failed integrity check."""


@dataclass(frozen=True)
class AssetSpec:
    """A portable relative filename and the exact expected SHA256 and byte count."""
    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not _relative_path(self.path):
            raise AssetSyncError('asset path must be a normalized relative filename')
        if not isinstance(self.sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', self.sha256):
            raise AssetSyncError('asset requires a lowercase SHA256 digest')
        if isinstance(self.size, bool) or not isinstance(self.size, int) or not 0 <= self.size <= _MAX_ASSET_BYTES:
            raise AssetSyncError('asset size exceeds the transfer limit')


@dataclass(frozen=True)
class AssetManifest:
    """Caller-authorized destination root and complete expected asset identities."""
    root: Path
    assets: Tuple[AssetSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'root', Path(self.root))
        object.__setattr__(self, 'assets', tuple(self.assets))
        if len({asset.path.casefold() for asset in self.assets}) != len(self.assets):
            raise AssetSyncError('manifest contains duplicate asset paths')


class AssetTransport(Protocol):  # pylint: disable=too-few-public-methods  # reason: structural transport protocol
    """Supply asset bytes without interpreting or executing their contents."""

    def iter_chunks(self, asset: AssetSpec) -> Iterator[bytes]:
        """Yield bounded chunks; transport errors abort the current file."""


@dataclass(frozen=True)
class AssetSyncResult:
    """Completed relative filenames and whether cancellation stopped the remainder."""
    saved: Tuple[str, ...] = ()
    cancelled: bool = False


def _destination(root: Path, asset: AssetSpec) -> Path:
    destination = root / asset.path
    for part in (destination, *destination.parents):
        if part.is_symlink():
            raise AssetSyncError('asset destination cannot traverse a symlink')
    if not destination.resolve().is_relative_to(root.resolve()):
        raise AssetSyncError('asset destination escapes the authorized root')
    return destination


def _receive(asset: AssetSpec, destination: Path, transport: AssetTransport, cancel: Event) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, filename = tempfile.mkstemp(prefix='.sync-', dir=destination.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            digest, size = hashlib.sha256(), 0
            for chunk in transport.iter_chunks(asset):
                if cancel.is_set():
                    return False
                if not isinstance(chunk, bytes) or len(chunk) > _MAX_ASSET_BYTES:
                    raise AssetSyncError('asset transport yielded an invalid chunk')
                size += len(chunk)
                if size > asset.size:
                    raise AssetSyncError('asset exceeds its declared size')
                stream.write(chunk)
                digest.update(chunk)
            if cancel.is_set():
                return False
            if size != asset.size or digest.hexdigest() != asset.sha256:
                raise AssetSyncError('asset hash or size does not match the manifest')
            stream.flush()
            os.fsync(stream.fileno())
        _destination(destination.parent, AssetSpec(destination.name, asset.sha256, asset.size))
        if cancel.is_set():
            return False
        os.replace(temporary, destination)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def sync_assets(manifest: AssetManifest, transport: AssetTransport, *,
                cancel: Optional[Event] = None) -> AssetSyncResult:
    """Verify before replace; cancellation/errors preserve the current destination file.

    Files completed before a later failure remain published. The caller owns and
    closes its transport. Scripts are stored as bytes and are never imported.
    """
    stopped = cancel if cancel is not None else Event()
    saved: List[str] = []
    try:
        destinations = [_destination(manifest.root, asset) for asset in manifest.assets]
        for asset, destination in zip(manifest.assets, destinations):
            if stopped.is_set() or not _receive(asset, destination, transport, stopped):
                return AssetSyncResult(tuple(saved), cancelled=True)
            saved.append(asset.path)
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, AssetSyncError):
            raise
        raise AssetSyncError('asset transfer failed; current file was not published') from error
    return AssetSyncResult(tuple(saved))
