"""Canonical whole-graph identities and destination-only tags for durable managed batches."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached, thaw
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.dag.graph import DagDefinition, parse_definition


def definition_dict(dag: DagDefinition) -> dict:
    """Serialize managed node contracts without borrowing mutable caller arrays."""
    return {"nodes": [{"id": node.id, "host": node.host, "depends_on": sorted(node.depends_on),
                       "task": thaw(node.task)} for node in sorted(dag.nodes, key=lambda item: item.id)]}


def batch_definition(value: Any) -> dict:
    """Reject ambiguous/legacy/action nodes before producing a stable, bounded graph digest."""
    data = detached(value)
    if not isinstance(data, dict) or set(data) != {"nodes"}:
        raise AgentTaskError("managed batch requires exactly one nodes list")
    nodes = data["nodes"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 100:
        raise AgentTaskError("managed batch requires one to one hundred nodes")
    for node in nodes:
        _node_fields(node)
    dag = parse_definition(data)
    dag.topological_order()
    keys = [(node.host, node.task["idempotency_key"]) for node in dag.nodes if node.task is not None]
    if len(keys) != len(set(keys)):
        raise AgentTaskError("managed batch requires distinct request keys per host")
    return definition_dict(dag)


def _node_fields(node: Any) -> None:
    if not isinstance(node, dict) or not {"id", "task"} <= set(node):
        raise AgentTaskError("managed batch nodes require id and task")
    if set(node) - {"id", "host", "depends_on", "task"}:
        raise AgentTaskError("managed batch nodes accept only managed task contracts")
    _node_identity(node)
    _node_dependencies(node)


def _node_identity(node: dict) -> None:
    if not isinstance(node["id"], str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", node["id"]) is None:
        raise AgentTaskError("managed batch node id is invalid")
    host = node.get("host", "local")
    if not isinstance(host, str) or not host.strip() or len(host) > 256:
        raise AgentTaskError("managed batch host identity is invalid")


def _node_dependencies(node: dict) -> None:
    deps = node.get("depends_on", [])
    if not isinstance(deps, list) or not all(isinstance(item, str) for item in deps) or len(deps) != len(set(deps)):
        raise AgentTaskError("managed batch dependencies must be distinct node identities")


def bind_definition(definition: Mapping[str, Any], batch_id: str, graph_hash: str) -> dict:
    """Bind every destination spec/key to the same immutable batch, topology and node identity."""
    result = detached(definition)
    for node in result["nodes"]:
        task = node["task"]
        task["spec"]["options"]["dag_batch"] = {"batch_id": batch_id, "graph_hash": graph_hash, "node_id": node["id"]}
        identity = {"batch": batch_id, "node": node["id"], "host": node["host"], "key": task["idempotency_key"]}
        task["idempotency_key"] = "dag:" + request_spec_digest(identity)
    return result


def host_fingerprint(base: str, token: str) -> str:
    """Bind reviewed host configuration without storing or exposing its bearer credential."""
    return hashlib.sha256((base + "\0" + token).encode()).hexdigest()
