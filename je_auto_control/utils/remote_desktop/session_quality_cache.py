"""Thread-safe per-session quality + last-snapshot store.

Round 33's bug audit flagged that the Qt panel held two raw dicts
(``_session_qualities``, ``_session_snapshots``) shared between the
asyncio bridge thread (which writes from a ``StatsPoller`` callback)
and the Qt thread (which reads during paint and clears on session
shutdown). Plain-dict access is GIL-safe for individual operations in
CPython, but ``clear()`` interleaved with ``__setitem__`` from another
thread is documented as undefined, and "set after the producer was
stopped but its task not yet awaited" can leak stale entries.

This module bundles both dicts behind a single ``threading.Lock`` and
exposes a small CRUD surface so the panel cannot reintroduce the bug
by accident. Every public method is internally atomic.

Snapshot semantics: ``snapshot()`` returns a *frozen* copy of the
table, so callers can iterate without holding the lock and without
risking ``RuntimeError: dictionary changed size during iteration``.
"""
from __future__ import annotations

import threading
from typing import Any, Dict


class SessionQualityCache:
    """Per-session colour string + last :class:`StatsSnapshot`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._qualities: Dict[str, str] = {}
        self._snapshots: Dict[str, Any] = {}

    def set(self, session_id: str, *, color: str, snapshot: Any) -> None:
        """Write the latest sample for one session."""
        with self._lock:
            self._qualities[session_id] = color
            self._snapshots[session_id] = snapshot

    def get_color(self, session_id: str, default: str = "#555") -> str:
        with self._lock:
            return self._qualities.get(session_id, default)

    def get_snapshot(self, session_id: str) -> Any:
        with self._lock:
            return self._snapshots.get(session_id)

    def drop(self, session_id: str) -> None:
        """Forget a session — call when its poller has been stopped."""
        with self._lock:
            self._qualities.pop(session_id, None)
            self._snapshots.pop(session_id, None)

    def reset(self) -> None:
        """Forget every session."""
        with self._lock:
            self._qualities.clear()
            self._snapshots.clear()

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Return a frozen view: ``{session_id: {color, snapshot}}``."""
        with self._lock:
            return {
                sid: {
                    "color": self._qualities[sid],
                    "snapshot": self._snapshots.get(sid),
                }
                for sid in self._qualities
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._qualities)

    def __contains__(self, session_id: object) -> bool:
        with self._lock:
            return session_id in self._qualities

    def known_sessions(self) -> list:
        """Return a list snapshot of currently-tracked session ids."""
        with self._lock:
            return list(self._qualities.keys())


__all__ = ["SessionQualityCache"]
