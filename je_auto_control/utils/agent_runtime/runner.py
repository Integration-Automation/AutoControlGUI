"""Autonomous skill/local-model driver over exactly the external task operations."""
from __future__ import annotations

import time
from concurrent.futures import CancelledError
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskResult, AgentTaskSpec, TERMINAL, thaw
from je_auto_control.utils.agent_runtime.ollama import OllamaTaskBackend
from je_auto_control.utils.loop_guard.loop_guard import LoopGuard, digest_result


def run_task(runtime: Any, task_id: str, *, backend: Any = None) -> AgentTaskResult:
    """Drive a task through observe/act/finish; a backend cannot bypass any shared gate."""
    row = runtime._row(task_id)
    spec = AgentTaskSpec.from_dict(row["spec"])
    if spec.mode == "external":
        raise AgentTaskError("external tasks are driven through observe/act/finish")
    if spec.mode == "ollama" and backend is None:
        backend = OllamaTaskBackend(spec)
    guard = LoopGuard()
    try:
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
    while runtime.get(task_id).state in {"queued", "running"}:
        observation = runtime.observe(task_id)
        receipts = runtime.store.actions(task_id)
        if spec.mode == "skill":
            if len(receipts) >= len(spec.actions):
                return runtime.finish(task_id)
            proposal = thaw(spec.actions[len(receipts)])
        else:
            proposal = _decision(runtime, task_id, spec, backend, observation.data, receipts)
        if proposal.get("stop"):
            return runtime.finish(task_id)
        action = {"tool": proposal["tool"], "arguments": proposal.get("arguments", {}),
                  "observation_id": observation.observation_id}
        result = runtime.act(task_id, action)
        verdict = guard.observe(action["tool"], action["arguments"], digest_result(result.result))
        if verdict.level == "critical":
            raise AgentTaskError("agent has stopped making progress")
    return runtime.get(task_id)


def _decision(runtime: Any, task_id: str, spec: AgentTaskSpec, backend: Any, observation: Any,
              receipts: list[dict]) -> dict:
    last_error: AgentTaskError | None = None
    for _attempt in range(spec.budget.retries + 1):
        runtime._token(task_id).checkpoint()
        row = runtime._row(task_id)
        remaining = spec.budget.wall_seconds - (time.time() - row["started"])
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
