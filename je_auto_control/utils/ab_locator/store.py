"""Persistent per-(target, strategy) success counters for the A/B framework."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ABStrategyStats:
    """Counts for one (target, strategy) pair."""

    target_id: str
    strategy: str
    successes: int = 0
    failures: int = 0
    total_elapsed_ms: float = 0.0

    @property
    def total(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        return self.successes / self.total if self.total else 0.0

    @property
    def average_ms(self) -> float:
        return self.total_elapsed_ms / self.total if self.total else 0.0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["success_rate"] = round(self.success_rate, 4)
        data["average_ms"] = round(self.average_ms, 2)
        return data


@dataclass
class ABReport:
    """Roll-up for one ``target_id`` across every strategy that ran."""

    target_id: str
    strategies: List[ABStrategyStats] = field(default_factory=list)

    def best_strategy(self) -> Optional[ABStrategyStats]:
        if not self.strategies:
            return None
        return max(
            self.strategies,
            key=lambda s: (s.success_rate, -s.average_ms),
        )

    def to_dict(self) -> Dict[str, Any]:
        winner = self.best_strategy()
        return {
            "target_id": self.target_id,
            "strategies": [s.to_dict() for s in self.strategies],
            "best_strategy": winner.strategy if winner else None,
            "best_success_rate": (
                round(winner.success_rate, 4) if winner else None
            ),
        }


class ABStore:
    """Thread-safe ``(target_id, strategy) → ABStrategyStats`` ledger."""

    DEFAULT_PATH = Path.home() / ".je_auto_control" / "ab_locator_stats.json"

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else self.DEFAULT_PATH
        self._lock = threading.RLock()
        self._cache: Dict[Tuple[str, str], ABStrategyStats] = {}
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path

    def record(self, *, target_id: str, strategy: str,
               succeeded: bool, elapsed_ms: float) -> ABStrategyStats:
        with self._lock:
            self._load_if_needed()
            key = (target_id, strategy)
            stats = self._cache.get(key) or ABStrategyStats(
                target_id=target_id, strategy=strategy,
            )
            if succeeded:
                stats.successes += 1
            else:
                stats.failures += 1
            stats.total_elapsed_ms += float(elapsed_ms)
            self._cache[key] = stats
            self._save()
            return stats

    def report(self, target_id: str) -> ABReport:
        with self._lock:
            self._load_if_needed()
            rows = [s for (tid, _), s in self._cache.items()
                    if tid == target_id]
        rows.sort(key=lambda s: s.strategy)
        return ABReport(target_id=target_id, strategies=rows)

    def all_reports(self) -> List[ABReport]:
        with self._lock:
            self._load_if_needed()
            target_ids = sorted({tid for tid, _ in self._cache})
        return [self.report(tid) for tid in target_ids]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass

    def _load_if_needed(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        try:
            payload = json.loads(raw)
        except ValueError:
            return
        if not isinstance(payload, list):
            return
        for row in payload:
            try:
                stats = ABStrategyStats(**row)
            except TypeError:
                continue
            self._cache[(stats.target_id, stats.strategy)] = stats

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "target_id": s.target_id, "strategy": s.strategy,
                "successes": s.successes, "failures": s.failures,
                "total_elapsed_ms": round(s.total_elapsed_ms, 3),
            }
            for s in self._cache.values()
        ]
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False),
                        encoding="utf-8")
        tmp.replace(self._path)


default_ab_store = ABStore()


__all__ = ["ABReport", "ABStore", "ABStrategyStats", "default_ab_store"]
