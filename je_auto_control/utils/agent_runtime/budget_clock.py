"""Persistent monotonic task budgets that cannot be extended by wall-clock rollback or restart."""
from __future__ import annotations

import time
from typing import Any, Callable


class BudgetClock:
    """Store elapsed high-water marks; a regressed monotonic clock expires existing work."""

    def __init__(self, store: Any, *, monotonic: Callable[[], float] | None = None,
                 wall: Callable[[], float] | None = None) -> None:
        self._store = store
        self._monotonic = monotonic or time.monotonic
        self._wall = wall or time.time

    def remaining(self, row: dict[str, Any]) -> float:
        """Return a durable remaining budget; queued tasks do not spend waiting time."""
        budget = float(row["spec"]["budget"]["wall_seconds"])
        if row["started"] is None:
            return budget
        now = self._monotonic()
        wall_elapsed = max(0.0, self._wall() - row["started"])
        with self._store.connection(write=True) as connection:
            record = connection.execute("SELECT * FROM agent_clocks WHERE task_id=?", (row["id"],)).fetchone()
            if record is None:
                started, spent = now, wall_elapsed
            else:
                started = record["started"]
                spent = budget if now < record["last_seen"] else max(record["spent"], now - started, wall_elapsed)
            connection.execute("INSERT INTO agent_clocks VALUES (?,?,?,?) ON CONFLICT(task_id) DO UPDATE "
                               "SET last_seen=excluded.last_seen,spent=excluded.spent",
                               (row["id"], started, now, spent))
        return max(0.0, budget - spent)
