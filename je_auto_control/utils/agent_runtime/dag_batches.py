"""Owner-scoped graph lifecycle and runtime-owned task/artifact host adapters."""
from __future__ import annotations

from contextlib import nullcontext
import json
import time
import uuid
from typing import Any

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached
from je_auto_control.utils.agent_runtime.policy import durable_payload, owns_task, TaskPolicy
from je_auto_control.utils.agent_runtime.submission import submitted_digest
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.agent_runtime.dag_batch_recording import (
    bound_node, claim_node, record_node, verify_node, validate_receipt,
)
from je_auto_control.utils.agent_runtime.dag_continuation import DagContinuation, FIELDS as CONTINUATION_FIELDS
from je_auto_control.utils.agent_runtime.dag_jobs import delivery_status
from je_auto_control.utils.agent_runtime.local_evidence import runtime_evidence_scope
from je_auto_control.utils.agent_runtime.dag_local import DagLocalTasks
from je_auto_control.utils.dag.batch_contract import batch_definition, bind_definition
from je_auto_control.utils.dag.inspection import inspect_definition
from je_auto_control.utils.dag.managed_tasks import (
    task_host_binding, registered_transfer_private_files, registered_transfer_binding, registered_host_transfer,
)
from je_auto_control.utils.rbac.authorization import AuthorizationContext, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

OPERATIONS = ("register", "get", "list", "begin", "claim", "record", "finish", "inspect",
              "run_background", "local_task") + tuple(CONTINUATION_FIELDS)
_FIELDS = {"register": {"definition"}, "get": {"batch_id"}, "list": set(),
           "begin": {"batch_id", "definition", "max_parallel"}, "claim": {"batch_id", "attempt", "node_id"},
           "record": {"batch_id", "attempt", "node_id", "receipt"}, "finish": {"batch_id", "attempt"},
           "inspect": {"batch_id"}, "run_background": {"batch_id", "definition", "max_parallel"},
           "local_task": {"batch_id", "attempt", "node_id", "operation", "body"}}
_FIELDS.update(CONTINUATION_FIELDS)


def _request(operation: Any, value: Any) -> dict:
    request = durable_payload(detached({} if value is None else value))
    if operation not in OPERATIONS or not isinstance(request, dict):
        raise AgentTaskError("invalid batch operation or request")
    optional = {"max_parallel"} if operation == "register" else set()
    if operation in {"review_continuation", "approve_continuation"}:
        optional |= {"decisions", "timeout_seconds"}
    if operation == "start_continuation":
        optional |= {"timeout_seconds"}
    if operation == "run_background":
        optional |= {"approval_id", "timeout_seconds"}
    if not _FIELDS[operation] <= set(request) or set(request) - _FIELDS[operation] - optional:
        raise AgentTaskError("invalid batch operation fields")
    return request


def _matching_handoff_submission(value: Any, accepted: dict, source: dict, expected: str) -> bool:
    return (value is not None and value['spec_digest'] == expected
            and accepted['spec_hash'] == request_spec_digest(source['spec']))


# pylint: disable-next=too-few-public-methods  # reason: one closed protocol entry point owns durable batch operations
class DagBatches:
    """Persist original graph/owner and pre-delivery claims; never infer continuation from lookup absence."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    @staticmethod
    def transfer_private_files() -> tuple:
        """Supply current host-owned credential paths without initializing a console or service."""
        return registered_transfer_private_files()

    def transfer_binding(self, host: str) -> str:
        """Pin a current registered transfer host only while this runtime remains available."""
        self.runtime.transfers.source.host.check_open()
        binding = registered_transfer_binding(host)
        self.runtime.transfers.source.host.check_open()
        return binding

    def transfer_call(self, host: str, binding: str, path: str, body: dict, timeout: float) -> dict:
        """Keep registered transfer I/O behind this runtime's existing host-owned adapter boundary."""
        self.runtime.transfers.source.host.check_open()
        result = registered_host_transfer(host, binding, path, body, timeout)
        self.runtime.transfers.source.host.check_open()
        return result

    def handoff_context(self, batch_id: str, node_id: str, *, origin_policies: list[str] | None = None,
                        connection: Any = None, identity_only: bool = False) -> dict:
        """Derive a local evidence recipient from a real original request and private DAG admission."""
        batch = self._row(batch_id, connection=connection)
        node = bound_node(batch, node_id)
        if node['host'] != 'local':
            raise AgentTaskError('local handoffs cannot authorize a remote destination')
        source, admission, expected = self._handoff_source(batch, node, connection=connection)
        policy = None if identity_only else self.handoff_policy(source, origin_policies)
        binding = {'batch_id': batch_id, 'node_id': node_id, 'graph_hash': batch['graph_hash'],
                   'source_task': source['id'], 'source_spec_digest': expected, 'owner': batch['owner'],
                   'request': request_spec_digest(node['task']), 'admission': admission}
        return {'binding': binding, 'source': source, 'state': batch['state'], 'policy': policy}

    def handoff_policy(self, source: dict, origin_policies: list[str] | None = None) -> TaskPolicy:
        """Preserve original effect policy for grants without a privately reviewed completion renewal."""
        policy_spec = detached(source['spec'])
        if origin_policies is not None:
            options = policy_spec['options']
            options['origin_policies'] = sorted(set(options.get('origin_policies', [])) | set(origin_policies))
        # pylint: disable-next=protected-access  # reason: original and issuing-session ceilings cover every actual effect
        return TaskPolicy(self.runtime._validated_spec(policy_spec))

    def _handoff_source(self, batch: dict, node: dict, *, connection: Any = None) -> tuple[dict, dict, str]:
        owner = batch['owner']
        transaction = self.runtime.store.connection() if connection is None else nullcontext(connection)
        with transaction as active_connection:
            with DeferredAuthorization(AuthorizationContext(**owner) if owner else None).scope():
                original = self.runtime.store.request_record(owner, node['task']['idempotency_key'],
                                                              connection=active_connection)
            if original is None:
                raise AgentTaskError('handoff original DAG request evidence is unavailable')
            source = self.runtime.store.read_task(active_connection, original['task_id'])
            found = active_connection.execute('SELECT * FROM agent_dag_local_tasks WHERE task_id=?',
                                               (source['id'],)).fetchone()
            submitted = active_connection.execute('SELECT spec_digest FROM agent_task_submissions WHERE task_id=?',
                                                   (source['id'],)).fetchone()
        expected = submitted_digest(node['task']['spec'])
        if (found is None or (found['batch_id'], found['node_id'], found['spec_digest'])
                != (batch['id'], node['id'], expected)
                or not _matching_handoff_submission(submitted, original, source, expected)):
            raise AgentTaskError('handoff requires the real bound local DAG admission and submission witness')
        if any(owner.get(key) != source['owner'].get(key) for key in ('user_id', 'store_path')):
            raise AgentTaskError('handoff original source owner differs from its batch')
        return source, dict(found), expected

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
                with runtime_evidence_scope(self.runtime):
                    if operation == "local_task":
                        return DagLocalTasks(self.runtime, batch, request, DeferredAuthorization.capture()).control()
                    return self._existing(operation, batch, request)

    def _existing(self, operation: str, batch: dict, request: dict) -> dict:
        if operation == "get":
            return self._describe(batch)
        owner = AuthorizationContext(**batch["owner"]) if batch["owner"] else None
        if operation == "inspect":
            definition = bind_definition(batch["definition"], batch["id"], batch["graph_hash"], batch["bindings"])
            with DeferredAuthorization(owner).scope():
                result = inspect_definition(definition)
            return {**result, "batch_id": batch["id"], "graph_hash": batch["graph_hash"], "batch_state": batch["state"]}
        identity = current_authorization()
        actor = ({"user_id": identity.user_id, "role": identity.role,
                  "namespace": request_spec_digest({"store": identity.store_path})}
                 if identity else {"user_id": "local"})
        continuation = DagContinuation(self, actor)
        if operation in {"pause_batch", "run_background"}:
            return (continuation.control(operation, batch, request) if operation == "pause_batch"
                    else self._background(batch, request, continuation))
        with DeferredAuthorization(owner).scope():
            if operation in CONTINUATION_FIELDS:
                return continuation.control(operation, batch, request)
            if operation == "begin":
                return self._begin(batch, request)
            return self._execution(operation, batch, request)

    def _background(self, batch: dict, request: dict, continuation: DagContinuation) -> dict:
        jobs = getattr(self.runtime, "background_dags", None)
        if jobs is None:
            raise AgentTaskError("background DAG execution requires an explicitly started service")
        jobs.ensure_available()
        actor = DeferredAuthorization.capture()
        owner = AuthorizationContext(**batch["owner"]) if batch["owner"] else None
        with DeferredAuthorization(owner).scope():
            started = (continuation.control("start_continuation", batch, request) if "approval_id" in request
                       else self._begin(batch, request))
        jobs.enqueue(started, batch["owner"], actor)
        return self._describe(self._row(batch["id"]))

    def stop_all(self) -> None:
        """Fence visible active/approved coordinators before stop-all snapshots destination tasks."""
        with self.runtime.store.connection() as connection:
            rows = connection.execute("SELECT id,owner FROM agent_dag_batches "
                                      "WHERE state IN ('running','approved')").fetchall()
        for row in rows:
            if owns_task(json.loads(row["owner"]), current_authorization()):
                self.control("pause_batch", {"batch_id": row["id"]})

    def _row(self, identifier: str, *, connection: Any = None) -> dict:
        # pylint: disable-next=protected-access  # reason: closed runtimes cannot accept new coordinator work
        if self.runtime._closed:
            raise AgentTaskError("runtime is closed")
        transaction = self.runtime.store.connection() if connection is None else nullcontext(connection)
        with transaction as active_connection:
            row = active_connection.execute("SELECT * FROM agent_dag_batches WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise AgentTaskError("batch does not exist or belongs to another caller")
            batch = dict(row)
            for key in ("owner", "definition", "hosts"):
                batch[key] = json.loads(batch[key])
            if not owns_task(batch["owner"], current_authorization()):
                raise AgentTaskError("batch does not exist or belongs to another caller")
            if request_spec_digest(batch["definition"]) != batch["graph_hash"]:
                raise AgentTaskError("batch graph digest mismatch")
            rows = active_connection.execute("SELECT node_id,task FROM agent_dag_bindings WHERE batch_id=?",
                                             (identifier,))
            batch["bindings"] = {item["node_id"]: json.loads(item["task"]) for item in rows}
            original = active_connection.execute("SELECT definition FROM agent_dag_inputs WHERE batch_id=?",
                                                 (identifier,)).fetchone()
        batch["input_definition"] = json.loads(original[0]) if original is not None else batch["definition"]
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
        original = batch_definition(request["definition"])
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
            connection.execute("INSERT INTO agent_dag_inputs VALUES (?,?)", (identifier, json.dumps(original)))
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
            approvals = [dict(row) for row in connection.execute(
                "SELECT id,state,source_snapshot,details,created FROM agent_dag_approvals "
                "WHERE batch_id=? ORDER BY created DESC LIMIT 50", (batch["id"],))]
        continuations = []
        for row in approvals:
            details = json.loads(row.pop("details"))
            continuations.append({**row, "actor": details["actor"]["user_id"], "note": details["note"],
                                  "decisions": details["public"]["decisions"]})
        return {"batch_id": batch["id"], "graph_hash": batch["graph_hash"], "definition": batch["definition"],
                "input_definition": batch["input_definition"],
                "continuations": continuations,
                "background": delivery_status(self.runtime, batch["id"]),
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
        return {"batch_id": batch["id"], "attempt": attempt, "hosts": hosts, "max_parallel": batch["max_parallel"],
                "definition": bind_definition(definition, batch["id"], batch["graph_hash"])}

    def _execution(self, operation: str, batch: dict, request: dict) -> dict:
        if batch["state"] != "running" or request["attempt"] != batch["attempt"]:
            raise AgentTaskError("batch execution attempt is inactive")
        if operation == "claim":
            self._validate_adopted_dependencies(batch, request)
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

    def _validate_adopted_dependencies(self, batch: dict, request: dict) -> None:
        node = bound_node(batch, request["node_id"])
        with self.runtime.store.connection() as connection:
            adopted = {row[0] for row in connection.execute(
                "SELECT node_id FROM agent_dag_adoptions WHERE batch_id=?", (batch["id"],))}
        continuation = DagContinuation(self, {})
        for dependency in node["depends_on"]:
            if dependency in adopted:
                continuation.validate_node(batch, dependency, request["attempt"])
