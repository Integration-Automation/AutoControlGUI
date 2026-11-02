"""Bounded effect-task ownership of actual permanently read-only browser helper processes."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import json
import threading
import time
from typing import Any, Callable, Iterator, Mapping

from je_auto_control.utils.agent_runtime.browser_retirement import retirement_proof
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

_CAPACITY = 16
_LIFETIME = 300


def _binding(row: Mapping) -> dict:
    return {"id": row["id"], "spec": deepcopy(row["spec"]), "owner": deepcopy(row["owner"])}


@dataclass(eq=False)
class RetainedBrowser:
    """One host-only reservation; neither a saved proof nor a matching ID creates ownership."""

    source: dict
    channel: Any = None
    proof: dict | None = None
    expires: float = 0
    busy: bool = False
    invalid: bool = False


class RetainedBrowsers:
    """Reserve capacity before detachment and retain failed reaping without evicting another reader."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._records: dict[str, RetainedBrowser] = {}
        self._closed = False

    @property
    def full(self) -> bool:
        """Include pending reservations and unavailable processes awaiting confirmed reaping."""
        with self._lock:
            return len(self._records) >= _CAPACITY

    @contextmanager
    def reserve(self, row: Mapping) -> Iterator[RetainedBrowser | None]:
        """Atomically reserve a bounded slot; never hold the lock during SDK/IPC or cleanup."""
        source = _binding(row)
        with self._lock:
            if self._closed:
                raise AgentTaskError("retained browser collection is closed")
            if source["id"] in self._records:
                raise AgentTaskError("retained browser source is already owned")
            entry = None if self.full else RetainedBrowser(source, expires=self._clock() + _LIFETIME)
            if entry is not None:
                self._records[source["id"]] = entry
        try:
            yield entry
        finally:
            if entry is not None and entry.proof is None:
                self.discard(source["id"])

    def commit(self, entry: RetainedBrowser, channel: Any, proof: dict) -> None:
        """Accept only the actual reserved slot; failed proof validation still owns detached cleanup."""
        with self._lock:
            if self._records.get(entry.source["id"]) is not entry or entry.channel is not None:
                raise AgentTaskError("retained browser reservation is unavailable")
            entry.channel = channel
        description = retirement_proof(proof)
        with self._lock:
            if self._closed or entry.invalid or channel.retired or self._clock() >= entry.expires:
                raise AgentTaskError("retained browser context is unavailable")
            entry.proof = description

    def require(self, row: Mapping) -> RetainedBrowser:
        """Validate original task/spec/owner and current lifetime; never manufacture a replacement."""
        source = _binding(row)
        with self._lock:
            entry = self._records.get(source["id"])
            if entry is None or (entry.proof is None and not entry.invalid):
                raise AgentTaskError("retained browser context is unavailable")
            same_source = (json.dumps(entry.source, sort_keys=True, allow_nan=False)
                           == json.dumps(source, sort_keys=True, allow_nan=False))
            invalid = (self._closed or entry.invalid or not same_source
                       or self._clock() >= entry.expires or entry.channel.retired)
            if not invalid:
                return entry
            entry.invalid = True
        self.discard(source["id"])
        raise AgentTaskError("retained browser context is unavailable")

    def borrow(self, row: Mapping) -> RetainedBrowser:
        """Grant one transient read borrower while process lifetime stays with this collection."""
        entry = self.require(row)
        with self._lock:
            if self._records.get(entry.source["id"]) is not entry or entry.invalid:
                raise AgentTaskError("retained browser context is unavailable")
            if entry.busy:
                raise AgentTaskError("retained browser context is busy")
            entry.busy = True
        return entry

    def release(self, entry: RetainedBrowser) -> None:
        """Release only this exact borrow, including after collection shutdown invalidated it."""
        with self._lock:
            entry.busy = False

    def discard(self, task_id: str) -> None:
        """Invalidate before reaping; failed or unconfirmed reaping remains owned and consumes capacity."""
        with self._lock:
            entry = self._records.get(task_id)
            if entry is None:
                return
            entry.invalid = True
            channel = entry.channel
        if channel is not None:
            channel.close()
            if not channel.retired:
                raise AgentTaskError("retained browser process cleanup is unconfirmed")
        with self._lock:
            if self._records.get(task_id) is entry:
                del self._records[task_id]

    def sources(self) -> list[dict]:
        """Return private copies for maintenance, including failed transfers but not live reservations."""
        with self._lock:
            return [deepcopy(entry.source) for entry in self._records.values()
                    if entry.proof is not None or entry.invalid]

    def close(self) -> None:
        """Drain all owned processes even if one fails; never accept another reservation afterwards."""
        with self._lock:
            self._closed = True
            identifiers = list(self._records)
        failures = []
        for task_id in identifiers:
            try:
                self.discard(task_id)
            except (OSError, RuntimeError, ValueError) as error:
                failures.append(type(error).__name__)
        if failures:
            raise AgentTaskError("retained browser process cleanup is unconfirmed")
