"""Anomaly detection over a single numeric series.

``data_drift`` answers "did the *distribution* shift between two batches" — it
cannot point at *which* value in one live series is anomalous, and
``slo.burn_alerts`` only thresholds error-budget burn, not arbitrary metric
values (latency spikes, cost spikes, CPU). This flags outliers in one series via
z-score, robust MAD (modified z-score), and an EWMA control chart.

Pure standard library (``math`` / ``statistics``); imports no ``PySide6``. Every
function is pure (values in, flags out), so it is fully deterministic in CI.
"""
import math
import statistics
from typing import Any, Dict, List, Sequence


def zscore_scores(values: Sequence[float]) -> List[float]:
    """Standard z-scores of ``values`` (0.0 when stdev is 0)."""
    count = len(values)
    if count < 2:
        return [0.0] * count
    mean = statistics.fmean(values)
    sigma = statistics.pstdev(values)
    if sigma == 0:
        return [0.0] * count
    return [(value - mean) / sigma for value in values]


def mad_scores(values: Sequence[float]) -> List[float]:
    """Iglewicz-Hoaglin modified z-scores (robust, median/MAD based)."""
    if not values:
        return []
    median = statistics.median(values)
    mad = statistics.median([abs(value - median) for value in values])
    if mad == 0:
        return [0.0] * len(values)
    return [0.6745 * (value - median) / mad for value in values]


def zscore_anomalies(values: Sequence[float], *,
                     threshold: float = 3.0) -> List[int]:
    """Indices whose z-score magnitude exceeds ``threshold``."""
    return [i for i, score in enumerate(zscore_scores(values))
            if abs(score) > threshold]


def mad_anomalies(values: Sequence[float], *,
                  threshold: float = 3.5) -> List[int]:
    """Indices whose modified z-score magnitude exceeds ``threshold``."""
    return [i for i, score in enumerate(mad_scores(values))
            if abs(score) > threshold]


def ewma_control(values: Sequence[float], *, alpha: float = 0.3,
                 limit: float = 3.0, target_mean: Any = None,
                 target_sigma: Any = None) -> List[int]:
    """Indices where the EWMA breaches its control limits (control chart).

    ``target_mean`` / ``target_sigma`` set the in-control baseline; when omitted
    they default to the series' own mean and population stdev.
    """
    if not values:
        return []
    mean = statistics.fmean(values) if target_mean is None else float(target_mean)
    if target_sigma is not None:
        sigma = float(target_sigma)
    else:
        sigma = statistics.pstdev(values) if len(values) > 1 else 0.0
    ewma = mean
    flagged: List[int] = []
    for i, value in enumerate(values):
        ewma = alpha * value + (1 - alpha) * ewma
        spread = math.sqrt(alpha / (2 - alpha)
                           * (1 - (1 - alpha) ** (2 * (i + 1))))
        bound = limit * sigma * spread
        if ewma > mean + bound or ewma < mean - bound:
            flagged.append(i)
    return flagged


def detect_anomalies(values: Sequence[float], *, method: str = "mad",
                     threshold: Any = None) -> List[Dict[str, Any]]:
    """Score each value and flag anomalies via ``method`` (``mad``/``zscore``).

    Returns ``[{index, value, score, is_anomaly}]``.
    """
    if method == "zscore":
        scores = zscore_scores(values)
        cutoff = 3.0 if threshold is None else float(threshold)
    elif method == "mad":
        scores = mad_scores(values)
        cutoff = 3.5 if threshold is None else float(threshold)
    else:
        raise ValueError(f"unknown method: {method!r}; use 'mad' or 'zscore'")
    return [{"index": i, "value": values[i], "score": scores[i],
             "is_anomaly": abs(scores[i]) > cutoff}
            for i in range(len(values))]
