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
#: Extra rows read per flow past ``window``: running rows have no duration.
_RUNNING_HEADROOM = 16


def _durations(flows: List[str], history_path: Optional[str],
               window: int) -> Dict[str, float]:
    """Mean recent wall-clock seconds per flow, from run history."""
    from je_auto_control.utils.run_history import (
        HistoryStore, default_history_store)
    store, owned = ((HistoryStore(history_path), True) if history_path
                    else (default_history_store, False))
    # Read per flow: one global newest-N read let a flow's runs fall behind
    # N unrelated runs, and the flow then got the default weight.
    try:
        records = [record for flow in dict.fromkeys(flows)
                   for record in store.list_runs(
                       limit=int(window) + _RUNNING_HEADROOM, script_path=flow)]
    finally:
        if owned:
            store.close()
    samples: Dict[str, List[float]] = {}
    for record in records:
        seconds = record.duration_seconds
        if seconds is not None:
            samples.setdefault(record.script_path, []).append(seconds)
    recent = max(1, int(window))
    return {flow: sum(values[:recent]) / len(values[:recent])
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
    if int(window) < 1:
        # window=0 divided by len(values[:0]) with a ZeroDivisionError.
        raise ValueError("window must be at least 1")
    means = _durations(flows, history_path, int(window))
    known = list(means.values())
    if default_weight is not None:
        fallback = float(default_weight)
    elif known:
        fallback = sum(known) / len(known)
    else:
        fallback = 1.0
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
    ``results`` lists concatenated. A :class:`TestSuiteResult` report names
    them ``errored`` and ``cases``; those are read too (they used to be
    dropped, so a sharded run with errors merged as clean) and the merged
    report carries both spellings.
    """
    reports = list(reports)
    merged: Dict[str, Any] = dict.fromkeys(_SUM_KEYS, 0)
    results: List[Any] = []
    for report in reports:
        for key in _SUM_KEYS:
            merged[key] += int(report.get(key, 0) or 0)
        merged["errors"] += int(report.get("errored", 0) or 0)
        results.extend(report.get("results", []) or [])
        results.extend(report.get("cases", []) or [])
    merged["errored"] = merged["errors"]
    merged["shards"] = len(reports)
    merged["results"] = results
    merged["cases"] = results
    return merged
