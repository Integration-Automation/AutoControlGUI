"""Thread-safe per-action duration profiler.

The executor wraps each action in :meth:`ActionProfiler.measure` (a context
manager) so users can answer "which action is the hot spot in this script?"
without external tooling. Stats accumulate across runs until the caller
explicitly resets them.

Profiling is *opt-in*: the global :data:`default_profiler` starts disabled
and ignores ``measure`` calls until :meth:`enable` is called. This keeps
hot-path overhead at zero for users who never look at the data.
"""
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional


@dataclass
class ActionStats:
    """Aggregated timing for a single action name."""
    name: str
    calls: int = 0
    total_seconds: float = 0.0
    min_seconds: float = field(default=float("inf"))
    max_seconds: float = 0.0
    last_seconds: float = 0.0
    errors: int = 0

    @property
    def average_seconds(self) -> float:
        """Mean wall-clock duration across all recorded calls."""
        if self.calls == 0:
            return 0.0
        return self.total_seconds / self.calls

    def to_dict(self) -> Dict[str, object]:
        """Render as a JSON-friendly dict (for REST / executor adapters)."""
        return {
            "name": self.name,
            "calls": self.calls,
            "total_seconds": self.total_seconds,
            "min_seconds": (0.0 if self.min_seconds == float("inf")
                            else self.min_seconds),
            "max_seconds": self.max_seconds,
            "last_seconds": self.last_seconds,
            "average_seconds": self.average_seconds,
            "errors": self.errors,
        }


class ActionProfiler:
    """Aggregate per-action wall-clock durations across executor runs.

    Safe to share across threads — every mutation goes through a lock.
    """

    __slots__ = ("_lock", "_stats", "_enabled")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: Dict[str, ActionStats] = {}
        self._enabled: bool = False

    @property
    def enabled(self) -> bool:
        """Whether new ``measure`` calls record samples."""
        return self._enabled

    def enable(self) -> None:
        """Start recording samples."""
        self._enabled = True

    def disable(self) -> None:
        """Stop recording samples (existing data is preserved)."""
        self._enabled = False

    def reset(self) -> None:
        """Drop all collected samples."""
        with self._lock:
            self._stats.clear()

    def record(self, name: str, seconds: float, *, error: bool = False) -> None:
        """Record a single sample for ``name``.

        Used directly by callers that already measured the duration. The
        :meth:`measure` context manager is the usual entry point.
        """
        if not self._enabled:
            return
        if not isinstance(name, str) or not name:
            return
        sample = max(0.0, float(seconds))
        with self._lock:
            stats = self._stats.get(name)
            if stats is None:
                stats = ActionStats(name=name)
                self._stats[name] = stats
            stats.calls += 1
            stats.total_seconds += sample
            stats.min_seconds = min(stats.min_seconds, sample)
            stats.max_seconds = max(stats.max_seconds, sample)
            stats.last_seconds = sample
            if error:
                stats.errors += 1

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        """Time the wrapped block and attribute it to ``name``."""
        if not self._enabled:
            yield
            return
        start = time.perf_counter()
        errored = False
        try:
            yield
        except BaseException:
            errored = True
            raise
        finally:
            self.record(name, time.perf_counter() - start, error=errored)

    def stats(self) -> List[ActionStats]:
        """Return a snapshot of stats, sorted by total time descending."""
        with self._lock:
            return sorted(
                (ActionStats(**vars(s)) for s in self._stats.values()),
                key=lambda s: s.total_seconds, reverse=True,
            )

    def hot_spots(self, limit: int = 10) -> List[ActionStats]:
        """Return the top ``limit`` actions by total time."""
        bound = max(0, int(limit))
        if bound == 0:
            return []
        return self.stats()[:bound]

    def get(self, name: str) -> Optional[ActionStats]:
        """Return stats for ``name`` or ``None`` if never recorded."""
        with self._lock:
            existing = self._stats.get(name)
            if existing is None:
                return None
            return ActionStats(**vars(existing))


default_profiler = ActionProfiler()
