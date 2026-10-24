"""Bounded task transport and coordination with verified remote completion."""
from __future__ import annotations

import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import urlencode, urlsplit

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import STATES, thaw
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint, cancellation_scope
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.run_history.run_outcome import is_run_interruption

Call = Callable[[str, dict[str, Any], float], dict[str, Any]]
_STOP: ContextVar[threading.Event | None] = ContextVar("dag_managed_stop", default=None)
_ACTIVE = frozenset({"queued", "running", "verifying", "pausing", "cancelling"})


class ManagedTaskDispatchError(AgentTaskError):
    """A failed/uncertain node retains bounded task identity for explicit recovery."""

    def __init__(self, outcome: dict[str, Any]) -> None:
        super().__init__("DAG managed task requires review; no downstream completion was granted")
        self.outcome = outcome


@contextmanager
def managed_stop_scope(event: threading.Event) -> Iterator[None]:
    """Allow running managed nodes to request pause when the DAG is stopped."""
    binding = _STOP.set(event)
    try:
        yield
    finally:
        _STOP.reset(binding)


def run_managed_task(host: str, task: Mapping[str, Any]) -> dict[str, Any]:
    """Submit once and wait for destination verification; never replay or resume actions."""
    if current_operation() is not None:
        raise AgentTaskError("a managed task cannot recursively dispatch another managed task")
    if host != "local" and "origin_policies" in task["spec"]["options"]:
        raise AgentTaskError("local origin witnesses cannot be sent to a remote task host")
    owner = DeferredAuthorization.capture()
    _authorize(owner, host)
    call = _connection(host)
    return _TaskWaiter(host, task, call, owner).run()


def _authorize(owner: DeferredAuthorization, host: str) -> None:
    cancellation_checkpoint()
    with owner.scope():
        if host != "local":
            authorize_command("AC_admin_broadcast_execute")


def authorize_task_host(owner: DeferredAuthorization, host: str) -> None:
    """Share live owner/host checks with read-only DAG inspection."""
    _authorize(owner, host)


def task_stop_requested() -> bool:
    """Read the owned DAG stop event without exposing its context binding."""
    stop = _STOP.get()
    return stop is not None and stop.is_set()


def task_connection(host: str) -> Call:
    """Share the closed local/registered-host transport without exposing credentials."""
    authorize_task_host(DeferredAuthorization.capture(), host)
    return _connection(host)


def _connection(host: str) -> Call:
    if host == "local":
        from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
        client = AgentRuntimeClient()
        return lambda operation, body, timeout: client.call(operation, body, timeout=timeout)
    base, token = _host_identity(host)

    def remote(operation: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        from je_auto_control.utils.agent_runtime.transport import request_json
        if operation == "get":
            return request_json(base + "/agent/task?" + urlencode(body), token=token, timeout=timeout)
        if operation not in {"submit", "pause", "lookup"}:
            raise AgentTaskError("unsupported remote DAG task operation")
        return request_json(base + "/agent/" + operation, body=body, token=token, timeout=timeout,
                            control=operation == "pause")
    return remote


def _host_identity(host: str) -> tuple[str, str]:
    from je_auto_control.utils.admin.admin_client import default_admin_console
    matches = [entry for entry in default_admin_console().list_hosts() if entry.label == host]
    if len(matches) != 1:
        raise AgentTaskError("DAG task host is not registered uniquely")
    base, token = matches[0].base_url.rstrip("/"), matches[0].token
    try:
        parsed = urlsplit(base)
        checks = (parsed.scheme in {"http", "https"}, bool(parsed.hostname), parsed.username is None,
                  parsed.password is None, not parsed.query, not parsed.fragment, parsed.port != 0)
        if not all(checks):
            raise ValueError("invalid host URL")
    except (TypeError, ValueError):
        raise AgentTaskError("invalid registered DAG task host") from None
    if not isinstance(token, str) or not token:
        raise AgentTaskError("DAG task host requires a registered token")
    return base, token


class _TaskWaiter:
    """One bounded coordinator; the destination runtime owns effects and resource exclusion."""

    def __init__(self, host: str, task: Mapping[str, Any], call: Call, owner: DeferredAuthorization) -> None:
        self.host, self.task, self.call, self.owner = host, task, call, owner
        self.task_id: str | None = None
        self.last: dict[str, Any] = {}
        self.deadline = time.monotonic() + task["wait_seconds"]

    def run(self) -> dict[str, Any]:
        """Coordinate one task and retain uncertainty when acknowledgement is incomplete."""
        try:
            self._checkpoint()
            reply = self.call("submit", {"spec": thaw(self.task["spec"]),
                                         "idempotency_key": self.task["idempotency_key"]}, self._timeout())
            identifier = reply.get("task_id")
            if not isinstance(identifier, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,256}", identifier) is None:
                raise AgentTaskError("invalid task acknowledgement")
            self.task_id = identifier
            return self._wait()
        except BaseException as error:  # reason: request bounded owned pause; preserve cancellation and hard exits
            self._pause()
            if not isinstance(error, Exception) or is_run_interruption(error):
                raise
            raise ManagedTaskDispatchError(self._summary("requires_review" if self.task_id else "unknown")) from None

    def _timeout(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTaskError("DAG task wait budget exhausted")
        return min(5, remaining)

    def _checkpoint(self) -> None:
        _authorize(self.owner, self.host)
        if task_stop_requested():
            raise AgentTaskError("DAG stopped; managed task requires explicit recovery")
        self._timeout()

    def _wait(self) -> dict[str, Any]:
        while True:
            self._checkpoint()
            reply = self.call("get", {"task_id": self.task_id}, self._timeout())
            if reply.get("task_id") != self.task_id or reply.get("state") not in STATES:
                raise AgentTaskError("invalid task status identity")
            self.last = reply
            if reply["state"] == "succeeded":
                _require_completion(reply, self.task["spec"])
                self._checkpoint()
                return self._summary("completed")
            if reply["state"] not in _ACTIVE:
                raise AgentTaskError("managed task is not progressing autonomously")
            threading.Event().wait(min(0.1, self._timeout()))

    def _pause(self) -> None:
        if self.task_id is None:
            return
        try:
            with cancellation_scope(None):
                reply = self.call("pause", {"task_id": self.task_id}, 5)
            if reply.get("task_id") == self.task_id and reply.get("state") in STATES:
                self.last = reply
        except BaseException as error:  # reason: cleanup cannot replace an original failure or claim remote retirement
            if not isinstance(error, Exception) or is_run_interruption(error):
                raise

    def _summary(self, outcome: str) -> dict[str, Any]:
        metadata = self.last.get("metadata", {})
        released = metadata.get("input_released") if isinstance(metadata, dict) else None
        state = self.last.get("state")
        return {"outcome": outcome, "task_id": self.task_id, "idempotency_key": self.task["idempotency_key"],
                "task_state": state if isinstance(state, str) and state in STATES else "unknown",
                "input_released": released if type(released) is bool else None}


def validate_recorded_completion(reply: dict[str, Any], spec: Mapping[str, Any]) -> None:
    """Require succeeded state and exact independent completion/retirement evidence."""
    if reply.get("state") != "succeeded":
        raise AgentTaskError("recorded task has not succeeded")
    _require_completion(reply, spec)


def _require_completion(reply: dict[str, Any], spec: Mapping[str, Any]) -> None:
    metadata, reports = reply.get("metadata"), reply.get("verification")
    if not isinstance(metadata, dict) or not isinstance(reports, list):
        raise AgentTaskError("completion evidence is missing")
    version = metadata.get("completion_contract")
    if type(version) is not int or version != 1 or metadata.get("input_released") is not True:
        raise AgentTaskError("completion retirement contract is unconfirmed")
    criteria = spec["success_criteria"]
    if len(reports) != len(criteria):
        raise AgentTaskError("completion criteria count changed")
    for report, clause in zip(reports, criteria):
        _require_clause(report, clause)


def _require_clause(report: Any, clause: Mapping[str, Any]) -> None:
    if not isinstance(report, dict) or report.get("kind") != clause["kind"] or report.get("status") != "passed":
        raise AgentTaskError("completion criteria were not independently confirmed")
