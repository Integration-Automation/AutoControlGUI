"""Derive a wait timeout from observed step durations instead of guessing.

Hard-coded waits are a perennial source of flakiness: too short and a slow
machine races the UI; too long and every failure pays the full timeout. The
durable fix is to *learn* the timeout from how long the step has actually taken.
``adaptive_timeout`` turns a sample of observed durations into a robust timeout:
a high percentile (the slow-but-real case) scaled by a safety ``factor``, then
clamped to a sane ``[min_s, max_s]`` band.

* :func:`recommend_timeout` — the single number to feed a wait / ``GateConfig``.
* :func:`timeout_stats` — the same with the percentiles and clamp flags exposed
  for logging / tuning.

Both are pure and reuse :func:`stats.percentile`; with no samples they fall back
to ``default_s`` (or ``min_s``). Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.stats.stats import percentile


def _clamp(value: float, min_s: float, max_s: Optional[float]) -> float:
    """Clamp ``value`` to ``[min_s, max_s]`` (``max_s`` None = no upper cap)."""
    bounded = max(float(min_s), float(value))
    if max_s is not None:
        bounded = min(float(max_s), bounded)
    return bounded


def _fallback(default_s: Optional[float], min_s: float) -> float:
    """The timeout to use when there are no duration samples."""
    return float(default_s) if default_s is not None else float(min_s)


def recommend_timeout(durations: Sequence[float], *, percentile_q: float = 95.0,
                      factor: float = 1.5, min_s: float = 1.0,
                      max_s: Optional[float] = 60.0,
                      default_s: Optional[float] = None) -> float:
    """Recommend a wait timeout (seconds) from observed ``durations``.

    Takes the ``percentile_q``-th percentile of the samples, scales it by
    ``factor``, and clamps to ``[min_s, max_s]``. With no samples returns
    ``default_s`` (or ``min_s``).
    """
    samples = [float(d) for d in durations if d is not None]
    if not samples:
        return _fallback(default_s, min_s)
    scaled = percentile(samples, float(percentile_q)) * float(factor)
    return _clamp(scaled, min_s, max_s)


def timeout_stats(durations: Sequence[float], *, percentile_q: float = 95.0,
                  factor: float = 1.5, min_s: float = 1.0,
                  max_s: Optional[float] = 60.0,
                  default_s: Optional[float] = None) -> Dict[str, Any]:
    """Recommend a timeout and expose the percentiles and clamp decisions.

    Returns ``{n, p50, p_high, percentile_q, recommended, floored, capped}``.
    """
    samples: List[float] = [float(d) for d in durations if d is not None]
    recommended = recommend_timeout(
        samples, percentile_q=percentile_q, factor=factor, min_s=min_s,
        max_s=max_s, default_s=default_s)
    if not samples:
        return {"n": 0, "p50": None, "p_high": None,
                "percentile_q": float(percentile_q),
                "recommended": recommended, "floored": False, "capped": False}
    p_high = percentile(samples, float(percentile_q))
    scaled = p_high * float(factor)
    return {
        "n": len(samples),
        "p50": percentile(samples, 50.0),
        "p_high": p_high,
        "percentile_q": float(percentile_q),
        "recommended": recommended,
        "floored": scaled < float(min_s),
        "capped": max_s is not None and scaled > float(max_s),
    }
