"""A mergeable streaming latency digest for percentile estimation.

``stats.percentile`` is exact but needs the full sorted sample list in memory;
for a long-running or sharded load/soak run you want an O(1)-per-record,
bounded-memory, *mergeable* structure instead. This adds a HdrHistogram-style
:class:`LatencyDigest` (records into significant-figure buckets, merges across
shards) plus :func:`exact_percentiles` for small sample sets.

Pure standard library (``math``); imports no ``PySide6``.
"""
import math
from typing import Dict, Iterable, Optional, Sequence

from je_auto_control.utils.stats import percentile


def exact_percentiles(samples: Sequence[float],
                      qs: Iterable[float] = (50, 90, 95, 99)) -> Dict[float, float]:
    """Return exact percentiles for a small sample set (delegates to stats)."""
    return {q: percentile(samples, q) for q in qs}


class LatencyDigest:
    """A mergeable percentile estimator using significant-figure buckets."""

    def __init__(self, *, sig_figs: int = 3) -> None:
        if sig_figs < 1:
            raise ValueError("sig_figs must be >= 1")
        self._sig = int(sig_figs)
        self._counts: Dict[float, int] = {}
        self._count = 0
        self._sum = 0.0
        self._min: Optional[float] = None
        self._max: Optional[float] = None

    def _bucket(self, value: float) -> float:
        if value <= 0:
            return 0.0
        digits = self._sig - 1 - math.floor(math.log10(value))
        return round(value, digits)

    def record(self, value: float) -> None:
        """Record one observation."""
        value = float(value)
        bucket = self._bucket(value)
        self._counts[bucket] = self._counts.get(bucket, 0) + 1
        self._count += 1
        self._sum += value
        self._min = value if self._min is None else min(self._min, value)
        self._max = value if self._max is None else max(self._max, value)

    @property
    def count(self) -> int:
        """Number of recorded observations."""
        return self._count

    def percentile(self, q: float) -> float:
        """Return the estimated ``q``-th percentile (0-100)."""
        if self._count == 0:
            return 0.0
        rank = (max(0.0, min(100.0, q)) / 100.0) * self._count
        cumulative = 0
        for bucket in sorted(self._counts):
            cumulative += self._counts[bucket]
            if cumulative >= rank:
                return bucket
        return self._max if self._max is not None else 0.0

    def quantiles(self, qs: Iterable[float]) -> Dict[float, float]:
        """Return ``{q: percentile(q)}`` for each requested quantile."""
        return {q: self.percentile(q) for q in qs}

    def summary(self) -> Dict[str, float]:
        """Return min/mean/max/count and the standard tail percentiles."""
        mean = self._sum / self._count if self._count else 0.0
        return {
            "count": self._count,
            "min": self._min if self._min is not None else 0.0,
            "max": self._max if self._max is not None else 0.0,
            "mean": mean,
            "p50": self.percentile(50), "p90": self.percentile(90),
            "p95": self.percentile(95), "p99": self.percentile(99),
        }

    def merge(self, other: "LatencyDigest") -> "LatencyDigest":
        """Fold ``other`` into this digest (for cross-shard aggregation)."""
        # pylint: disable=protected-access  # reason: same-class instance merge
        for bucket, count in other._counts.items():
            self._counts[bucket] = self._counts.get(bucket, 0) + count
        self._count += other._count
        self._sum += other._sum
        for value in (other._min, other._max):
            if value is None:
                continue
            self._min = value if self._min is None else min(self._min, value)
            self._max = value if self._max is None else max(self._max, value)
        return self
