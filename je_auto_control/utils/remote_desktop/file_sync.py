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

When both sides mirror the same folder, a file that *arrived* from the peer
is new on disk and would be pushed straight back, and back again from the
other side. The receiving code tells the engine with
:meth:`FolderSyncEngine.note_received`; the engine then leaves that file
alone until its content changes locally.
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_POLL_S = 3.0
#: How many "this came from the peer" notes one engine keeps.
_MAX_RECEIVED_NOTES = 4096


class FolderSyncEngine:
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
        self._snapshot: Dict[str, float] = {}  # rel_path -> mtime
        self._received: Dict[str, str] = {}  # rel_path -> sha256 of what the peer sent
        self._received_lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None:
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
        with self._lifecycle_lock:
            self._stop.set()
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join(timeout=2.0)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Block until the baseline snapshot exists; ``True`` if it does.

        ``start()`` returns as soon as the worker is spawned, so a file
        created immediately after it can still land in the baseline and
        never be pushed. Callers that add files right after starting
        should wait here first.
        """
        return self._ready.wait(timeout)

    def note_received(self, remote_name: str, *, sha256: Optional[str] = None) -> None:
        """Record that ``remote_name`` in the watched folder came from the peer.

        The engine will not push it back while its content is still what the
        peer sent. Pass the content's ``sha256`` to note a file *before* it
        is written -- otherwise a poll landing between the write and this
        call would already have echoed it; without it the file on disk is
        hashed now. A later local edit changes the hash and is pushed as usual.
        """
        rel = Path(remote_name).as_posix()
        digest = sha256.lower() if sha256 else self._digest(self._watch / rel)
        if digest is None:
            return
        with self._received_lock:
            # A note may be made before its file lands, so notes cannot be
            # pruned by what is on disk; the oldest go once there are many.
            self._received.pop(rel, None)
            self._received[rel] = digest
            while len(self._received) > _MAX_RECEIVED_NOTES:
                self._received.pop(next(iter(self._received)))

    @staticmethod
    def _digest(path: Path) -> Optional[str]:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    def _is_echo(self, rel: str) -> bool:
        """Whether ``rel`` still holds exactly what the peer sent."""
        with self._received_lock:
            noted = self._received.get(rel)
        if noted is None:
            return False
        if self._digest(self._watch / rel) == noted:
            return True
        # Edited here since it arrived: it is a local change again.
        with self._received_lock:
            self._received.pop(rel, None)
        return False

    def poll_once(self) -> List[str]:
        """Run one diff pass now and return the relative paths pushed.

        The first pass only records what is already there. The background
        thread calls this every interval; tests and callers that drive the
        engine themselves can call it directly.
        """
        if not self._ready.is_set():
            self._snapshot = self._scan()
            self._ready.set()
            return []
        current = self._scan()
        pushed: List[str] = []
        changed = [(rel, mtime) for rel, mtime in current.items()
                   if self._snapshot.get(rel, float("-inf")) < mtime]
        for rel, mtime in changed:
            if self._is_echo(rel):
                self._snapshot[rel] = mtime
            elif self._push(rel, mtime):
                pushed.append(rel)
        # Track deletions in snapshot (don't propagate, just stop
        # tracking). Do NOT blindly merge ``current`` here — that would
        # mark failed sends as already-synced and break the next-tick
        # retry promise made in this engine's docstring. Successful
        # sends already updated ``_snapshot[rel]``.
        self._snapshot = {
            rel: mtime for rel, mtime in self._snapshot.items()
            if rel in current
        }
        return pushed

    def _push(self, rel: str, mtime: float) -> bool:
        try:
            self._sender(str(self._watch / rel), rel)
        except (RuntimeError, OSError, ValueError) as error:
            autocontrol_logger.warning("folder sync push %s: %r", rel, error)
            return False
        self._snapshot[rel] = mtime
        autocontrol_logger.info("folder sync: pushed %s", rel)
        return True

    def _scan(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        try:
            iterator = (self._watch.rglob("*") if self._include_subdirs
                        else self._watch.iterdir())
            for entry in iterator:
                if not entry.is_file():
                    continue
                rel = str(entry.relative_to(self._watch).as_posix())
                try:
                    out[rel] = entry.stat().st_mtime
                except OSError:
                    continue
        except OSError as error:
            autocontrol_logger.warning("folder sync scan: %r", error)
        return out

    def _loop(self, stop: threading.Event) -> None:
        # Build initial snapshot WITHOUT sending; treat pre-existing files
        # as "already synced" so engaging sync mid-edit doesn't re-upload
        # the entire directory.
        self.poll_once()
        while not stop.is_set():
            stop.wait(self._interval)
            if stop.is_set():
                return
            self.poll_once()


__all__ = ["FolderSyncEngine"]
