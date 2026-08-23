"""Client-side rate limiting for paced API / action calls.

The framework had ``RetryPolicy`` / ``CircuitBreaker`` (which *recover* from
failures) and a FIFO ``work_queue``, but nothing to shape the *rate* of calls —
so a flow hammering an external API had no way to stay under a quota. This adds
the two standard limiters plus a leading-edge throttle, all with an injectable
clock so they are deterministic in tests.

* :class:`TokenBucket` — smooth rate with burst capacity (lazy refill).
* :class:`SlidingWindowLimiter` — a fixed call budget per rolling window
  (Cloudflare's O(1) weighted-counter approximation).
* :func:`throttle` — a decorator that fires a function at most once per interval.

Pure standard library (``threading`` for the lock, ``time`` only as the default
clock); imports no ``PySide6``.
"""
import functools
import threading
import time
from typing import Callable, Dict, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException


class TokenBucket:
    """A token-bucket limiter: ``rate`` tokens/sec up to ``capacity`` burst."""

    def __init__(self, rate: float, capacity: float, *,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if rate <= 0 or capacity <= 0:
            raise AutoControlException("rate and capacity must be positive")
        self._rate = float(rate)
        self._capacity = float(capacity)
        self._clock = clock
        self._tokens = float(capacity)
        self._updated = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._updated = now

    @property
    def tokens(self) -> float:
        """Current token count after refilling for elapsed time."""
        with self._lock:
            self._refill()
            return self._tokens

    def try_acquire(self, n: float = 1.0) -> bool:
        """Take ``n`` tokens if available; return whether it succeeded."""
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    def time_until_available(self, n: float = 1.0) -> float:
        """Seconds until ``n`` tokens would be available (0 if already)."""
        with self._lock:
            self._refill()
            if self._tokens >= n:
                return 0.0
            return (n - self._tokens) / self._rate

    def acquire(self, n: float = 1.0, *, timeout: Optional[float] = None,
                sleep: Callable[[float], None] = time.sleep) -> bool:
        """Block until ``n`` tokens are taken or ``timeout`` elapses."""
        deadline = None if timeout is None else self._clock() + timeout
        while True:
            if self.try_acquire(n):
                return True
            wait = self.time_until_available(n)
            if deadline is not None and self._clock() + wait > deadline:
                return False
            sleep(wait if wait > 0 else 0.0)


class SlidingWindowLimiter:
    """Allow ``limit`` calls per ``window_s`` via a weighted rolling counter."""

    def __init__(self, limit: int, window_s: float, *,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if limit <= 0 or window_s <= 0:
            raise AutoControlException("limit and window_s must be positive")
        self._limit = int(limit)
        self._window = float(window_s)
        self._clock = clock
        self._cur_start = clock()
        self._cur = 0
        self._prev = 0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        elapsed = self._clock() - self._cur_start
        if elapsed < self._window:
            return
        if elapsed < 2 * self._window:
            self._prev = self._cur
            self._cur_start += self._window
        else:
            self._prev = 0
            self._cur_start = self._clock()
        self._cur = 0

    def _estimate(self) -> float:
        elapsed_in_cur = self._clock() - self._cur_start
        weight = max(0.0, (self._window - elapsed_in_cur) / self._window)
        return self._prev * weight + self._cur

    def try_acquire(self, n: int = 1) -> bool:
        """Record ``n`` calls if the weighted estimate stays under the limit."""
        with self._lock:
            self._roll()
            if self._estimate() + n <= self._limit:
                self._cur += n
                return True
            return False

    def time_until_available(self, n: int = 1) -> float:
        """Seconds until ``n`` more calls would fit (0 if they already do)."""
        with self._lock:
            self._roll()
            if self._estimate() + n <= self._limit:
                return 0.0
            return max(0.0, self._window - (self._clock() - self._cur_start))


def throttle(interval_s: float, *,
             clock: Callable[[], float] = time.monotonic) -> Callable:
    """Decorator: call the wrapped function at most once per ``interval_s``.

    Leading-edge — the first call fires immediately; calls within the interval
    are dropped (the wrapper returns ``None``).
    """
    def decorator(func: Callable) -> Callable:
        state: Dict[str, Optional[float]] = {"last": None}
        lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                now = clock()
                last = state["last"]
                if last is not None and now - last < interval_s:
                    return None
                state["last"] = now
            return func(*args, **kwargs)

        return wrapper

    return decorator
