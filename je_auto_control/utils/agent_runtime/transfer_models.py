"""Portable criterion selections and immutable descriptors for reviewed outcome transfers."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from typing import Any, ClassVar, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.config_sync.asset_models import AssetFile, AssetManifest
from je_auto_control.utils.config_sync.blob_models import SyncAssetBlob
from je_auto_control.utils.config_sync.contract import ConfigSyncError

MAX_TRANSFER_FILES = 500
MAX_TRANSFER_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


def _object(value: Any, fields: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise AgentTaskError('transfer envelope has invalid or unknown fields')
    return value


def _hex(value: str, length: int) -> None:
    if not isinstance(value, str) or re.fullmatch(f'[0-9a-f]{{{length}}}', value) is None:
        raise AgentTaskError('transfer identity or digest has an invalid hexadecimal format')


def _deadline(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentTaskError('transfer expiry must be a finite timestamp')
    try:
        finite = math.isfinite(value)
    except OverflowError as error:
        raise AgentTaskError('transfer expiry exceeds the timestamp range') from error
    if not finite:
        raise AgentTaskError('transfer expiry must be a finite timestamp')


def _portable_files(files: tuple[AssetFile, ...]) -> None:
    try:
        AssetManifest(files)
    except ConfigSyncError as error:
        raise AgentTaskError('transfer output names collide on a supported filesystem') from error


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _selection_names(names: tuple[str, ...]) -> None:
    if not isinstance(names, tuple) or len(names) > MAX_TRANSFER_FILES:
        raise AgentTaskError('transfer selection requires at most five hundred immutable names')
    files = tuple(_selection_name(name) for name in names)
    if not files:
        return
    _portable_files(files)


def _selection_name(name: str) -> AssetFile:
    if not isinstance(name, str) or any(separator in name for separator in ('/', '\\', ':')):
        raise AgentTaskError('transfer selection requires portable plain output names')
    try:
        return AssetFile(name, '0' * 64, 0)
    except ConfigSyncError as error:
        raise AgentTaskError('transfer selection contains an invalid output name') from error


@dataclass(frozen=True)
class TransferSelection:
    """One detached file-criterion index and its explicitly selected output names."""

    criterion: int
    names: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.criterion, bool) or not isinstance(self.criterion, int) or self.criterion < 0:
            raise AgentTaskError('transfer criterion must be a nonnegative integer')
        _selection_names(self.names)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TransferSelection:
        """Validate an exact wire object and detach its mutable name list."""
        if not isinstance(value, Mapping) or set(value) != {'criterion', 'names'}:
            raise AgentTaskError('transfer selection requires criterion and names only')
        if not isinstance(value['names'], list):
            raise AgentTaskError('transfer selection wire names must be a list')
        return cls(value['criterion'], tuple(value['names']))

    def to_dict(self) -> dict[str, Any]:
        """Return a new wire object without exposing the stored immutable tuple."""
        return {'criterion': self.criterion, 'names': list(self.names)}


@dataclass(frozen=True)
class TransferFile:
    """One immutable output name and its content-addressed chunk descriptor."""

    name: str
    blob: SyncAssetBlob

    def __post_init__(self) -> None:
        _selection_name(self.name)
        if not isinstance(self.blob, SyncAssetBlob):
            raise AgentTaskError('transfer file requires a typed immutable blob descriptor')

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TransferFile:
        """Detach the flat transfer file envelope into the existing blob descriptor."""
        value = _object(value, {'name', 'size', 'sha256', 'chunks'})
        try:
            blob = SyncAssetBlob.from_dict({'schema_version': 1, 'size': value['size'],
                                           'sha256': value['sha256'], 'chunks': value['chunks']})
        except ConfigSyncError as error:
            raise AgentTaskError('transfer file has an invalid blob descriptor') from error
        return cls(value['name'], blob)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh filename, size, full digest and ordered chunk list."""
        return {'name': self.name, 'size': self.blob.size, 'sha256': self.blob.sha256,
                'chunks': list(self.blob.chunks)}


@dataclass(frozen=True)
class TransferManifest:
    """An immutable portable export envelope whose digest pins every declared value."""

    export_id: str
    source_task: str
    source_snapshot: str
    submission_digest: str
    files: tuple[TransferFile, ...]
    expires: float
    contract: ClassVar[int] = 1

    def __post_init__(self) -> None:
        _hex(self.export_id, 32)
        _hex(self.source_task, 32)
        _hex(self.source_snapshot, 64)
        _hex(self.submission_digest, 64)
        _deadline(self.expires)
        _manifest_files(self.files)
        if len(_canonical(self.to_dict())) > MAX_MANIFEST_BYTES:
            raise AgentTaskError('transfer manifest exceeds one mebibyte')

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TransferManifest:
        """Detach the portable manifest without reading files or acquiring task authority."""
        value = _object(value, {'contract', 'export_id', 'source_task', 'source_snapshot',
                                'submission_digest', 'files', 'expires'})
        version = value['contract']
        if isinstance(version, bool) or not isinstance(version, int) or version != 1:
            raise AgentTaskError('unsupported transfer manifest contract')
        if not isinstance(value['files'], list) or not 1 <= len(value['files']) <= MAX_TRANSFER_FILES:
            raise AgentTaskError('transfer manifest requires one to five hundred files')
        return cls(value['export_id'], value['source_task'], value['source_snapshot'],
                   value['submission_digest'], tuple(TransferFile.from_dict(item) for item in value['files']),
                   value['expires'])

    def to_dict(self) -> dict[str, Any]:
        """Copy the complete versioned envelope without exposing mutable stored objects."""
        return {'contract': 1, 'export_id': self.export_id, 'source_task': self.source_task,
                'source_snapshot': self.source_snapshot, 'submission_digest': self.submission_digest,
                'files': [item.to_dict() for item in self.files], 'expires': self.expires}

    @property
    def digest(self) -> str:
        """Hash the exact canonical envelope; this does not attest the underlying file bytes."""
        return sha256(_canonical(self.to_dict())).hexdigest()


def _manifest_files(files: tuple[TransferFile, ...]) -> None:
    if not isinstance(files, tuple) or not 1 <= len(files) <= MAX_TRANSFER_FILES:
        raise AgentTaskError('transfer manifest requires one to five hundred immutable files')
    if any(not isinstance(item, TransferFile) for item in files):
        raise AgentTaskError('transfer manifest requires typed immutable file descriptors')
    if sum(item.blob.size for item in files) > MAX_TRANSFER_BYTES:
        raise AgentTaskError('transfer manifest exceeds sixty-four mebibytes')
    _portable_files(tuple(AssetFile(item.name, item.blob.sha256, item.blob.size) for item in files))


def _review_envelope(reply: Mapping) -> tuple[Mapping, TransferManifest]:
    """Parse the shared closed review envelope before source or destination identity checks."""
    value = _object(reply, {'review', 'digest', 'manifest', 'review_expires', 'approval_required'})
    _hex(value['review'], 32)
    _hex(value['digest'], 64)
    _deadline(value['review_expires'])
    return value, TransferManifest.from_dict(value['manifest'])
