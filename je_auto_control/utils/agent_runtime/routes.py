"""Authenticated REST adapters for the runtime explicitly owned by a server."""
from __future__ import annotations

from typing import Any, Callable
from concurrent.futures import CancelledError

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

OPERATIONS = ("submit", "observe", "act", "finish", "pause", "resume", "cancel", "shutdown", "draft", "stop_all",
              "receipts", "reconcile", "prune", "trigger", "recover_target")


def route(operation: str) -> Callable[..., Any]:
    """Build a fixed-operation handler; caller input never selects an arbitrary callable."""
    def handle(context: Any) -> tuple[int, dict[str, Any]]:
        runtime = context.agent_runtime
        if runtime is None:
            return 503, {"error": "agent runtime is not enabled on this server"}
        try:
            return 200, dispatch(runtime, operation, context.body, context.query_first("task_id"))
        except AgentTaskError as error:
            return 409, {"error": str(error)}
        except CancelledError:
            return 409, {"error": "agent operation was cancelled"}
    return handle


def dispatch(runtime: Any, operation: str, body: Any = None, task_id: str | None = None) -> dict[str, Any]:
    """Apply one known operation with strict, bounded request fields."""
    if operation == "list":
        return {"tasks": [item.to_dict() for item in runtime.list()]}
    if operation == "get":
        if not task_id:
            raise AgentTaskError("task_id is required")
        return runtime.get(task_id).to_dict()
    if not isinstance(body, dict):
        raise AgentTaskError("request body must be an object")
    operations = {"shutdown": lambda: runtime.request_shutdown(), "stop_all": lambda: _stop_all(runtime, body),
                  "submit": lambda: _submit(runtime, body), "draft": lambda: _draft(body),
                  "prune": lambda: _prune(runtime, body), "trigger": lambda: _trigger(runtime, body),
                  "recover_target": lambda: _recover_target(runtime, body)}
    if operation in operations:
        return operations[operation]()
    return _task_operation(runtime, operation, body)


def _submit(runtime: Any, body: dict) -> dict:
    if "spec" not in body or set(body) - {"spec", "idempotency_key"}:
        raise AgentTaskError("submit requires spec and accepts an optional idempotency_key")
    task = runtime.submit(body["spec"], idempotency_key=body.get("idempotency_key"))
    if getattr(runtime, "background", None) is not None:
        runtime.background.start(task.task_id)
    return {"task_id": task.task_id, "state": task.state}


def _recover_target(runtime: Any, body: dict) -> dict:
    if set(body) != {"target", "note"} or not isinstance(body["target"], str):
        raise AgentTaskError("recover_target requires target and operator note")
    from je_auto_control.utils.agent_runtime.native_recovery import recover_target
    return recover_target(runtime, body["target"], body["note"])


def _stop_all(runtime: Any, body: dict) -> dict:
    if body:
        raise AgentTaskError("stop_all requires an empty body")
    return runtime.stop_all()


def _draft(body: dict) -> dict:
    if set(body) != {"workflow", "config"}:
        raise AgentTaskError("draft requires workflow and config")
    from je_auto_control.utils.agent_runtime.workflow_specs import draft_agent_workflow
    return {"draft": draft_agent_workflow(body["workflow"], body["config"])}


def _prune(runtime: Any, body: dict) -> dict:
    if set(body) - {"keep_days"}:
        raise AgentTaskError("prune accepts only keep_days")
    return runtime.prune(body.get("keep_days", 30))


def _trigger(runtime: Any, body: dict) -> dict:
    if "operation" not in body or set(body) - {"operation", "request"}:
        raise AgentTaskError("trigger accepts operation and an optional request object")
    return runtime.triggers.control(body["operation"], body.get("request"))


def _task_operation(runtime: Any, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    _check_task_fields(operation, body)
    task_id = body["task_id"]
    if operation == "act":
        return runtime.act(task_id, body["action"]).to_dict()
    if operation == "reconcile":
        return runtime.reconcile(task_id, body["review"]).to_dict()
    if operation == "receipts":
        return runtime.receipts(task_id, body.get("offset", 0), body.get("limit", 100))
    handlers = {name: getattr(runtime, name) for name in OPERATIONS
                if name not in {"submit", "act", "shutdown", "draft", "stop_all", "prune", "reconcile",
                                "receipts", "trigger", "recover_target"}}
    if operation not in handlers:
        raise AgentTaskError("unknown task operation")
    result = handlers[operation](task_id).to_dict()
    if operation == "resume" and getattr(runtime, "background", None) is not None:
        runtime.background.start(task_id)
    return result


def _check_task_fields(operation: str, body: dict) -> None:
    required = {"task_id"} | {"act": {"action"}, "reconcile": {"review"}}.get(operation, set())
    optional = {"offset", "limit"} if operation == "receipts" else set()
    if not required <= set(body) or set(body) - required - optional or not isinstance(body.get("task_id"), str):
        raise AgentTaskError("invalid task operation fields")
