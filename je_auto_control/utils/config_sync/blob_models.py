"""Bounded content-addressed chunk descriptors and portable profile asset references contain no local paths."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import cast

from je_auto_control.utils.config_sync.asset_models import AssetFile, MAX_FILE_BYTES
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _schema_one

CHUNK_BYTES = 256 * 1024
ASSET_TAG = '$autocontrol_asset'


def validate_digest(value: str) -> None:
    """Require an exact lowercase SHA-256 identifier before a database or HTTP request."""
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ConfigSyncError('asset hash must be 64 lowercase hexadecimal characters')


@dataclass(frozen=True)
class SyncAssetBlob:
    """One immutable blob of up to 64 MiB, split into verified 256-KiB content-addressed chunks."""

    sha256: str
    size: int
    chunks: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_digest(self.sha256)
        if isinstance(self.size, bool) or not isinstance(self.size, int) or not 0 <= self.size <= MAX_FILE_BYTES:
            raise ConfigSyncError('asset blob size must be an integer between zero and 64 MiB')
        if not isinstance(self.chunks, tuple) or len(self.chunks) != (self.size + CHUNK_BYTES - 1) // CHUNK_BYTES:
            raise ConfigSyncError('asset blob requires the exact bounded chunk count')
        for digest in self.chunks:
            validate_digest(digest)
        if self.size == 0 and self.sha256 != sha256(b'').hexdigest():
            raise ConfigSyncError('empty asset blob has an invalid hash')

    def to_dict(self) -> dict[str, object]:
        """Copy a version-one content descriptor without a filesystem location."""
        return {'schema_version': 1, 'sha256': self.sha256, 'size': self.size, 'chunks': list(self.chunks)}

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> SyncAssetBlob:
        """Reject unknown fields and oversized chunk lists before construction."""
        if (not isinstance(body, dict) or set(body) != {'schema_version', 'sha256', 'size', 'chunks'}
                or not _schema_one(body['schema_version']) or not isinstance(body['chunks'], list)
                or len(body['chunks']) > MAX_FILE_BYTES // CHUNK_BYTES):
            raise ConfigSyncError('invalid asset blob descriptor')
        return cls(cast(str, body['sha256']), cast(int, body['size']), tuple(body['chunks']))


@dataclass(frozen=True)
class SyncAssetReference:
    """Bind immutable verified bytes to an explicit portable path under the inert generation's assets directory."""

    path: str
    blob: SyncAssetBlob

    def __post_init__(self) -> None:
        if not isinstance(self.blob, SyncAssetBlob):
            raise ConfigSyncError('asset reference requires a typed content descriptor')
        AssetFile(self.path, self.blob.sha256, self.blob.size)
        if not self.path.startswith('assets/'):
            raise ConfigSyncError('profile asset references must stay under assets/')

    @property
    def file(self) -> AssetFile:
        """Provide the same bounded relative descriptor used by the verified generation publisher."""
        return AssetFile(self.path, self.blob.sha256, self.blob.size)

    def to_dict(self) -> dict[str, object]:
        """Copy an exact reserved marker; arbitrary additional payload cannot hide inside an asset reference."""
        return {ASSET_TAG: {'path': self.path, 'blob': self.blob.to_dict()}}

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> SyncAssetReference:
        """Validate the complete reserved marker without reading any file or network data."""
        if not isinstance(body, dict) or set(body) != {ASSET_TAG}:
            raise ConfigSyncError('invalid portable asset reference')
        raw = body[ASSET_TAG]
        if not isinstance(raw, dict) or set(raw) != {'path', 'blob'}:
            raise ConfigSyncError('invalid portable asset reference fields')
        return cls(cast(str, raw['path']), SyncAssetBlob.from_dict(raw['blob']))
