"""Polling additive folder mirror using content digests, explicit receive receipts and owned stopped workers."""
from __future__ import annotations

from _thread import LockType
from contextlib import closing
from dataclasses import dataclass, field
from hashlib import sha256
import os
from os import fstat, stat_result
import threading
from pathlib import Path
from typing import BinaryIO, Callable, Generator, Optional

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_DEFAULT_POLL_S = 3.0


@dataclass
class _ContentState:
    snapshot: dict[str, str] = field(default_factory=dict)
    baselined: bool = False
    received: set[str] = field(default_factory=set)
    versions: dict[str, int] = field(default_factory=dict)
    sequence: int = 0
    lock: LockType = field(default_factory=threading.Lock)


# pylint: disable-next=too-many-instance-attributes  # reason: watch options, worker ownership and locked content baseline
class FolderSyncEngine:
    """Mirror new or changed bytes through a synchronous sender; retry failures on the next tick.

    Existing files establish a baseline on the first run; restarts retain pending/offline
    edits. Deletions never propagate. Receiving transports
    call record_received after publishing a file to prevent sending those bytes back.
    A stopped but blocked sender remains owned; start cannot overlap it with a new run.
    """

    def __init__(self, *, watch_dir: Path, sender: Callable[[str, str], None],
                 poll_interval_s: float = _DEFAULT_POLL_S, include_subdirs: bool = False) -> None:
        self._watch = Path(watch_dir)
        self._sender = sender
        self._interval = max(0.5, float(poll_interval_s))
        self._include_subdirs = bool(include_subdirs)
        self._content = _ContentState()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()

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

    def stop(self) -> None:
        """Signal cancellation and wait at most two seconds, retaining ownership of a blocked sender."""
        with self._lifecycle_lock:
            self._stop.set()
            self._ready.clear()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def is_running(self) -> bool:
        """Report a live worker, including a stopped worker finishing an in-flight sender call."""
        with self._lifecycle_lock:
            return self._thread is not None and self._thread.is_alive()

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Wait for a complete initial content baseline; stopped or failed scans are never ready."""
        return self._ready.wait(timeout)

    def record_received(self, path: str | Path) -> bool:
        """Accept an already-published regular file inside this watch root as received, without echoing it.

        Return False for outside, excluded, missing, redirected or changing files. Receipt
        hashing never starts a worker, and later local content edits still propagate.
        """
        selected = Path(path)
        try:
            root = self._watch.resolve(strict=True)
            if selected.is_symlink():
                return False
            selected = selected.resolve(strict=True)
            relative = selected.relative_to(root)
            if not self._include_subdirs and len(relative.parts) != 1:
                return False
            digest = self._digest(selected, None)
        except (OSError, ValueError) as error:
            raise_caused_run_interruption(error)
            return False
        if digest is None:
            return False
        with self._content.lock:
            self._content.snapshot[relative.as_posix()] = digest
            self._content.received.add(relative.as_posix())
            self._content.sequence += 1
            self._content.versions[relative.as_posix()] = self._content.sequence
        return True

    @staticmethod
    def _digest(path: Path, stop: Optional[threading.Event]) -> Optional[str]:
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

    def _paths(self, stop: threading.Event) -> Generator[Path, None, None]:
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

    def _scan(self, stop: threading.Event) -> Optional[dict[str, str]]:
        out: dict[str, str] = {}
        with closing(self._paths(stop)) as paths:
            for entry in paths:
                digest = self._digest(entry, stop)
                if digest is None:
                    return None
                out[entry.relative_to(self._watch).as_posix()] = digest
        return out

    def _poll(self, current: dict[str, str], stop: threading.Event) -> None:
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

    def _accept_scan(self, current: dict[str, str], stop: threading.Event) -> bool:
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
        try:
            while not stop.is_set():
                try:
                    with self._content.lock:
                        self._content.received.clear()
                    current = self._scan(stop)
                    if current is None or not self._accept_scan(current, stop):
                        return
                except OSError as error:
                    raise_caused_run_interruption(error)
                    autocontrol_logger.warning('folder sync scan: %r', error)
                stop.wait(self._interval)
        finally:
            with self._lifecycle_lock:
                if self._thread is threading.current_thread():
                    self._thread = None
                    self._ready.clear()


def _identity(value: stat_result) -> tuple[int, int, int, int]:
    # Windows path stat and descriptor fstat can expose different ctime semantics; compare ctime within one descriptor.
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _read_digest(stream: BinaryIO, stop: Optional[threading.Event]) -> Optional[str]:
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


__all__ = ['FolderSyncEngine']
