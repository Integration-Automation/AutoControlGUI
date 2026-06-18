"""Risk-based test selection from run history (pure standard library).

Instead of always running the whole suite, rank flows by how *risky* they
are — recently failing, flaky, stale, or never-run — and run the riskiest
first (or only the top-k). Risk is derived entirely from the run-history
store (:mod:`je_auto_control.utils.run_history`); no third-party
dependency.

Each flow is identified by its ``script_path`` in the history. The score
is in ``[0, 1]``::

    score = 0.5 * failure_rate
          + 0.2 * (last run failed)
          + 0.2 * flakiness
          + 0.1 * staleness

A flow that has never run scores ``0.8`` — untested means risky.
"""
import time
from typing import Any, Dict, List, Optional

_WEIGHT_FAILURE = 0.5
_WEIGHT_LAST_FAILED = 0.2
_WEIGHT_FLAKY = 0.2
_WEIGHT_STALE = 0.1
_UNTESTED_SCORE = 0.8
_STALE_DAYS = 30.0
_SECONDS_PER_DAY = 86400.0
_FINISHED = ("ok", "error")


def _open_store(history_path: Optional[str]):
    """Return ``(store, owned)``; ``owned`` stores must be closed by caller."""
    from je_auto_control.utils.run_history import (
        HistoryStore, default_history_store)
    if history_path:
        return HistoryStore(history_path), True
    # default_history_store is a shared instance, not a factory — use it
    # directly and leave it open (the caller must not close it).
    return default_history_store, False


def _runs_by_flow(store: Any, limit: int) -> Dict[str, List[Any]]:
    grouped: Dict[str, List[Any]] = {}
    for rec in store.list_runs(limit=limit):
        grouped.setdefault(rec.script_path, []).append(rec)
    return grouped


def _flaky(chrono: List[str]) -> tuple:
    """Return ``(flaky_rate, transition_count)`` over a status sequence."""
    if len(chrono) < 2:
        return 0.0, 0
    transitions = sum(1 for a, b in zip(chrono, chrono[1:]) if a != b)
    return transitions / (len(chrono) - 1), transitions


def _score_flow(records: List[Any], window: int,
                now: float) -> Dict[str, Any]:
    finished = [r for r in records if r.status in _FINISHED][:window]
    if not finished:
        return {"runs": 0, "failures": 0, "last_status": None,
                "flaky": False, "score": _UNTESTED_SCORE}
    total = len(finished)
    failures = sum(1 for r in finished if r.status == "error")
    last_failed = finished[0].status == "error"
    flaky_rate, transitions = _flaky([r.status for r in reversed(finished)])
    age_days = max(0.0, (now - finished[0].started_at) / _SECONDS_PER_DAY)
    score = (_WEIGHT_FAILURE * failures / total
             + _WEIGHT_LAST_FAILED * (1.0 if last_failed else 0.0)
             + _WEIGHT_FLAKY * flaky_rate
             + _WEIGHT_STALE * min(1.0, age_days / _STALE_DAYS))
    return {"runs": total, "failures": failures,
            "last_status": finished[0].status, "flaky": transitions >= 2,
            "score": round(min(1.0, score), 4)}


def rank_flows(flows: List[str], *, history_path: Optional[str] = None,
               window: int = 10) -> List[Dict[str, Any]]:
    """Return ``flows`` scored and sorted by risk (riskiest first).

    Each entry is ``{flow, score, runs, failures, last_status, flaky}``.
    A flow absent from history scores ``0.8`` (untested is treated as
    risky). ``window`` caps how many recent runs per flow are considered.
    """
    flows = list(flows)
    store, owned = _open_store(history_path)
    now = time.time()
    try:
        grouped = _runs_by_flow(store, max(100, window * max(1, len(flows))))
    finally:
        if owned:
            store.close()
    ranked: List[Dict[str, Any]] = []
    for flow in flows:
        info = _score_flow(grouped.get(flow, []), window, now)
        info["flow"] = flow
        ranked.append(info)
    ranked.sort(key=lambda d: (-d["score"], d["flow"]))
    return ranked


def select_flows(flows: List[str], *, k: Optional[int] = None,
                 threshold: Optional[float] = None,
                 history_path: Optional[str] = None,
                 window: int = 10) -> List[str]:
    """Return flow names to run, riskiest first.

    With ``k`` keep the top-k; with ``threshold`` keep score >= threshold;
    with neither, return every flow ordered by risk.
    """
    ranked = rank_flows(flows, history_path=history_path, window=window)
    if threshold is not None:
        ranked = [r for r in ranked if r["score"] >= float(threshold)]
    if k is not None:
        ranked = ranked[: max(0, int(k))]
    return [r["flow"] for r in ranked]
