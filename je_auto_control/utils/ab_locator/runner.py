"""Run the same goal with N locator strategies in parallel.

Each strategy is a :class:`Locator` (from :mod:`anchor_locator`). The
runner resolves every locator, records win / loss to
:class:`ABStore`, and returns a per-strategy result map. After K runs
``best_strategy()`` can recommend the strategy that consistently wins.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from je_auto_control.utils.ab_locator.store import (
    ABReport, ABStore, default_ab_store,
)
from je_auto_control.utils.anchor_locator.locator import (
    Locator, _resolve_single,
)


@dataclass(frozen=True)
class StrategyResult:
    """One strategy's attempt at locating the target."""

    strategy: str
    succeeded: bool
    coordinates: Optional[Tuple[int, int]]
    elapsed_ms: float
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.coordinates is not None:
            data["coordinates"] = list(self.coordinates)
        return data


@dataclass(frozen=True)
class ABRunOutcome:
    """Per-strategy results + the winner ranked by elapsed time."""

    target_id: str
    results: Dict[str, StrategyResult]
    winner: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "winner": self.winner,
            "results": {k: r.to_dict() for k, r in self.results.items()},
        }


def ab_locate(*, target_id: str,
              strategies: Mapping[str, Locator],
              max_parallel: int = 4,
              record: bool = True,
              store: Optional[ABStore] = None,
              ) -> ABRunOutcome:
    """Run every strategy in parallel and record outcomes."""
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValueError("target_id must be a non-empty string")
    if not strategies:
        raise ValueError("strategies must contain at least one entry")
    pool_size = max(1, int(max_parallel))
    items = list(strategies.items())
    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        results = list(pool.map(_run_one, items))
    by_name = dict(results)
    winner = _pick_winner(by_name)
    if record:
        target_store = store if store is not None else default_ab_store
        for name, result in by_name.items():
            target_store.record(
                target_id=target_id, strategy=name,
                succeeded=result.succeeded,
                elapsed_ms=result.elapsed_ms,
            )
    return ABRunOutcome(
        target_id=target_id, results=by_name, winner=winner,
    )


def best_strategy(target_id: str,
                  store: Optional[ABStore] = None) -> Optional[str]:
    """Convenience: return the historically best strategy name for ``target_id``."""
    target_store = store if store is not None else default_ab_store
    report = target_store.report(target_id)
    winner = report.best_strategy()
    return winner.strategy if winner is not None else None


def report_for(target_id: str,
                store: Optional[ABStore] = None) -> ABReport:
    """Convenience: return the full :class:`ABReport` for ``target_id``."""
    target_store = store if store is not None else default_ab_store
    return target_store.report(target_id)


def _run_one(item) -> Tuple[str, StrategyResult]:
    name, locator = item
    started = time.monotonic()
    try:
        coords = _resolve_single(locator)
    except (RuntimeError, OSError, ValueError) as error:
        return name, StrategyResult(
            strategy=name, succeeded=False, coordinates=None,
            elapsed_ms=_ms_since(started), error=repr(error),
        )
    elapsed = _ms_since(started)
    if coords is None:
        return name, StrategyResult(
            strategy=name, succeeded=False, coordinates=None,
            elapsed_ms=elapsed, error="not found",
        )
    return name, StrategyResult(
        strategy=name, succeeded=True, coordinates=coords,
        elapsed_ms=elapsed,
    )


def _pick_winner(results: Dict[str, StrategyResult]) -> Optional[str]:
    winners = [(name, r) for name, r in results.items() if r.succeeded]
    if not winners:
        return None
    return min(winners, key=lambda pair: pair[1].elapsed_ms)[0]


def _ms_since(started: float) -> float:
    return round((time.monotonic() - started) * 1000.0, 2)


__all__ = [
    "ABRunOutcome", "StrategyResult", "ab_locate",
    "best_strategy", "report_for",
]
