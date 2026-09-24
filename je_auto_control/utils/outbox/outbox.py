"""Transactional outbox: durably buffer events and drain them at-least-once.

``events.cloud_events`` posts immediately and synchronously — a crash between
"did the work" and "sent the event" loses it, and a network blip drops it (no
durability, no retry, no replay). The outbox pattern persists each event and
drains it later with at-least-once delivery and a dead-letter cap.

Pure standard library (``json``); imports no ``PySide6``. The delivery ``sink``
is injected and the store is in-memory with JSON persistence, so draining is
fully deterministic in CI.
"""
import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List

from je_auto_control.utils.json_store.json_store import atomic_write_text

Sink = Callable[[Any], Any]


class Outbox:
    """An ordered buffer of events drained to a sink with retry + dead-letter."""

    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []
        self._counter = 0
        # One outbox per name is shared by every executor thread. Drains are
        # serialised too: two concurrent drains both sent the same entry.
        self._lock = threading.RLock()

    def enqueue(self, event: Any) -> str:
        """Append ``event`` as pending; return its id."""
        with self._lock:
            self._counter += 1
            entry_id = str(self._counter)
            self._events.append({"id": entry_id, "event": event,
                                 "status": "pending", "attempts": 0})
            return entry_id

    def pending(self) -> List[Dict[str, Any]]:
        """Entries still awaiting successful delivery."""
        with self._lock:
            return [entry for entry in self._events if entry["status"] == "pending"]

    def dead_letters(self) -> List[Dict[str, Any]]:
        """Entries that exhausted their delivery attempts."""
        with self._lock:
            return [entry for entry in self._events if entry["status"] == "failed"]

    def drain(self, sink: Sink, *, max_batch: int = 100,
              max_attempts: int = 5) -> Dict[str, int]:
        """Deliver up to ``max_batch`` pending entries via ``sink``.

        On a sink exception the entry is retried until ``max_attempts``, then
        dead-lettered. Returns ``{sent, failed, remaining}``.
        """
        with self._lock:
            return self._drain(sink, max_batch, max_attempts)

    def _drain(self, sink: Sink, max_batch: int,
               max_attempts: int) -> Dict[str, int]:
        sent = 0
        failed = 0
        for entry in self.pending()[:max_batch]:
            entry["attempts"] += 1
            try:
                sink(entry["event"])
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught  # reason: counts as a failed attempt
                if entry["attempts"] >= max_attempts:
                    entry["status"] = "failed"
                    entry["error"] = str(error)
                    failed += 1
                continue
            entry["status"] = "sent"
            sent += 1
        return {"sent": sent, "failed": failed, "remaining": len(self.pending())}

    def to_dict(self) -> Dict[str, Any]:
        """Return the outbox state as a plain dict."""
        with self._lock:
            return {"counter": self._counter,
                    "events": [dict(entry) for entry in self._events]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Outbox":
        """Build an outbox from a :meth:`to_dict` mapping."""
        outbox = cls()
        outbox._counter = int(data.get("counter", 0))
        outbox._events = [dict(entry) for entry in data.get("events", [])]
        return outbox

    def save(self, path: str) -> str:
        """Persist the outbox to ``path`` as JSON; return the path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(out, json.dumps(self.to_dict(), indent=2))
        return str(out)

    @classmethod
    def load(cls, path: str) -> "Outbox":
        """Load an outbox from a JSON file."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
