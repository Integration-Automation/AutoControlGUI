"""Physical activity gates with explicit idle acquisition and manual takeover semantics."""
from __future__ import annotations

import sys
import threading
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError


def physical_event(kind: str, flags: int) -> bool:
    """Classify Win32 hook metadata without recording key values or pointer coordinates."""
    masks = {"keyboard": 0x10, "mouse": 0x01}
    if kind not in masks:
        raise AgentTaskError("unknown physical input source")
    return not bool(flags & masks[kind])


class ActivityGate:
    """A trusted listener/probe pair; injected input cannot keep resetting human activity."""

    def __init__(self, listener: Any, idle: Callable[[], float], interactive: Callable[[], bool],
                 takeover: Callable[[], None]) -> None:
        self._listener, self._idle, self._interactive = listener, idle, interactive
        self._takeover = takeover
        self._observed = threading.Event()
        self._armed = False
        self._started = False

    def notify(self) -> None:
        """Remember presence only; a callback never receives or stores typed content."""
        first = not self._observed.is_set()
        self._observed.set()
        if self._armed and first:
            self._takeover()

    def ready(self) -> None:
        """Acquire only an unlocked session after sixty seconds of human inactivity."""
        if not self._started:
            self._listener.start()
            self._started = True
        if not self._armed:
            if not self._interactive() or self._idle() < 60 or self._observed.is_set():
                raise AgentControlBusy("desktop is locked, active or has not been idle for sixty seconds")
            self._armed = True
        self.check()

    def check(self) -> None:
        """Refuse input after takeover, listener loss or a session lock."""
        if self._observed.is_set():
            raise AgentTaskError("human input took back desktop control; explicit resume is required")
        if not self._listener.alive() or not self._interactive():
            raise AgentTaskError("physical activity monitoring or interactive session is unavailable")

    def close(self) -> None:
        """Retire only this gate's listener; native process retirement remains the outer bound."""
        self._listener.stop()
        self._armed = False


def desktop_activity_gate(takeover: Callable[[], None]) -> ActivityGate:
    """Select an explicit platform monitor; unsupported shared desktops cannot acquire input."""
    if sys.platform != "win32":
        raise AgentControlBusy("shared-desktop physical activity monitoring needs a trusted platform adapter")
    from je_auto_control.utils.agent_runtime.activity_windows import windows_gate
    return windows_gate(takeover)
