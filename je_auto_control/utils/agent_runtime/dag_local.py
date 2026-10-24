"""Closed local-node transport admits claimed DAG work under the original owner's authority."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from je_auto_control.utils.agent_runtime.dag_admission import admission_scope, actor_identity
from je_auto_control.utils.agent_runtime.dag_batch_recording import bound_node
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.submission import submitted_digest
from je_auto_control.utils.rbac.authorization import AuthorizationContext
from je_auto_control.utils.rbac.deferred import DeferredAuthorization


# pylint: disable-next=too-few-public-methods  # reason: one closed per-node transport operation owns validation/admission
class DagLocalTasks:
    """Only exact bound local requests can be accepted, inspected or retired through a batch attempt."""

    def __init__(self, runtime: Any, batch: dict, request: dict, actor: DeferredAuthorization) -> None:
        self.runtime, self.batch, self.request, self.actor = runtime, batch, request, actor
        self.node = bound_node(batch, request["node_id"])
        self.owner = DeferredAuthorization(AuthorizationContext(**batch["owner"]) if batch["owner"] else None)

    def control(self) -> dict:
        """Validate closed fields, original authority and trusted request identity before any local operation."""
        operation, body = self.request["operation"], self.request["body"]
        if (not isinstance(operation, str) or self.node["host"] != "local"
                or operation not in {"submit", "get", "lookup", "pause"}):
            raise AgentTaskError("local DAG transport accepts only finite local task operations")
        if not isinstance(body, dict):
            raise AgentTaskError("local DAG transport body must be an object")
        if operation != "pause":
            self._active()
        if operation == "pause":
            with self.owner.context_scope():
                return self._read(operation, body)
        with self.owner.scope():
            return self._submit(body) if operation == "submit" else self._read(operation, body)

    def _active(self) -> None:
        if self.batch["state"] != "running" or self.request["attempt"] != self.batch["attempt"]:
            raise AgentTaskError("local DAG transport attempt is inactive")
        with self.runtime.store.connection() as connection:
            row = connection.execute("SELECT phase FROM agent_dag_nodes WHERE batch_id=? AND node_id=?",
                                     (self.batch["id"], self.node["id"])).fetchone()
        if row is None or row["phase"] != "claimed":
            raise AgentTaskError("local DAG admission requires an unsettled pre-delivery claim")

    def _request_key(self, body: dict) -> None:
        if body.get("idempotency_key") != self.node["task"]["idempotency_key"]:
            raise AgentTaskError("local DAG task request key changed")
        if "spec" in body and submitted_digest(body["spec"]) != submitted_digest(self.node["task"]["spec"]):
            raise AgentTaskError("local DAG task specification changed")

    def _submit(self, body: dict) -> dict:
        if set(body) != {"spec", "idempotency_key"}:
            raise AgentTaskError("local DAG submit requires exact spec and request key only")
        self._request_key(body)
        jobs = getattr(self.runtime, "background", None)
        if jobs is None:
            raise AgentTaskError("local DAG admission requires an explicitly started task service")
        grant = {"batch_id": self.batch["id"], "node_id": self.node["id"], "attempt": self.request["attempt"],
                 "actor": asdict(self.actor.context) if self.actor.context is not None else {},
                 "spec_digest": submitted_digest(self.node["task"]["spec"])}
        with self.actor.scope(), self.owner.scope(), admission_scope(grant):
            task = self.runtime.submit(body["spec"], idempotency_key=body["idempotency_key"])
        self._binding(task.task_id)
        jobs.start(task.task_id)
        return {"task_id": task.task_id, "state": task.state}

    def _read(self, operation: str, body: dict) -> dict:
        if operation == "lookup":
            if not {"idempotency_key"} <= set(body) or set(body) - {"idempotency_key", "spec"}:
                raise AgentTaskError("local DAG lookup accepts only the bound key and optional specification")
            self._request_key(body)
            result = self.runtime.lookup(body["idempotency_key"], body.get("spec"))
            if result["found"]:
                self._binding(result["task"]["task_id"])
            return result
        if set(body) != {"task_id"}:
            raise AgentTaskError("local DAG read/control requires only the admitted task identity")
        self._binding(body["task_id"])
        return (self.runtime.pause(body["task_id"]).to_dict() if operation == "pause"
                else self.runtime.get(body["task_id"]).to_dict())

    def _binding(self, task_id: str) -> None:
        if not isinstance(task_id, str) or not 1 <= len(task_id) <= 256:
            raise AgentTaskError("local DAG task identity must be a bounded string")
        with self.runtime.store.connection() as connection:
            row = connection.execute("SELECT * FROM agent_dag_local_tasks WHERE task_id=?", (task_id,)).fetchone()
        expected = {"batch_id": self.batch["id"], "node_id": self.node["id"], "attempt": self.request["attempt"],
                    "spec_digest": submitted_digest(self.node["task"]["spec"])}
        actor = asdict(self.actor.context) if self.actor.context is not None else {}
        if (row is None or any(row[key] != value for key, value in expected.items())
                or actor_identity(json.loads(row["actor"])) != actor_identity(actor)):
            raise AgentTaskError("local DAG task identity or admitting actor differs")
