"""Polling-based recorder for accessibility events.

The pure-Python recorder polls :func:`find_accessibility_element`
output at a configurable interval and emits an event whenever the
*focused element* (by name + role) changes, or when its bounds shift
by more than ``min_movement_px`` pixels. macOS's native AXObserver
API would be lower-latency but requires the pyobjc run-loop bridge;
polling is good enough for human-speed automation playback and works
on Windows / Linux through the same interface.

Thread-safe — :meth:`start` spawns a background thread that the
recorder owns; :meth:`stop` joins it.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple


_DEFAULT_POLL_S = 0.25
_DEFAULT_MIN_MOVEMENT = 8


@dataclass(frozen=True)
class AXRecorderEvent:
    """One observed accessibility change."""

    timestamp_iso: str
    kind: str           # "focus" | "bounds" | "tree_changed"
    role: str
    name: str
    bounds: Tuple[int, int, int, int]
    app_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["bounds"] = list(self.bounds)
        return data


# A snapshot fetcher takes ``app_name`` and returns the focused
# element as a dict (name / role / bounds / app_name) or None. The
# default uses :func:`find_accessibility_element`; tests inject a fake.
SnapshotFetcher = Callable[[Optional[str]], Optional[Dict[str, Any]]]


class AccessibilityRecorder:
    """Capture focused-element changes to a list. Drain via :meth:`events`."""

    def __init__(self, *, app_name: Optional[str] = None,
                 poll_interval_s: float = _DEFAULT_POLL_S,
                 min_movement_px: int = _DEFAULT_MIN_MOVEMENT,
                 fetcher: Optional[SnapshotFetcher] = None) -> None:
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be positive")
        self._app_name = app_name
        self._poll = float(poll_interval_s)
        self._min_movement = max(0, int(min_movement_px))
        self._fetcher = fetcher or _default_fetcher
        self._events: List[AXRecorderEvent] = []
        self._previous: Optional[Dict[str, Any]] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # --- lifecycle -----------------------------------------------

    def start(self) -> None:
        """Spawn the background polling thread if not already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="AccessibilityRecorder", daemon=True,
        )
        self._thread.start()

    def stop(self) -> List[AXRecorderEvent]:
        """Signal the loop and wait for it; return every captured event."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._poll * 4 + 1.0)
        self._thread = None
        return self.events()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def events(self) -> List[AXRecorderEvent]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
        self._previous = None

    # --- sample-now helpers (for tests + adhoc use) --------------

    def sample_once(self) -> Optional[AXRecorderEvent]:
        """Take one snapshot, emit an event if it differs from the previous."""
        snapshot = self._fetcher(self._app_name)
        return self._compare_and_emit(snapshot)

    # --- internals -----------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.sample_once()
            except (RuntimeError, OSError, ValueError):
                pass
            self._stop.wait(self._poll)

    def _compare_and_emit(self, snapshot: Optional[Dict[str, Any]],
                          ) -> Optional[AXRecorderEvent]:
        if snapshot is None:
            if self._previous is not None:
                event = _make_event(
                    "tree_changed", self._previous, kind_override=True,
                )
                self._record(event)
                self._previous = None
                return event
            return None
        if self._previous is None:
            event = _make_event("focus", snapshot)
            self._record(event)
            self._previous = snapshot
            return event
        if self._is_different_element(snapshot, self._previous):
            event = _make_event("focus", snapshot)
        elif self._bounds_moved(snapshot, self._previous):
            event = _make_event("bounds", snapshot)
        else:
            return None
        self._record(event)
        self._previous = snapshot
        return event

    def _is_different_element(self, a: Dict[str, Any],
                               b: Dict[str, Any]) -> bool:
        return (a.get("name") != b.get("name")
                or a.get("role") != b.get("role"))

    def _bounds_moved(self, a: Dict[str, Any],
                       b: Dict[str, Any]) -> bool:
        new = tuple(a.get("bounds") or (0, 0, 0, 0))
        old = tuple(b.get("bounds") or (0, 0, 0, 0))
        if len(new) < 4 or len(old) < 4:
            return False
        moved = sum(abs(int(n) - int(o)) for n, o in zip(new, old))
        return moved > self._min_movement

    def _record(self, event: AXRecorderEvent) -> None:
        with self._lock:
            self._events.append(event)


def _make_event(kind: str, snapshot: Dict[str, Any],
                kind_override: bool = False) -> AXRecorderEvent:
    bounds = snapshot.get("bounds") or (0, 0, 0, 0)
    return AXRecorderEvent(
        timestamp_iso=_now_iso(),
        kind=kind,
        role=str(snapshot.get("role") or ""),
        name=str(snapshot.get("name") or ""),
        bounds=tuple(int(v) for v in bounds[:4]),
        app_name=str(snapshot.get("app_name") or ""),
        details={"raw": dict(snapshot)} if kind_override else {},
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _default_fetcher(app_name: Optional[str]) -> Optional[Dict[str, Any]]:
    try:
        from je_auto_control.utils.accessibility.accessibility_api import (
            find_accessibility_element,
        )
        element = find_accessibility_element(app_name=app_name)
    except (RuntimeError, OSError, ValueError):
        return None
    if element is None:
        return None
    return {
        "name": getattr(element, "name", ""),
        "role": getattr(element, "role", ""),
        "bounds": getattr(element, "bounds", (0, 0, 0, 0)),
        "app_name": getattr(element, "app_name", ""),
    }


__all__ = [
    "AXRecorderEvent", "AccessibilityRecorder", "SnapshotFetcher",
]
