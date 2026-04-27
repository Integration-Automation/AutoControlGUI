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
from pathlib import Path
from typing import Callable, Dict, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_POLL_S = 3.0


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
        self._stop = threading.Event()
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
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name="folder-sync", daemon=True,
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

    def _loop(self) -> None:
        # Build initial snapshot WITHOUT sending; treat pre-existing files
        # as "already synced" so engaging sync mid-edit doesn't re-upload
        # the entire directory.
        self._snapshot = self._scan()
        while not self._stop.is_set():
            self._stop.wait(self._interval)
            if self._stop.is_set():
                return
            current = self._scan()
            for rel, mtime in current.items():
                prev = self._snapshot.get(rel)
                if prev is not None and prev >= mtime:
                    continue
                full = self._watch / rel
                try:
                    self._sender(str(full), rel)
                    self._snapshot[rel] = mtime
                    autocontrol_logger.info("folder sync: pushed %s", rel)
                except (RuntimeError, OSError, ValueError) as error:
                    autocontrol_logger.warning(
                        "folder sync push %s: %r", rel, error,
                    )
            # Track deletions in snapshot (don't propagate, just stop
            # tracking). Do NOT blindly merge ``current`` here — that would
            # mark failed sends as already-synced and break the next-tick
            # retry promise made in this engine's docstring. Successful
            # sends already updated ``_snapshot[rel]`` above.
            self._snapshot = {
                rel: mtime for rel, mtime in self._snapshot.items()
                if rel in current
            }


__all__ = ["FolderSyncEngine"]
