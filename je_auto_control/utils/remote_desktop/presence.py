"""Thread-safe presence registry for the multi-viewer remote desktop.

Tracks one ``ViewerPresence`` row per connected viewer: identity,
role (``controller`` / ``observer``), and most-recent cursor position.
Plugged into :class:`MultiViewerHost` it lets the host fan out the
roster to every viewer so each one can render the other cursors as
ghost overlays, and gates input dispatch by role so observers cannot
move the mouse / type.

Pure stdlib + dataclasses — no aiortc / Qt deps — so the module is
unit-testable on any platform and can be re-used by the REST API and
the MCP server.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


ROLE_CONTROLLER = "controller"
ROLE_OBSERVER = "observer"
_VALID_ROLES = frozenset({ROLE_CONTROLLER, ROLE_OBSERVER})


class PresenceError(ValueError):
    """Raised when a presence operation is invalid (unknown id, bad role)."""


@dataclass(frozen=True)
class ViewerPresence:
    """One row in the live viewer roster."""

    viewer_id: str
    label: str
    role: str
    cursor_x: Optional[int] = None
    cursor_y: Optional[int] = None
    last_seen_iso: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def can_control(self) -> bool:
        return self.role == ROLE_CONTROLLER


PresenceListener = Callable[[str, Optional[ViewerPresence]], None]


class PresenceRegistry:
    """In-memory, lock-guarded ``viewer_id → ViewerPresence`` registry."""

    def __init__(self) -> None:
        self._rows: Dict[str, ViewerPresence] = {}
        self._lock = threading.RLock()
        self._listeners: List[PresenceListener] = []

    # --- registration ---------------------------------------------

    def register(self, viewer_id: str, label: str,
                 *, role: str = ROLE_OBSERVER) -> ViewerPresence:
        """Insert (or replace) the row for ``viewer_id`` and notify listeners."""
        normalised_role = _normalise_role(role)
        row = ViewerPresence(
            viewer_id=_require_id(viewer_id),
            label=str(label or ""),
            role=normalised_role,
            cursor_x=None, cursor_y=None,
            last_seen_iso=_now_iso(),
        )
        self._set(row)
        return row

    def unregister(self, viewer_id: str) -> bool:
        """Drop the row; returns True if it existed, False otherwise."""
        with self._lock:
            existed = self._rows.pop(viewer_id, None) is not None
        if existed:
            self._notify(viewer_id, None)
        return existed

    def clear(self) -> None:
        """Drop every row. Each removal emits a listener event."""
        with self._lock:
            ids = list(self._rows.keys())
            self._rows.clear()
        for viewer_id in ids:
            self._notify(viewer_id, None)

    # --- mutation -------------------------------------------------

    def update_cursor(self, viewer_id: str, x: int, y: int) -> ViewerPresence:
        """Move the cursor pin without touching role / label."""
        with self._lock:
            existing = self._rows.get(viewer_id)
            if existing is None:
                raise PresenceError(f"unknown viewer_id: {viewer_id!r}")
            updated = ViewerPresence(
                viewer_id=existing.viewer_id, label=existing.label,
                role=existing.role,
                cursor_x=int(x), cursor_y=int(y),
                last_seen_iso=_now_iso(),
            )
            self._rows[viewer_id] = updated
        self._notify(viewer_id, updated)
        return updated

    def update_role(self, viewer_id: str, role: str) -> ViewerPresence:
        """Promote / demote a viewer between controller and observer."""
        normalised_role = _normalise_role(role)
        with self._lock:
            existing = self._rows.get(viewer_id)
            if existing is None:
                raise PresenceError(f"unknown viewer_id: {viewer_id!r}")
            updated = ViewerPresence(
                viewer_id=existing.viewer_id, label=existing.label,
                role=normalised_role,
                cursor_x=existing.cursor_x, cursor_y=existing.cursor_y,
                last_seen_iso=_now_iso(),
            )
            self._rows[viewer_id] = updated
        self._notify(viewer_id, updated)
        return updated

    def can_control(self, viewer_id: str) -> bool:
        """Convenience: True iff the viewer is currently a controller."""
        with self._lock:
            row = self._rows.get(viewer_id)
        return row is not None and row.can_control()

    # --- inspection ----------------------------------------------

    def list(self) -> List[ViewerPresence]:
        with self._lock:
            return sorted(self._rows.values(), key=lambda r: r.viewer_id)

    def get(self, viewer_id: str) -> Optional[ViewerPresence]:
        with self._lock:
            return self._rows.get(viewer_id)

    def count(self) -> int:
        with self._lock:
            return len(self._rows)

    def controller_ids(self) -> List[str]:
        with self._lock:
            return [row.viewer_id for row in self._rows.values()
                    if row.can_control()]

    # --- listeners ------------------------------------------------

    def add_listener(self, listener: PresenceListener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: PresenceListener) -> bool:
        with self._lock:
            try:
                self._listeners.remove(listener)
            except ValueError:
                return False
        return True

    # --- internals ------------------------------------------------

    def _set(self, row: ViewerPresence) -> None:
        with self._lock:
            self._rows[row.viewer_id] = row
        self._notify(row.viewer_id, row)

    def _notify(self, viewer_id: str,
                row: Optional[ViewerPresence]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(viewer_id, row)
            except (RuntimeError, OSError, ValueError):
                continue


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_id(viewer_id: str) -> str:
    if not isinstance(viewer_id, str) or not viewer_id.strip():
        raise PresenceError("viewer_id must be a non-empty string")
    return viewer_id.strip()


def _normalise_role(role: str) -> str:
    lowered = (role or "").strip().lower()
    if lowered not in _VALID_ROLES:
        raise PresenceError(
            f"role must be one of {sorted(_VALID_ROLES)}, got {role!r}",
        )
    return lowered


_default_registry: Optional[PresenceRegistry] = None
_default_registry_lock = threading.Lock()


def default_presence_registry() -> PresenceRegistry:
    """Singleton accessor for the per-process presence registry."""
    global _default_registry
    if _default_registry is None:
        with _default_registry_lock:
            if _default_registry is None:
                _default_registry = PresenceRegistry()
    return _default_registry


__all__ = [
    "PresenceError", "PresenceListener", "PresenceRegistry",
    "ROLE_CONTROLLER", "ROLE_OBSERVER", "ViewerPresence",
    "default_presence_registry",
]
