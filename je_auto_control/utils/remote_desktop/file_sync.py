"""Polling-based folder mirror over the existing files DataChannel.

Each :class:`FolderSyncEngine` watches a local directory; on each tick it
diffs the current filesystem state against its snapshot and pushes any
new / modified files to the peer using a sender callable (typically
``WebRTCDesktopViewer.send_file`` or ``WebRTCDesktopHost.push_file``).
Deletions and renames aren't propagated — sync is "additive only" so
local edits never silently destroy remote work. The receiving side just
treats the pushed files like any other file transfer (saved into the
inbox dir).

Polling interval default 3s — enough for most edit/save workflows
without burning CPU; bump it lower for tighter sync.
"""
from __future__ import annotations

import threading
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_POLL_S = 3.0


class FolderSyncEngine:  # pylint: disable=too-many-instance-attributes  # reason: per-run lifecycle and locked content state
    """Mirror a local directory onto the peer side via a file-send callable.

    ``sender(local_path, remote_name)`` should perform the actual transfer
    (raise on failure). The engine retries on the next tick.
    """

    def __init__(self, *, watch_dir: Path,
                 sender: Callable[[str, str], None],
                 poll_interval_s: float = _DEFAULT_POLL_S,
                 include_subdirs: bool = False) -> None:
        self._watch = Path(watch_dir)
        self._sender = sender
        self._interval = max(0.5, float(poll_interval_s))
        self._include_subdirs = bool(include_subdirs)
        self._snapshot: Dict[str, str] = {}  # rel_path -> content SHA256
        self._received: Dict[str, str] = {}
        self._content_lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()

    def start(self) -> None:
        """Start one mirror worker; a stopped worker still draining its sender blocks restart."""
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if not self._watch.exists() or not self._watch.is_dir():
                raise FileNotFoundError(
                    f"watch dir not a directory: {self._watch}"
                )
            # A fresh event per run, never clear() on the old one: a thread that
            # outlived stop()'s join would see it cleared and keep running.
            self._stop = threading.Event()
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._loop, args=(self._stop,), name="folder-sync", daemon=True,
            )
            self._thread.start()
        autocontrol_logger.info(
            "folder sync: watching %s every %.1fs", self._watch, self._interval,
        )

    def stop(self) -> None:
        """Cancel and join for at most two seconds without releasing ownership of a live sender."""
        with self._lifecycle_lock:
            self._stop.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lifecycle_lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None

    def _request_stop(self) -> None:
        """Revoke new sends without waiting for a currently draining transfer."""
        with self._lifecycle_lock:
            self._stop.set()

    def is_running(self) -> bool:
        """Whether this engine's worker is still alive, including a draining transfer."""
        return self._thread is not None and self._thread.is_alive()

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Block until the baseline snapshot exists; ``True`` if it does.

        ``start()`` returns as soon as the worker is spawned, so a file
        created immediately after it can still land in the baseline and
        never be pushed. Callers that add files right after starting
        should wait here first.
        """
        return self._ready.wait(timeout)

    def mark_received(self, path: Path) -> None:
        """Suppress only this received file identity when its inbox is also watched."""
        target = Path(path)
        if not target.resolve().is_relative_to(self._watch.resolve()) or target.is_symlink():
            return
        try:
            identity = self._identity(target)
            relative = target.resolve().relative_to(self._watch.resolve()).as_posix()
            with self._content_lock:
                self._received[relative] = identity[0]
        except OSError:
            return

    @staticmethod
    def _identity(path: Path) -> Tuple[str, int, int]:
        before = path.stat()
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(65536), b''):
                digest.update(chunk)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise OSError('file changed while being captured')
        return digest.hexdigest(), after.st_size, after.st_mtime_ns

    def _scan(self) -> Dict[str, Tuple[str, int, int]]:
        out: Dict[str, Tuple[str, int, int]] = {}
        try:
            iterator = (self._watch.rglob("*") if self._include_subdirs
                        else self._watch.iterdir())
            for entry in iterator:
                if (not entry.is_file() or entry.is_symlink() or entry.name.endswith('.part')
                        or entry.name.startswith('.sync-')
                        or not entry.resolve().is_relative_to(self._watch.resolve())):
                    continue
                rel = str(entry.relative_to(self._watch).as_posix())
                try:
                    out[rel] = self._identity(entry)
                except OSError:
                    continue
        except OSError as error:
            autocontrol_logger.warning("folder sync scan: %r", error)
        return out

    def _loop(self, stop: threading.Event) -> None:
        # Build initial snapshot WITHOUT sending; treat pre-existing files
        # as "already synced" so engaging sync mid-edit doesn't re-upload
        # the entire directory.
        observed = self._scan()
        self._snapshot = {name: identity[0] for name, identity in observed.items()}
        self._ready.set()
        while not stop.is_set():
            stop.wait(self._interval)
            if stop.is_set():
                return
            current = self._scan()
            for rel, identity in current.items():
                if stop.is_set():
                    return
                self._push_if_changed(rel, identity, observed.get(rel), stop)
            # Track deletions in snapshot (don't propagate, just stop
            # tracking). Do NOT blindly merge ``current`` here — that would
            # mark failed sends as already-synced and break the next-tick
            # retry promise made in this engine's docstring. Successful
            # sends already updated ``_snapshot[rel]`` above.
            self._snapshot = {
                rel: digest for rel, digest in self._snapshot.items()
                if rel in current
            }
            observed = current

    def _push_if_changed(self, relative: str, identity: Tuple[str, int, int],
                         observed: Optional[Tuple[str, int, int]], stop: threading.Event) -> None:
        with self._content_lock:
            received = self._received.pop(relative, None)
        if received == identity[0]:
            self._snapshot[relative] = received
        if self._snapshot.get(relative) == identity[0] or observed != identity:
            return
        try:
            self._send_snapshot(relative, identity)
            if not stop.is_set():
                self._snapshot[relative] = identity[0]
                autocontrol_logger.info('folder sync: pushed %s', relative)
        except (RuntimeError, OSError, ValueError) as error:
            autocontrol_logger.warning('folder sync push %s: %r', relative, error)

    def _send_snapshot(self, relative: str, expected: Tuple[str, int, int]) -> None:
        """Send owned, stable bytes; the synchronous sender must consume them before returning."""
        source = self._watch / relative
        if source.is_symlink() or not source.resolve().is_relative_to(self._watch.resolve()):
            raise OSError('source escaped the watched directory')
        with tempfile.TemporaryDirectory(prefix='je-folder-sync-') as folder:
            captured = Path(folder) / source.name
            shutil.copyfile(source, captured)
            if self._identity(source) != expected or self._identity(captured)[:2] != expected[:2]:
                raise OSError('source changed before transfer')
            self._sender(str(captured), relative)


__all__ = ["FolderSyncEngine"]
