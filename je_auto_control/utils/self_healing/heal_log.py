"""Append-only JSON-lines log of self-healing locator events."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


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

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict snapshot safe for JSON / network transport."""
        return asdict(self)


class HealEventLog:
    """Thread-safe append-only JSON-lines store for HealEvent records."""

    DEFAULT_PATH = Path.home() / ".je_auto_control" / "self_healing_events.jsonl"

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else self.DEFAULT_PATH
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        """Filesystem path the log writes to (parent created on append)."""
        return self._path

    def append(self, event: HealEvent) -> None:
        """Atomically append one event as a JSON line."""
        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fp:
                fp.write(payload)
                fp.write("\n")

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
            with self._path.open("r", encoding="utf-8") as fp:
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
    try:
        return HealEvent(**payload)
    except TypeError:
        return None


default_heal_log = HealEventLog()


__all__ = ["HealEvent", "HealEventLog", "default_heal_log"]
