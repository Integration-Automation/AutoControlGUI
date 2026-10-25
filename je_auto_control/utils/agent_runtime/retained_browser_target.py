"""Closed transient read borrowers; the runtime collection owns the original helper lifetime."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from je_auto_control.utils.agent_runtime.browser_retirement import retirement_proof, refuse_browser_input
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.retained_browser import RetainedBrowser, RetainedBrowsers


class RetainedBrowserTarget:
    """Read only the private effect binding's real original context, never a new helper or page."""

    def __init__(self, pool: RetainedBrowsers, source: Mapping, spec: Any,
                 current_source: Callable[[], dict], current_operation: Callable[[], Any]) -> None:
        self._pool, self._source, self._spec = pool, deepcopy(dict(source)), spec
        self._current_source = current_source
        self._current_operation = current_operation
        self._entry: RetainedBrowser | None = None
        self._operation: Any = None

    def ready(self, spec: Any) -> tuple[bool, str]:
        """Borrow the exact existing context under the current task; no configure/startup is allowed."""
        operation = self._current_operation()
        if spec != self._spec or operation is None or operation.spec != spec:
            raise AgentTaskError("retained browser reader requires its exact task scope")
        self._operation = operation
        operation.checkpoint()
        source = self._current_source()
        if self._entry is None:
            self._entry = self._pool.borrow(source)
        try:
            capabilities = self._capabilities()
            bound = self._request("bind_browser_reader", {"spec": self._spec.to_dict()})
            retirement_proof(bound, capabilities["context_id"])
        except BaseException:  # reason: failed or cancelled readiness must release its transient read borrow
            self._fail()
            raise
        return True, ""

    def _check(self) -> None:
        operation, entry = self._operation, self._entry
        if operation is None or self._current_operation() is not operation or entry is None:
            raise AgentTaskError("retained browser reader has no current scoped borrow")
        operation.checkpoint()
        if self._pool.require(self._current_source()) is not entry:
            raise AgentTaskError("retained browser context is unavailable")

    def _request(self, operation: str, payload: dict) -> Any:
        self._check()
        if self._entry is None:
            raise AgentTaskError("retained browser reader is unavailable")
        result = self._entry.channel.request(operation, payload, timeout=self._spec.budget.action_seconds,
                                             check=self._check, on_event=refuse_browser_input)
        self._check()
        return result

    def _capabilities(self) -> dict:
        if self._entry is None or self._entry.proof is None:
            raise AgentTaskError("retained browser context is unavailable")
        return retirement_proof(self._request("readonly_capabilities", {}), self._entry.proof["context_id"])

    def _call(self, operation: str, payload: dict) -> Any:
        try:
            self._capabilities()
            result = self._request(operation, payload)
            self._capabilities()
            return result
        except BaseException:  # reason: cancellation/failure permanently invalidates this context, never retries reads
            self._fail()
            raise

    def _fail(self) -> None:
        try:
            self._pool.discard(self._source["id"])
        finally:
            self.cleanup()

    def observe(self) -> dict:
        """Return fresh scoped DOM observation from the retained original SDK page."""
        return self._call("observe", {})

    def verify_browser(self, clause: Mapping) -> Any:
        """Read only this task's unchanged pinned independent browser criterion."""
        if clause not in self._spec.success_criteria:
            raise AgentTaskError("browser criterion is not pinned to this read-only task")
        return self._call("verify_browser", {"clause": dict(clause)})

    def perform(self, _name: str, _arguments: dict) -> Any:
        """Read borrowers cannot execute tools or reuse the ordinary target."""
        raise AgentTaskError("read-only browser cannot perform tools")

    def cleanup(self) -> None:
        """Release only this transient borrow; original process lifetime stays with its collection."""
        if self._entry is not None:
            self._pool.release(self._entry)
        self._entry = self._operation = None
