"""Duration-aware suite sharding (pure standard library).

Splitting a suite across N workers by *count* wastes time when tests differ
in duration — the slowest worker defines wall-clock. This balances shards by
**historical per-flow duration** (from the run-history store) using greedy
bin-packing, so each shard takes roughly the same time. :func:`merge_results`
recombines the per-shard reports afterwards — the standard companion step.

Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional

_SUM_KEYS = ("total", "passed", "failed", "skipped", "errors")


def _durations(flows: List[str], history_path: Optional[str],
               window: int) -> Dict[str, float]:
    """Mean recent wall-clock seconds per flow, from run history."""
    from je_auto_control.utils.run_history import (
        HistoryStore, default_history_store)
    store, owned = ((HistoryStore(history_path), True) if history_path
                    else (default_history_store, False))
    try:
        records = store.list_runs(
            limit=max(100, int(window) * max(1, len(flows))))
    finally:
        if owned:
            store.close()
    samples: Dict[str, List[float]] = {}
    for record in records:
        seconds = record.duration_seconds
        if seconds is not None:
            samples.setdefault(record.script_path, []).append(seconds)
    return {flow: sum(values[:window]) / len(values[:window])
            for flow, values in samples.items() if values}


def shard_flows(flows: List[str], shards: int, *,
                history_path: Optional[str] = None, window: int = 20,
                default_weight: Optional[float] = None) -> List[List[str]]:
    """Split ``flows`` into ``shards`` lists balanced by mean duration.

    Flows with no history use ``default_weight`` (or the mean of known flows,
    else 1.0). Greedy: heaviest flow first onto the currently-lightest shard.
    """
    flows = list(flows)
    count = max(1, int(shards))
    means = _durations(flows, history_path, int(window))
    known = list(means.values())
    fallback = (default_weight if default_weight is not None
                else (sum(known) / len(known) if known else 1.0))
    ordered = sorted(flows, key=lambda f: means.get(f, fallback), reverse=True)
    buckets: List[List[str]] = [[] for _ in range(count)]
    loads = [0.0] * count
    for flow in ordered:
        index = min(range(count), key=lambda k: loads[k])
        buckets[index].append(flow)
        loads[index] += means.get(flow, fallback)
    return buckets


def merge_results(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge per-shard report dicts into one consolidated report.

    Numeric keys (total/passed/failed/skipped/errors) are summed and
    ``results`` lists concatenated.
    """
    reports = list(reports)
    merged: Dict[str, Any] = {key: 0 for key in _SUM_KEYS}
    results: List[Any] = []
    for report in reports:
        for key in _SUM_KEYS:
            merged[key] += int(report.get(key, 0) or 0)
        results.extend(report.get("results", []) or [])
    merged["shards"] = len(reports)
    merged["results"] = results
    return merged
