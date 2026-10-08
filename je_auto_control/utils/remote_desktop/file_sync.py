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

**A file still being written is not pushed.** A changed file goes out only
once its size and modification time are the same on two polls in a row, so
a large copy or a slow save is sent whole, one poll later, instead of as a
truncated first half. Names that mark a file as in progress (``*.part``,
``*.partial``, ``*.tmp``, ``*.crdownload`` -- which covers the
``.<name>.<id>.part`` files the receivers here write) are never mirrored: a
program that writes under such a name and renames when it is done is picked
up complete.

**A file that arrived from the peer is not pushed back.** When both sides
mirror the same folder, a received file is new on disk and would be sent
straight back, and back again from the other side. The receivers in this
package (:class:`~je_auto_control.utils.remote_desktop.webrtc_files.FileTransferReceiver`
and :class:`~je_auto_control.utils.remote_desktop.file_transfer.FileReceiver`)
call :func:`note_incoming` just before they rename a finished file into
place; every live engine whose folder holds it records the content's hash
through :meth:`FolderSyncEngine.note_received` and leaves the file alone
until it changes locally.
"""
from __future__ import annotations

import hashlib
import threading
import weakref
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple, Union

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_POLL_S = 3.0
#: How many "this came from the peer" notes one engine keeps.
_MAX_RECEIVED_NOTES = 4096
#: Name endings that mark a file as still being written; never mirrored.
IN_PROGRESS_SUFFIXES = (".part", ".partial", ".tmp", ".crdownload")

_ENGINES: "weakref.WeakSet[FolderSyncEngine]" = weakref.WeakSet()
_ENGINES_LOCK = threading.Lock()


class _FileState(NamedTuple):
    """What one scan saw of a file: its mtime, and (mtime ns, size) to compare."""
    mtime: float
    signature: Tuple[int, int]


def _file_digest(path: Path) -> Optional[str]:
    """The SHA-256 of a file read in chunks; ``None`` when it cannot be read."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


class FolderSyncEngine:
    """Mirror a local directory onto the peer side via a file-send callable.

    ``sender(local_path, remote_name)`` should perform the actual transfer
    (raise on failure). The engine retries on the next tick.

    ``wait_until_stable`` (default on) holds a changed file back until two
    polls in a row see the same size and modification time; turn it off to
    push on first sight, as the engine did before. ``ignore_suffixes`` are
    the name endings never mirrored (default :data:`IN_PROGRESS_SUFFIXES`).
    """

    def __init__(self, *, watch_dir: Path,
                 sender: Callable[[str, str], None],
                 poll_interval_s: float = _DEFAULT_POLL_S,
                 include_subdirs: bool = False,
                 wait_until_stable: bool = True,
                 ignore_suffixes: Sequence[str] = IN_PROGRESS_SUFFIXES) -> None:
        self._watch = Path(watch_dir)
        self._sender = sender
        self._interval = max(0.5, float(poll_interval_s))
        self._include_subdirs = bool(include_subdirs)
        self._wait_until_stable = bool(wait_until_stable)
        self._ignore_suffixes = tuple(suffix.lower() for suffix in ignore_suffixes)
        self._snapshot: Dict[str, float] = {}  # rel_path -> mtime
        # rel_path -> what the last poll saw of a changed file not pushed yet
        self._settling: Dict[str, Tuple[int, int]] = {}
        self._received: Dict[str, str] = {}  # rel_path -> sha256 of what the peer sent
        self._received_lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()
        with _ENGINES_LOCK:
            _ENGINES.add(self)

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

    def relative_name(self, path: Union[str, Path]) -> Optional[str]:
        """``path`` as this engine names it, or ``None`` if it does not mirror it.

        A file directly in the watched folder is covered; one in a subfolder
        only when the engine was built with ``include_subdirs``.
        """
        try:
            relative = Path(path).resolve().relative_to(self._watch.resolve())
        except (OSError, ValueError):
            return None
        if not relative.parts or (len(relative.parts) > 1 and not self._include_subdirs):
            return None
        return relative.as_posix()

    def note_received(self, remote_name: str, *, sha256: Optional[str] = None) -> None:
        """Record that ``remote_name`` in the watched folder came from the peer.

        The engine will not push it back while its content is still what the
        peer sent. Pass the content's ``sha256`` to note a file *before* it
        is written -- otherwise a poll landing between the write and this
        call would already have echoed it; without it the file on disk is
        hashed now. A later local edit changes the hash and is pushed as usual.

        The receivers in this package call this through :func:`note_incoming`;
        call it directly only for a file that arrived some other way.
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
        return _file_digest(path)

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

    def _has_settled(self, rel: str, state: _FileState) -> bool:
        """Whether ``rel`` looks the same as it did on the previous poll."""
        if not self._wait_until_stable or self._settling.get(rel) == state.signature:
            return True
        self._settling[rel] = state.signature
        return False

    def poll_once(self) -> List[str]:
        """Run one diff pass now and return the relative paths pushed.

        The first pass only records what is already there. The background
        thread calls this every interval; tests and callers that drive the
        engine themselves can call it directly.
        """
        current = self._scan()
        if not self._ready.is_set():
            self._snapshot = {rel: state.mtime for rel, state in current.items()}
            self._ready.set()
            return []
        pushed: List[str] = []
        changed = [(rel, state) for rel, state in current.items()
                   if self._snapshot.get(rel, float("-inf")) < state.mtime]
        for rel, state in changed:
            if self._is_echo(rel):
                self._snapshot[rel] = state.mtime
            elif self._has_settled(rel, state) and self._push(rel, state.mtime):
                pushed.append(rel)
        self._forget(current, {rel for rel, _state in changed})
        return pushed

    def _forget(self, current: Dict[str, _FileState], waiting: set) -> None:
        """Drop what is tracked for files that are gone or no longer waiting."""
        # Track deletions in snapshot (don't propagate, just stop
        # tracking). Do NOT blindly merge ``current`` here — that would
        # mark failed sends as already-synced and break the next-tick
        # retry promise made in this engine's docstring. Successful
        # sends already updated ``_snapshot[rel]``.
        self._snapshot = {
            rel: mtime for rel, mtime in self._snapshot.items()
            if rel in current
        }
        self._settling = {rel: seen for rel, seen in self._settling.items() if rel in waiting}

    def _push(self, rel: str, mtime: float) -> bool:
        try:
            self._sender(str(self._watch / rel), rel)
        except (RuntimeError, OSError, ValueError) as error:
            # _settling keeps the file's state, so the retry is the next tick.
            autocontrol_logger.warning("folder sync push %s: %r", rel, error)
            return False
        self._snapshot[rel] = mtime
        self._settling.pop(rel, None)
        autocontrol_logger.info("folder sync: pushed %s", rel)
        return True

    def _scan(self) -> Dict[str, _FileState]:
        out: Dict[str, _FileState] = {}
        try:
            iterator = (self._watch.rglob("*") if self._include_subdirs
                        else self._watch.iterdir())
            for entry in iterator:
                if not entry.is_file() or entry.name.lower().endswith(self._ignore_suffixes):
                    continue
                rel = str(entry.relative_to(self._watch).as_posix())
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                out[rel] = _FileState(stat.st_mtime, (stat.st_mtime_ns, stat.st_size))
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


def live_engines() -> List[FolderSyncEngine]:
    """Every :class:`FolderSyncEngine` that still exists in this process."""
    with _ENGINES_LOCK:
        return list(_ENGINES)


def note_incoming(final_path: Union[str, Path],
                  content_path: Union[str, Path, None] = None) -> int:
    """Tell every engine mirroring ``final_path``'s folder that the peer sent it.

    For the code that receives a file. Call it *before* the finished file is
    renamed into place, passing the temporary file that holds the content as
    ``content_path``: the note is then in place before any poll can see the
    file under its final name. Returns how many engines were told; when no
    engine mirrors that folder the file is not even read.
    """
    covering = [(engine, name) for engine in live_engines()
                for name in [engine.relative_name(final_path)] if name is not None]
    if not covering:
        return 0
    digest = _file_digest(Path(content_path if content_path is not None else final_path))
    if digest is None:
        return 0
    for engine, name in covering:
        engine.note_received(name, sha256=digest)
    return len(covering)


__all__ = ["FolderSyncEngine", "IN_PROGRESS_SUFFIXES", "live_engines", "note_incoming"]
