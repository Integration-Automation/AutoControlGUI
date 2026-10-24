"""Owner-scoped durable graph registration and one-shot managed batch execution records."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached
from je_auto_control.utils.agent_runtime.policy import durable_payload, owns_task
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.agent_runtime.dag_batch_recording import (
    bound_node, claim_node, record_node, verify_node, validate_receipt,
)
from je_auto_control.utils.dag.batch_contract import batch_definition, bind_definition
from je_auto_control.utils.dag.inspection import inspect_definition
from je_auto_control.utils.dag.managed_tasks import task_host_binding
from je_auto_control.utils.rbac.authorization import AuthorizationContext, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

OPERATIONS = ("register", "get", "list", "begin", "claim", "record", "finish", "inspect")
_FIELDS = {"register": {"definition"}, "get": {"batch_id"}, "list": set(),
           "begin": {"batch_id", "definition", "max_parallel"}, "claim": {"batch_id", "attempt", "node_id"},
           "record": {"batch_id", "attempt", "node_id", "receipt"}, "finish": {"batch_id", "attempt"},
           "inspect": {"batch_id"}}


def _request(operation: Any, value: Any) -> dict:
    request = durable_payload(detached({} if value is None else value))
    if operation not in OPERATIONS or not isinstance(request, dict):
        raise AgentTaskError("invalid batch operation or request")
    optional = {"max_parallel"} if operation == "register" else set()
    if not _FIELDS[operation] <= set(request) or set(request) - _FIELDS[operation] - optional:
        raise AgentTaskError("invalid batch operation fields")
    return request


# pylint: disable-next=too-few-public-methods  # reason: one closed protocol entry point owns durable batch operations
class DagBatches:
    """Persist original graph/owner and pre-delivery claims; never infer continuation from lookup absence."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def control(self, operation: str, request: Any = None) -> dict:
        """Operate on a closed batch protocol; inspection/registration never acquire an input target."""
        request = _request(operation, request)
        if current_operation() is not None:
            raise AgentTaskError("a managed task cannot coordinate other managed tasks")
        # pylint: disable-next=protected-access  # reason: a closed runtime may not register or deliver new batches
        if self.runtime._closed:
            raise AgentTaskError("runtime is closed")
        with DeferredAuthorization.capture().scope():
            if operation == "register":
                return self._register(request)
            if operation == "list":
                return self._list()
            identifier = request["batch_id"]
            if not isinstance(identifier, str):
                raise AgentTaskError("batch_id must be a string")
            # pylint: disable-next=protected-access  # reason: serialize this runtime's batch lifecycle transitions
            with self.runtime._lock("dag:" + identifier):
                batch = self._row(identifier)
                return self._existing(operation, batch, request)

    def _existing(self, operation: str, batch: dict, request: dict) -> dict:
        if operation == "get":
            return self._describe(batch)
        if operation == "inspect":
            definition = bind_definition(batch["definition"], batch["id"], batch["graph_hash"])
            result = inspect_definition(definition)
            return {**result, "batch_id": batch["id"], "graph_hash": batch["graph_hash"], "batch_state": batch["state"]}
        owner = AuthorizationContext(**batch["owner"]) if batch["owner"] else None
        with DeferredAuthorization(owner).scope():
            if operation == "begin":
                return self._begin(batch, request)
            return self._execution(operation, batch, request)

    def _row(self, identifier: str) -> dict:
        # pylint: disable-next=protected-access  # reason: closed runtimes cannot accept new coordinator work
        if self.runtime._closed:
            raise AgentTaskError("runtime is closed")
        with self.runtime.store.connection() as connection:
            row = connection.execute("SELECT * FROM agent_dag_batches WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise AgentTaskError("batch does not exist or belongs to another caller")
        batch = dict(row)
        for key in ("owner", "definition", "hosts"):
            batch[key] = json.loads(batch[key])
        if not owns_task(batch["owner"], current_authorization()):
            raise AgentTaskError("batch does not exist or belongs to another caller")
        if request_spec_digest(batch["definition"]) != batch["graph_hash"]:
            raise AgentTaskError("batch graph digest mismatch")
        return batch

    def _normalize(self, value: Any) -> tuple[dict, dict]:
        definition = batch_definition(value)
        hosts = {}
        for node in definition["nodes"]:
            host, spec = node["host"], node["task"]["spec"]
            if "dag_batch" in spec["options"]:
                raise AgentTaskError("caller-supplied batch tags are not accepted")
            if host == "local":
                # pylint: disable-next=protected-access  # reason: bind local authority before freezing the graph
                node["task"]["spec"] = self.runtime._validated_spec(spec).to_dict()
            elif "origin_policies" in spec["options"]:
                raise AgentTaskError("local origin witnesses cannot be sent to a remote batch host")
            hosts[host] = task_host_binding(host)
        return definition, hosts

    def _register(self, request: dict) -> dict:
        definition, hosts = self._normalize(request["definition"])
        parallel = request.get("max_parallel", 4)
        if isinstance(parallel, bool) or not isinstance(parallel, int) or not 1 <= parallel <= 64:
            raise AgentTaskError("batch max_parallel must be an integer from one to sixty-four")
        identifier, now = uuid.uuid4().hex, time.time()
        identity = current_authorization()
        owner = ({"user_id": identity.user_id, "role": identity.role,
                  "store_path": identity.store_path} if identity else {})
        with self.runtime.store.connection(write=True) as connection:
            connection.execute("INSERT INTO agent_dag_batches VALUES (?,?,?,?,?,?,?,?,?,?)",
                (identifier, json.dumps(owner), json.dumps(definition), request_spec_digest(definition),
                 json.dumps(hosts), parallel, "registered", "", now, now))
            for node in definition["nodes"]:
                connection.execute("INSERT INTO agent_dag_nodes VALUES (?,?,?,?,?)",
                                   (identifier, node["id"], "pending", "{}", now))
        return self._describe(self._row(identifier))

    def _list(self) -> dict:
        with self.runtime.store.connection() as connection:
            rows = connection.execute("SELECT id,owner FROM agent_dag_batches "
                                      "ORDER BY created DESC LIMIT 200").fetchall()
        return {"batches": [self._describe(self._row(row["id"])) for row in rows
                            if owns_task(json.loads(row["owner"]), current_authorization())]}

    def _describe(self, batch: dict) -> dict:
        with self.runtime.store.connection() as connection:
            rows = connection.execute("SELECT node_id,phase,receipt FROM agent_dag_nodes "
                                      "WHERE batch_id=? ORDER BY node_id", (batch["id"],)).fetchall()
        return {"batch_id": batch["id"], "graph_hash": batch["graph_hash"], "definition": batch["definition"],
                "max_parallel": batch["max_parallel"], "state": batch["state"], "resume_permitted": False,
                "nodes": [{"id": row["node_id"], "phase": row["phase"],
                           "receipt": json.loads(row["receipt"])} for row in rows]}

    def _begin(self, batch: dict, request: dict) -> dict:
        definition, hosts = self._normalize(request["definition"])
        if (request_spec_digest(definition) != batch["graph_hash"] or hosts != batch["hosts"]
                or not isinstance(request["max_parallel"], int) or isinstance(request["max_parallel"], bool)
                or request["max_parallel"] != batch["max_parallel"]):
            raise AgentTaskError("batch graph, host configuration or parallelism changed")
        attempt = uuid.uuid4().hex
        with self.runtime.store.connection(write=True) as connection:
            cursor = connection.execute("UPDATE agent_dag_batches SET state='running',attempt=?,updated=? "
                "WHERE id=? AND state='registered'", (attempt, time.time(), batch["id"]))
            if cursor.rowcount != 1:
                raise AgentTaskError("batch was already started; explicit recovery is required")
        return {"batch_id": batch["id"], "attempt": attempt, "hosts": hosts,
                "definition": bind_definition(definition, batch["id"], batch["graph_hash"])}

    def _execution(self, operation: str, batch: dict, request: dict) -> dict:
        if batch["state"] != "running" or request["attempt"] != batch["attempt"]:
            raise AgentTaskError("batch execution attempt is inactive")
        if operation == "record":
            receipt = validate_receipt(request["receipt"])
            if receipt["outcome"] == "completed":
                node = bound_node(batch, request["node_id"])
                verify_node(batch, node, receipt["task_id"])
        with self.runtime.store.connection(write=True) as connection:
            if operation == "claim":
                claim_node(connection, batch, request)
            elif operation == "record":
                record_node(connection, batch, request)
            else:
                unfinished = connection.execute("SELECT 1 FROM agent_dag_nodes WHERE batch_id=? AND phase!='confirmed'",
                                                (batch["id"],)).fetchone()
                state = "waiting_review" if unfinished else "succeeded"
                connection.execute("UPDATE agent_dag_batches SET state=?,updated=? WHERE id=?",
                                   (state, time.time(), batch["id"]))
        return self._describe(self._row(batch["id"]))
