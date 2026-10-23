"""Managed-task CLI parsing; the existing CLI owns terminal output."""
from __future__ import annotations

import argparse
import json
from typing import Any, Callable

from je_auto_control.utils.agent_runtime import api
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.path_guard.path_guard import validate_path


def register_parser(subparsers: Any, handler: Callable[..., int]) -> None:
    """Register additive task commands without changing legacy CLI flags."""
    parser = subparsers.add_parser("agent-task", help="Manage explicitly authorized agent tasks")
    operations = parser.add_subparsers(dest="agent_operation", required=True)
    for operation in ("start", "stop", "status", "submit", "list", "get", "observe", "act", "finish",
                      "pause", "resume", "cancel", "draft"):
        item = operations.add_parser(operation)
        item.set_defaults(func=handler)
        if operation == "start":
            item.add_argument("--directory")
        elif operation == "submit":
            item.add_argument("spec", help="JSON task specification")
        elif operation == "draft":
            from je_auto_control.utils.agent_runtime.workflow_specs import WORKFLOWS
            item.add_argument("workflow", choices=WORKFLOWS)
            item.add_argument("config", help="JSON workflow configuration")
        elif operation not in {"list", "status", "stop"}:
            item.add_argument("task_id")
            if operation == "act":
                item.add_argument("action", help="JSON grounded action request")


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    """Run one parsed operation and return a JSON-compatible result."""
    operation = arguments.agent_operation
    if operation == "start":
        return api.start_agent_runtime(arguments.directory)
    if operation == "status":
        return api.agent_runtime_status()
    if operation == "stop":
        return api.stop_agent_runtime()
    if operation == "submit":
        return api.submit_agent_task(_read(arguments.spec))
    if operation == "draft":
        from je_auto_control.utils.agent_runtime.workflow_specs import draft_agent_workflow
        return {"draft": draft_agent_workflow(arguments.workflow, _read(arguments.config))}
    if operation == "list":
        return api.list_agent_tasks()
    body: dict[str, Any] = {"task_id": arguments.task_id}
    if operation == "act":
        body["action"] = _read(arguments.action)
    return AgentRuntimeClient().call(operation, body)


def _read(path: str) -> Any:
    resolved = validate_path(path)
    if resolved.stat().st_size > 1_000_000:
        raise ValueError("task JSON exceeds one megabyte")
    return json.loads(resolved.read_text(encoding="utf-8"))
