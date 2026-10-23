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
                      "pause", "resume", "cancel", "draft", "stop-all", "receipts", "reconcile", "prune", "trigger",
                      "recover-target", "skill", "target", "targets"):
        item = operations.add_parser(operation)
        item.set_defaults(func=handler)
        _operation_arguments(item, operation)


def _operation_arguments(item: Any, operation: str) -> None:
    if operation == "start":
        item.add_argument("--directory")
    elif operation == "submit":
        item.add_argument("spec", help="JSON task specification")
        item.add_argument("--idempotency-key")
    elif operation == "prune":
        item.add_argument("--keep-days", type=int, default=30)
    elif operation == "draft":
        from je_auto_control.utils.agent_runtime.workflow_specs import WORKFLOWS
        item.add_argument("workflow", choices=WORKFLOWS)
        item.add_argument("config", help="JSON workflow configuration")
    elif operation in {"trigger", "skill", "target"}:
        _reviewed_arguments(item, operation)
    elif operation == "recover-target":
        item.add_argument("target")
        item.add_argument("note", help="Operator review after manually releasing held input")
    elif operation not in {"list", "status", "stop", "stop-all", "targets"}:
        item.add_argument("task_id")
        if operation in {"act", "reconcile"}:
            item.add_argument("action" if operation == "act" else "review", help="JSON action request or owner review")


def _reviewed_arguments(item: Any, operation: str) -> None:
    from je_auto_control.utils.agent_runtime.task_triggers import OPERATIONS as TRIGGERS
    from je_auto_control.utils.agent_runtime.task_skills import OPERATIONS as SKILLS
    from je_auto_control.utils.agent_runtime.target_profiles import OPERATIONS as TARGETS
    choices = {"trigger": TRIGGERS, "skill": SKILLS, "target": TARGETS}[operation]
    item.add_argument(operation + "_operation", choices=choices)
    item.add_argument("request", nargs="?", help="JSON reviewed operation request")


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    """Run one parsed operation and return a JSON-compatible result."""
    operation = arguments.agent_operation
    operations = {"start": lambda: api.start_agent_runtime(arguments.directory),
                  "targets": api.list_agent_targets,
                  "target": lambda: api.manage_agent_target(arguments.target_operation,
                                                             _read(arguments.request) if arguments.request else {}),
                  "status": api.agent_runtime_status, "stop": api.stop_agent_runtime,
                  "stop-all": api.stop_all_agent_tasks, "list": api.list_agent_tasks,
                  "submit": lambda: api.submit_agent_task(_read(arguments.spec), arguments.idempotency_key),
                  "draft": lambda: _draft(arguments), "prune": lambda: api.prune_agent_tasks(arguments.keep_days),
                  "reconcile": lambda: api.reconcile_agent_task(arguments.task_id, _read(arguments.review)),
                  "recover-target": lambda: api.recover_agent_target(arguments.target, arguments.note),
                  "skill": lambda: api.manage_agent_skill(arguments.skill_operation,
                                                            _read(arguments.request) if arguments.request else {}),
                  "trigger": lambda: api.manage_agent_trigger(arguments.trigger_operation,
                                                                _read(arguments.request) if arguments.request else {})}
    if operation in operations:
        return operations[operation]()
    task_operations = {"observe": api.observe_agent_task, "finish": api.finish_agent_task}
    if operation in task_operations:
        return task_operations[operation](arguments.task_id)
    body: dict[str, Any] = {"task_id": arguments.task_id}
    if operation == "act":
        return api.act_agent_task(arguments.task_id, _read(arguments.action))
    return AgentRuntimeClient().call(operation, body)


def _draft(arguments: argparse.Namespace) -> dict:
    from je_auto_control.utils.agent_runtime.workflow_specs import draft_agent_workflow
    return {"draft": draft_agent_workflow(arguments.workflow, _read(arguments.config))}


def _read(path: str) -> Any:
    resolved = validate_path(path)
    if resolved.stat().st_size > 1_000_000:
        raise ValueError("task JSON exceeds one megabyte")
    return json.loads(resolved.read_text(encoding="utf-8"))
