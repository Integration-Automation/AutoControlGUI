"""Autonomous skill/local-model driver over exactly the external task operations."""
from __future__ import annotations

from concurrent.futures import CancelledError
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError, AgentObservationStale
from je_auto_control.utils.agent_runtime.models import AgentTaskResult, AgentTaskSpec, TERMINAL, thaw
from je_auto_control.utils.agent_runtime.ollama import OllamaTaskBackend
from je_auto_control.utils.loop_guard.loop_guard import LoopGuard, digest_result
from je_auto_control.utils.agent_runtime.workflow_values import captures, expected, resolve, verified_prefix
from je_auto_control.utils.agent_runtime.receipts import effective_actions


def run_task(runtime: Any, task_id: str, *, backend: Any = None) -> AgentTaskResult:
    """Drive a task through observe/act/finish; a backend cannot bypass any shared gate."""
    row = runtime._row(task_id)
    spec = AgentTaskSpec.from_dict(row["spec"])
    if spec.mode == "external":
        raise AgentTaskError("external tasks are driven through observe/act/finish")
    guard = LoopGuard()
    try:
        if spec.mode == "ollama" and backend is None:
            with runtime._scope(row):
                backend = OllamaTaskBackend(spec)
        return _loop(runtime, task_id, spec, backend, guard)
    except CancelledError:
        runtime._settle_control(task_id)
        return runtime.get(task_id)
    except AgentControlBusy:
        return runtime.get(task_id)
    except AgentTaskError as error:
        state = runtime.get(task_id).state
        if state not in TERMINAL and state not in {"paused", "waiting_user", "cancelling", "pausing"}:
            runtime.store.update(task_id, "waiting_user", reason=str(error))
        runtime._retire(task_id)
        return runtime.get(task_id)


def _loop(runtime: Any, task_id: str, spec: AgentTaskSpec, backend: Any, guard: LoopGuard) -> AgentTaskResult:
    stale_attempts = 0
    while runtime.get(task_id).state in {"queued", "running"}:
        observation = runtime.observe(task_id)
        receipts = effective_actions(runtime.store.actions(task_id))
        if spec.mode == "skill":
            if not verified_prefix(spec, receipts):
                raise AgentTaskError("previous workflow read-back did not match; review before continuing")
            if len(receipts) >= len(spec.actions):
                return runtime.finish(task_id)
            proposal = thaw(spec.actions[len(receipts)])
        else:
            proposal = _decision(runtime, task_id, spec, backend, observation.data, receipts)
        if proposal.get("stop"):
            return runtime.finish(task_id)
        values = captures(spec, receipts)
        action = _grounded_action(proposal, values, observation.observation_id)
        try:
            result = runtime.act(task_id, action)
        except AgentObservationStale:
            if stale_attempts >= spec.budget.retries or not _can_reobserve(runtime, task_id):
                raise
            stale_attempts += 1
            continue
        stale_attempts = 0
        _check_step(proposal, values, result.result, action, guard if spec.mode != "skill" else None)
    return runtime.get(task_id)


def _grounded_action(proposal: dict, values: dict, observation_id: str) -> dict:
    action = {"tool": proposal["tool"], "arguments": resolve(proposal.get("arguments", {}), values),
              "observation_id": observation_id}
    if proposal.get("reference") is not None:
        action["reference"] = proposal["reference"]
    return action


def _can_reobserve(runtime: Any, task_id: str) -> bool:
    target = runtime._target(runtime._row(task_id))
    return getattr(target, "can_reobserve", False) is True


def _check_step(proposal: dict, values: dict, result: Any, action: dict, guard: LoopGuard | None) -> None:
    if "expect_not_result" in proposal and thaw(result) == proposal["expect_not_result"]:
        raise AgentTaskError("workflow confirmation is stale; review before continuing")
    required, value = expected(proposal, values)
    if required and thaw(result) != value:
        raise AgentTaskError("workflow read-back did not match; review before continuing")
    if guard is not None:
        verdict = guard.observe(action["tool"], action["arguments"], digest_result(result))
        if verdict.level == "critical":
            raise AgentTaskError("agent has stopped making progress")


def _decision(runtime: Any, task_id: str, spec: AgentTaskSpec, backend: Any, observation: Any,
              receipts: list[dict]) -> dict:
    last_error: AgentTaskError | None = None
    for _attempt in range(spec.budget.retries + 1):
        runtime._token(task_id).checkpoint()
        row = runtime._row(task_id)
        remaining = runtime.clock.remaining(row)
        if remaining <= 0:
            runtime._check_budget(task_id)
        try:
            proposal = backend.decide(observation, receipts, timeout=min(spec.budget.model_seconds, remaining),
                                      check=runtime._token(task_id).checkpoint)
            if not isinstance(proposal, dict):
                raise AgentTaskError("model decision must be an object")
            return proposal
        except AgentTaskError as error:
            last_error = error
    raise AgentTaskError("local model decision retries exhausted") from last_error
