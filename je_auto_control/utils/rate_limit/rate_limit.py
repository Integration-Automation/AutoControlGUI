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
import math
import threading
import time
from typing import Callable, Dict, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException


def _positive_finite(value: float) -> bool:
    return math.isfinite(value) and value > 0


class TokenBucket:
    """A token-bucket limiter: ``rate`` tokens/sec up to ``capacity`` burst."""

    def __init__(self, rate: float, capacity: float, *,
                 clock: Callable[[], float] = time.monotonic) -> None:
        # NaN passed `<= 0` (every comparison with NaN is false): a NaN
        # rate or capacity let every request through, or spun a waiter at
        # 100% CPU. Values arrive from JSON via AC_rate_limit.
        if not (_positive_finite(rate) and _positive_finite(capacity)):
            raise AutoControlException("rate and capacity must be positive finite numbers")
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

    def _check_request(self, n: float) -> float:
        """``n`` as a float; a request the bucket can never satisfy is an error.

        A negative ``n`` minted tokens past capacity, and ``n`` above capacity
        made :meth:`acquire` without a timeout wait forever.
        """
        amount = float(n)
        if not math.isfinite(amount) or amount <= 0 or amount > self._capacity:
            raise AutoControlException(
                f"n must be in (0, capacity={self._capacity}], got {n!r}")
        return amount

    def try_acquire(self, n: float = 1.0) -> bool:
        """Take ``n`` tokens if available; return whether it succeeded."""
        n = self._check_request(n)
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    def time_until_available(self, n: float = 1.0) -> float:
        """Seconds until ``n`` tokens would be available (0 if already)."""
        n = self._check_request(n)
        with self._lock:
            self._refill()
            if self._tokens >= n:
                return 0.0
            return (n - self._tokens) / self._rate

    def acquire(self, n: float = 1.0, *, timeout: Optional[float] = None,
                sleep: Callable[[float], None] = time.sleep) -> bool:
        """Block until ``n`` tokens are taken or ``timeout`` elapses."""
        self._check_request(n)
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
        if not (limit > 0 and _positive_finite(window_s)):
            raise AutoControlException("limit and window_s must be positive (window_s finite)")
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

    def _check_request(self, n: int) -> int:
        count = int(n)
        if count <= 0 or count > self._limit:
            raise AutoControlException(f"n must be in (0, limit={self._limit}], got {n!r}")
        return count

    def try_acquire(self, n: int = 1) -> bool:
        """Record ``n`` calls if the weighted estimate stays under the limit."""
        n = self._check_request(n)
        with self._lock:
            self._roll()
            if self._estimate() + n <= self._limit:
                self._cur += n
                return True
            return False

    def time_until_available(self, n: int = 1) -> float:
        """Seconds until ``n`` more calls would fit (0 if they already do).

        Solves the weighted estimate for the wait instead of answering "the
        rest of this window": after the roll the current count becomes the
        previous one at full weight, so that answer was often too short.
        """
        n = self._check_request(n)
        with self._lock:
            self._roll()
            if self._estimate() + n <= self._limit:
                return 0.0
            room = self._limit - n
            remaining = self._window - (self._clock() - self._cur_start)
            if self._cur <= room:
                # Fits in this window once the previous one has decayed enough.
                return max(0.0, remaining - (room - self._cur) * self._window / self._prev)
            # Only after the roll, once the current count (then "previous") decays.
            return remaining + self._window - room * self._window / self._cur


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
