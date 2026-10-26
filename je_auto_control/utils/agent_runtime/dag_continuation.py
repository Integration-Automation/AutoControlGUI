"""Whole-graph review and one-shot continuation approval never replay a possible delivery."""
from __future__ import annotations

import json
from contextlib import nullcontext
import time
import uuid
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached, positive
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.agent_runtime.dag_batch_recording import bound_node
from je_auto_control.utils.agent_runtime.dag_continuation_evidence import ContinuationEvidence, completion
from je_auto_control.utils.agent_runtime.dag_continuation_plan import dispatch_template, validate_decision
from je_auto_control.utils.agent_runtime.dag_transfer_checks import DagTransferChecks, remote_reports
from je_auto_control.utils.agent_runtime.dag_transfer_stop import pause_dependents
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


def _deadline(request: dict) -> float:
    timeout = request.get('timeout_seconds', 30)
    positive(timeout, 'DAG continuation timeout_seconds', 300)
    return time.monotonic() + timeout


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
            connection.execute("UPDATE agent_dag_approvals SET state='cancelled' WHERE batch_id=? "
                               "AND state IN ('ready','provisional','starting')",
                               (batch["id"],))
        # pylint: disable-next=protected-access  # reason: preserve the registry's owner-scoped public projection
        return self.batches._describe(self.batches._row(batch["id"]))

    def _approve(self, batch: dict, request: dict) -> dict:
        deadline = _deadline(request)
        note = request["note"]
        if not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise AgentTaskError("DAG continuation requires a bounded nonempty review note")
        selected = _decisions(request["decisions"], batch)
        if selected is None:
            raise AgentTaskError("DAG continuation approval requires explicit decisions for every node")
        plan_hash = request_spec_digest({"decisions": selected, "actor": self.actor})
        with self.batches.runtime.store.connection() as connection:
            previous = connection.execute("SELECT id,state,details FROM agent_dag_approvals "
                "WHERE batch_id=? AND source_snapshot=? AND plan_hash=?",
                (batch["id"], request["snapshot"], plan_hash)).fetchone()
        if previous is not None:
            if previous['state'] == 'provisional':
                return self._resume_approval(batch, request, dict(previous), deadline)
            return {"batch_id": batch["id"], "approval_id": previous["id"], "approval_state": previous["state"]}
        if batch["state"] != "waiting_review":
            raise AgentTaskError("DAG continuation approval requires a stopped batch")
        review = self._gather(self._baseline(batch), request["decisions"], request.get("timeout_seconds", 30))
        if review["public"]["snapshot"] != request["snapshot"] or not review["public"]["can_approve"]:
            raise AgentTaskError("DAG continuation evidence or decisions changed; review again")
        return self._save_approval(batch, request, review, plan_hash, deadline)

    def _save_approval(self, batch: dict, request: dict, review: dict, plan_hash: str, deadline: float) -> dict:
        identifier = uuid.uuid4().hex
        details = {**review, "note": request['note'], "actor": self.actor}
        checks = (DagTransferChecks(self.batches.runtime.store, batch,
            lambda: self._remote_checks(batch, review['reports'], deadline), baseline=review['baseline'])
            if remote_reports(batch, review['reports']) else None)
        with (self.batches.runtime.transfers.activity() if checks is not None else nullcontext()):
            with self.batches.runtime.store.connection(write=True) as connection:
                connection.execute("INSERT INTO agent_dag_approvals VALUES (?,?,?,?,?,?,?)",
                    (identifier, batch["id"], request["snapshot"], plan_hash, json.dumps(details),
                     'provisional' if checks is not None else 'ready', time.time()))
                if checks is None:
                    self._commit_approval(connection, batch, identifier, review['reports'])
                else:
                    checks.pin(connection, identifier)
            if checks is not None:
                checks.finish(identifier, 'provisional', lambda connection:
                              self._commit_approval(connection, batch, identifier, review['reports']))
        return {"batch_id": batch["id"], "approval_id": identifier, "approval_state": "ready"}

    def _commit_approval(self, connection: Any, batch: dict, identifier: str, reports: list) -> None:
        self._apply(connection, batch, identifier, reports)
        connection.execute("UPDATE agent_dag_approvals SET state='ready' WHERE id=?", (identifier,))
        connection.execute("UPDATE agent_dag_batches SET state='approved',attempt='',updated=? WHERE id=?",
                           (time.time(), batch['id']))
        self._handoff_checks(connection, batch, reports)

    def _resume_approval(self, batch: dict, request: dict, previous: dict, deadline: float) -> dict:
        details = json.loads(previous['details'])
        if batch['state'] != 'waiting_review' or details['actor'] != self.actor or details['note'] != request['note']:
            raise AgentTaskError('provisional adoption requires its original explicit approval request')
        checks = DagTransferChecks(self.batches.runtime.store, batch,
            lambda: self._remote_checks(batch, details['reports'], deadline), baseline=details['baseline'])
        with self.batches.runtime.transfers.activity():
            with self.batches.runtime.store.connection() as connection:
                checks.pin(connection, previous['id'])
            checks.finish(previous['id'], 'provisional', lambda connection:
                          self._commit_approval(connection, batch, previous['id'], details['reports']))
        return {'batch_id': batch['id'], 'approval_id': previous['id'], 'approval_state': 'ready'}

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
        deadline = _deadline(request)
        with self.batches.runtime.store.connection() as connection:
            row = connection.execute("SELECT * FROM agent_dag_approvals WHERE id=? AND batch_id=?",
                                     (request["approval_id"], batch["id"])).fetchone()
        if row is None or row["state"] != "ready" or batch["state"] != "approved":
            raise AgentTaskError("DAG continuation approval was consumed or cancelled")
        details = json.loads(row["details"])
        self._start_context(batch, request, details)
        baseline = self._baseline(batch) if remote_reports(batch, details['reports']) else None
        review = self._gather(details["baseline"], details["public"]["decisions"], request.get("timeout_seconds", 30))
        if review["public"]["snapshot"] != row["source_snapshot"] or not review["public"]["can_approve"]:
            raise AgentTaskError("DAG continuation evidence changed after approval")
        attempt = self._activate(batch, row['id'], review['reports'], deadline, baseline)
        adopted = {item["decision"]["node_id"]: item["decision"]["task_id"] for item in review["reports"]
                   if item["decision"]["action"] != "dispatch"}
        return {"batch_id": batch["id"], "attempt": attempt, "hosts": batch["hosts"], "adopted": adopted,
                "max_parallel": batch["max_parallel"],
                "definition": bind_definition(batch["definition"], batch["id"], batch["graph_hash"], batch["bindings"])}

    def _activate(self, batch: dict, identifier: str, reports: list, deadline: float, baseline: dict | None) -> str:
        attempt = uuid.uuid4().hex
        checks = (DagTransferChecks(self.batches.runtime.store, batch,
            lambda: self._remote_checks(batch, reports, deadline), baseline=baseline)
            if remote_reports(batch, reports) else None)
        with (self.batches.runtime.transfers.activity() if checks is not None else nullcontext()):
            with self.batches.runtime.store.connection(write=True) as connection:
                if checks is not None:
                    checks.pin(connection, identifier)
                    checks.guard(connection, identifier, 'ready')
                    connection.execute("UPDATE agent_dag_approvals SET state='starting' WHERE id=?", (identifier,))
                else:
                    self._commit_start(connection, batch, identifier, attempt, reports)
            if checks is not None:
                checks.finish(identifier, 'starting', lambda connection:
                              self._commit_start(connection, batch, identifier, attempt, reports))
        return attempt

    def _commit_start(self, connection: Any, batch: dict, identifier: str, attempt: str, reports: list) -> None:
        connection.execute("UPDATE agent_dag_approvals SET state='used' WHERE id=?", (identifier,))
        connection.execute("UPDATE agent_dag_batches SET state='running',attempt=?,updated=? WHERE id=?",
                           (attempt, time.time(), batch['id']))
        self._handoff_checks(connection, batch, reports)

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
            if self._remote_grant(batch, node_id, dict(adoption)):
                nodes = bind_definition(
                    batch['definition'], batch['id'], batch['graph_hash'], batch['bindings'])['nodes']
                pause_dependents(self.batches.runtime, batch, node_id, nodes,
                                 ContinuationEvidence(batch, runtime=self.batches.runtime).connection)
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
            with self.batches.runtime.store.connection() as connection:
                approval = connection.execute('SELECT details FROM agent_dag_approvals WHERE id=? AND batch_id=?',
                    (adoption['approval_id'], batch['id'])).fetchone()
            if approval is None:
                raise AgentTaskError('DAG adoption approval evidence is missing')
            decisions = json.loads(approval[0])['public']['decisions']
            decision: dict = next((item for item in decisions if item['node_id'] == node_id), {})
            if 'handoff_id' in decision:
                evidence.successor(node, original, adoption['task_id'], decision['handoff_id'])
            else:
                evidence.successor(node, original, adoption['task_id'])

    def _remote_grant(self, batch: dict, node_id: str, adoption: dict) -> bool:
        if bound_node(batch, node_id)['host'] == 'local':
            return False
        with self.batches.runtime.store.connection() as connection:
            row = connection.execute('SELECT details FROM agent_dag_approvals WHERE id=? AND batch_id=?',
                (adoption['approval_id'], batch['id'])).fetchone()
        return row is not None and any(item['node_id'] == node_id and 'handoff_id' in item
            for item in json.loads(row['details'])['public']['decisions'])

    def _handoff_checks(self, connection: Any, batch: dict, reports: list[dict]) -> None:
        for report in reports:
            decision = report['decision']
            if 'handoff_id' in decision and bound_node(batch, decision['node_id'])['host'] == 'local':
                self.batches.runtime.recovery.handoff_evidence(batch['id'], decision['node_id'],
                    report['original']['task_id'], decision['task_id'], decision['handoff_id'], connection=connection)

    def _remote_checks(self, batch: dict, reports: list[dict], deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTaskError('remote adoption confirmation deadline expired')
        evidence = ContinuationEvidence(batch, remaining, self.batches.runtime)
        for report in remote_reports(batch, reports):
            decision = report['decision']
            node = bound_node(batch, decision['node_id'])
            current = validate_decision(self.batches.runtime, decision, node, 'claimed',
                                       evidence.original(node), evidence, '')
            if current != report:
                raise AgentTaskError('remote adoption evidence changed after its local provisional write')
