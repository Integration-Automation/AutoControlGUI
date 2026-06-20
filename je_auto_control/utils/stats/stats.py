"""Descriptive statistics and A/B significance testing (pure standard library).

``ab_locator`` ranks strategies by raw success rate and ``run_history`` stores
durations, but nothing computed percentiles or told you whether a difference is
*statistically significant* (rather than noise). This adds the analysis layer:
percentiles / summary stats, a two-proportion z-test (conversion rates), Welch's
t-test (continuous metrics), Cohen's d effect size, and a 2x2 chi-square test.

The normal CDF is exact via ``math.erf``; the t-distribution p-value uses the
regularized incomplete beta function (continued fraction), so results match
reference implementations without SciPy. Imports no ``PySide6``.
"""
import math
import statistics
from typing import Any, Dict, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException


# --- descriptive -----------------------------------------------------------

def percentile(values: Sequence[float], q: float,
               method: str = "linear") -> float:
    """Return the ``q``-th percentile (0-100) of ``values``."""
    if not values:
        raise AutoControlException("percentile of empty data")
    data = sorted(float(value) for value in values)
    if q <= 0:
        return data[0]
    if q >= 100:
        return data[-1]
    if method == "nearest":
        return data[max(0, math.ceil(q / 100 * len(data)) - 1)]
    pos = (q / 100) * (len(data) - 1)
    low = math.floor(pos)
    if low + 1 >= len(data):
        return data[low]
    return data[low] + (pos - low) * (data[low + 1] - data[low])


def describe(values: Sequence[float]) -> Dict[str, float]:
    """Return summary statistics (n/min/max/mean/stdev/variance + percentiles)."""
    if not values:
        raise AutoControlException("describe of empty data")
    data = [float(value) for value in values]
    summary: Dict[str, float] = {
        "n": len(data), "min": min(data), "max": max(data),
        "mean": statistics.fmean(data),
        "variance": statistics.pvariance(data),
        "stdev": statistics.pstdev(data),
    }
    for q in (50, 90, 95, 99):
        summary[f"p{q}"] = percentile(data, q)
    return summary


# --- distribution helpers --------------------------------------------------

def normal_cdf(z: float) -> float:
    """Standard normal cumulative distribution at ``z`` (exact via erf)."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _clamp(value: float, floor: float = 1e-30) -> float:
    return floor if abs(value) < floor else value


def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1, a - 1
    c = 1.0
    d = 1.0 / _clamp(1.0 - qab * x / qap)
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 / _clamp(1.0 + aa * d)
        c = _clamp(1.0 + aa / c)
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 / _clamp(1.0 + aa * d)
        c = _clamp(1.0 + aa / c)
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-12:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    # x is a domain ratio in [0, 1]; both boundaries are reachable (e.g. x == 1
    # when the t-statistic is 0). NOSONAR: the analyzer mis-models these as
    # constant, but they are genuine, exercised guards.
    if x <= 0:  # NOSONAR python:S2583 reason: reachable beta-domain lower bound
        return 0.0
    if x >= 1:  # NOSONAR python:S2583 reason: reachable beta-domain upper bound
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1 - x) / b


def _t_two_sided_p(t: float, df: float) -> float:
    """Two-sided p-value for a t-statistic with ``df`` degrees of freedom."""
    return _betai(df / 2.0, 0.5, df / (df + t * t))


def _z_critical(alpha: float) -> float:
    target = 1 - alpha / 2
    low, high = 0.0, 40.0
    for _ in range(100):
        mid = (low + high) / 2
        if normal_cdf(mid) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _t_critical(alpha: float, df: float) -> float:
    low, high = 0.0, 1000.0
    for _ in range(100):
        mid = (low + high) / 2
        if _t_two_sided_p(mid, df) > alpha:
            low = mid
        else:
            high = mid
    return (low + high) / 2


# --- significance tests ----------------------------------------------------

def two_proportion_z_test(a_conv: int, a_n: int, b_conv: int, b_n: int, *,
                          alpha: float = 0.05) -> Dict[str, Any]:
    """Two-proportion z-test comparing conversion rates A vs B."""
    if a_n <= 0 or b_n <= 0:
        raise AutoControlException("sample sizes must be positive")
    p1, p2 = a_conv / a_n, b_conv / b_n
    pooled = (a_conv + b_conv) / (a_n + b_n)
    se_pool = math.sqrt(pooled * (1 - pooled) * (1 / a_n + 1 / b_n))
    z = (p2 - p1) / se_pool if se_pool > 0 else 0.0
    p_value = 2 * (1 - normal_cdf(abs(z)))
    se = math.sqrt(p1 * (1 - p1) / a_n + p2 * (1 - p2) / b_n)
    margin = _z_critical(alpha) * se
    diff = p2 - p1
    return {"z": z, "p_value": p_value, "significant": p_value < alpha,
            "diff": diff, "ci_low": diff - margin, "ci_high": diff + margin}


def welch_t_test(a: Sequence[float], b: Sequence[float], *,
                 alpha: float = 0.05) -> Dict[str, Any]:
    """Welch's t-test (unequal variance) comparing two samples."""
    if len(a) < 2 or len(b) < 2:
        raise AutoControlException("each sample needs at least two values")
    na, nb = len(a), len(b)
    mean_a, mean_b = statistics.fmean(a), statistics.fmean(b)
    var_a, var_b = statistics.variance(a), statistics.variance(b)
    se = math.sqrt(var_a / na + var_b / nb)
    if se == 0:
        return {"t": 0.0, "df": float(na + nb - 2), "p_value": 1.0,
                "significant": False, "mean_diff": mean_b - mean_a,
                "ci_low": 0.0, "ci_high": 0.0}
    t = (mean_b - mean_a) / se
    df = (var_a / na + var_b / nb) ** 2 / (
        (var_a / na) ** 2 / (na - 1) + (var_b / nb) ** 2 / (nb - 1))
    p_value = _t_two_sided_p(t, df)
    margin = _t_critical(alpha, df) * se
    diff = mean_b - mean_a
    return {"t": t, "df": df, "p_value": p_value, "significant": p_value < alpha,
            "mean_diff": diff, "ci_low": diff - margin, "ci_high": diff + margin}


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's d effect size between samples ``a`` and ``b``."""
    if len(a) < 2 or len(b) < 2:
        raise AutoControlException("each sample needs at least two values")
    na, nb = len(a), len(b)
    var_a, var_b = statistics.variance(a), statistics.variance(b)
    pooled = math.sqrt(((na - 1) * var_a + (nb - 1) * var_b) / (na + nb - 2))
    if pooled == 0:
        return 0.0
    return (statistics.fmean(b) - statistics.fmean(a)) / pooled


def chi_square_2x2(a_conv: int, a_fail: int, b_conv: int,
                   b_fail: int) -> Dict[str, Any]:
    """Chi-square test of independence for a 2x2 contingency table (df=1)."""
    observed = [(a_conv, a_fail), (b_conv, b_fail)]
    row_totals = [a_conv + a_fail, b_conv + b_fail]
    col_totals = [a_conv + b_conv, a_fail + b_fail]
    total = a_conv + a_fail + b_conv + b_fail
    if total <= 0:
        raise AutoControlException("contingency table must have observations")
    chi2 = 0.0
    for i in range(2):
        for j in range(2):
            expected = row_totals[i] * col_totals[j] / total
            if expected > 0:
                chi2 += (observed[i][j] - expected) ** 2 / expected
    p_value = 2 * (1 - normal_cdf(math.sqrt(chi2)))
    return {"chi2": chi2, "df": 1, "p_value": p_value,
            "significant": p_value < 0.05}
