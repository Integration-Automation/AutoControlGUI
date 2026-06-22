"""Detect distribution drift between a reference and a current sample.

``stats`` has two-sample tests for A/B *experiment* outcomes (proportions /
means), but no Population Stability Index and no Kolmogorov-Smirnov two-sample
test for the canonical "is today's data shaped like the baseline" check. This
adds PSI, KS, and a categorical-drift summary that pair with ``data_profile``.

Pure standard library (``math`` / ``bisect`` / ``collections`` + reuse of
``stats.percentile``); imports no ``PySide6``. Every function is pure
(sequences in, dict/float out) so it is fully deterministic in CI.
"""
import bisect
import math
from collections import Counter
from typing import Any, Dict, List, Sequence

from je_auto_control.utils.stats.stats import percentile

_EPSILON = 1e-6


def _require(reference: Sequence[Any], current: Sequence[Any]) -> None:
    if not reference or not current:
        raise ValueError("reference and current must both be non-empty")


def _bin_edges(reference: Sequence[float], bins: int) -> List[float]:
    return [percentile(reference, index * 100.0 / bins)
            for index in range(1, bins)]


def _bucket_fractions(values: Sequence[float],
                      edges: Sequence[float]) -> List[float]:
    counts = [0] * (len(edges) + 1)
    for value in values:
        counts[bisect.bisect_right(edges, value)] += 1
    total = len(values) or 1
    return [count / total for count in counts]


def psi(reference: Sequence[float], current: Sequence[float],
        bins: int = 10) -> float:
    """Population Stability Index of ``current`` against ``reference`` bins."""
    _require(reference, current)
    edges = _bin_edges([float(value) for value in reference], bins)
    ref_fractions = _bucket_fractions([float(v) for v in reference], edges)
    cur_fractions = _bucket_fractions([float(v) for v in current], edges)
    score = 0.0
    for ref_part, cur_part in zip(ref_fractions, cur_fractions):
        ref_part = max(ref_part, _EPSILON)
        cur_part = max(cur_part, _EPSILON)
        score += (cur_part - ref_part) * math.log(cur_part / ref_part)
    return score


def _ks_statistic(reference: Sequence[float],
                  current: Sequence[float]) -> float:
    ref_sorted = sorted(float(value) for value in reference)
    cur_sorted = sorted(float(value) for value in current)
    n_ref, n_cur = len(ref_sorted), len(cur_sorted)
    statistic = 0.0
    for value in sorted(set(ref_sorted) | set(cur_sorted)):
        cdf_ref = bisect.bisect_right(ref_sorted, value) / n_ref
        cdf_cur = bisect.bisect_right(cur_sorted, value) / n_cur
        statistic = max(statistic, abs(cdf_ref - cdf_cur))
    return statistic


def _kolmogorov(lam: float) -> float:
    if lam <= 0:
        return 1.0
    total = 0.0
    for term_index in range(1, 101):
        term = 2 * (-1) ** (term_index - 1) * math.exp(
            -2 * term_index * term_index * lam * lam)
        total += term
        if abs(term) < 1e-10:
            break
    return min(1.0, max(0.0, total))


def ks_two_sample(reference: Sequence[float],
                  current: Sequence[float]) -> Dict[str, float]:
    """Two-sample Kolmogorov-Smirnov test: ``{statistic, p_value}``."""
    _require(reference, current)
    statistic = _ks_statistic(reference, current)
    n_ref, n_cur = len(reference), len(current)
    en = math.sqrt(n_ref * n_cur / (n_ref + n_cur))
    p_value = _kolmogorov((en + 0.12 + 0.11 / en) * statistic)
    return {"statistic": statistic, "p_value": p_value}


def categorical_drift(reference: Sequence[Any],
                      current: Sequence[Any]) -> Dict[str, float]:
    """Chi-square statistic and total-variation distance over categories."""
    _require(reference, current)
    ref_counts, cur_counts = Counter(reference), Counter(current)
    ref_total = sum(ref_counts.values())
    cur_total = sum(cur_counts.values())
    categories = set(ref_counts) | set(cur_counts)
    chi_square = 0.0
    total_variation = 0.0
    for category in categories:
        ref_part = ref_counts.get(category, 0) / ref_total
        cur_part = cur_counts.get(category, 0) / cur_total
        expected = ref_part * cur_total
        if expected > 0:
            chi_square += (cur_counts.get(category, 0) - expected) ** 2 / expected
        total_variation += abs(ref_part - cur_part)
    return {"chi_square": chi_square, "total_variation": 0.5 * total_variation,
            "categories": len(categories)}


def detect_drift(reference: Sequence[float], current: Sequence[float], *,
                 threshold: float = 0.25, bins: int = 10) -> Dict[str, Any]:
    """Numeric drift report: PSI (with verdict) plus the KS test."""
    score = psi(reference, current, bins)
    return {"psi": score, "drifted": score >= threshold,
            "ks": ks_two_sample(reference, current)}
