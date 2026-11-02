"""Presence-only monotonic state; source leases never substitute for native input ownership."""
from __future__ import annotations

import math
from dataclasses import dataclass
import threading
import time
from typing import Callable
import uuid

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError


@dataclass
class _Timing:
    sampled: float | None = None
    physical: float | None = None
    last_clock: float | None = None


@dataclass
class _Flags:
    interactive: bool = False
    held: bool = False
    live: bool = False
    failed: bool = False


class PresenceState:
    """Bind finite leases to continuously sampled physical idle and an irrevocable revision."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._mutex = threading.RLock()
        self._generation = uuid.uuid4().hex
        self._revision = 0
        self._leases: dict[str, int | None] = {}
        self._timing, self._flags = _Timing(), _Flags()

    def _advance(self) -> None:
        if self._revision == (1 << 63) - 1:
            self._flags.failed, self._flags.live = True, False
        else:
            self._revision += 1

    def _tick(self) -> float | None:
        if self._flags.failed:
            return None
        try:
            value = self._clock()
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0):
                raise ValueError('invalid monotonic source clock')
            if self._timing.last_clock is not None and value < self._timing.last_clock:
                raise ValueError('regressing monotonic source clock')
            self._timing.last_clock = float(value)
            return self._timing.last_clock
        except (OSError, RuntimeError, TypeError, ValueError, OverflowError):
            self.fail()
            return None

    def _require_tick(self) -> float:
        value = self._tick()
        if value is None:
            raise AgentTaskError('physical presence source clock is unavailable')
        return value

    def refresh(self, interactive: bool, held: bool) -> None:
        """Record a fresh verified native sample; gaps and lock changes start new physical idle."""
        with self._mutex:
            if not isinstance(interactive, bool) or not isinstance(held, bool):
                self.fail()
                raise AgentTaskError('physical presence flags must be boolean')
            now = self._require_tick()
            if (self._timing.sampled is None or now - self._timing.sampled > 0.25
                    or interactive != self._flags.interactive):
                self._timing.physical = now
                self._advance()
            self._flags.interactive, self._flags.held = interactive, held
            self._timing.sampled, self._flags.live = now, not self._flags.failed

    def physical(self) -> None:
        """Remember only the time/revision of physical presence, without any input payload."""
        with self._mutex:
            self._timing.physical = self._require_tick()
            self._advance()

    def fail(self) -> None:
        """Permanently invalidate this source after a native or clock failure."""
        with self._mutex:
            if not self._flags.failed:
                self._advance()
            self._flags.failed, self._flags.live = True, False

    def _snapshot(self) -> dict:
        now = self._tick()
        if (now is not None and self._flags.live and self._timing.sampled is not None
                and now - self._timing.sampled > 0.25):
            self._flags.live, self._timing.physical = False, now
            self._advance()
        idle = max(0.0, now - self._timing.physical) if now is not None and self._timing.physical is not None else 0.0
        state = self._availability(idle)
        return {'state': state, 'idle_seconds': idle, 'interactive': self._flags.interactive,
                'held': self._flags.held, 'generation': self._generation, 'revision': self._revision,
                'native_evidence': 'not_recorded'}

    def _availability(self, idle: float) -> str:
        if self._flags.failed or self._timing.sampled is not None and not self._flags.live:
            return 'unavailable'
        if self._timing.sampled is None:
            return 'not_started'
        if not self._flags.interactive:
            return 'locked'
        if self._flags.held or idle < 60:
            return 'waiting_idle'
        return 'monitoring'

    def inspect(self) -> dict:
        """Return detached coarse presence metadata; native acceptance remains unrecorded."""
        with self._mutex:
            return self._snapshot()

    def acquire(self) -> dict:
        """Allocate one finite presence lease after fresh unlocked, released, sixty-second idle."""
        with self._mutex:
            if self._snapshot()['state'] != 'monitoring':
                raise AgentControlBusy('physical presence needs fresh unlocked, released, sixty-second idle')
            if len(self._leases) >= 16:
                raise AgentControlBusy('physical presence lease capacity is busy')
            identifier = uuid.uuid4().hex
            if identifier in self._leases:
                raise AgentTaskError('physical presence lease identity collision')
            self._leases[identifier] = self._revision
            return {'generation': self._generation, 'lease_id': identifier}

    def _validate(self, generation: str, lease_id: str) -> None:
        if generation != self._generation or not isinstance(lease_id, str) or lease_id not in self._leases:
            raise AgentTaskError('physical presence lease identity is unavailable')

    def check(self, generation: str, lease_id: str) -> dict:
        """Refuse a lost lease permanently; held input alone does not revoke its existing owner."""
        with self._mutex:
            self._validate(generation, lease_id)
            snapshot = self._snapshot()
            if (self._leases[lease_id] != self._revision or not self._flags.live
                    or not self._flags.interactive or self._flags.failed):
                self._leases[lease_id] = None
                raise AgentTaskError('physical presence changed; explicit resume with a new lease is required')
            return snapshot

    def release(self, generation: str, lease_id: str) -> None:
        """Release only this presence token; no keyboard/mouse cleanup is certified."""
        with self._mutex:
            self._validate(generation, lease_id)
            del self._leases[lease_id]

    def close(self) -> None:
        """Fence all outstanding leases without permitting a restart of this source."""
        self.fail()
