"""Generation-bound negative-only takeover notices with retained coarse cleanup failure diagnostics."""
from __future__ import annotations

import sqlite3
import threading
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.exception.exceptions import AutoControlException


class NativeControl:
    """One input helper's host callback; no old helper can select a newer task's callback."""

    def __init__(self, takeover: Callable[[], None] | None) -> None:
        self._takeover = takeover
        self._channel: Any = None
        self._sent = False
        self._error: str | None = None
        self._mutex = threading.Lock()

    def bind(self, channel: Any) -> None:
        """Bind the actual owned channel object after its bootstrap, never a supplied PID/generation."""
        with self._mutex:
            if self._channel is not None:
                raise AgentTaskError('native takeover notice already has an owner')
            self._channel = channel

    def notify(self, kind: str, current: Any) -> None:
        """Stop only the bound input lifetime, without joining from its IPC reader thread."""
        if kind != 'physical_input':
            raise AgentTaskError('unexpected native takeover notice')
        with self._mutex:
            if self._takeover is None or self._channel is None or current is not self._channel or self._sent:
                return
            self._sent = True
            try:
                threading.Thread(target=self._run, name='AgentTakeover', daemon=True).start()
            except (RuntimeError, OSError) as error:
                self._error = type(error).__name__
                raise AgentTaskError('native takeover notice thread could not start') from error

    def _run(self) -> None:
        try:
            if self._takeover is not None:
                self._takeover()
        except (AutoControlException, OSError, RuntimeError, ValueError, TypeError, sqlite3.Error) as error:
            # The runtime's durable control/journal state retains input ownership for an explicit retry.
            with self._mutex:
                self._error = type(error).__name__

    def status(self) -> dict:
        """Expose only a coarse error class; a notification never proves successful input cleanup."""
        with self._mutex:
            return {'notice': 'requested' if self._sent else 'not_requested', 'cleanup_error': self._error}
