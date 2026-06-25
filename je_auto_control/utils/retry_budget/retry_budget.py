"""Retry budget: bound retries by a wall-clock deadline and full jitter.

:class:`resilience.RetryPolicy` retries a fixed number of attempts with plain
exponential backoff. Two things it can't express are exactly what flaky,
contended UI automation needs:

* a **wall-clock deadline** — "keep retrying, but give up after 30 s total",
  independent of how many attempts that takes; and
* **jitter** — randomized backoff so many retrying workers don't resynchronize
  into a thundering herd.

``retry_budget`` adds both. :class:`RetryBudget` is bounded by ``max_attempts``
*and / or* ``deadline_s``; :func:`run_with_budget` honours whichever is hit
first and never sleeps past the deadline. Delays use capped exponential backoff
with a selectable jitter strategy. The randomness source (``uniform``), the
clock and the sleeper are all injectable, so every delay and decision is
deterministic in tests. Imports no ``PySide6``.
"""
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

# A uniform sampler: ``(low, high) -> float`` in ``[low, high)``.
Uniform = Callable[[float, float], float]

# Jitter strategies.
JITTER_FULL = "full"
JITTER_EQUAL = "equal"
JITTER_NONE = "none"


def _default_uniform(low: float, high: float) -> float:
    """Uniform sample in ``[low, high)`` for retry jitter (non-crypto)."""
    return random.uniform(low, high)  # nosec B311  # reason: non-crypto retry jitter


def backoff_delay(attempt: int, *, base: float, max_delay: float,
                  multiplier: float) -> float:
    """Capped exponential backoff for a 1-based ``attempt`` (pure).

    ``base * multiplier ** (attempt - 1)``, clamped to ``[0, max_delay]``.
    """
    if attempt < 1:
        return 0.0
    raw = float(base) * (float(multiplier) ** (attempt - 1))
    return max(0.0, min(float(max_delay), raw))


def jittered_delay(raw: float, jitter: str, *,
                   uniform: Uniform = _default_uniform) -> float:
    """Apply a jitter strategy to a raw backoff delay (pure given ``uniform``).

    ``full`` (default) samples ``[0, raw)``; ``equal`` samples
    ``[raw/2, raw)``; ``none`` returns ``raw`` unchanged.
    """
    bounded = max(0.0, float(raw))
    if jitter == JITTER_NONE or bounded <= 0.0:
        return bounded
    if jitter == JITTER_EQUAL:
        return bounded / 2.0 + uniform(0.0, bounded / 2.0)
    return uniform(0.0, bounded)


@dataclass
class RetryBudget:
    """A retry budget bounded by attempts and / or a wall-clock deadline."""

    max_attempts: Optional[int] = 5
    deadline_s: Optional[float] = None
    base_delay_s: float = 0.1
    max_delay_s: float = 5.0
    multiplier: float = 2.0
    jitter: str = JITTER_FULL
    exceptions: Tuple[Type[BaseException], ...] = (Exception,)

    def raw_delay(self, attempt: int) -> float:
        """Capped exponential backoff for ``attempt`` (no jitter; pure)."""
        return backoff_delay(attempt, base=self.base_delay_s,
                             max_delay=self.max_delay_s,
                             multiplier=self.multiplier)

    def next_delay(self, attempt: int, *,
                   uniform: Uniform = _default_uniform) -> float:
        """The jittered delay to wait before retry after ``attempt`` (pure)."""
        return jittered_delay(self.raw_delay(attempt), self.jitter,
                              uniform=uniform)

    def plan(self, attempts: int, *,
             uniform: Uniform = _default_uniform) -> List[float]:
        """The jittered delay schedule for the first ``attempts`` retries."""
        count = max(0, int(attempts))
        return [self.next_delay(i, uniform=uniform)
                for i in range(1, count + 1)]


def _sleep_before_retry(budget: RetryBudget, attempt: int, elapsed: float,
                        uniform: Uniform) -> Optional[float]:
    """Return the delay before the next attempt, or ``None`` to stop retrying."""
    if budget.max_attempts is not None and attempt >= int(budget.max_attempts):
        return None
    delay = budget.next_delay(attempt, uniform=uniform)
    if budget.deadline_s is None:
        return max(0.0, delay)
    remaining = float(budget.deadline_s) - elapsed
    if remaining <= 0:
        return None
    return max(0.0, min(delay, remaining))


def run_with_budget(func: Callable[..., Any], budget: RetryBudget, *,
                    args: Tuple[Any, ...] = (),
                    kwargs: Optional[Dict[str, Any]] = None,
                    clock: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], None] = time.sleep,
                    uniform: Uniform = _default_uniform) -> Any:
    """Call ``func`` until it succeeds or the budget is spent; re-raise on giveup.

    Stops at whichever of ``max_attempts`` / ``deadline_s`` is hit first and
    never sleeps past the deadline. Exceptions outside ``budget.exceptions``
    propagate immediately. ``clock`` / ``sleep`` / ``uniform`` are injectable.
    """
    call_kwargs = kwargs if kwargs is not None else {}
    start = clock()
    attempt = 0
    last_error: Optional[BaseException] = None
    while True:
        attempt += 1
        try:
            return func(*args, **call_kwargs)
        except budget.exceptions as error:
            last_error = error
        wait = _sleep_before_retry(budget, attempt, clock() - start, uniform)
        if wait is None:
            raise last_error
        if wait > 0:
            sleep(wait)
