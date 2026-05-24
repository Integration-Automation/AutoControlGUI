"""Manager that fans a :class:`FailureReport` out to every registered backend."""
from __future__ import annotations

import threading
from typing import Any, Dict, List

from je_auto_control.utils.failure_hooks.backends import TicketBackend
from je_auto_control.utils.failure_hooks.report import (
    FailureReport, TicketResult,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


class FailureHookManager:
    """Thread-safe registry + fan-out for ticket backends."""

    def __init__(self) -> None:
        self._backends: List[TicketBackend] = []
        self._lock = threading.RLock()
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self, value: bool = True) -> None:
        self._enabled = bool(value)

    def register(self, backend: TicketBackend) -> None:
        if not hasattr(backend, "name") or not hasattr(backend, "create_issue"):
            raise TypeError(
                "backend must expose ``name`` and ``create_issue``",
            )
        with self._lock:
            self._backends.append(backend)

    def unregister(self, backend_name: str) -> bool:
        with self._lock:
            before = len(self._backends)
            self._backends = [b for b in self._backends
                               if getattr(b, "name", None) != backend_name]
            return len(self._backends) != before

    def list_backends(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{"name": getattr(b, "name", repr(b)),
                     "type": type(b).__name__}
                    for b in self._backends]

    def clear(self) -> None:
        with self._lock:
            self._backends.clear()

    def fire(self, report: FailureReport) -> List[TicketResult]:
        if not self._enabled:
            return []
        with self._lock:
            targets = list(self._backends)
        results: List[TicketResult] = []
        for backend in targets:
            results.append(self._invoke(backend, report))
        return results

    def _invoke(self, backend: TicketBackend,
                 report: FailureReport) -> TicketResult:
        name = getattr(backend, "name", type(backend).__name__)
        try:
            return backend.create_issue(report)
        except (RuntimeError, OSError, ValueError) as error:
            autocontrol_logger.warning(
                "failure-hook backend %r raised: %r", name, error,
            )
            return TicketResult(
                backend=name, succeeded=False,
                error=f"{type(error).__name__}: {error}",
            )


default_failure_hook_manager = FailureHookManager()


__all__ = ["FailureHookManager", "default_failure_hook_manager"]
