"""Initial execution of a registered graph with durable pre-delivery claims and verified receipts."""
from __future__ import annotations

import threading
from typing import Any, Callable, Mapping

from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.dag.batch_contract import definition_dict
from je_auto_control.utils.dag.graph import DagDefinition, parse_definition
from je_auto_control.utils.dag.managed_tasks import run_managed_task, ManagedTaskDispatchError
from je_auto_control.utils.exception.cancellation import cancellation_scope


def run_batch(dag: DagDefinition, batch_id: str, max_parallel: int,
              stop_event: threading.Event | None, execute: Callable[..., Any],
              recovery: Mapping[str, Any] | None) -> Any:
    """Begin the registered batch once; a later run requires explicit recovery rather than another submit."""
    if current_operation() is not None:
        raise AgentTaskError("a managed task cannot coordinate another managed batch")
    client = AgentRuntimeClient()
    definition = definition_dict(dag)
    if recovery is None:
        started = client.call("dag", {"operation": "begin", "request": {
            "batch_id": batch_id, "definition": definition, "max_parallel": max_parallel}})
    else:
        approved = client.call("dag", {"operation": "approve_continuation", "request": {
            **recovery, "batch_id": batch_id, "definition": definition}})
        started = client.call("dag", {"operation": "start_continuation", "request": {
            "batch_id": batch_id, "definition": definition, "approval_id": approved["approval_id"],
            "max_parallel": max_parallel, "timeout_seconds": recovery.get("timeout_seconds", 30)}})
    return execute_started(client, started, stop_event, execute, max_parallel)


def execute_started(client: Any, started: dict, stop_event: threading.Event | None,
                    execute: Callable[..., Any], max_parallel: int) -> Any:
    """Coordinate one pre-authorized attempt with the same claims, verification and finalization path."""
    runner = _BatchRun(client, started)
    try:
        return execute(parse_definition(started["definition"]), max_parallel=max_parallel,
                       local_runner=runner.run_node, remote_runner=runner.run_node, stop_event=stop_event)
    finally:
        with cancellation_scope(None):
            try:
                runner.control("finish", {})
            except (AgentTaskError, OSError, RuntimeError, ValueError, TypeError):
                # The persisted running/claimed states require review; no completion is inferred from a lost reply.
                pass


class _BatchRun:
    """One authorized attempt; no private coordinator identity enters destination specifications."""

    def __init__(self, client: Any, started: dict) -> None:
        self.client, self.started = client, started

    def control(self, operation: str, request: dict) -> dict:
        """Send only the frozen batch/attempt identity with bounded lifecycle fields."""
        return self.client.call("dag", {"operation": operation, "request": {
            "batch_id": self.started["batch_id"], "attempt": self.started["attempt"], **request}})

    def run_node(self, node: Any, _definition: Any) -> dict:
        """Claim before destination contact; report independently checked completion before releasing dependants."""
        if node.id in self.started.get("adopted", {}):
            return self.control("validate_node", {"node_id": node.id})
        self.control("claim", {"node_id": node.id})
        try:
            result = run_managed_task(node.host, node.task, host_binding=self.started["hosts"][node.host])
            self.control("record", {"node_id": node.id,
                                    "receipt": {"outcome": "completed", "task_id": result["task_id"]}})
            return result
        except BaseException as error:  # reason: retain uncertainty and preserve cancellation/hard exits
            task_id = error.outcome.get("task_id") if isinstance(error, ManagedTaskDispatchError) else None
            with cancellation_scope(None):
                try:
                    self.control("record", {"node_id": node.id, "receipt": {"outcome": "unknown", "task_id": task_id}})
                except (AgentTaskError, OSError, RuntimeError, ValueError, TypeError):
                    pass  # the durable pre-delivery claim remains an unsettled, non-replayable witness
            raise
