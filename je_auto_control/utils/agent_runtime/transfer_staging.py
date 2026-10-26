"""Journal exclusive staging objects and retire only their verified identities without recursive deletion."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, BinaryIO, Callable, Iterator
import uuid

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.config_sync.asset_models import AssetManifest


def _identity(status: Any) -> list[int]:
    return [status.st_dev, status.st_ino]


def _object(path: Path, identity: list[int], *, directory: bool) -> None:
    if path.is_symlink() or path.resolve() != path:
        raise AgentTaskError('owned staging path changed through a filesystem link')
    status = path.stat()
    if _identity(status) != identity or (path.is_dir() if directory else path.is_file()) is not True:
        raise AgentTaskError('owned staging filesystem identity changed')


def _stage(root: Path, root_identity: list[int], witness: dict) -> Path:
    stage = Path(witness['path'])
    if stage.parent != root or not stage.name.startswith('.incoming-') or not stage.is_absolute():
        raise AgentTaskError('staging journal is outside its exact import root')
    _object(root, root_identity, directory=True)
    return stage


def _known_path(stage: Path, name: str) -> Path:
    if not isinstance(name, str) or '\\' in name or any(part in {'', '.', '..'} for part in name.split('/')):
        raise AgentTaskError('invalid staging journal relative path')
    path = stage / name
    if not path.is_relative_to(stage):
        raise AgentTaskError('staging journal path escaped its allocation')
    return path


def _parents(stage: Path, path: Path, directories: dict) -> None:
    for parent in (path.parent, *path.parent.parents):
        if parent == stage.parent:
            break
        name = '' if parent == stage else parent.relative_to(stage).as_posix()
        if name not in directories:
            raise AgentTaskError('staging parent has no recorded identity')
        _object(parent, directories[name], directory=True)


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _known_objects(stage: Path, witness: dict) -> set[Path]:
    return {stage, *[_known_path(stage, name) for name in witness['directories'] if name],
            *[_known_path(stage, name) for name in witness['files']]}


def _validate_contents(stage: Path, witness: dict) -> None:
    directories, files = witness['directories'], witness['files']
    known = _known_objects(stage, witness)
    for name, identity in directories.items():
        path = stage if not name else _known_path(stage, name)
        if not _present(path):
            continue
        _object(path, identity, directory=True)
        if any(child not in known for child in path.iterdir()):
            raise AgentTaskError('owned staging contains an unrecognized object; cleanup requires review')
    for name, identity in files.items():
        path = _known_path(stage, name)
        if _present(path):
            _parents(stage, path, directories)
            _object(path, identity, directory=False)


def cleanup_staging(root: Path, root_identity: list[int], witness: dict) -> None:
    """Remove only journaled files and empty directories after validating the complete candidate tree."""
    stage = _stage(root, root_identity, witness)
    if not _present(stage):
        return
    if witness.get('cleaned') is True:
        raise AgentTaskError('a retired staging name now contains an unrelated object')
    _validate_contents(stage, witness)
    for name, identity in witness['files'].items():
        path = _known_path(stage, name)
        if _present(path):
            _object(root, root_identity, directory=True)
            _parents(stage, path, witness['directories'])
            _object(path, identity, directory=False)
            path.unlink()
    for name in sorted(witness['directories'], key=lambda value: (value.count('/'), len(value)), reverse=True):
        path = stage if not name else _known_path(stage, name)
        if _present(path):
            _object(root, root_identity, directory=True)
            _object(path, witness['directories'][name], directory=True)
            path.rmdir()


@dataclass
class _StagingState:
    witness: dict = field(default_factory=dict)
    used: set[str] = field(default_factory=set)


class ImportStaging:
    """Preallocate and journal all exclusive output identities before the shared publisher writes bytes."""

    def __init__(self, root: Path, identity: list[int], record: Callable[[dict], None],
                 retired: Callable[[dict], None]) -> None:
        self.root, self.identity, self.record, self.retired = root, identity, record, retired
        self._state = _StagingState()

    @contextmanager
    def directory(self, root: Path, manifest: AssetManifest) -> Iterator[Path]:
        """Publish one durable ownership witness before yielding the allocated staging directory."""
        if root != self.root or self._state.witness:
            raise AgentTaskError('staging allocation requires its original exclusive import root')
        _object(root, self.identity, directory=True)
        stage = Path(mkdtemp(prefix='.incoming-', dir=root))
        witness = {'allocation': uuid.uuid4().hex, 'path': str(stage), 'directories': {'': _identity(stage.stat())},
                   'files': {}, 'cleaned': False}
        self._state.witness = witness
        try:
            for name in [*(str('files/' + asset.path) for asset in manifest.files), 'manifest.json']:
                self._allocate(stage, name)
            self.record(witness)
            yield stage
        finally:
            cleanup_staging(root, self.identity, witness)
            self.retired(witness)

    def _allocate(self, stage: Path, name: str) -> None:
        path = _known_path(stage, name)
        for parent in reversed(path.parent.parents):
            if parent == stage or not parent.is_relative_to(stage):
                continue
            self._allocate_directory(stage, parent)
        if path.parent != stage:
            self._allocate_directory(stage, path.parent)
        _parents(stage, path, self._state.witness['directories'])
        with path.open('xb') as stream:
            self._state.witness['files'][name] = _identity(os.fstat(stream.fileno()))

    def _allocate_directory(self, stage: Path, path: Path) -> None:
        name = path.relative_to(stage).as_posix()
        if name not in self._state.witness['directories']:
            path.mkdir()
            self._state.witness['directories'][name] = _identity(path.stat())

    @contextmanager
    def open(self, path: Path) -> Iterator[BinaryIO]:
        """Borrow one exact empty preallocated file; reopening or replacing it never authorizes a write."""
        witness = self._state.witness
        stage = _stage(self.root, self.identity, witness)
        name = path.relative_to(stage).as_posix()
        if name not in witness['files'] or name in self._state.used:
            raise AgentTaskError('publisher output has no unused staging identity')
        _parents(stage, path, witness['directories'])
        _object(path, witness['files'][name], directory=False)
        with path.open('r+b') as stream:
            status = os.fstat(stream.fileno())
            if _identity(status) != witness['files'][name] or status.st_size != 0:
                raise AgentTaskError('preallocated staging file changed before its first write')
            self._state.used.add(name)
            yield stream
