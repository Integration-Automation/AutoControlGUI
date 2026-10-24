"""Durable dispatch claims and independent destination verification for one managed DAG batch."""
from __future__ import annotations

import json
import re
import time
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.dag.batch_contract import bind_definition
from je_auto_control.utils.dag import managed_tasks
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.exception.exceptions import AutoControlException


def bound_node(batch: dict, identifier: Any) -> dict:
    """Resolve a node solely from the immutable batch instead of accepting a caller's destination spec."""
    definition = bind_definition(batch["definition"], batch["id"], batch["graph_hash"])
    for node in definition["nodes"]:
        if node["id"] == identifier:
            return node
    raise AgentTaskError("batch node does not exist")


def claim_node(connection: Any, batch: dict, request: dict) -> None:
    """Record possible delivery before networking; a missing reply can never reset this claim."""
    node = bound_node(batch, request["node_id"])
    if managed_tasks.task_host_binding(node["host"]) != batch["hosts"][node["host"]]:
        raise AgentTaskError("managed batch host configuration changed")
    for dependency in node["depends_on"]:
        row = connection.execute("SELECT phase FROM agent_dag_nodes WHERE batch_id=? AND node_id=?",
                                 (batch["id"], dependency)).fetchone()
        if row is None or row[0] != "confirmed":
            raise AgentTaskError("batch dependencies are not independently confirmed")
    cursor = connection.execute("UPDATE agent_dag_nodes SET phase='claimed',updated=? "
        "WHERE batch_id=? AND node_id=? AND phase='pending'", (time.time(), batch["id"], node["id"]))
    if cursor.rowcount != 1:
        raise AgentTaskError("batch node was already claimed; explicit recovery is required")


def verify_node(batch: dict, node: dict, task_id: str) -> None:
    """Require the exact tagged spec/key, task identity and independent completion/retirement contract."""
    owner = DeferredAuthorization.capture()
    managed_tasks.authorize_task_host(owner, node["host"])
    call = managed_tasks.bound_task_connection(node["host"], batch["hosts"][node["host"]])
    try:
        reply = call("lookup", {"idempotency_key": node["task"]["idempotency_key"], "spec": node["task"]["spec"]}, 5)
    except AuthorizationError:
        raise
    except (AutoControlException, OSError, RuntimeError, ValueError, TypeError, LookupError):
        raise AgentTaskError("batch destination completion could not be verified") from None
    managed_tasks.authorize_task_host(owner, node["host"])
    if not isinstance(reply, dict):
        raise AgentTaskError("batch destination request binding is unverified")
    version = reply.get("spec_match_contract")
    # pylint: disable-next=unidiomatic-typecheck  # reason: an exact protocol integer excludes boolean versions
    if (type(version) is not int or version != 1
            or reply.get("found") is not True or reply.get("spec_match") != "matches"):
        raise AgentTaskError("batch destination request binding is unverified")
    task = reply.get("task")
    if not isinstance(task, dict) or task.get("task_id") != task_id:
        raise AgentTaskError("batch destination task identity changed")
    managed_tasks.validate_recorded_completion(task, node["task"]["spec"])


def validate_receipt(receipt: Any) -> dict:
    """Reject malformed coordination data before any destination lookup or durable transition."""
    if not isinstance(receipt, dict) or set(receipt) != {"outcome", "task_id"}:
        raise AgentTaskError("batch receipt requires outcome and task_id only")
    if not isinstance(receipt["outcome"], str) or receipt["outcome"] not in {"completed", "unknown", "requires_review"}:
        raise AgentTaskError("invalid batch receipt outcome")
    _receipt_identity(receipt["task_id"], receipt["outcome"] == "completed")
    return receipt


def _receipt_identity(identifier: Any, required: bool) -> None:
    if identifier is None and required:
        raise AgentTaskError("completed batch receipt requires a task identity")
    if identifier is not None and (not isinstance(identifier, str)
                                   or re.fullmatch(r"[A-Za-z0-9_-]{1,256}", identifier) is None):
        raise AgentTaskError("invalid batch receipt task identity")


def record_node(connection: Any, batch: dict, request: dict) -> None:
    """Store only bounded coordination identity; completion was independently checked before this transaction."""
    receipt = validate_receipt(request["receipt"])
    phase = "confirmed" if receipt["outcome"] == "completed" else "unknown"
    cursor = connection.execute("UPDATE agent_dag_nodes SET phase=?,receipt=?,updated=? "
        "WHERE batch_id=? AND node_id=? AND phase='claimed'",
        (phase, json.dumps(receipt), time.time(), batch["id"], request["node_id"]))
    if cursor.rowcount != 1:
        raise AgentTaskError("batch receipt requires one unsettled dispatch claim")
