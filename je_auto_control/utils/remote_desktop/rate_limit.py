"""Token bucket rate limiter used by the WebRTC host to cap viewer abuse.

Two configurable buckets per session:
  * ``input``: mouse / key / scroll / type events.
  * ``files``: file_begin / file chunk volume.

Defaults are generous (200 input/s, 8 file transfers/min) — they only kick
in for clearly malicious patterns. When the bucket is exhausted the
caller drops the message; the host writes a single audit_log entry per
rate-limit window so logs don't fill up.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimitConfig:
    input_per_second: float = 200.0
    input_burst: float = 400.0
    files_per_minute: float = 8.0
    files_burst: float = 12.0


class _TokenBucket:
    def __init__(self, *, rate_per_second: float, burst: float) -> None:
        self._rate = float(rate_per_second)
        self._capacity = float(burst)
        self._tokens = float(burst)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def take(self, n: float = 1.0) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False


class RateLimiter:
    """Per-host rate limiter with two named buckets."""

    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        cfg = config or RateLimitConfig()
        self._input = _TokenBucket(
            rate_per_second=cfg.input_per_second, burst=cfg.input_burst,
        )
        self._files = _TokenBucket(
            rate_per_second=cfg.files_per_minute / 60.0, burst=cfg.files_burst,
        )
        self._last_warn_input = 0.0
        self._last_warn_files = 0.0

    def allow_input(self) -> bool:
        return self._input.take(1.0)

    def allow_file(self) -> bool:
        return self._files.take(1.0)

    def should_warn_input(self) -> bool:
        """Return True at most once every 5 seconds — for audit log dedup."""
        now = time.monotonic()
        if now - self._last_warn_input >= 5.0:
            self._last_warn_input = now
            return True
        return False

    def should_warn_files(self) -> bool:
        now = time.monotonic()
        if now - self._last_warn_files >= 5.0:
            self._last_warn_files = now
            return True
        return False


__all__ = ["RateLimitConfig", "RateLimiter"]
