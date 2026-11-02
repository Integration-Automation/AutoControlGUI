"""Polling additive folder mirror using content digests, explicit receive receipts and owned stopped workers."""
from __future__ import annotations

from _thread import LockType
from asyncio import CancelledError as AsyncCancelledError
from concurrent.futures import CancelledError
from contextlib import closing
from dataclasses import dataclass, field
from hashlib import sha256
import os
from os import fstat, stat_result
import threading
from pathlib import Path
from typing import BinaryIO, Callable, Generator, Optional, Protocol

from je_auto_control.utils.exception.control_signals import OperationCancelledError, raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt

_DEFAULT_POLL_S = 3.0


class FolderSyncStateError(AutoControlException, RuntimeError):
    """A folder baseline cannot be handed to another worker safely."""


@dataclass(frozen=True)
class FolderSyncCheckpoint:
    """Immutable in-memory baseline for a retired worker; contains no file bytes or sender authority."""
    watch_dir: Path
    include_subdirs: bool
    entries: tuple[tuple[str, str], ...]
    baselined: bool

    def __post_init__(self) -> None:
        if not isinstance(self.watch_dir, Path) or not self.watch_dir.is_absolute():
            raise FolderSyncStateError('checkpoint requires an absolute watch path')
        if not isinstance(self.include_subdirs, bool) or not isinstance(self.baselined, bool):
            raise FolderSyncStateError('checkpoint flags must be booleans')
        _validate_checkpoint_entries(self.entries, self.include_subdirs)


def _validate_checkpoint_entries(entries: tuple[tuple[str, str], ...], include_subdirs: bool) -> None:
    if not isinstance(entries, tuple) or not all(_checkpoint_entry(item) for item in entries):
        raise FolderSyncStateError('checkpoint entries must contain relative names and SHA-256 digests')
    if len(dict(entries)) != len(entries):
        raise FolderSyncStateError('checkpoint contains duplicate paths')
    if not include_subdirs and any('/' in name for name, _digest in entries):
        raise FolderSyncStateError('checkpoint excludes subdirectories')


def _checkpoint_entry(item: object) -> bool:
    if not isinstance(item, tuple) or len(item) != 2:
        return False
    name, digest = item
    return (_checkpoint_name(name) and isinstance(digest, str) and len(digest) == 64
            and all(char in '0123456789abcdef' for char in digest))


def _checkpoint_name(name: object) -> bool:
    if not isinstance(name, str) or not name or '\x00' in name:
        return False
    selected = Path(name)
    if selected.anchor or selected.as_posix() != name:
        return False
    return all(part not in ('', '.', '..') for part in name.split('/'))


@dataclass
class _ContentState:
    snapshot: dict[str, str] = field(default_factory=dict)
    baselined: bool = False
    received: set[str] = field(default_factory=set)
    versions: dict[str, int] = field(default_factory=dict)
    sequence: int = 0
    lock: LockType = field(default_factory=threading.Lock)


# pylint: disable-next=too-few-public-methods  # reason: polling needs only a cooperative stop check
class _StopFlag(Protocol):
    def is_set(self) -> bool:
        """Whether the current polling operation must stop before another side effect."""


@dataclass
class _PollStop:
    event: threading.Event
    cancelled: Optional[Callable[[], bool]]

    def is_set(self) -> bool:
        """Combine owner cancellation with the owned run event."""
        if self.event.is_set():
            return True
        if self.cancelled is not None and self.cancelled():
            self.event.set()
        return self.event.is_set()


# pylint: disable-next=too-many-instance-attributes  # reason: watch options, worker ownership and locked content baseline
class FolderSyncEngine:
    """Mirror new or changed bytes through a synchronous sender; retry failures on the next tick.

    Existing files establish a baseline on the first run; restarts retain pending/offline
    edits. Deletions never propagate. Receiving transports
    call record_received after publishing a file to prevent sending those bytes back.
    A stopped but blocked sender remains owned; start cannot overlap it with a new run.
    Retired workers can export an immutable checkpoint for an explicitly authorised
    replacement sender watching the same path and recursion mode.
    """

    def __init__(self, *, watch_dir: Path, sender: Callable[[str, str], None],
                 poll_interval_s: float = _DEFAULT_POLL_S, include_subdirs: bool = False,
                 cancelled: Optional[Callable[[], bool]] = None,
                 checkpoint: Optional[FolderSyncCheckpoint] = None) -> None:
        self._watch = Path(watch_dir).absolute()
        self._sender = sender
        self._interval = max(0.5, float(poll_interval_s))
        self._include_subdirs = bool(include_subdirs)
        self._cancelled = cancelled
        self._content = _ContentState()
        if checkpoint is not None:
            if (not isinstance(checkpoint, FolderSyncCheckpoint) or checkpoint.watch_dir != self._watch
                    or checkpoint.include_subdirs != self._include_subdirs):
                raise FolderSyncStateError('checkpoint watch path or recursion mode does not match')
            self._content.snapshot = dict(checkpoint.entries)
            self._content.baselined = checkpoint.baselined
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.RLock()

    def start(self) -> None:
        """Start one polling worker, or retain the existing worker until it actually ends."""
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if not self._watch.is_dir():
                raise FileNotFoundError(f'watch dir not a directory: {self._watch}')
            self._stop = threading.Event()
            self._ready = threading.Event()
            self._thread = threading.Thread(target=self._loop, args=(self._stop,), name='folder-sync', daemon=True)
            self._thread.start()
        autocontrol_logger.info('folder sync: watching %s every %.1fs', self._watch, self._interval)

    def request_stop(self) -> None:
        """Signal cancellation without joining, including from an owner predicate on the bridge thread."""
        with self._lifecycle_lock:
            self._stop.set()
            self._ready.clear()

    def stop(self) -> None:
        """Signal cancellation and wait at most two seconds, retaining ownership of a blocked sender."""
        with self._lifecycle_lock:
            self.request_stop()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    @property
    def stop_requested(self) -> bool:
        """Expose the current run's cancellation request to an owning synchronous sender."""
        return self._stop.is_set()

    def is_running(self) -> bool:
        """Report a live worker, including a stopped worker finishing an in-flight sender call."""
        with self._lifecycle_lock:
            return self._thread is not None and self._thread.is_alive()

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Wait for a complete initial content baseline; stopped or failed scans are never ready."""
        return self._ready.wait(timeout)

    def checkpoint(self) -> FolderSyncCheckpoint:
        """Copy metadata without filesystem access only after stop and actual worker retirement.

        The caller must bind a replacement to its authorised peer. An initial baseline
        includes pre-existing files and is not evidence that those bytes were delivered.
        """
        with self._lifecycle_lock:
            if not self._stop.is_set() or self.is_running():
                raise FolderSyncStateError('previous folder worker has not retired; retry after it exits')
            with self._content.lock:
                return FolderSyncCheckpoint(self._watch, self._include_subdirs,
                                            tuple(self._content.snapshot.items()), self._content.baselined)

    def record_received(self, path: str | Path) -> bool:
        """Accept an already-published regular file inside this watch root as received, without echoing it.

        Return False for outside, excluded, missing, redirected or changing files. Receipt
        hashing never starts a worker, and later local content edits still propagate.
        """
        return self._record_received(path, None)

    def record_receipt(self, receipt: FileReceiveReceipt) -> bool:
        """Record originally received bytes without hashing or consuming a later local edit to the published path."""
        if not isinstance(receipt, FileReceiveReceipt):
            return False
        return self._record_received(receipt.path, receipt.sha256)

    def _record_received(self, path: str | Path, digest: Optional[str]) -> bool:
        if self._cancelled is not None and self._cancelled():
            return False
        try:
            target = self._receipt_target(path)
            if target is None:
                return False
            selected, relative = target
            if digest is None:
                digest = self._digest(selected, None)
        except (OSError, ValueError) as error:
            raise_caused_run_interruption(error)
            return False
        if digest is None:
            return False
        with self._lifecycle_lock:
            if self._cancelled is not None and self._cancelled():
                return False
            with self._content.lock:
                self._content.snapshot[relative] = digest
                self._content.received.add(relative)
                self._content.sequence += 1
                self._content.versions[relative] = self._content.sequence
        return True

    def _receipt_target(self, path: str | Path) -> Optional[tuple[Path, str]]:
        selected = Path(path)
        root = self._watch.resolve(strict=True)
        if selected.is_symlink():
            return None
        selected = selected.resolve(strict=True)
        relative = selected.relative_to(root)
        if not self._include_subdirs and len(relative.parts) != 1:
            return None
        if not selected.is_file():
            return None
        return selected, relative.as_posix()

    @staticmethod
    def _digest(path: Path, stop: Optional[_StopFlag]) -> Optional[str]:
        if path.is_symlink() or not path.is_file():
            raise OSError('folder sync requires a regular file')
        before = path.stat()
        with path.open('rb') as stream:
            if _identity(before) != _identity(fstat(stream.fileno())):
                raise OSError('folder sync file changed before hashing')
            digest = _read_digest(stream, stop)
        if path.is_symlink() or _identity(before) != _identity(path.stat()):
            raise OSError('folder sync file changed during hashing')
        return digest

    def _paths(self, stop: _StopFlag) -> Generator[Path, None, None]:
        root = self._watch.resolve(strict=True)
        directories = [self._watch]
        visited: set[Path] = set()
        while directories:
            directory = directories.pop()
            resolved = directory.resolve(strict=True)
            if resolved in visited or not resolved.is_relative_to(root):
                continue
            visited.add(resolved)
            with os.scandir(directory) as entries:
                for entry in entries:
                    if stop.is_set():
                        return
                    selected = self._select_entry(entry, directories)
                    if selected is not None:
                        yield selected

    def _select_entry(self, entry: os.DirEntry[str], directories: list[Path]) -> Optional[Path]:
        if entry.is_symlink():
            return None
        if entry.is_dir(follow_symlinks=False):
            if self._include_subdirs:
                directories.append(Path(entry.path))
        elif entry.is_file(follow_symlinks=False):
            return Path(entry.path)
        return None

    def _scan(self, stop: _StopFlag) -> Optional[dict[str, str]]:
        out: dict[str, str] = {}
        with closing(self._paths(stop)) as paths:
            for entry in paths:
                digest = self._digest(entry, stop)
                if digest is None:
                    return None
                out[entry.relative_to(self._watch).as_posix()] = digest
        return out

    def _poll(self, current: dict[str, str], stop: _StopFlag) -> None:
        for relative, digest in current.items():
            if stop.is_set():
                return
            with self._content.lock:
                previous = self._content.snapshot.get(relative)
                version = self._content.versions.get(relative, 0)
                received = relative in self._content.received
            if received or previous == digest:
                continue
            try:
                self._sender(str(self._watch / relative), relative)
            except (RuntimeError, OSError, ValueError) as error:
                raise_caused_run_interruption(error)
                autocontrol_logger.warning('folder sync push %s: %r', relative, error)
            else:
                with self._content.lock:
                    if self._content.versions.get(relative, 0) == version:
                        self._content.snapshot[relative] = digest
                autocontrol_logger.info('folder sync: pushed %s', relative)
        self._prune(current)

    def _prune(self, current: dict[str, str]) -> None:
        with self._content.lock:
            self._content.snapshot = {name: digest for name, digest in self._content.snapshot.items()
                                      if name in current or name in self._content.received}
            self._content.versions = {name: version for name, version in self._content.versions.items()
                                      if name in self._content.snapshot}

    def _accept_scan(self, current: dict[str, str], stop: _StopFlag) -> bool:
        with self._lifecycle_lock:
            if stop.is_set():
                return False
            with self._content.lock:
                initial = not self._content.baselined
                if initial:
                    self._content.snapshot = dict(current, **self._content.snapshot)
                    self._content.baselined = True
            self._ready.set()
        if not initial:
            self._poll(current, stop)
        return True

    def _loop(self, stop: threading.Event) -> None:
        guard = _PollStop(stop, self._cancelled)
        try:
            while not guard.is_set():
                try:
                    with self._content.lock:
                        self._content.received.clear()
                    current = self._scan(guard)
                    if current is None or not self._accept_scan(current, guard):
                        return
                except OSError as error:
                    raise_caused_run_interruption(error)
                    autocontrol_logger.warning('folder sync scan: %r', error)
                stop.wait(self._interval)
        except (CancelledError, AsyncCancelledError, OperationCancelledError):
            if self._thread is not threading.current_thread():
                raise
            stop.set()
        finally:
            with self._lifecycle_lock:
                if self._thread is threading.current_thread():
                    self._thread = None
                    self._ready.clear()


def _identity(value: stat_result) -> tuple[int, int, int, int]:
    # Windows path stat and descriptor fstat can expose different ctime semantics; compare ctime within one descriptor.
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _read_digest(stream: BinaryIO, stop: Optional[_StopFlag]) -> Optional[str]:
    digest = sha256()
    opened = fstat(stream.fileno())
    while True:
        if stop is not None and stop.is_set():
            return None
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    after = fstat(stream.fileno())
    if _identity(opened) != _identity(after) or opened.st_ctime_ns != after.st_ctime_ns:
        raise OSError('folder sync file changed during hashing')
    return digest.hexdigest()


__all__ = ['FolderSyncEngine', 'FolderSyncCheckpoint', 'FolderSyncStateError']
