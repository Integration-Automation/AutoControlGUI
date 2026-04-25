"""Token-bucket rate limiter for MCP tool calls.

Default config is generous (60 calls / second sustained, burst 60),
intended only as a safety net against runaway loops. Deployments
that need a stricter ceiling pass a custom :class:`RateLimiter` to
:class:`MCPServer`.
"""
import threading
import time
from typing import Optional


class RateLimiter:
    """Standard token-bucket: refill ``rate_per_sec`` tokens per second up to ``capacity``."""

    def __init__(self, rate_per_sec: float = 60.0,
                 capacity: Optional[float] = None) -> None:
        self._rate = max(0.0, float(rate_per_sec))
        self._capacity = float(capacity) if capacity is not None else self._rate
        self._tokens = self._capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    @property
    def rate_per_sec(self) -> float:
        return self._rate

    @property
    def capacity(self) -> float:
        return self._capacity

    def try_acquire(self) -> bool:
        """Take one token if available; return ``True`` on success."""
        if self._rate <= 0:
            return True
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._capacity,
                                self._tokens + elapsed * self._rate)
            if self._tokens < 1.0:
                return False
            self._tokens -= 1.0
            return True


__all__ = ["RateLimiter"]
