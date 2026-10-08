"""Move the files synced scripts refer to, verified by content hash.

A script that arrives without the template images it matches against fails
on its first step. Config sync lists such files in an :class:`AssetManifest`
-- relative path, SHA-256, size -- and :func:`sync_assets` brings each one in
through an :class:`AssetTransport`: the bytes are hashed before anything is
written, and the file is replaced atomically, so a transfer that was cut
short or tampered with never becomes a half-written or wrong file.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple, Union

from je_auto_control.utils.config_sync.bucket import ConfigSyncError

_SHA256_HEX_CHARS = 64


class AssetSyncError(ConfigSyncError):
    """An asset could not be read, fetched, verified or written."""


def file_sha256(path: Union[str, Path]) -> str:
    """The SHA-256 of a file's content, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checked_digest(value: Any) -> str:
    text = str(value).lower()
    if len(text) != _SHA256_HEX_CHARS or any(char not in "0123456789abcdef" for char in text):
        raise AssetSyncError(f"not a SHA-256 hex digest: {value!r}")
    return text


@dataclass(frozen=True)
class AssetRef:
    """One file: where it belongs under the root, and what it must contain."""
    path: str
    sha256: str
    size: int

    def to_dict(self) -> Dict[str, Any]:
        """A JSON-ready copy."""
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class AssetManifest:
    """The files that should exist under ``root``, by relative posix path."""
    root: Path
    assets: Tuple[AssetRef, ...] = ()

    @classmethod
    def from_directory(cls, root: Union[str, Path],
                       patterns: Iterable[str] = ("*",)) -> "AssetManifest":
        """List the files under ``root`` matching any of ``patterns`` (recursive)."""
        base = Path(root)
        found: Dict[str, AssetRef] = {}
        for pattern in patterns:
            for path in sorted(base.rglob(pattern)) if base.is_dir() else ():
                if path.is_file():
                    relative = path.relative_to(base).as_posix()
                    found[relative] = AssetRef(relative, file_sha256(path), path.stat().st_size)
        return cls(root=base, assets=tuple(found[key] for key in sorted(found)))

    @classmethod
    def from_entries(cls, root: Union[str, Path],
                     entries: Mapping[str, Mapping[str, Any]]) -> "AssetManifest":
        """Build a manifest from ``{relative path: {"sha256": ..., "size": ...}}``."""
        refs = []
        for path, body in sorted(entries.items()):
            size = body.get("size", 0)
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise AssetSyncError(f"asset {path!r}: size must be an integer >= 0")
            refs.append(AssetRef(str(path), _checked_digest(body.get("sha256")), size))
        return cls(root=Path(root), assets=tuple(refs))

    def destination(self, asset: AssetRef) -> Path:
        """Where ``asset`` goes; refuses a path that would leave the root."""
        relative = PurePosixPath(asset.path)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts \
                or ":" in asset.path or "\\" in asset.path:
            raise AssetSyncError(f"asset path {asset.path!r} does not stay inside the folder")
        target = self.root.joinpath(*relative.parts)
        root = self.root.resolve()
        if root != target.resolve() and root not in target.resolve().parents:
            raise AssetSyncError(f"asset path {asset.path!r} resolves outside the folder")
        return target


class AssetTransport(Protocol):
    """Where asset content travels: a content-addressed blob store."""

    def fetch(self, sha256: str) -> bytes:
        """The content stored under ``sha256``; raise ``AssetSyncError`` if absent."""

    def store(self, sha256: str, data: bytes) -> None:
        """Keep ``data`` under ``sha256``."""

    def has(self, sha256: str) -> bool:
        """Whether content for ``sha256`` is already stored."""


class DirectoryAssetTransport:
    """An :class:`AssetTransport` over a folder both machines can reach.

    A shared drive, a mounted bucket or a folder another sync tool mirrors.
    Blobs are named by their hash, so identical files are stored once.
    """

    def __init__(self, directory: Union[str, Path]) -> None:
        self._directory = Path(directory)

    def _blob(self, sha256: str) -> Path:
        return self._directory / _checked_digest(sha256)

    def fetch(self, sha256: str) -> bytes:
        """Read the blob stored under ``sha256``."""
        try:
            return self._blob(sha256).read_bytes()
        except OSError as error:
            raise AssetSyncError(f"asset {sha256} is not in {self._directory}: {error}") from error

    def store(self, sha256: str, data: bytes) -> None:
        """Write ``data`` under ``sha256`` atomically."""
        from je_auto_control.utils.json_store.json_store import atomic_write_bytes
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(self._blob(sha256), data)
        except OSError as error:
            raise AssetSyncError(f"cannot store asset {sha256}: {error}") from error

    def has(self, sha256: str) -> bool:
        """Whether the blob exists."""
        return self._blob(sha256).is_file()


@dataclass
class AssetSyncResult:
    """What :func:`sync_assets` or :func:`publish_assets` did.

    ``transferred`` and ``unchanged`` list relative paths, ``failed`` maps a
    path to why it was not written, ``hashes`` records the verified SHA-256
    of every file now in place.
    """
    transferred: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    failed: Dict[str, str] = field(default_factory=dict)
    hashes: Dict[str, str] = field(default_factory=dict)
    cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """A JSON-ready copy."""
        return {"transferred": list(self.transferred), "unchanged": list(self.unchanged),
                "failed": dict(self.failed), "hashes": dict(self.hashes),
                "cancelled": self.cancelled}


def _receive(manifest: AssetManifest, asset: AssetRef, transport: AssetTransport) -> bool:
    """Bring one asset in; whether a file was written."""
    from je_auto_control.utils.json_store.json_store import atomic_write_bytes
    target = manifest.destination(asset)
    wanted = _checked_digest(asset.sha256)
    try:
        if target.is_file() and file_sha256(target) == wanted:
            return False
        data = transport.fetch(wanted)
        if len(data) != asset.size or hashlib.sha256(data).hexdigest() != wanted:
            raise AssetSyncError("content does not match its SHA-256 and size; not written")
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, data)
    except OSError as error:
        raise AssetSyncError(str(error)) from error
    return True


def sync_assets(manifest: AssetManifest, transport: AssetTransport, *,
                cancel: Optional[threading.Event] = None) -> AssetSyncResult:
    """Make the files under ``manifest.root`` match the manifest.

    A file already holding the right content is left alone. Anything else is
    fetched, checked against its SHA-256 and size, and only then moved into
    place in one step -- the existing file stays untouched when the check
    fails. One bad asset does not stop the others; it is reported in
    ``failed``. Setting ``cancel`` stops before the next file.
    """
    result = AssetSyncResult()
    for asset in manifest.assets:
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break
        try:
            written = _receive(manifest, asset, transport)
        except AssetSyncError as error:
            result.failed[asset.path] = str(error)
            continue
        (result.transferred if written else result.unchanged).append(asset.path)
        result.hashes[asset.path] = asset.sha256
    return result


def publish_assets(manifest: AssetManifest, transport: AssetTransport, *,
                   cancel: Optional[threading.Event] = None) -> AssetSyncResult:
    """Put the manifest's local files where other machines can fetch them.

    A file whose content no longer matches the manifest is reported in
    ``failed`` rather than stored under the wrong hash.
    """
    result = AssetSyncResult()
    for asset in manifest.assets:
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break
        try:
            if transport.has(asset.sha256):
                result.unchanged.append(asset.path)
            else:
                data = manifest.destination(asset).read_bytes()
                if hashlib.sha256(data).hexdigest() != _checked_digest(asset.sha256):
                    raise AssetSyncError("file changed since the manifest was built")
                transport.store(asset.sha256, data)
                result.transferred.append(asset.path)
        except (AssetSyncError, OSError) as error:
            result.failed[asset.path] = str(error)
            continue
        result.hashes[asset.path] = asset.sha256
    return result


__all__ = [
    "AssetManifest", "AssetRef", "AssetSyncError", "AssetSyncResult", "AssetTransport",
    "DirectoryAssetTransport", "file_sha256", "publish_assets", "sync_assets",
]
