"""Whole-graph review and one-shot continuation approval never replay a possible delivery."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.agent_runtime.dag_batch_recording import bound_node
from je_auto_control.utils.agent_runtime.dag_continuation_evidence import ContinuationEvidence, completion
from je_auto_control.utils.agent_runtime.dag_continuation_plan import dispatch_template, validate_decision
from je_auto_control.utils.dag.batch_contract import batch_definition, bind_definition

FIELDS = {"pause_batch": {"batch_id"}, "review_continuation": {"batch_id", "definition"},
          "approve_continuation": {"batch_id", "definition", "snapshot", "decisions", "note"},
          "start_continuation": {"batch_id", "definition", "approval_id", "max_parallel"},
          "validate_node": {"batch_id", "attempt", "node_id"}}


def _decisions(value: Any, batch: dict) -> dict[str, dict] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != len(batch["definition"]["nodes"]):
        raise AgentTaskError("DAG continuation requires one explicit decision for every node")
    result = {}
    for decision in value:
        if not isinstance(decision, dict) or not isinstance(decision.get("node_id"), str):
            raise AgentTaskError("invalid DAG continuation node decision")
        if decision["node_id"] in result:
            raise AgentTaskError("duplicate DAG continuation node decision")
        result[decision["node_id"]] = decision
    if set(result) != {node["id"] for node in batch["definition"]["nodes"]}:
        raise AgentTaskError("DAG continuation decisions do not match the original graph")
    return result


def _input_matches(batch: dict, definition: Any) -> None:
    if request_spec_digest(batch_definition(definition)) != request_spec_digest(batch["input_definition"]):
        raise AgentTaskError("DAG continuation input graph changed")


# pylint: disable-next=too-few-public-methods  # reason: one closed continuation protocol collaborates with the batch registry
class DagContinuation:
    """Bind explicit decisions to local claims, current authority and fresh destination receipts."""

    def __init__(self, batches: Any, actor: dict) -> None:
        self.batches, self.actor = batches, actor

    def control(self, operation: str, batch: dict, request: dict) -> dict:
        """Review without writes, approve without dispatch, or acquire exactly one approved attempt."""
        if operation == "pause_batch":
            return self._pause(batch)
        if operation == "validate_node":
            return self.validate_node(batch, request["node_id"], request["attempt"])
        _input_matches(batch, request["definition"])
        if operation == "start_continuation":
            return self._start(batch, request)
        if operation == "approve_continuation":
            return self._approve(batch, request)
        if batch["state"] != "waiting_review":
            raise AgentTaskError("continuation review requires an explicitly stopped batch")
        baseline = self._baseline(batch)
        return self._gather(baseline, request.get("decisions"), request.get("timeout_seconds", 30))["public"]

    def _baseline(self, batch: dict) -> dict:
        with self.batches.runtime.store.connection() as connection:
            nodes = [dict(row) for row in connection.execute(
                "SELECT * FROM agent_dag_nodes WHERE batch_id=? ORDER BY node_id", (batch["id"],))]
        return detached({"batch": batch, "nodes": nodes, "actor": self.actor})

    def _gather(self, baseline: dict, decisions: Any, timeout: float) -> dict:
        batch = baseline["batch"]
        selected = _decisions(decisions, batch)
        evidence = ContinuationEvidence(batch, timeout, self.batches.runtime)
        local_hash = request_spec_digest(baseline)
        reports = []
        for row in baseline["nodes"]:
            node = bound_node(batch, row["node_id"])
            choice = selected[node["id"]] if selected is not None else None
            reports.append(self._review_node(node, row["phase"], choice, evidence, local_hash))
        plan = [item["decision"] for item in reports]
        snapshot = request_spec_digest({"baseline": baseline, "reports": reports})
        public = {"batch_id": batch["id"], "graph_hash": batch["graph_hash"], "snapshot": snapshot,
                  "definition": batch["input_definition"], "decisions": plan, "approval_required": True,
                  "can_approve": all(item["ready"] for item in reports), "resume_permitted": False,
                  "nodes": [{"id": item["decision"]["node_id"], "ready": item["ready"],
                             "issue": item.get("issue", "")} for item in reports]}
        return {"public": public, "baseline": baseline, "reports": reports}

    def _review_node(self, node: dict, phase: str, choice: dict | None,
                     evidence: ContinuationEvidence, snapshot: str) -> dict:
        try:
            original = evidence.original(node)
            if choice is None:
                choice = self._default(node, phase, original, snapshot)
            return validate_decision(self.batches.runtime, choice, node, phase, original, evidence, snapshot)
        except AgentTaskError:
            decision = choice or {"node_id": node["id"], "action": "wait"}
            return {"decision": decision, "ready": False, "issue": "destination_or_decision_requires_review"}

    def _default(self, node: dict, phase: str, original: dict | None, snapshot: str) -> dict:
        if original is not None:
            completion(original, node)
            return {"node_id": node["id"], "action": "adopt", "task_id": original["task_id"]}
        if phase == "pending":
            spec, _authority = dispatch_template(self.batches.runtime, node, snapshot)
            return {"node_id": node["id"], "action": "dispatch", "spec": spec}
        return {"node_id": node["id"], "action": "wait"}

    def _pause(self, batch: dict) -> dict:
        with self.batches.runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE agent_dag_batches SET state='waiting_review',attempt='',updated=? WHERE id=?",
                               (time.time(), batch["id"]))
            connection.execute("UPDATE agent_dag_approvals SET state='cancelled' WHERE batch_id=? AND state='ready'",
                               (batch["id"],))
        # pylint: disable-next=protected-access  # reason: preserve the registry's owner-scoped public projection
        return self.batches._describe(self.batches._row(batch["id"]))

    def _approve(self, batch: dict, request: dict) -> dict:
        note = request["note"]
        if not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise AgentTaskError("DAG continuation requires a bounded nonempty review note")
        selected = _decisions(request["decisions"], batch)
        if selected is None:
            raise AgentTaskError("DAG continuation approval requires explicit decisions for every node")
        plan_hash = request_spec_digest({"decisions": selected, "actor": self.actor})
        with self.batches.runtime.store.connection() as connection:
            previous = connection.execute("SELECT id,state FROM agent_dag_approvals "
                "WHERE batch_id=? AND source_snapshot=? AND plan_hash=?",
                (batch["id"], request["snapshot"], plan_hash)).fetchone()
        if previous is not None:
            return {"batch_id": batch["id"], "approval_id": previous["id"], "approval_state": previous["state"]}
        if batch["state"] != "waiting_review":
            raise AgentTaskError("DAG continuation approval requires a stopped batch")
        review = self._gather(self._baseline(batch), request["decisions"], request.get("timeout_seconds", 30))
        if review["public"]["snapshot"] != request["snapshot"] or not review["public"]["can_approve"]:
            raise AgentTaskError("DAG continuation evidence or decisions changed; review again")
        identifier = uuid.uuid4().hex
        details = {**review, "note": note, "actor": self.actor}
        with self.batches.runtime.store.connection(write=True) as connection:
            connection.execute("INSERT INTO agent_dag_approvals VALUES (?,?,?,?,?,?,?)",
                (identifier, batch["id"], request["snapshot"], plan_hash, json.dumps(details), "ready", time.time()))
            self._apply(connection, batch, identifier, review["reports"])
            connection.execute("UPDATE agent_dag_batches SET state='approved',attempt='',updated=? WHERE id=?",
                               (time.time(), batch["id"]))
        return {"batch_id": batch["id"], "approval_id": identifier, "approval_state": "ready"}

    @staticmethod
    def _apply(connection: Any, batch: dict, identifier: str, reports: list[dict]) -> None:
        for report in reports:
            decision = report["decision"]
            node_id = decision["node_id"]
            if decision["action"] == "dispatch":
                task = bound_node(batch, node_id)["task"]
                task["spec"] = decision["spec"]
                task["idempotency_key"] = "dag:" + request_spec_digest({"approval": identifier, "node": node_id})
                connection.execute("INSERT OR REPLACE INTO agent_dag_bindings VALUES (?,?,?)",
                                   (batch["id"], node_id, json.dumps(task)))
            else:
                receipt = {"outcome": "completed", "task_id": decision["task_id"]}
                connection.execute("UPDATE agent_dag_nodes SET phase='confirmed',receipt=?,updated=? "
                                   "WHERE batch_id=? AND node_id=?",
                                   (json.dumps(receipt), time.time(), batch["id"], node_id))
                connection.execute("INSERT OR REPLACE INTO agent_dag_adoptions VALUES (?,?,?,?,?)",
                    (batch["id"], node_id, decision["task_id"], report["original"]["task_id"], identifier))

    def _start(self, batch: dict, request: dict) -> dict:
        with self.batches.runtime.store.connection() as connection:
            row = connection.execute("SELECT * FROM agent_dag_approvals WHERE id=? AND batch_id=?",
                                     (request["approval_id"], batch["id"])).fetchone()
        if row is None or row["state"] != "ready" or batch["state"] != "approved":
            raise AgentTaskError("DAG continuation approval was consumed or cancelled")
        details = json.loads(row["details"])
        self._start_context(batch, request, details)
        review = self._gather(details["baseline"], details["public"]["decisions"], request.get("timeout_seconds", 30))
        if review["public"]["snapshot"] != row["source_snapshot"] or not review["public"]["can_approve"]:
            raise AgentTaskError("DAG continuation evidence changed after approval")
        attempt = uuid.uuid4().hex
        with self.batches.runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE agent_dag_approvals SET state='used' WHERE id=?", (row["id"],))
            connection.execute("UPDATE agent_dag_batches SET state='running',attempt=?,updated=? WHERE id=?",
                               (attempt, time.time(), batch["id"]))
        adopted = {item["decision"]["node_id"]: item["decision"]["task_id"] for item in review["reports"]
                   if item["decision"]["action"] != "dispatch"}
        return {"batch_id": batch["id"], "attempt": attempt, "hosts": batch["hosts"], "adopted": adopted,
                "definition": bind_definition(batch["definition"], batch["id"], batch["graph_hash"], batch["bindings"])}

    def _start_context(self, batch: dict, request: dict, details: dict) -> None:
        parallel = request["max_parallel"]
        if (details["actor"] != self.actor or not isinstance(parallel, int) or isinstance(parallel, bool)
                or parallel != batch["max_parallel"]):
            raise AgentTaskError("DAG continuation actor or parallelism changed")

    def validate_node(self, batch: dict, node_id: str, attempt: str) -> dict:
        """Recheck adopted dependency evidence under the active attempt without dispatch or input."""
        if batch["state"] != "running" or batch["attempt"] != attempt:
            raise AgentTaskError("DAG continuation attempt is inactive")
        with self.batches.runtime.store.connection() as connection:
            adoption = connection.execute("SELECT * FROM agent_dag_adoptions WHERE batch_id=? AND node_id=?",
                                          (batch["id"], node_id)).fetchone()
        if adoption is None:
            raise AgentTaskError("DAG node has no explicit adoption")
        try:
            self._validate_adoption(batch, node_id, dict(adoption))
        except AgentTaskError:
            with self.batches.runtime.store.connection(write=True) as connection:
                receipt = json.dumps({"outcome": "requires_review", "task_id": adoption["task_id"]})
                connection.execute("UPDATE agent_dag_nodes SET phase='unknown',receipt=?,updated=? "
                                   "WHERE batch_id=? AND node_id=?",
                                   (receipt, time.time(), batch["id"], node_id))
            raise
        return {"outcome": "completed", "task_id": adoption["task_id"],
                "task_state": "succeeded", "input_released": True}

    def _validate_adoption(self, batch: dict, node_id: str, adoption: dict) -> None:
        node = bound_node(batch, node_id)
        evidence = ContinuationEvidence(batch, runtime=self.batches.runtime)
        original = evidence.original(node)
        if original is None or original.get("task_id") != adoption["source_task"]:
            raise AgentTaskError("DAG adoption source identity changed")
        if adoption["task_id"] == adoption["source_task"]:
            completion(original, node)
        else:
            evidence.successor(node, original, adoption["task_id"])
