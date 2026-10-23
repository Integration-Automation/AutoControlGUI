"""Authenticated REST adapters for the runtime explicitly owned by a server."""
from __future__ import annotations

from typing import Any, Callable
from concurrent.futures import CancelledError

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

OPERATIONS = ("submit", "observe", "act", "finish", "pause", "resume", "cancel", "shutdown", "draft", "stop_all")


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
    if operation == "shutdown":
        return runtime.request_shutdown()
    if operation == "stop_all":
        return _stop_all(runtime, body)
    if operation == "submit":
        return _submit(runtime, body)
    if operation == "draft":
        return _draft(body)
    return _task_operation(runtime, operation, body)


def _submit(runtime: Any, body: dict) -> dict:
    if set(body) != {"spec"}:
        raise AgentTaskError("submit requires only spec")
    task = runtime.submit(body["spec"])
    if getattr(runtime, "background", None) is not None:
        runtime.background.start(task.task_id)
    return {"task_id": task.task_id, "state": task.state}


def _stop_all(runtime: Any, body: dict) -> dict:
    if body:
        raise AgentTaskError("stop_all requires an empty body")
    return runtime.stop_all()


def _draft(body: dict) -> dict:
    if set(body) != {"workflow", "config"}:
        raise AgentTaskError("draft requires workflow and config")
    from je_auto_control.utils.agent_runtime.workflow_specs import draft_agent_workflow
    return {"draft": draft_agent_workflow(body["workflow"], body["config"])}


def _task_operation(runtime: Any, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    expected = {"task_id", "action"} if operation == "act" else {"task_id"}
    if set(body) != expected or not isinstance(body.get("task_id"), str):
        raise AgentTaskError("invalid task operation fields")
    task_id = body["task_id"]
    if operation == "act":
        return runtime.act(task_id, body["action"]).to_dict()
    handlers = {name: getattr(runtime, name) for name in OPERATIONS
                if name not in {"submit", "act", "shutdown", "draft", "stop_all"}}
    if operation not in handlers:
        raise AgentTaskError("unknown task operation")
    result = handlers[operation](task_id).to_dict()
    if operation == "resume" and getattr(runtime, "background", None) is not None:
        runtime.background.start(task_id)
    return result
