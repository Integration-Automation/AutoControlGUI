"""Bulkhead concurrency isolation + server rate-limit header parsing.

``resilience`` recovers from failures and ``rate_limit`` paces calls, but
nothing capped the number of *simultaneous* in-flight calls to one resource
(so a slow dependency could exhaust every worker), and the HTTP client read
``Retry-After`` / ``RateLimit-*`` headers but honored none of them. This adds a
bulkhead (bounded-concurrency permit with load-shedding) and a parser for the
server's advised delay.

The permit counting is lock-guarded and non-blocking (reject when full), so the
accounting is deterministic and CI-testable without spawning threads. Pure
standard library (``threading`` + ``email.utils``); imports no ``PySide6``.
"""
import threading
import time
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Literal, Mapping, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException


class BulkheadFullError(AutoControlException):
    """Raised when a bulkhead has no free permit."""


class Bulkhead:
    """Cap simultaneous in-flight calls to one resource; reject when full."""

    def __init__(self, max_concurrent: int, *, name: str = "bulkhead") -> None:
        if max_concurrent < 1:
            raise AutoControlException("max_concurrent must be >= 1")
        self.name = name
        self._max = int(max_concurrent)
        self._in_flight = 0
        self._lock = threading.Lock()

    @property
    def in_flight(self) -> int:
        """Current number of held permits."""
        with self._lock:
            return self._in_flight

    def try_enter(self) -> bool:
        """Take a permit if one is free; return whether it succeeded."""
        with self._lock:
            if self._in_flight < self._max:
                self._in_flight += 1
                return True
            return False

    def release(self) -> None:
        """Return a permit."""
        with self._lock:
            if self._in_flight > 0:
                self._in_flight -= 1

    def __enter__(self) -> "Bulkhead":
        if not self.try_enter():
            raise BulkheadFullError(f"{self.name} is full ({self._max})")
        return self

    def __exit__(self, *_exc: Any) -> Literal[False]:
        self.release()
        return False

    def run(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Run ``func`` under a permit (raises ``BulkheadFullError`` if full)."""
        with self:
            return func(*args, **kwargs)


def _get_header(headers: Mapping[str, Any], name: str) -> Optional[Any]:
    lower = name.lower()
    for key, value in headers.items():
        if key.lower() == lower:
            return value
    return None


def parse_retry_after(headers: Mapping[str, Any], *,
                      now: Optional[float] = None) -> Optional[float]:
    """Return the ``Retry-After`` delay in seconds (delta or HTTP-date)."""
    raw = _get_header(headers, "Retry-After")
    if raw is None:
        return None
    text = str(raw).strip()
    if text.isdigit():
        return float(text)
    try:
        target = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    when = time.time() if now is None else now
    return max(0.0, target.timestamp() - when)


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_ratelimit(headers: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse de-facto ``RateLimit-Limit/Remaining/Reset`` headers."""
    limit = _get_header(headers, "RateLimit-Limit")
    remaining = _get_header(headers, "RateLimit-Remaining")
    reset = _get_header(headers, "RateLimit-Reset")
    if limit is None and remaining is None and reset is None:
        return None
    return {"limit": _as_int(limit), "remaining": _as_int(remaining),
            "reset": _as_int(reset)}


def next_delay(response: Mapping[str, Any], *,
               now: Optional[float] = None) -> float:
    """Return the server-advised wait (seconds) from a response, or 0.0."""
    headers = response.get("headers", {}) if isinstance(response, Mapping) else {}
    delay = parse_retry_after(headers, now=now)
    if delay is not None:
        return delay
    info = parse_ratelimit(headers)
    if info and info.get("remaining") == 0 and info.get("reset") is not None:
        return float(info["reset"])
    return 0.0
