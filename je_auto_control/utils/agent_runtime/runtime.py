"""Shared managed-task lifecycle with fenced dispatch and evidence-based completion."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import CancelledError
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import (
    AgentActionRequest, AgentActionResult, AgentObservation, AgentTaskHandle, AgentTaskResult,
    AgentTaskSpec, TERMINAL, detached, freeze, thaw,
)
from je_auto_control.utils.agent_runtime.ownership import ControlBroker, ControlLease
from je_auto_control.utils.agent_runtime.policy import TaskPolicy, durable_payload
from je_auto_control.utils.agent_runtime.runtime_lock import RuntimeLock
from je_auto_control.utils.agent_runtime.store import AgentTaskStore
from je_auto_control.utils.agent_runtime.verification import validate_criteria, verify
from je_auto_control.utils.exception.cancellation import CancellationToken, cancellation_scope
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.dispatch import command_guard
from je_auto_control.utils.rbac.authorization import AuthorizationContext, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.script_vars.execution import execution_scope

_ERRORS = (AutoControlException, OSError, RuntimeError, TypeError, ValueError, LookupError)


def _fingerprint(observation: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(detached(observation), sort_keys=True).encode("utf-8")).hexdigest()


def _identity_dict() -> dict[str, Any]:
    identity = current_authorization()
    if identity is None:
        return {}
    return {"user_id": identity.user_id, "role": identity.role, "store_path": identity.store_path}


class AgentRuntime:
    """One owned runtime per database; native targets and all dependencies remain injectable."""

    def __init__(self, path: str | Path, *, targets: Mapping[str, Any] | None = None) -> None:
        self.store = AgentTaskStore(path)
        self._owner_lock = RuntimeLock(str(self.store.path) + ".lock")
        self.broker = ControlBroker(self.store)
        self._targets = dict(targets) if targets is not None else _default_targets()
        self._tokens: dict[str, CancellationToken] = {}
        self._executing: set[str] = set()
        self._stop_final: dict[str, str] = {}
        self._leases: dict[str, ControlLease] = {}
        self._observations: dict[str, AgentObservation] = {}
        self._mutex = threading.RLock()
        self._task_locks: dict[str, Any] = {}
        self._closed = False
        self.background: Any = None
        self.shutdown_requested = threading.Event()
        try:
            self.store.recover()
        except BaseException:  # reason: construction failure must release only the newly owned OS lock
            self._owner_lock.close()
            raise

    def _lock(self, task_id: str) -> Any:
        with self._mutex:
            return self._task_locks.setdefault(task_id, threading.RLock())

    def _row(self, task_id: str) -> dict[str, Any]:
        if self._closed:
            raise AgentTaskError("runtime is closed")
        row = self.store.get(task_id)
        identity = current_authorization()
        owner = row["owner"].get("user_id")
        if identity is not None and identity.role != "admin" and identity.user_id != owner:
            raise AgentTaskError("task does not exist or its owner is another caller")
        return row

    def submit(self, spec: AgentTaskSpec | Mapping[str, Any]) -> AgentTaskHandle:
        """Persist a validated, detached specification without acquiring or operating a target."""
        if self._closed:
            raise AgentTaskError("runtime is closed")
        spec = spec if isinstance(spec, AgentTaskSpec) else AgentTaskSpec.from_dict(spec)
        if spec.target not in self._targets:
            raise AgentTaskError("task target has not been configured")
        TaskPolicy(spec)
        validate_criteria(spec.success_criteria)
        with DeferredAuthorization.capture().scope():
            task_id = self.store.create(durable_payload(spec.to_dict()), _identity_dict())
        return AgentTaskHandle(task_id)

    def get(self, task_id: str) -> AgentTaskResult:
        """Read owner-scoped task status without observing the desktop."""
        row = self._row(task_id)
        return AgentTaskResult(task_id, row["state"], row["spec"]["goal"], row["reason"], row["steps"],
                               tuple(freeze(row["verification"])))

    def list(self, limit: int = 100) -> list[AgentTaskResult]:
        """List only tasks visible to the current principal."""
        identity = current_authorization()
        rows = self.store.list(limit)
        visible = [row for row in rows if identity is None or identity.role == "admin"
                   or row["owner"].get("user_id") == identity.user_id]
        return [self.get(row["id"]) for row in visible]

    def _target(self, row: Mapping[str, Any]) -> Any:
        target = self._targets.get(row["spec"]["target"])
        if target is None:
            raise AgentTaskError("task target is no longer configured")
        return target

    def _token(self, task_id: str) -> CancellationToken:
        with self._mutex:
            return self._tokens.setdefault(task_id, CancellationToken(len(self._tokens) + 1))

    @contextmanager
    def _scope(self, row: Mapping[str, Any]) -> Iterator[TaskPolicy]:
        spec = AgentTaskSpec.from_dict(row["spec"])
        owner = AuthorizationContext(**row["owner"]) if row["owner"] else None
        policy = TaskPolicy(spec)

        def guard(name: str, arguments: Any) -> None:
            self._check_budget(row["id"])
            policy.check(name, arguments)
            lease = self._leases.get(row["id"])
            if lease is not None:
                self.broker.validate(lease)

        with DeferredAuthorization(owner).scope(), cancellation_scope(self._token(row["id"])):
            with command_guard(guard), execution_scope(thaw(spec.inputs)):
                yield policy

    def _check_budget(self, task_id: str) -> None:
        row = self._row(task_id)
        limits = row["spec"]["budget"]
        if row["started"] is not None and time.time() - row["started"] >= limits["wall_seconds"]:
            self._budget_failure(task_id, "task wall budget exhausted", "timed_out")

    def _budget_failure(self, task_id: str, reason: str, state: str) -> None:
        self._request_stop(task_id, "cancelling", state)
        raise AgentTaskError(reason)

    def _activate(self, row: dict[str, Any]) -> dict[str, Any]:
        if row["state"] not in {"queued", "running", "verifying"}:
            raise AgentTaskError(f"task cannot operate while {row['state']}")
        self._check_budget(row["id"])
        spec = AgentTaskSpec.from_dict(row["spec"])
        ready, reason = self._target(row).ready(spec)
        if not ready:
            raise AgentTaskError(reason or "target is not ready")
        self._token(row["id"]).checkpoint()
        if row["id"] not in self._leases:
            lease = self.broker.acquire(spec.target, row["id"])
            with self._mutex:
                self._leases[row["id"]] = lease
        try:
            self._token(row["id"]).checkpoint()
            self.store.start(row["id"])
        except (CancelledError, AgentTaskError):
            self._retire(row["id"])
            raise
        return self._row(row["id"])

    def observe(self, task_id: str) -> AgentObservation:
        """Capture fresh target state only after authority and ownership checks."""
        with self._lock(task_id):
            row = self._row(task_id)
            with self._scope(row):
                row = self._activate(row)
                try:
                    with self.broker.dispatch(self._leases[task_id]):
                        data = detached(self._target(row).observe())
                        self._token(task_id).checkpoint()
                    observation = AgentObservation(uuid.uuid4().hex, task_id, time.time(), freeze(data))
                    self._observations[task_id] = observation
                    return observation
                finally:
                    self._settle_control(task_id)

    def _ground(self, row: Mapping[str, Any], request: AgentActionRequest) -> None:
        observation = self._observations.get(row["id"])
        if observation is None or request.observation_id != observation.observation_id:
            raise AgentTaskError("observation is missing or no longer current")
        if time.time() - observation.captured_at > 30:
            raise AgentTaskError("observation has expired")
        current = self._target(row).observe()
        if _fingerprint(current) != _fingerprint(observation.data):
            self._observations.pop(row["id"], None)
            raise AgentTaskError("observation changed; observe again before acting")

    def act(self, task_id: str, value: Mapping[str, Any]) -> AgentActionResult:
        """Execute one grounded, authorized action and persist its result certainty."""
        request = AgentActionRequest.from_dict(value)
        with self._lock(task_id):
            row = self._row(task_id)
            with self._scope(row) as policy:
                row = self._activate(row)
                policy.check(request.tool, request.arguments)
                if row["steps"] >= row["spec"]["budget"]["max_steps"]:
                    self._budget_failure(task_id, "task step budget exhausted", "failed")
                with self.broker.dispatch(self._leases[task_id]):
                    self._ground(row, request)
                    return self._perform(row, request)

    def _perform(self, row: Mapping[str, Any], request: AgentActionRequest) -> AgentActionResult:
        task_id = row["id"]
        self._observations.pop(task_id, None)
        arguments = thaw(request.arguments)
        action_id = self.store.prepare(task_id, request.tool, durable_payload(arguments))
        self._executing.add(task_id)
        try:
            self._token(task_id).checkpoint()
            self.store.settle(action_id, "dispatched")
            result = self._target(row).perform(request.tool, arguments)
            result = durable_payload(result)
            self.store.settle(action_id, "confirmed", result)
            return AgentActionResult(action_id, freeze(result))
        except (CancelledError, *_ERRORS) as error:
            self.store.settle(action_id, "uncertain", {"error": type(error).__name__})
            if not self._token(task_id).is_cancelled:
                self.store.update(task_id, "waiting_user", reason="action outcome requires review")
            raise
        finally:
            self._executing.discard(task_id)
            self._settle_control(task_id)

    def finish(self, task_id: str) -> AgentTaskResult:
        """Verify every completion condition; a model's stop message is never success evidence."""
        with self._lock(task_id):
            row = self._row(task_id)
            if row["state"] in TERMINAL:
                return self.get(task_id)
            with self._scope(row) as policy:
                row = self._activate(row)
                try:
                    self.store.update(task_id, "verifying")
                    with self.broker.dispatch(self._leases[task_id]):
                        observations = detached(self._target(row).observe())
                        receipts = self.store.actions(task_id)
                        reports = verify(policy, receipts, observations)
                    self._token(task_id).checkpoint()
                    complete = all(item["status"] == "passed" for item in reports)
                    uncertain = any(item["status"] == "uncertain" for item in receipts)
                    state = "succeeded" if complete and not uncertain else "waiting_user"
                    self.store.update(task_id, state, reason="" if state == "succeeded" else "completion not proven",
                                      verification=reports)
                    self._retire(task_id)
                    return self.get(task_id)
                finally:
                    self._settle_control(task_id)

    def pause(self, task_id: str) -> AgentTaskResult:
        """Request pause immediately; transfer control only after active input retires."""
        return self._request_stop(task_id, "pausing", "paused")

    def cancel(self, task_id: str) -> AgentTaskResult:
        """Request cancellation without closing another worker's native resources."""
        return self._request_stop(task_id, "cancelling", "cancelled")

    def _request_stop(self, task_id: str, pending: str, settled: str) -> AgentTaskResult:
        row = self._row(task_id)
        if row["state"] in TERMINAL:
            self._retire(task_id)
            return self.get(task_id)
        self._stop_final[task_id] = settled
        self._token(task_id).cancel()
        self.store.update(task_id, pending)
        if task_id not in self._executing and self._retire(task_id):
            self.store.update(task_id, settled)
        return self.get(task_id)

    def _settle_control(self, task_id: str) -> None:
        state = self._row(task_id)["state"]
        stops = {"pausing": "paused", "cancelling": "cancelled"}
        if state in stops and self._retire(task_id):
            self.store.update(task_id, self._stop_final.get(task_id, stops[state]))
        elif state in TERMINAL or state == "waiting_user":
            self._retire(task_id)

    def _retire(self, task_id: str) -> bool:
        self._observations.pop(task_id, None)
        lease = self._leases.get(task_id)
        if lease is None:
            return True
        row = self.store.get(task_id)
        if not self.broker.release(lease, self._target(row).cleanup):
            return False
        with self._mutex:
            self._leases.pop(task_id, None)
        return True

    def resume(self, task_id: str) -> AgentTaskResult:
        """Reauthorize a paused task; a fresh observation is required before any action."""
        with self._lock(task_id):
            row = self._row(task_id)
            if row["state"] not in {"paused", "waiting_user", "recovering"}:
                raise AgentTaskError("task is not ready to resume")
            if any(action["status"] == "uncertain" for action in self.store.actions(task_id)):
                raise AgentTaskError("uncertain actions require reconciliation before resume")
            owner = AuthorizationContext(**row["owner"]) if row["owner"] else None
            with DeferredAuthorization(owner).scope():
                self._tokens.pop(task_id, None)
                self._stop_final.pop(task_id, None)
                self._observations.pop(task_id, None)
                self.store.update(task_id, "queued")
            return self.get(task_id)

    def close(self) -> None:
        """Retire owned input before releasing the service lock; live tasks remain recoverable."""
        if self._closed:
            return
        for task_id in list(self._leases):
            self._token(task_id).cancel()
            if not self._retire(task_id):
                raise AgentTaskError("runtime still has active input or cleanup")
        self._closed = True
        self._owner_lock.close()

    def request_shutdown(self) -> dict[str, Any]:
        """Stop only after every active input owner has completed cancellation and cleanup."""
        identity = current_authorization()
        if identity is not None and identity.role != "admin":
            raise AgentTaskError("runtime shutdown requires host management")
        for task_id in list(self._leases):
            self.cancel(task_id)
        if self._leases:
            raise AgentTaskError("runtime still has active input or cleanup")
        self.shutdown_requested.set()
        return {"stopping": True}


def _default_targets() -> dict[str, Any]:
    from je_auto_control.utils.agent_runtime.targets import DesktopTarget
    return {"local-desktop": DesktopTarget()}
