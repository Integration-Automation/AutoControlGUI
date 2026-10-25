"""Bounded source-file descriptors and verified chunks remain private until export consent commits."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import stat
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import TransferFile, MAX_TRANSFER_BYTES
from je_auto_control.utils.config_sync.blob_models import CHUNK_BYTES, SyncAssetBlob


@dataclass(frozen=True)
class SourceFile:
    """An actual confined source path plus its exact reviewed identity and blob descriptor."""

    path: str
    blob: SyncAssetBlob
    witness: tuple[int, ...]

    @property
    def file(self) -> TransferFile:
        """Apply portable output-name rules only when this source is actually selected for transfer."""
        return TransferFile(Path(self.path).name, self.blob)


def _identity(value: os.stat_result) -> tuple[int, ...]:
    created = getattr(value, 'st_birthtime_ns', value.st_ctime_ns) if os.name == 'nt' else value.st_ctime_ns
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, created


def confined_file(policy: Any, value: str) -> Path:
    """Resolve only host-selected criterion paths and reject links in every original component."""
    original = Path(value).expanduser().absolute()
    for part in (original, *original.parents):
        if part.is_symlink() or getattr(part.lstat(), 'st_file_attributes', 0) & 0x400:
            raise AgentTaskError('export source cannot contain linked path components')
    path = Path(policy.path(str(original)))
    if path.resolve() != path:
        raise AgentTaskError('export source path identity changed')
    return path


def snapshot_file(policy: Any, value: str, checkpoint: Callable[[], None], *,
                  storage: tuple[Any, str] | None = None, max_bytes: int = MAX_TRANSFER_BYTES,
                  inspect: Callable[[bytes], None] | None = None) -> SourceFile:
    """Hash one regular bounded file and optionally stage its verified chunks in one private account."""
    checkpoint()
    path = confined_file(policy, value)
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or not 0 <= opened.st_size <= max_bytes:
            raise AgentTaskError('export requires one regular unlinked file within sixty-four mebibytes')
        _unchanged(policy, path, opened)
        blob = _read_blob(stream, opened.st_size, checkpoint, storage, inspect)
        _unchanged(policy, path, opened)
        final = os.fstat(stream.fileno())
        if _identity(final) != _identity(opened) or final.st_ctime_ns != opened.st_ctime_ns:
            raise AgentTaskError('export source changed while snapshotting')
    return SourceFile(str(path), blob, (*_identity(opened), opened.st_ctime_ns))


def _unchanged(policy: Any, path: Path, opened: os.stat_result) -> None:
    if confined_file(policy, str(path)) != path or _identity(path.stat()) != _identity(opened):
        raise AgentTaskError('export source descriptor or path changed')


def verify_source_files(policy: Any, files: tuple[SourceFile, ...], checkpoint: Callable[[], None]) -> None:
    """Recheck actual file versions around grant publication without hashing bytes under the runtime writer."""
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    for source in files:
        checkpoint()
        path = confined_file(policy, source.path)
        with os.fdopen(os.open(path, flags), 'rb') as stream:
            current = os.fstat(stream.fileno())
            _unchanged(policy, path, current)
            if (*_identity(current), current.st_ctime_ns) != source.witness:
                raise AgentTaskError('export file changed during grant creation')
        checkpoint()


def _read_blob(stream: Any, size: int, checkpoint: Callable[[], None],
               storage: tuple[Any, str] | None, inspect: Callable[[bytes], None] | None) -> SyncAssetBlob:
    digest, chunks, received = sha256(), [], 0
    while True:
        checkpoint()
        body = stream.read(CHUNK_BYTES)
        checkpoint()
        if not body:
            break
        received += len(body)
        if received > size:
            raise AgentTaskError('export source grew beyond its reviewed size')
        chunk = sha256(body).hexdigest()
        digest.update(body)
        chunks.append(chunk)
        if inspect is not None:
            inspect(body)
        if storage is not None:
            storage[0].put_chunk(storage[1], chunk, body)
    if received != size:
        raise AgentTaskError('export source size changed while reading')
    blob = SyncAssetBlob(digest.hexdigest(), received, tuple(chunks))
    if storage is not None:
        storage[0].commit(storage[1], blob)
    return blob
