"""Flaky-test detection — score intermittent failures from run history.

The SQLite run-history store already records every scheduler / trigger /
hotkey / REST run with an ``ok`` or ``error`` status. A *flaky* script is
one that produces *both* outcomes over time without its definition
changing — the most expensive kind of failure to chase manually.

:func:`analyze_flakiness` groups historical runs by script (or source id),
counts pass/fail outcomes and the number of pass<->fail *flips* in
chronological order, and emits a per-script flakiness score so a flaky
script surfaces above one that is consistently green or consistently red.

This is read-only analytics over data the framework already collects; it
adds no new storage and has zero Qt dependency.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from je_auto_control.utils.run_history.history_store import (
    HistoryStore, STATUS_ERROR, STATUS_OK, default_history_store,
)

_GROUP_KEYS = ("script_path", "source_id")


@dataclass(frozen=True)
class FlakyEntry:
    """Flakiness statistics for one script / source group."""

    key: str
    total_runs: int
    ok: int
    error: int
    flips: int
    flip_rate: float
    pass_rate: float
    last_status: str
    flaky: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FlakinessReport:
    """Ranked flakiness across every qualifying group."""

    generated_at: float
    group_by: str
    total_groups: int
    flaky_count: int
    entries: List[FlakyEntry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "group_by": self.group_by,
            "total_groups": self.total_groups,
            "flaky_count": self.flaky_count,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _count_flips(statuses: List[str]) -> int:
    """Count adjacent pass<->fail transitions in a chronological list."""
    return sum(
        1 for prev, curr in zip(statuses, statuses[1:]) if prev != curr
    )


def _entry_for_group(key: str, statuses: List[str]) -> FlakyEntry:
    """Build a :class:`FlakyEntry` from chronological ``ok``/``error`` values."""
    total = len(statuses)
    ok = statuses.count(STATUS_OK)
    error = statuses.count(STATUS_ERROR)
    flips = _count_flips(statuses)
    flip_rate = flips / (total - 1) if total > 1 else 0.0
    pass_rate = ok / total if total else 0.0
    return FlakyEntry(
        key=key, total_runs=total, ok=ok, error=error,
        flips=flips, flip_rate=round(flip_rate, 4),
        pass_rate=round(pass_rate, 4),
        last_status=statuses[-1], flaky=(ok > 0 and error > 0),
    )


def _grouped_statuses(records: List[Any], group_by: str
                      ) -> Dict[str, List[str]]:
    """Map each group key to its chronological list of finished statuses.

    ``records`` arrive newest-first (the store's default order); we reverse
    per group so flips are counted oldest -> newest.
    """
    buckets: Dict[str, List[str]] = {}
    for record in records:
        if record.status not in (STATUS_OK, STATUS_ERROR):
            continue
        key = getattr(record, group_by)
        buckets.setdefault(key, []).append(record.status)
    return {key: list(reversed(values)) for key, values in buckets.items()}


def analyze_flakiness(store: Optional[HistoryStore] = None,
                      limit: int = 500,
                      min_runs: int = 2,
                      group_by: str = "script_path") -> FlakinessReport:
    """Score flakiness across run history grouped by script or source.

    :param store: history store to read (defaults to the shared store).
    :param limit: maximum number of recent runs to consider.
    :param min_runs: minimum finished runs a group needs to be scored.
    :param group_by: ``"script_path"`` (default) or ``"source_id"``.
    """
    if group_by not in _GROUP_KEYS:
        raise ValueError(
            f"group_by must be one of {list(_GROUP_KEYS)}, got {group_by!r}"
        )
    active_store = store if store is not None else default_history_store
    records = active_store.list_runs(limit=int(limit))
    grouped = _grouped_statuses(records, group_by)
    entries = [
        _entry_for_group(key, statuses)
        for key, statuses in grouped.items()
        if len(statuses) >= max(1, int(min_runs))
    ]
    entries.sort(key=lambda e: (e.flip_rate, e.error), reverse=True)
    flaky_count = sum(1 for entry in entries if entry.flaky)
    return FlakinessReport(
        generated_at=time.time(), group_by=group_by,
        total_groups=len(entries), flaky_count=flaky_count, entries=entries,
    )
