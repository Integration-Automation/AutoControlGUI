"""Portable content-addressed asset manifests contain relative names and hashes, never machine roots."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import cast
import unicodedata

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _schema_one

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 256 * 1024 * 1024
MAX_ASSETS = 1024
_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}


@dataclass(frozen=True)
class AssetFile:
    """One portable relative asset name, SHA-256 and exact bounded byte length."""

    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        _portable_path(self.path)
        if not isinstance(self.sha256, str) or re.fullmatch('[0-9a-f]{64}', self.sha256) is None:
            raise ConfigSyncError('asset SHA-256 must be 64 lowercase hexadecimal characters')
        if isinstance(self.size, bool) or not isinstance(self.size, int) or not 0 <= self.size <= MAX_FILE_BYTES:
            raise ConfigSyncError('asset size must be an integer between zero and 64 MiB')

    def to_dict(self) -> dict[str, object]:
        """Return a root-free JSON descriptor."""
        return asdict(self)

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> AssetFile:
        """Reject unknown or malformed descriptor fields."""
        if not isinstance(body, dict) or set(body) != {'path', 'sha256', 'size'}:
            raise ConfigSyncError('invalid asset descriptor')
        return cls(cast(str, body['path']), cast(str, body['sha256']), cast(int, body['size']))


@dataclass(frozen=True)
class AssetManifest:
    """A complete, sorted, collision-free generation of at most 1024 assets and 256 MiB."""

    files: tuple[AssetFile, ...]

    def __post_init__(self) -> None:
        if (not isinstance(self.files, tuple) or not 1 <= len(self.files) <= MAX_ASSETS
                or not all(isinstance(item, AssetFile) for item in self.files)):
            raise ConfigSyncError('asset manifest requires 1–1024 immutable file descriptors')
        if sum(item.size for item in self.files) > MAX_BUNDLE_BYTES:
            raise ConfigSyncError('asset manifest exceeds 256 MiB')
        _collision_free(self.files)
        object.__setattr__(self, 'files', tuple(sorted(self.files, key=lambda item: item.path)))

    def to_dict(self) -> dict[str, object]:
        """Copy the portable version-one manifest."""
        return {'schema_version': 1, 'files': [item.to_dict() for item in self.files]}

    @property
    def digest(self) -> str:
        """Return the complete canonical manifest's content address."""
        return sha256(_encoded(self.to_dict()).encode('ascii')).hexdigest()

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> AssetManifest:
        """Validate bounded manifest JSON before touching any filesystem."""
        if (not isinstance(body, dict) or set(body) != {'schema_version', 'files'}
                or not _schema_one(body['schema_version']) or not isinstance(body['files'], list)
                or len(body['files']) > MAX_ASSETS):
            raise ConfigSyncError('invalid asset manifest')
        return cls(tuple(AssetFile.from_dict(cast(dict[str, object], item)) for item in body['files']))


@dataclass(frozen=True)
class AssetSyncResult:
    """A complete verified local generation; its data is never executed or activated."""

    directory: Path
    manifest_digest: str
    reused: bool
    file_count: int
    byte_count: int


def _portable_path(value: str) -> None:
    if not isinstance(value, str):
        raise ConfigSyncError('asset path must be text')
    if (not value or len(value) > 512 or not value.isprintable()
            or any(char in value for char in '\\:*?"<>|') or value.startswith('/')):
        raise ConfigSyncError('asset path must be a portable relative filename')
    for part in value.split('/'):
        _portable_component(part)


def _portable_component(part: str) -> None:
    if (part in {'', '.', '..'} or part.endswith(('.', ' ')) or len(part) > 128
            or part.split('.')[0].upper() in _RESERVED):
        raise ConfigSyncError('asset path contains an unsafe or nonportable component')


def _collision_free(files: tuple[AssetFile, ...]) -> None:
    names = {unicodedata.normalize('NFC', item.path).casefold() for item in files}
    if len(names) != len(files):
        raise ConfigSyncError('asset names collide on a supported filesystem')
    for name in names:
        if any('/'.join(name.split('/')[:index]) in names for index in range(1, len(name.split('/')))):
            raise ConfigSyncError('asset file and directory names collide')
    _consistent_prefixes(files)


def _name_key(value: str) -> str:
    return unicodedata.normalize('NFC', value).casefold()


def _consistent_prefixes(files: tuple[AssetFile, ...]) -> None:
    previous: tuple[str, ...] = ()
    for asset in sorted(files, key=lambda item: _name_key(item.path)):
        current = tuple(asset.path.split('/'))
        for before, after in zip(previous, current):
            if _name_key(before) != _name_key(after):
                break
            if before != after:
                raise ConfigSyncError('asset directory spellings must be consistent across the manifest')
        previous = current
