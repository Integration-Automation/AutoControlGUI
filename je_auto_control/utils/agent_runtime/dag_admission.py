"""Trusted local DAG admission records bind original ownership, caller authority and a live attempt."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentTaskError, AgentHumanReview
from je_auto_control.utils.agent_runtime.models import detached
from je_auto_control.utils.agent_runtime.policy import owns_task
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

_ADMISSION: ContextVar[dict | None] = ContextVar("agent_local_dag_admission", default=None)


@contextmanager
def admission_scope(value: dict) -> Iterator[None]:
    """Carry service-authored evidence only across the synchronous task acceptance transaction."""
    binding = _ADMISSION.set(detached(value))
    try:
        yield
    finally:
        _ADMISSION.reset(binding)


def current_admission() -> dict | None:
    """Return a detached trusted envelope; model-visible spec options cannot create admission evidence."""
    value = _ADMISSION.get()
    return detached(value) if value is not None else None


def actor_identity(value: dict) -> tuple[Any, Any]:
    """Use the real user-store namespace without freezing a user's changing role."""
    return value.get("user_id"), value.get("store_path")


def bind_admission(connection: Any, task_id: str, admission: Any, *, create: bool) -> None:
    """Bind admission atomically or verify an exact previous binding, never backfilling old tasks."""
    value = getattr(admission, "dag", None)
    if value is None:
        return
    if value["spec_digest"] != admission.submitted_digest:
        raise AgentTaskError("local DAG admission specification differs from its trusted submission witness")
    row = connection.execute("SELECT * FROM agent_dag_local_tasks WHERE task_id=?", (task_id,)).fetchone()
    if row is not None:
        fields = ("batch_id", "node_id", "attempt", "spec_digest")
        if (any(row[key] != value[key] for key in fields)
                or actor_identity(json.loads(row["actor"])) != actor_identity(value["actor"])):
            raise AgentTaskError("local DAG task admission differs from the accepted binding")
        return
    if not create:
        raise AgentTaskError("local DAG admission cannot adopt a request without trusted admission evidence")
    connection.execute("INSERT INTO agent_dag_local_tasks VALUES (?,?,?,?,?,?,?)",
        (task_id, value["batch_id"], value["node_id"], value["attempt"], json.dumps(value["actor"]),
         value["spec_digest"], time.time()))


def check_admission(runtime: Any, task_id: str) -> None:
    """Revalidate live graph/claim, original owner and actual actor before managed input."""
    with runtime.store.connection() as connection:
        row = connection.execute("SELECT a.*,b.owner,b.state,b.attempt AS active_attempt,n.phase "
            "FROM agent_dag_local_tasks a JOIN agent_dag_batches b ON b.id=a.batch_id "
            "JOIN agent_dag_nodes n ON n.batch_id=a.batch_id AND n.node_id=a.node_id "
            "WHERE a.task_id=?", (task_id,)).fetchone()
    if row is None:
        return
    if row["state"] != "running" or row["attempt"] != row["active_attempt"] or row["phase"] != "claimed":
        raise AgentHumanReview("local DAG task attempt or delivery claim requires review")
    owner = json.loads(row["owner"])
    actor = json.loads(row["actor"])
    authority = DeferredAuthorization(AuthorizationContext(**actor) if actor else None)
    with authority.scope():
        if not owns_task(owner, current_authorization()):
            raise AuthorizationError("local DAG caller can no longer manage the original owner's work")
    with DeferredAuthorization(AuthorizationContext(**owner) if owner else None).scope():
        pass
