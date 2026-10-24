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
from typing import Any, Iterator, Mapping, List

from je_auto_control.utils.agent_runtime.errors import AgentTaskError, AgentObservationStale, AgentHumanReview
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.models import (
    AgentActionRequest, AgentActionResult, AgentObservation, AgentTaskHandle, AgentTaskResult,
    AgentTaskSpec, TERMINAL, detached, freeze, thaw,
)
from je_auto_control.utils.agent_runtime.ownership import ControlBroker, ControlLease
from je_auto_control.utils.agent_runtime.policy import (
    TaskPolicy, durable_payload, canonical_spec, owns_task, validate_root_snapshot,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.agent_runtime.runtime_lock import RuntimeLock
from je_auto_control.utils.agent_runtime.budget_clock import BudgetClock
from je_auto_control.utils.agent_runtime.evidence import TaskEvidence
from je_auto_control.utils.agent_runtime.receipts import reconcile, row_report
from je_auto_control.utils.agent_runtime.task_triggers import AgentTriggers
from je_auto_control.utils.agent_runtime.task_skills import AgentSkills
from je_auto_control.utils.agent_runtime.task_recovery import AgentRecovery, recovery_link, require_no_successor
from je_auto_control.utils.agent_runtime.origin_policy import bind_origin, validate_origins
from je_auto_control.utils.agent_runtime.store import AgentTaskStore, request_spec_digest
from je_auto_control.utils.agent_runtime.verification import validate_criteria, verify
from je_auto_control.utils.exception.cancellation import CancellationToken, cancellation_scope
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.dispatch import command_guard
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, current_authorization
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
        self.clock = BudgetClock(self.store)
        self.evidence = TaskEvidence(self.store)
        self.triggers = AgentTriggers(self)
        self.skills = AgentSkills(self)
        self._targets = dict(targets) if targets is not None else _default_targets()
        self._tokens: dict[str, CancellationToken] = {}
        self._executing: set[str] = set()
        self._stop_final: dict[str, str] = {}
        self._leases: dict[str, ControlLease] = {}
        self._observations: dict[str, AgentObservation] = {}
        self._observation_times: dict[str, float] = {}
        self._mutex = threading.RLock()
        self._task_locks: dict[str, Any] = {}
        self._closed = False
        self.background: Any = None
        self.shutdown_requested = threading.Event()
        self._next_retention = 0.0
        try:
            from je_auto_control.utils.agent_runtime.target_profiles import AgentTargetProfiles
            self.target_profiles = AgentTargetProfiles(self)
            self.store.recover()
        except BaseException:  # reason: construction failure must release only the newly owned OS lock
            self._owner_lock.close()
            raise

    def _lock(self, task_id: str) -> Any:
        with self._mutex:
            return self._task_locks.setdefault(task_id, threading.RLock())

    @property
    def recovery(self) -> AgentRecovery:
        """Use a stateless recovery collaborator over this runtime's durable task evidence."""
        return AgentRecovery(self)

    def _row(self, task_id: str) -> dict[str, Any]:
        if self._closed:
            raise AgentTaskError("runtime is closed")
        row = self.store.get(task_id)
        identity = current_authorization()
        if not owns_task(row["owner"], identity):
            raise AgentTaskError("task does not exist or its owner is another caller")
        return row

    def _validated_spec(self, spec: AgentTaskSpec | Mapping[str, Any]) -> AgentTaskSpec:
        spec = spec if isinstance(spec, AgentTaskSpec) else AgentTaskSpec.from_dict(spec)
        spec = canonical_spec(spec)
        spec = bind_origin(spec)
        if spec.target not in self._targets:
            raise AgentTaskError("task target has not been configured")
        spec = self.target_profiles.bind(spec)
        TaskPolicy(spec)
        validate_criteria(spec.success_criteria)
        return spec

    def submit(self, spec: AgentTaskSpec | Mapping[str, Any], *,
               idempotency_key: str | None = None) -> AgentTaskHandle:
        """Persist a validated, detached specification without acquiring or operating a target."""
        if self._closed:
            raise AgentTaskError("runtime is closed")
        spec = self._validated_spec(spec)
        return self._create_task(spec, idempotency_key)

    def _create_task(self, spec: AgentTaskSpec, key: str | None,
                     event: tuple[str, str, str] | None = None,
                     recovery: tuple[str, str, str] | None = None) -> AgentTaskHandle:
        with DeferredAuthorization.capture().scope():
            task_id = self.store.create(durable_payload(spec.to_dict()), _identity_dict(),
                                        idempotency_key=key, trigger_event=event, recovery=recovery)
        self.evidence.ensure(task_id)
        return AgentTaskHandle(task_id, self.store.get(task_id)["state"])

    def lookup(self, idempotency_key: str, spec: AgentTaskSpec | Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Inspect this principal's accepted request without acquiring input or dispatching work."""
        with DeferredAuthorization.capture().scope():
            expected = None
            if spec is not None:
                expected = spec if isinstance(spec, AgentTaskSpec) else AgentTaskSpec.from_dict(spec)
            record = self.store.request_record(_identity_dict(), idempotency_key)
            task = self.get(record["task_id"]).to_dict() if record is not None else None
            result: dict[str, Any] = {"found": task is not None, "task": task, "spec_match_contract": 1}
            if expected is not None:
                result["spec_match"] = self._request_match(record, expected)
            return result

    def _request_match(self, record: dict[str, Any] | None, spec: AgentTaskSpec) -> str:
        if record is None:
            return "not_found"
        try:
            expected = self._validated_spec(spec)
            digest = request_spec_digest(expected.to_dict())
        except AuthorizationError:
            raise
        except (AgentTaskError, OSError, ValueError):
            return "unverifiable"
        return "matches" if digest == record["spec_hash"] else "differs"

    def get(self, task_id: str) -> AgentTaskResult:
        """Read owner-scoped task status without observing the desktop."""
        row = self._row(task_id)
        metadata = self.evidence.metadata(task_id)
        with self._mutex:
            metadata["input_released"] = task_id not in self._leases
        metadata["target"] = row["spec"]["target"]
        link = recovery_link(self.store, task_id)
        if link:
            metadata["recovery"] = link
        if "target_profile" in row["spec"]["options"]:
            metadata["target_profile"] = thaw(row["spec"]["options"]["target_profile"])
        pin = self.skills.task_pin(row) if "skill_pin" in row["spec"]["options"] else {}
        if pin:
            metadata["skill_pin"] = pin
        return AgentTaskResult(task_id, row["state"], row["spec"]["goal"], row["reason"], row["steps"],
                               tuple(freeze(row["verification"])), freeze(metadata))

    def receipts(self, task_id: str, offset: int = 0, limit: int = 100) -> dict[str, Any]:
        """Inspect owner-scoped receipts, immutable reviews and per-row completion status."""
        row = self._row(task_id)
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise AgentTaskError("receipt offset must be a nonnegative integer")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise AgentTaskError("receipt limit must be between one and two hundred")
        actions = self.store.actions(task_id)
        with self.store.connection() as connection:
            reviews = [dict(item) for item in connection.execute("SELECT * FROM agent_reviews WHERE task_id=?",
                                                                 (task_id,))]
        return {"task_id": task_id, "actions": actions[offset:offset + limit], "total": len(actions),
                "offset": offset, "reviews": reviews[-200:],
                "rows": row_report(AgentTaskSpec.from_dict(row["spec"]), actions)}

    def reconcile(self, task_id: str, review: Mapping[str, Any]) -> AgentTaskResult:
        """Record an explicit owner's witness for one uncertain attempt; resume remains a separate action."""
        with self._lock(task_id):
            row = self._row(task_id)
            if row["state"] not in {"waiting_user", "recovering", "paused", "cancelled", "timed_out", "failed"} or (
                    task_id in self._leases):
                raise AgentTaskError("reconciliation requires a stopped task with no active input owner")
            with DeferredAuthorization.capture().scope():
                reconcile(self.store, task_id, review)
            receipt = next(item for item in self.store.actions(task_id) if item["id"] == review["action_id"])
            self.evidence.action(task_id, receipt, finished=True)
            self.evidence.publish(task_id)
            return self.get(task_id)

    def list(self, limit: int = 100) -> list[AgentTaskResult]:
        """List only tasks visible to the current principal."""
        identity = current_authorization()
        rows = self.store.list(limit)
        visible = [row for row in rows if owns_task(row["owner"], identity)]
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
        try:
            self.target_profiles.check(spec)
            policy = TaskPolicy(spec)
        except AgentTaskError as error:
            paused = self.pause(row["id"])
            if paused.state == "paused":
                self.store.update(row["id"], "paused", reason=f"task scope requires review: {error}")
            raise

        def checkpoint() -> None:
            self._token(row["id"]).checkpoint()
            self._check_budget(row["id"])
            policy.validate_snapshot()
            self.target_profiles.check(spec)
            with DeferredAuthorization(owner).scope():
                pass

        def guard(name: str, arguments: Any) -> None:
            self._check_budget(row["id"])
            self.target_profiles.check(spec)
            policy.check(name, arguments)
            lease = self._leases.get(row["id"])
            if lease is not None:
                self.broker.validate(lease)

        def takeover() -> None:
            self.pause(row["id"])

        task_id = row["id"]
        with self._mutex:
            self._executing.add(task_id)
        try:
            with DeferredAuthorization(owner).scope(), cancellation_scope(self._token(task_id)):
                with (command_guard(guard), execution_scope(thaw(spec.inputs)),
                      operation_scope(TaskOperation(spec, checkpoint, current_authorization(), takeover))):
                    yield policy
        except AuthorizationError:
            self.cancel(task_id)
            raise
        except AgentHumanReview as error:
            state = self.store.get(task_id)["state"]
            if state not in TERMINAL and state not in {"pausing", "cancelling"}:
                self.store.update(task_id, "waiting_user", reason=str(error))
            raise
        finally:
            with self._mutex:
                self._executing.discard(task_id)
            self._settle_control(task_id)

    def _check_budget(self, task_id: str) -> None:
        row = self._row(task_id)
        if self.clock.remaining(row) <= 0:
            self._budget_failure(task_id, "task wall budget exhausted", "timed_out")

    def _budget_failure(self, task_id: str, reason: str, state: str) -> None:
        self._request_stop(task_id, "cancelling", state)
        raise AgentTaskError(reason)

    def _activate(self, row: dict[str, Any]) -> dict[str, Any]:
        if row["state"] not in {"queued", "running", "verifying"}:
            raise AgentTaskError(f"task cannot operate while {row['state']}")
        self._check_budget(row["id"])
        spec = AgentTaskSpec.from_dict(row["spec"])
        self._token(row["id"]).checkpoint()
        check_resume = getattr(self._target(row), "check_resume", None)
        if callable(check_resume):
            check_resume(spec, self.store.actions(row["id"]))
        if row["id"] not in self._leases:
            lease = self.broker.acquire(spec.target, row["id"])
            with self._mutex:
                self._leases[row["id"]] = lease
        try:
            self._token(row["id"]).checkpoint()
            with self.broker.dispatch(self._leases[row["id"]]):
                ready, reason = self._target(row).ready(spec)
            if not ready:
                raise AgentTaskError(reason or "target is not ready")
            self.store.start(row["id"])
            self._check_budget(row["id"])
        except (CancelledError, *_ERRORS):
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
                    self._observation_times[task_id] = time.monotonic()
                    if row["spec"]["options"].get("persist_images") and data.get("image"):
                        self.evidence.image(task_id, observation.observation_id, data["image"])
                    return observation
                finally:
                    self._settle_control(task_id)

    def _ground(self, row: Mapping[str, Any], request: AgentActionRequest) -> None:
        observation = self._observations.get(row["id"])
        if observation is None or request.observation_id != observation.observation_id:
            raise AgentObservationStale("observation is missing or no longer current")
        age = time.monotonic() - self._observation_times.get(row["id"], float("-inf"))
        if not 0 <= age <= 30 or time.time() - observation.captured_at > 30:
            raise AgentObservationStale("observation has expired")
        current = self._target(row).observe()
        if _fingerprint(current) != _fingerprint(observation.data):
            self._observations.pop(row["id"], None)
            raise AgentObservationStale("observation changed; observe again before acting")

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
        from je_auto_control.utils.agent_runtime.observation_refs import resolve_action
        observation = self._observations[task_id]
        arguments, grounding = resolve_action(request.tool, request.arguments, request.reference, observation.data)
        TaskPolicy(AgentTaskSpec.from_dict(row["spec"])).check(request.tool, arguments)
        grounding.update(observation_id=observation.observation_id, fingerprint=_fingerprint(observation.data))
        self._observations.pop(task_id, None)
        self._observation_times.pop(task_id, None)
        action_id = self.store.prepare(task_id, request.tool, durable_payload(arguments),
                                       grounding=durable_payload(grounding))
        try:
            self._token(task_id).checkpoint()
            self.evidence.action(task_id, self.store.actions(task_id)[-1])
            self.store.settle(action_id, "dispatched")
            result = self._target(row).perform(request.tool, arguments)
            result = durable_payload(result)
            self.store.settle(action_id, "confirmed", result)
            self.evidence.action(task_id, self.store.actions(task_id)[-1], finished=True)
            return AgentActionResult(action_id, freeze(result))
        except (CancelledError, *_ERRORS) as error:
            receipt = self.store.actions(task_id)[-1]
            if receipt["status"] in {"prepared", "dispatched"}:
                status = "uncertain" if receipt["status"] == "dispatched" else "failed"
                self.store.settle(action_id, status, {"error": type(error).__name__})
            if not self._token(task_id).is_cancelled:
                self.store.update(task_id, "waiting_user", reason="action outcome requires review")
            raise
        finally:
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
                    if not self.store.transition(task_id, "running", "verifying"):
                        return self.get(task_id)
                    with self.broker.dispatch(self._leases[task_id]):
                        observations = detached(self._target(row).observe())
                        receipts = self.store.actions(task_id)
                        reports = verify(policy, receipts, observations,
                                         browser_read=getattr(self._target(row), "verify_browser", None))
                    self._token(task_id).checkpoint()
                    complete = all(item["status"] == "passed" for item in reports)
                    uncertain = any(item["status"] == "uncertain" for item in receipts)
                    state = "succeeded" if complete and not uncertain else "waiting_user"
                    self._publish_completion(task_id, state, reports)
                    return self.get(task_id)
                finally:
                    self._settle_control(task_id)

    def _publish_completion(self, task_id: str, state: str, reports: List[dict[str, Any]]) -> None:
        """Retire input before publishing success; concurrent control requests retain priority."""
        pending = "input cleanup unconfirmed; review before continuing"
        if not self.store.transition(task_id, "verifying", "verifying", reason=pending, verification=reports):
            return
        try:
            retired = self._retire(task_id)
        except _ERRORS:
            self.store.transition(task_id, "verifying", "waiting_user", reason=pending, verification=reports)
            raise
        reason = "" if state == "succeeded" else "completion not proven"
        if not retired:
            state, reason = "waiting_user", pending
        if self.store.transition(task_id, "verifying", state, reason=reason, verification=reports):
            self.evidence.publish(task_id)

    def pause(self, task_id: str) -> AgentTaskResult:
        """Request pause immediately; transfer control only after active input retires."""
        return self._request_stop(task_id, "pausing", "paused")

    def cancel(self, task_id: str) -> AgentTaskResult:
        """Request cancellation without closing another worker's native resources."""
        return self._request_stop(task_id, "cancelling", "cancelled")

    def stop_all(self) -> dict[str, Any]:
        """Cancel every visible task; operators cannot stop another principal's work."""
        identifiers = self._visible_live_ids()
        for task_id in identifiers:
            self._stop_final[task_id] = "cancelled"
            self._token(task_id).cancel()
        with self.store.connection(write=True) as connection:
            connection.executemany("UPDATE agent_tasks SET state='cancelling',updated=? WHERE id=? "
                "AND state NOT IN ('succeeded','failed','cancelled','timed_out')",
                [(time.time(), identifier) for identifier in identifiers])
        queued = self._cancel_without_input(identifiers)
        snapshots = self._stop_snapshots([task_id for task_id in identifiers[:1000] if task_id in queued])
        results: List[dict[str, Any]] = []
        errors: List[dict[str, str]] = []
        for task_id in identifiers:
            if task_id in queued:
                if task_id in snapshots:
                    results.append(snapshots[task_id])
                continue
            try:
                result = self.cancel(task_id)
                if len(results) < 1000:
                    results.append(result.to_dict())
            except _ERRORS as error:
                errors.append({"task_id": task_id, "error": type(error).__name__})
        return {"tasks": results, "requested": len(identifiers), "cleanup_errors": errors[:1000]}

    def _stop_snapshots(self, identifiers: List[str]) -> dict[str, dict]:
        if not identifiers:
            return {}
        with self.store.connection() as connection:
            connection.execute("CREATE TEMP TABLE agent_stop_page (id TEXT PRIMARY KEY)")
            connection.executemany("INSERT INTO agent_stop_page VALUES (?)", [(item,) for item in identifiers])
            rows = connection.execute("SELECT t.*,p.task_id AS report_pending FROM agent_tasks t "
                "JOIN agent_stop_page s ON s.id=t.id LEFT JOIN agent_evidence_pending p ON p.task_id=t.id").fetchall()
        return {row["id"]: AgentTaskResult(row["id"], row["state"], json.loads(row["spec"])["goal"], row["reason"],
                row["steps"], tuple(freeze(json.loads(row["verification"]))),
                freeze({"details_deferred": True, "report_pending": row["report_pending"] is not None})).to_dict()
                for row in rows}

    def _cancel_without_input(self, identifiers: List[str]) -> set[str]:
        with self._mutex:
            queued = {task_id for task_id in identifiers if task_id not in self._leases
                      and task_id not in self._executing}
        with self.store.connection(write=True) as connection:
            connection.executemany("UPDATE agent_tasks SET state='cancelled',updated=? "
                                   "WHERE id=? AND state='cancelling'", [(time.time(), item) for item in queued])
        if self.background is not None:
            self.evidence.defer(list(queued))
        else:
            for task_id in queued:
                self.evidence.publish(task_id)
        return queued

    def _visible_live_ids(self) -> List[str]:
        identity = current_authorization()
        with self.store.connection() as connection:
            rows = connection.execute("SELECT id,owner FROM agent_tasks "
                "WHERE state NOT IN ('succeeded','failed','cancelled','timed_out')").fetchall()
        return [row["id"] for row in rows if owns_task(json.loads(row["owner"]), identity)]

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
            self.evidence.publish(task_id)
        return self.get(task_id)

    def _settle_control(self, task_id: str) -> None:
        state = self._row(task_id)["state"]
        stops = {"pausing": "paused", "cancelling": "cancelled"}
        if state in stops and self._retire(task_id):
            self.store.update(task_id, self._stop_final.get(task_id, stops[state]))
            self.evidence.publish(task_id)
        elif state in TERMINAL or state == "waiting_user":
            self._retire(task_id)

    def _retire(self, task_id: str) -> bool:
        self._observations.pop(task_id, None)
        self._observation_times.pop(task_id, None)
        lease = self._leases.get(task_id)
        if lease is None:
            return True
        row = self.store.get(task_id)
        if not self.broker.release(lease, self._target(row).cleanup):
            return False
        with self._mutex:
            self._leases.pop(task_id, None)
        self.evidence.publish(task_id)
        return True

    def resume(self, task_id: str) -> AgentTaskResult:
        """Reauthorize a paused task; a fresh observation is required before any action."""
        with self._lock(task_id):
            row = self._row(task_id)
            require_no_successor(self.store, task_id)
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
        self.evidence.history.close()
        self._owner_lock.close()

    def maintain(self) -> None:
        """Expire abandoned leases and retire revoked owners even between client requests."""
        for task_id in list(self._leases):
            row = self.store.get(task_id)
            if self.clock.remaining(row) <= 0:
                self._request_stop(task_id, "cancelling", "timed_out")
                continue
            owner = AuthorizationContext(**row["owner"]) if row["owner"] else None
            try:
                validate_root_snapshot(row["spec"]["roots"])
                validate_origins(AgentTaskSpec.from_dict(row["spec"]))
                self.target_profiles.check(AgentTaskSpec.from_dict(row["spec"]))
                with DeferredAuthorization(owner).scope():
                    pass
            except (AutoControlException, OSError, ValueError):
                stopped = self.cancel(task_id)
                if stopped.state == "cancelled":
                    self.store.update(task_id, "cancelled",
                                      reason="owner authorization or origin scope requires review")
        self._settle_stopped()
        self.evidence.flush()
        if time.monotonic() >= self._next_retention:
            self.prune()
            self._next_retention = time.monotonic() + 3600

    def _settle_stopped(self) -> None:
        with self.store.connection() as connection:
            identifiers = [row[0] for row in connection.execute(
                "SELECT id FROM agent_tasks WHERE state IN ('pausing','cancelling') LIMIT 100")]
        for task_id in identifiers:
            if task_id not in self._executing:
                try:
                    self._settle_control(task_id)
                except _ERRORS as error:
                    autocontrol_logger.warning("agent input retirement needs review: %s", type(error).__name__)

    def prune(self, keep_days: int = 30) -> dict[str, Any]:
        """Remove expired visible metadata and owned artifacts, preserving user output and external journals."""
        from je_auto_control.utils.agent_runtime.retention import prune_tasks
        return prune_tasks(self, keep_days)

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
    from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
    return {"local-desktop": NativeDesktopTarget(),
            "local-files": NativeDesktopTarget(resource_path=Path.home() / ".je_auto_control" /
                                                "input_ownership" / "file-workflows.lock", recovery_probe=lambda: None)}
