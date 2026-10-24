"""Read an exact Android endpoint and pin its boot before proposing finite guarded commands."""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.android_commands import (
    AndroidActionProposal, android_input_command, compile_android_action)
from je_auto_control.utils.agent_runtime.android_scope import (
    AndroidSnapshot, IDENTITY_PROBE, parse_android_snapshot, validate_android_binding)
from je_auto_control.utils.agent_runtime.android_transport import ManagedAdbServer, _deadline
from je_auto_control.utils.agent_runtime.errors import AgentHumanReview, AgentTaskError
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint


def _remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise AgentTaskError("Android identity inspection deadline exhausted")
    return value


class AndroidDeviceSession:
    """Internal read-only session; no automatic app launch, boot adoption or input dispatch."""

    def __init__(self, server: ManagedAdbServer, *, serial: str, physical_id: str, package: str, user: int = 0) -> None:
        validate_android_binding(physical_id, package, user)
        if (not isinstance(serial, str) or not 1 <= len(serial) <= 256
                or any(ord(char) < 33 or ord(char) > 126 for char in serial)):
            raise AgentTaskError("Android connection serial must be an exact bounded token")
        self._server = server
        self._serial = serial
        self._binding = (physical_id, package, user)
        self._boot: str | None = None
        self._mutex = threading.Lock()

    def _select(self, timeout: float, check: Callable[[], None]) -> int:
        rows = [row for row in self._server.list_devices(timeout=timeout, check=check) if row.serial == self._serial]
        if len(rows) != 1 or rows[0].state != "device":
            raise AgentTaskError("reviewed Android endpoint is ambiguous, offline or unauthorized")
        value = rows[0].transport_id
        if (not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]{0,19}", value) is None
                or int(value) > 2**64 - 1):
            raise AgentTaskError("Android endpoint lacks an exact transport identity")
        return int(value)

    def inspect(self, *, timeout: float = 5,
                check: Callable[[], None] = cancellation_checkpoint) -> tuple[int, AndroidSnapshot]:
        """Read current identity/focus; never adopt a new boot into an existing session."""
        deadline = _deadline(timeout)
        transport = self._select(_remaining(deadline), check)
        result = self._server.shell(transport, IDENTITY_PROBE, timeout=_remaining(deadline), limit=262144, check=check)
        if result.returncode != 0 or result.stderr:
            raise AgentTaskError("Android identity evidence is unavailable; remote diagnostics are withheld")
        physical, package, user = self._binding
        snapshot = parse_android_snapshot(result.stdout, physical, package, user=user)
        check()
        _remaining(deadline)
        self._pin(snapshot)
        return transport, snapshot

    def _pin(self, snapshot: AndroidSnapshot) -> None:
        with self._mutex:
            if self._boot is not None and snapshot.boot_id != self._boot:
                raise AgentHumanReview("Android boot changed; review the old task before creating a new session")
            self._boot = snapshot.boot_id

    def propose(self, name: str, arguments: dict[str, Any], *, timeout: float = 5,
                check: Callable[[], None] = cancellation_checkpoint) -> AndroidActionProposal:
        """Return a host-only command proposal, never a task/model payload or input approval."""
        android_input_command(name, arguments)
        transport, snapshot = self.inspect(timeout=timeout, check=check)
        command = compile_android_action(snapshot, name, arguments)
        check()
        return AndroidActionProposal(transport, snapshot, command)
