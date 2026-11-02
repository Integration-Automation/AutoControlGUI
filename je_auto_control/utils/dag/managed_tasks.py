"""Bounded task and artifact transports preserve registered-host authority and completion contracts."""
from __future__ import annotations

import re
import json
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import urlencode, urlsplit
from pathlib import Path

from je_auto_control.utils.admin.admin_client import current_admin_hosts_path
from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.completion_contract import require_completion as _require_completion
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import STATES, thaw, positive
from je_auto_control.utils.dag.batch_contract import host_fingerprint
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint, cancellation_scope
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.run_history.run_outcome import is_run_interruption

Call = Callable[[str, dict[str, Any], float], dict[str, Any]]
_STOP: ContextVar[threading.Event | None] = ContextVar("dag_managed_stop", default=None)
_RUNTIME: ContextVar[tuple[Call, Callable[[], None]] | None] = ContextVar("dag_managed_runtime", default=None)
_ACTIVE = frozenset({"queued", "running", "verifying", "pausing", "cancelling"})


def registered_transfer_private_files() -> tuple[Path, ...]:
    """Expose only the actual host credential book location without loading configuration or tokens."""
    return (current_admin_hosts_path(),)


def registered_transfer_binding(host: str) -> str:
    """Pin the current persisted transfer endpoint and credential without loading or rewriting its book."""
    owner = _transfer_owner(host)
    identity = _registered_transfer_identity(host)
    _authorize(owner, host)
    return host_fingerprint(*identity)


def registered_host_transfer(host: str, binding: str, path: str, body: dict, timeout: float) -> dict:
    """Use only reviewed transfer routes with fresh pre/post host and local authorization checks."""
    if not isinstance(path, str) or path not in {'/agent/transfer', '/agent/transfer/peer'}:
        raise AgentTaskError('unavailable registered transfer route')
    if (not isinstance(body, dict) or set(body) != {'operation', 'request'}
            or not isinstance(body['operation'], str) or not isinstance(body['request'], dict)):
        raise AgentTaskError('invalid registered transfer envelope')
    if not isinstance(binding, str) or re.fullmatch('[0-9a-f]{64}', binding) is None:
        raise AgentTaskError('invalid registered transfer binding')
    positive(timeout, 'transfer timeout', 30)
    deadline = time.monotonic() + timeout
    owner = _transfer_owner(host)
    base, token = _transfer_live(host, binding, owner, deadline)
    result = _remote_json(base + path, body=body, token=token, timeout=deadline - time.monotonic())
    _transfer_live(host, binding, owner, deadline)
    return result


def _transfer_owner(host: str) -> DeferredAuthorization:
    if not isinstance(host, str) or not host or host == 'local':
        raise AgentTaskError('transfer requires an actual registered remote host')
    if current_operation() is not None:
        raise AgentTaskError('a managed task cannot recursively dispatch registered transfers')
    owner = DeferredAuthorization.capture()
    _authorize(owner, host)
    return owner


def _transfer_live(host: str, binding: str, owner: DeferredAuthorization, deadline: float) -> tuple[str, str]:
    _authorize(owner, host)
    identity = _registered_transfer_identity(host)
    if host_fingerprint(*identity) != binding:
        raise AgentTaskError('registered transfer host configuration changed')
    if time.monotonic() >= deadline:
        raise AgentTaskError('registered transfer deadline exhausted')
    return identity


def _registered_transfer_identity(host: str) -> tuple[str, str]:
    try:
        payload = json.loads(current_admin_hosts_path().read_text(encoding='utf-8-sig'))
        entries = payload['hosts']
        if not isinstance(entries, list):
            raise ValueError('invalid host collection')
        matches = [entry for entry in entries if isinstance(entry, dict) and entry.get('label') == host]
        if len(matches) != 1:
            raise ValueError('host must be uniquely registered')
        entry = matches[0]
        if (not {'label', 'base_url', 'token'} <= set(entry)
                or set(entry) - {'label', 'base_url', 'token', 'tags'}):
            raise ValueError('invalid host entry')
        return _validated_host_identity(entry['base_url'], entry['token'])
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise AgentTaskError('current registered transfer host is unavailable') from error


class ManagedTaskDispatchError(AgentTaskError):
    """A failed/uncertain node retains bounded task identity for explicit recovery."""

    def __init__(self, outcome: dict[str, Any]) -> None:
        super().__init__("DAG managed task requires review; no downstream completion was granted")
        self.outcome = outcome


@contextmanager
def managed_runtime_scope(local_call: Call, check: Callable[[], None]) -> Iterator[None]:
    """Bind service-owned local transport and live source authority to copied node contexts."""
    binding = _RUNTIME.set((local_call, check))
    try:
        yield
    finally:
        _RUNTIME.reset(binding)


@contextmanager
def managed_local_scope(local_call: Call) -> Iterator[None]:
    """Override one node's local transport while retaining its enclosing live source checks."""
    runtime = _RUNTIME.get()
    with managed_runtime_scope(local_call, runtime[1] if runtime is not None else cancellation_checkpoint):
        yield


@contextmanager
def managed_stop_scope(event: threading.Event) -> Iterator[None]:
    """Allow running managed nodes to request pause when the DAG is stopped."""
    binding = _STOP.set(event)
    try:
        yield
    finally:
        _STOP.reset(binding)


def run_managed_task(host: str, task: Mapping[str, Any], *, host_binding: str | None = None) -> dict[str, Any]:
    """Submit once and wait for destination verification; never replay or resume actions."""
    if current_operation() is not None:
        raise AgentTaskError("a managed task cannot recursively dispatch another managed task")
    if host != "local" and "origin_policies" in task["spec"]["options"]:
        raise AgentTaskError("local origin witnesses cannot be sent to a remote task host")
    owner = DeferredAuthorization.capture()
    _authorize(owner, host)
    call = _connection(host) if host_binding is None else bound_task_connection(host, host_binding)
    return _TaskWaiter(host, task, call, owner).run()


def _authorize(owner: DeferredAuthorization, host: str) -> None:
    cancellation_checkpoint()
    runtime = _RUNTIME.get()
    if runtime is not None:
        runtime[1]()
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
        runtime = _RUNTIME.get()
        if runtime is not None:
            return runtime[0]
        from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
        client = AgentRuntimeClient()
        return lambda operation, body, timeout: client.call(operation, body, timeout=timeout)
    return bound_task_connection(host, task_host_binding(host))


def task_host_binding(host: str) -> str:
    """Pin one reviewed registered host configuration; local tasks belong to the coordinator runtime."""
    authorize_task_host(DeferredAuthorization.capture(), host)
    if host == "local":
        return "local"
    return host_fingerprint(*_host_identity(host))


def bound_task_connection(host: str, binding: str) -> Call:
    """Pin a registered endpoint and revalidate its current configuration and owner around every call."""
    owner = DeferredAuthorization.capture()
    authorize_task_host(owner, host)
    if host == "local":
        if binding != "local":
            raise AgentTaskError("managed batch host configuration changed")
        return _connection(host)
    base, token = _live_task_host(host, binding, owner)
    remote = _remote_connection(base, token)

    def checked(operation: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        _live_task_host(host, binding, owner)
        result = remote(operation, body, timeout)
        _live_task_host(host, binding, owner)
        return result
    return checked


def _live_task_host(host: str, binding: str, owner: DeferredAuthorization) -> tuple[str, str]:
    _authorize(owner, host)
    base, token = _host_identity(host)
    if host_fingerprint(base, token) != binding:
        raise AgentTaskError("managed batch host configuration changed")
    return base, token


def _remote_connection(base: str, token: str) -> Call:

    def remote(operation: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        if operation == "get":
            return _remote_json(base + "/agent/task?" + urlencode(body), token=token, timeout=timeout)
        if operation not in {"submit", "pause", "lookup"}:
            raise AgentTaskError("unsupported remote DAG task operation")
        return _remote_json(base + "/agent/" + operation, body=body, token=token, timeout=timeout,
                            control=operation == "pause")
    return remote


def _remote_json(url: str, *, body: dict | None = None, token: str, timeout: float, control: bool = False) -> dict:
    from je_auto_control.utils.agent_runtime.transport import request_json
    options: dict[str, Any] = {'body': body, 'token': token, 'timeout': timeout, 'control': control}
    if urlsplit(url).path.endswith(('/agent/transfer', '/agent/transfer/peer')):
        options['delegate_local'] = False
    return request_json(url, **options)


def _host_identity(host: str) -> tuple[str, str]:
    return _registered_transfer_identity(host)


def _validated_host_identity(base: Any, token: Any) -> tuple[str, str]:
    if not isinstance(base, str):
        raise AgentTaskError('invalid registered DAG task host')
    base = base.rstrip('/')
    try:
        parsed = urlsplit(base)
        checks = (parsed.scheme in {"http", "https"}, bool(parsed.hostname), parsed.username is None,
                  parsed.password is None, '?' not in base, '#' not in base, parsed.port != 0)
        if not all(checks):
            raise ValueError("invalid host URL")
    except (TypeError, ValueError):
        raise AgentTaskError("invalid registered DAG task host") from None
    return base, _checked_host_token(token)


def _checked_host_token(token: Any) -> str:
    if not isinstance(token, str) or not token:
        raise AgentTaskError("DAG task host requires a registered token")
    if any(ord(character) < 32 or ord(character) == 127 for character in token):
        raise AgentTaskError('registered host credential contains invalid header characters')
    return token


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
