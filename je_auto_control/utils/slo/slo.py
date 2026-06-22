"""Service-level objectives: SLI, error budget and multi-window burn-rate alerts.

The framework emits raw signals (``observability`` metrics, ``run_history``
durations) but had no operational layer turning them into an SLO, an error
budget, or burn-rate alerts. This adds that: compute the SLI over a window of
outcome records, the error budget against a target, and the multi-window
multi-burn-rate alerts from the Google SRE workbook.

Records are plain data (``[{"timestamp": float, "ok": bool}, ...]``) so the
whole thing is offline and deterministic; the clock is injectable. Pure
standard library; imports no ``PySide6``.
"""
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException


@dataclass(frozen=True)
class BurnRule:
    """One multi-window burn-rate alert tier."""

    severity: str
    long_window_s: float
    short_window_s: float
    threshold: float


def default_burn_rules() -> List[BurnRule]:
    """Return the canonical Google SRE burn-rate tiers (for a 30-day SLO)."""
    return [
        BurnRule("page", 3600.0, 300.0, 14.4),
        BurnRule("page", 21600.0, 1800.0, 6.0),
        BurnRule("ticket", 259200.0, 21600.0, 1.0),
    ]


def _window(records: Sequence[Mapping[str, Any]], window_s: Optional[float],
            now: float) -> List[Mapping[str, Any]]:
    if window_s is None:
        return list(records)
    cutoff = now - window_s
    return [r for r in records if float(r.get("timestamp", now)) >= cutoff]


def _counts(records: Sequence[Mapping[str, Any]]) -> tuple:
    total = len(records)
    good = sum(1 for r in records if r.get("ok"))
    return good, total


def evaluate_slo(records: Sequence[Mapping[str, Any]], target: float, *,
                 window_s: Optional[float] = None,
                 now: Optional[float] = None) -> Dict[str, Any]:
    """Return the SLI and error budget for ``records`` against ``target``."""
    if not 0.0 < target < 1.0:
        raise AutoControlException("target must be between 0 and 1")
    when = time.time() if now is None else now
    good, total = _counts(_window(records, window_s, when))
    if total == 0:
        return {"sli": 1.0, "good": 0, "total": 0, "target": target,
                "budget_total": 0.0, "budget_remaining": 0.0,
                "budget_remaining_fraction": 1.0, "burn_rate": 0.0}
    bad = total - good
    allowed = (1.0 - target) * total
    bad_rate = bad / total
    return {
        "sli": good / total, "good": good, "total": total, "target": target,
        "budget_total": allowed,
        "budget_remaining": allowed - bad,
        "budget_remaining_fraction": (1.0 - bad / allowed) if allowed else 0.0,
        "burn_rate": bad_rate / (1.0 - target),
    }


def burn_rate(records: Sequence[Mapping[str, Any]], target: float, *,
              window_s: Optional[float] = None,
              now: Optional[float] = None) -> float:
    """Return the error-budget burn rate over the window (1.0 = on-budget)."""
    return evaluate_slo(records, target, window_s=window_s, now=now)["burn_rate"]


def burn_alerts(records: Sequence[Mapping[str, Any]], target: float, *,
                rules: Optional[Sequence[BurnRule]] = None,
                now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Return fired multi-window burn-rate alerts (both windows over threshold)."""
    when = time.time() if now is None else now
    active = rules if rules is not None else default_burn_rules()
    alerts: List[Dict[str, Any]] = []
    for rule in active:
        long_rate = burn_rate(records, target, window_s=rule.long_window_s,
                              now=when)
        short_rate = burn_rate(records, target, window_s=rule.short_window_s,
                               now=when)
        if long_rate > rule.threshold and short_rate > rule.threshold:
            alerts.append({
                "severity": rule.severity, "threshold": rule.threshold,
                "long_burn_rate": long_rate, "short_burn_rate": short_rate,
                "long_window_s": rule.long_window_s,
                "short_window_s": rule.short_window_s,
            })
    return alerts
