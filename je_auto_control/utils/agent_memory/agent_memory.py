"""Persistent episodic memory for agents (pure standard library).

An agent that re-derives "how do I log in to this app" on every run wastes
tokens and repeats mistakes. :class:`AgentMemory` records each episode —
the *goal*, the *trajectory* (steps/tool-calls taken), and the *outcome* —
to a SQLite file, and recalls the most relevant past episodes by keyword so
they can be injected into the planner's context. This is the cross-run
"context engineering" memory layer.

Recall uses a dependency-free term-frequency score over each episode's
goal + tags + outcome (a lightweight BM25 stand-in); a vector/embedding
tier can be layered on later without changing the API.

Pure standard library (``sqlite3`` / ``json`` / ``re``); imports no
``PySide6``.
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from je_auto_control.utils.sqlite_support import (
    last_row_id, require_sqlite3,
)

if TYPE_CHECKING:  # reason: sqlite3 types are named only in annotations
    import sqlite3

_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass
class Episode:
    """One recorded (goal -> trajectory -> outcome) experience."""
    id: int
    goal: str
    steps: List[Any]
    outcome: str
    tags: List[str] = field(default_factory=list)
    created: float = 0.0
    score: float = 0.0


def _tokens(text: str) -> List[str]:
    return _TOKEN.findall((text or "").lower())


def _row_to_episode(row: "sqlite3.Row", score: float = 0.0) -> Episode:
    return Episode(
        id=int(row["id"]), goal=row["goal"],
        steps=json.loads(row["steps"] or "[]"),
        outcome=row["outcome"] or "", tags=json.loads(row["tags"] or "[]"),
        created=float(row["created"]), score=score)


class AgentMemory:
    """A SQLite-backed store of agent episodes with keyword recall."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def _connect(self) -> "sqlite3.Connection":
        driver = require_sqlite3()
        conn = driver.connect(self._db_path, timeout=30.0,
                              isolation_level=None)
        conn.row_factory = driver.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS episodes ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, goal TEXT NOT NULL, "
                "steps TEXT NOT NULL, outcome TEXT DEFAULT '', "
                "tags TEXT DEFAULT '[]', created REAL NOT NULL)")

    def remember(self, goal: str, *, steps: Optional[List[Any]] = None,
                 outcome: str = "",
                 tags: Optional[List[str]] = None) -> int:
        """Store an episode; return its id."""
        if not goal or not str(goal).strip():
            raise ValueError("an episode needs a non-empty goal")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO episodes (goal, steps, outcome, tags, created) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(goal), json.dumps(steps or []), str(outcome),
                 json.dumps(list(tags or [])), time.time()))
            return last_row_id(cur)

    def get(self, episode_id: int) -> Optional[Episode]:
        """Return an episode by id or ``None``."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM episodes WHERE id=?",
                               (int(episode_id),)).fetchone()
        return _row_to_episode(row) if row is not None else None

    def forget(self, episode_id: int) -> bool:
        """Delete an episode; return whether it existed."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM episodes WHERE id=?",
                               (int(episode_id),))
            return cur.rowcount > 0

    def recent(self, limit: int = 10) -> List[Episode]:
        """Return the most recently stored episodes (newest first)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM episodes ORDER BY id DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [_row_to_episode(row) for row in rows]

    def recall(self, query: str, *, limit: int = 5) -> List[Episode]:
        """Return episodes most relevant to ``query`` (keyword TF score).

        Episodes with zero matching terms are excluded; ties break toward
        the more recent episode.
        """
        terms = _tokens(query)
        if not terms:
            return []
        scored: List[Episode] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM episodes").fetchall()
        for row in rows:
            score = _relevance(row, terms)
            if score > 0:
                scored.append(_row_to_episode(row, score=score))
        scored.sort(key=lambda ep: (ep.score, ep.created), reverse=True)
        return scored[: max(0, int(limit))]

    def stats(self) -> Dict[str, int]:
        """Return ``{"episodes": N}`` for dashboards."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) c FROM episodes").fetchone()
        return {"episodes": int(row["c"])}


def _relevance(row: "sqlite3.Row", terms: List[str]) -> float:
    haystack = " ".join([row["goal"] or "", row["outcome"] or "",
                         " ".join(json.loads(row["tags"] or "[]"))])
    counts = _tokens(haystack)
    if not counts:
        return 0.0
    return float(sum(counts.count(term) for term in terms))
