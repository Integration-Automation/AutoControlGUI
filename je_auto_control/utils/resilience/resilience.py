"""Resilience primitives — retry-with-backoff and a circuit breaker.

Two reusable wrappers around any callable (or, via the executor commands,
any action list):

* :class:`RetryPolicy` retries on configured exceptions with exponential
  backoff (and optional cap) — for transient failures.
* :class:`CircuitBreaker` opens after N consecutive failures and
  short-circuits calls (raising :class:`CircuitOpenError`) until a reset
  timeout elapses, then half-opens for a trial — so a downed dependency
  isn't hammered by a retry storm.

Both take injectable ``sleep`` / ``clock`` callables, so behaviour is
unit-tested deterministically with a fake clock. Pure standard library;
imports no ``PySide6``.
"""
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple, Type


class CircuitOpenError(RuntimeError):
    """Raised by :class:`CircuitBreaker` when the circuit is open."""


@dataclass
class RetryPolicy:
    """Retry a callable on failure with exponential backoff."""
    max_attempts: int = 3
    backoff: float = 0.1
    multiplier: float = 2.0
    max_backoff: Optional[float] = None
    exceptions: Tuple[Type[BaseException], ...] = (Exception,)

    def run(self, func: Callable[..., Any], *args: Any,
            sleep: Optional[Callable[[float], None]] = None,
            **kwargs: Any) -> Any:
        """Call ``func`` until it succeeds or attempts are exhausted."""
        sleeper = sleep or time.sleep
        attempts = max(1, int(self.max_attempts))
        delay = self.backoff
        last_error: Optional[BaseException] = None
        for attempt in range(1, attempts + 1):
            try:
                return func(*args, **kwargs)
            except self.exceptions as error:
                last_error = error
                if attempt >= attempts:
                    break
                if delay > 0:
                    sleeper(delay)
                delay *= self.multiplier
                if self.max_backoff is not None:
                    delay = min(delay, self.max_backoff)
        raise last_error  # type: ignore[misc]


def retry_call(func: Callable[..., Any], *args: Any, max_attempts: int = 3,
               backoff: float = 0.1, **kwargs: Any) -> Any:
    """Convenience: run ``func`` under a default :class:`RetryPolicy`."""
    policy = RetryPolicy(max_attempts=int(max_attempts), backoff=float(backoff))
    return policy.run(func, *args, **kwargs)


class CircuitBreaker:
    """Open after consecutive failures; short-circuit until a reset timeout."""

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 30.0,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self._threshold = max(1, int(failure_threshold))
        self._reset = float(reset_timeout)
        self._clock = clock or time.monotonic
        self._failures = 0
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> str:
        """``closed`` / ``open`` / ``half_open``."""
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self._reset:
            return "half_open"
        return "open"

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Invoke ``func`` unless the circuit is open."""
        if self.state == "open":
            raise CircuitOpenError("circuit is open")
        try:
            result = func(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = self._clock()

    def _record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
