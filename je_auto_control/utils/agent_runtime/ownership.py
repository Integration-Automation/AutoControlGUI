"""Fenced input ownership; running dispatch must retire before ownership transfers."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.store import AgentTaskStore


@dataclass(frozen=True)
class ControlLease:
    """An owner-bound generation checked by the host immediately before input."""

    target: str
    owner: str
    generation: int


class ControlBroker:
    """One host broker serializes target dispatch and refuses premature transfers."""

    def __init__(self, store: AgentTaskStore) -> None:
        self._store = store
        self._mutex = threading.Lock()
        self._locks: dict[str, Any] = {}

    def _lock(self, target: str) -> Any:
        with self._mutex:
            return self._locks.setdefault(target, threading.RLock())

    def acquire(self, target: str, owner: str) -> ControlLease:
        """Claim an unowned target, preserving its monotonically increasing fence."""
        lock = self._lock(target)
        if not lock.acquire(blocking=False):
            raise AgentControlBusy("target control still has active input or cleanup")
        try:
            return self._claim(target, owner)
        finally:
            lock.release()

    def _claim(self, target: str, owner: str) -> ControlLease:
        with self._store.connection(write=True) as connection:
            row = connection.execute("SELECT owner,generation FROM agent_control WHERE target=?",
                                     (target,)).fetchone()
            if row is not None and row["owner"] not in ("", owner):
                raise AgentControlBusy("target control is held by another task")
            if row is not None and row["owner"] == owner:
                return ControlLease(target, owner, row["generation"])
            generation = 1 if row is None else row["generation"] + 1
            connection.execute("INSERT INTO agent_control VALUES (?,?,?) ON CONFLICT(target) "
                               "DO UPDATE SET owner=excluded.owner,generation=excluded.generation",
                               (target, owner, generation))
            return ControlLease(target, owner, generation)

    def validate(self, lease: ControlLease) -> None:
        """Reject a cancelled or stale worker even if it still has an old reference."""
        with self._store.connection() as connection:
            row = connection.execute("SELECT owner,generation FROM agent_control WHERE target=?",
                                     (lease.target,)).fetchone()
        if row is None or (row["owner"], row["generation"]) != (lease.owner, lease.generation):
            raise AgentTaskError("target control generation is no longer owned")

    @contextmanager
    def dispatch(self, lease: ControlLease) -> Iterator[None]:
        """Own the target through the whole operation, including nested input."""
        with self._lock(lease.target):
            self.validate(lease)
            yield

    def release(self, lease: ControlLease, cleanup: Callable[[], None]) -> bool:
        """Release only after owned dispatch and cleanup finish; never steal an active operation."""
        lock = self._lock(lease.target)
        if not lock.acquire(blocking=False):
            return False
        try:
            self.validate(lease)
            cleanup()
            with self._store.connection(write=True) as connection:
                connection.execute("UPDATE agent_control SET owner='' WHERE target=? AND owner=? AND generation=?",
                                   (lease.target, lease.owner, lease.generation))
            return True
        finally:
            lock.release()
