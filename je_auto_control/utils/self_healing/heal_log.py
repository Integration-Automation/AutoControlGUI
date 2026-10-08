"""Append-only JSON-lines log of self-healing locator events.

A line written before the version / context fields existed has none of them
and still loads: every field added since is optional. A line written by a
newer build may carry fields this one does not know; they are dropped rather
than costing the reader the whole event.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

from je_auto_control.utils.json_store.json_store import append_json_line


@dataclass(frozen=True)
class HealEvent:
    """One self-healing locate attempt persisted to disk."""

    timestamp: str
    method: str
    coordinates: Optional[List[int]]
    duration_ms: float
    template_path: Optional[str] = None
    description: Optional[str] = None
    image_error: Optional[str] = None
    vlm_error: Optional[str] = None
    # --- added with schema_version 2; absent from older lines -------------
    #: ``None`` on a line written before the field existed.
    schema_version: Optional[int] = None
    run_id: Optional[str] = None
    step_id: Optional[str] = None
    locator_id: Optional[str] = None
    locator_version: Optional[str] = None
    backend: Optional[str] = None
    model: Optional[str] = None
    #: ``[x1, y1, x2, y2]`` both strategies were confined to, if any.
    screen_region: Optional[List[int]] = None
    image_ms: Optional[float] = None
    vlm_ms: Optional[float] = None
    #: What was done with the hit (``"click"``); ``None`` for a bare locate.
    action: Optional[str] = None
    #: ``True`` / ``False`` once a caller-supplied check ran after the action;
    #: ``None`` when nothing verified it. A located element is not a verified
    #: action, so this is never inferred from ``method``.
    action_verified: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict snapshot safe for JSON / network transport."""
        return asdict(self)


def default_heal_log_path() -> Path:
    """``~/.je_auto_control/self_healing_events.jsonl``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "self_healing_events.jsonl"


class HealEventLog:
    """Thread-safe append-only JSON-lines store for HealEvent records."""

    def __init__(self, path: Optional[Path] = None) -> None:
        # Only an explicit path is kept; the default is resolved on every
        # use, because this module builds a shared instance while the
        # package imports -- before a test suite's conftest.py can set HOME.
        self._explicit_path: Optional[Path] = (
            Path(path) if path is not None else None)
        self._lock = threading.Lock()

    @property
    def _path(self) -> Path:
        return self._explicit_path or default_heal_log_path()

    @property
    def path(self) -> Path:
        """Filesystem path the log writes to (parent created on append)."""
        return self._path

    def append(self, event: HealEvent) -> None:
        """Atomically append one event as a JSON line."""
        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        with self._lock:
            append_json_line(self._path, payload)

    def list_events(self, limit: int = 100) -> List[HealEvent]:
        """Return up to ``limit`` most-recent events (oldest first in slice)."""
        capped = max(0, int(limit))
        if capped == 0:
            return []
        lines = self._read_tail(capped)
        events: List[HealEvent] = []
        for raw in lines:
            event = _parse_line(raw)
            if event is not None:
                events.append(event)
        return events

    def clear(self) -> None:
        """Remove the log file. A subsequent append recreates it."""
        with self._lock:
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass

    def _read_tail(self, limit: int) -> List[str]:
        with self._lock:
            if not self._path.exists():
                return []
            # errors="replace": a write cut inside a multi-byte character left
            # bytes strict UTF-8 refused, and the whole log became unreadable
            # instead of that one line being skipped.
            with self._path.open("r", encoding="utf-8", errors="replace") as fp:
                lines = fp.readlines()
        return lines[-limit:]


def _parse_line(raw: str) -> Optional[HealEvent]:
    text = raw.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    known = {name: payload[name] for name in _FIELD_NAMES if name in payload}
    try:
        return HealEvent(**known)
    except TypeError:
        return None


#: Schema written by this build. 1 is the original eight-field line, which
#: carried no ``schema_version`` key at all.
HEAL_EVENT_SCHEMA_VERSION = 2

_FIELD_NAMES = frozenset(spec.name for spec in fields(HealEvent))


default_heal_log = HealEventLog()


__all__ = [
    "HEAL_EVENT_SCHEMA_VERSION", "HealEvent", "HealEventLog", "default_heal_log",
]
