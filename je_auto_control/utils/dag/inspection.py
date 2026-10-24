"""Inspect keyed DAG requests without submitting work or granting continuation."""
from __future__ import annotations

import re
import time
from typing import Any, Mapping, cast

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import STATES, detached, positive, thaw
from je_auto_control.utils.dag.graph import DagDefinition, DagDefinitionError, DagNode, parse_definition
from je_auto_control.utils.dag import managed_tasks
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.deferred import DeferredAuthorization


def inspect_definition(definition: Mapping[str, Any] | DagDefinition, timeout_seconds: float = 30) -> dict[str, Any]:
    """Return bounded keyed snapshots and optional node-spec matches without granting continuation."""
    positive(timeout_seconds, "DAG inspection timeout_seconds", 300)
    if current_operation() is not None:
        raise AgentTaskError("a managed task cannot inspect other managed tasks")
    dag = definition if isinstance(definition, DagDefinition) else parse_definition(detached(definition))
    if len(dag.nodes) > 100:
        raise DagDefinitionError("DAG inspection accepts at most 100 nodes")
    order = dag.topological_order()
    owner = DeferredAuthorization.capture()
    deadline = time.monotonic() + timeout_seconds
    _checkpoint(owner, "local", deadline)
    nodes = dag.by_id()
    reports = []
    for identifier in order:
        node = nodes[identifier]
        _checkpoint(owner, "local", deadline)
        reports.append(_inspect_node(node, owner, deadline))
    return {"inspection_only": True, "resume_permitted": False, "checked_at": time.time(), "nodes": reports}


def _checkpoint(owner: DeferredAuthorization, host: str, deadline: float) -> float:
    managed_tasks.authorize_task_host(owner, host)
    if managed_tasks.task_stop_requested():
        raise AgentTaskError("DAG inspection was stopped")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AgentTaskError("DAG inspection deadline exhausted")
    return min(5, remaining)


def _inspect_node(node: DagNode, owner: DeferredAuthorization, deadline: float) -> dict[str, Any]:
    report = {"id": node.id, "host": node.host, "depends_on": list(node.depends_on),
              "lookup": "not_managed", "task_id": None, "task_state": "unknown",
              "input_released": None, "recorded_completion": None, "request_match": "unverified"}
    if node.task is None:
        return report
    report["idempotency_key"] = node.task["idempotency_key"]
    timeout = _checkpoint(owner, node.host, deadline)
    try:
        connection = managed_tasks.task_connection(node.host)
        reply = connection("lookup", {"idempotency_key": node.task["idempotency_key"]}, timeout)
    except AuthorizationError:
        raise
    except (AutoControlException, OSError, RuntimeError, ValueError, TypeError, LookupError):
        # A remote diagnostic may contain tokens or paths. Keep only a fixed outcome.
        _checkpoint(owner, node.host, deadline)
        report.update(lookup="unavailable", error="lookup_unavailable")
        return report
    _checkpoint(owner, node.host, deadline)
    try:
        report.update(_lookup_snapshot(reply))
    except AgentTaskError:
        report.update(lookup="unavailable", error="lookup_unavailable")
        return report
    if report["lookup"] == "found":
        report.update(_match_request(node.host, node.task, owner, deadline, connection, reply))
    return report


def _matching_supported(reply: Any) -> bool:
    version = reply.get("spec_match_contract") if isinstance(reply, dict) else None
    # pylint: disable-next=unidiomatic-typecheck  # reason: exact protocol integer excludes bool and subclasses
    return type(version) is int and version == 1


def _match_request(host: str, task: Mapping[str, Any], owner: DeferredAuthorization, deadline: float,
                   connection: managed_tasks.Call, initial: dict) -> dict[str, Any]:
    if not _matching_supported(initial):
        return {}
    spec = task["spec"]
    if host != "local" and "origin_policies" in spec["options"]:
        return {"request_match": "unverifiable"}
    timeout = _checkpoint(owner, host, deadline)
    try:
        reply = connection("lookup", {"idempotency_key": task["idempotency_key"], "spec": thaw(spec)}, timeout)
    except AuthorizationError:
        raise
    except (AutoControlException, OSError, RuntimeError, ValueError, TypeError, LookupError):
        _checkpoint(owner, host, deadline)
        return {"request_match": "unverifiable"}
    _checkpoint(owner, host, deadline)
    return _match_snapshot(initial, reply, spec)


def _match_snapshot(initial: dict, reply: Any, spec: Mapping[str, Any]) -> dict[str, Any]:
    if not _matching_supported(reply):
        return {"request_match": "unverifiable"}
    try:
        snapshot = _lookup_snapshot(reply)
    except AgentTaskError:
        return {"request_match": "unverifiable"}
    if snapshot.get("lookup") != "found" or snapshot.get("task_id") != initial["task"]["task_id"]:
        return {"request_match": "unverifiable", "lookup": "unavailable", "task_state": "unknown",
                "input_released": None, "recorded_completion": None, "error": "request_changed"}
    match = reply.get("spec_match")
    valid = isinstance(match, str) and match in {"matches", "differs", "unverifiable"}
    snapshot["request_match"] = match if valid else "unverifiable"
    if snapshot["request_match"] == "matches":
        snapshot["recorded_completion"] = _matched_completion(reply["task"], spec)
    return snapshot


def _matched_completion(task: dict, spec: Mapping[str, Any]) -> bool:
    try:
        managed_tasks.validate_recorded_completion(task, spec)
    except AgentTaskError:
        return False
    return True


def _lookup_snapshot(reply: Any) -> dict[str, Any]:
    if not isinstance(reply, dict) or not isinstance(reply.get("found"), bool):
        raise AgentTaskError("invalid lookup response")
    task = reply.get("task")
    if reply["found"] is False:
        if task is not None:
            raise AgentTaskError("inconsistent lookup response")
        return {"lookup": "not_found"}
    identifier, state = _task_identity(task)
    task = cast(dict[str, Any], task)
    metadata = task.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    released = metadata.get("input_released")
    return {"lookup": "found", "task_id": identifier, "task_state": state,
            "input_released": released if isinstance(released, bool) else None,
            "recorded_completion": _recorded_completion(task, metadata)}


def _task_identity(task: Any) -> tuple[str, str]:
    if not isinstance(task, dict):
        raise AgentTaskError("missing lookup task")
    identifier, state = task.get("task_id"), task.get("state")
    if not isinstance(identifier, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,256}", identifier) is None:
        raise AgentTaskError("invalid lookup task identity")
    if not isinstance(state, str) or state not in STATES:
        raise AgentTaskError("invalid lookup task state")
    return identifier, state


def _recorded_completion(task: dict, metadata: dict) -> bool:
    version, reports = metadata.get("completion_contract"), task.get("verification")
    # pylint: disable-next=unidiomatic-typecheck  # reason: the protocol excludes bool and int subclasses
    if type(version) is not int or version != 1 or metadata.get("input_released") is not True:
        return False
    if not isinstance(reports, list) or not 1 <= len(reports) <= 100:
        return False
    statuses = (isinstance(item, dict) and item.get("status") == "passed" for item in reports)
    return task["state"] == "succeeded" and all(statuses)
