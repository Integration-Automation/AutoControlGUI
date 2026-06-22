"""Time-windowed deduplication (at-least-once → exactly-once inbox).

``work_queue`` dedups only ``new`` / ``in_progress`` references — once an item
completes, the same reference enqueues again, and redelivered webhooks are
reprocessed. This is the missing "seen this id in the last N seconds → drop it"
inbox that converts at-least-once delivery to exactly-once-in-window.

Pure standard library; imports no ``PySide6``. The clock is injectable, so TTL
eviction is fully deterministic in CI.
"""
import time
from typing import Callable, Dict


class DedupWindow:
    """A sliding time window of recently-seen message ids."""

    def __init__(self, ttl_s: float, *,
                 clock: Callable[[], float] = time.time) -> None:
        self._ttl = float(ttl_s)
        self._clock = clock
        self._seen: Dict[str, float] = {}

    def _purge(self, now: float) -> None:
        cutoff = now - self._ttl
        expired = [key for key, ts in self._seen.items() if ts <= cutoff]
        for key in expired:
            del self._seen[key]

    def seen(self, message_id: str) -> bool:
        """Whether ``message_id`` is in the window and not expired."""
        now = self._clock()
        self._purge(now)
        return message_id in self._seen

    def mark(self, message_id: str) -> None:
        """Record ``message_id`` as seen now."""
        self._seen[str(message_id)] = self._clock()

    def check_and_mark(self, message_id: str) -> bool:
        """Atomically return ``True`` if first-seen (and mark), else ``False``."""
        now = self._clock()
        self._purge(now)
        if message_id in self._seen:
            return False
        self._seen[str(message_id)] = now
        return True

    def purge_expired(self) -> int:
        """Drop expired entries; return how many remain."""
        self._purge(self._clock())
        return len(self._seen)

    def size(self) -> int:
        """Number of live (non-expired) entries."""
        return self.purge_expired()
