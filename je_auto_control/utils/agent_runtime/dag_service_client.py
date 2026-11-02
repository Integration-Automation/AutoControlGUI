"""Runtime-bound batch coordination and destination calls refresh both approving and original owners."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.rbac.authorization import AuthorizationContext
from je_auto_control.utils.rbac.deferred import DeferredAuthorization


class DagServiceClient:
    """Never consult a process-global connection file for a service's local managed destinations."""

    def __init__(self, runtime: Any, delivery: dict) -> None:
        self.runtime, self.started = runtime, delivery["started"]
        self.owner = DeferredAuthorization(AuthorizationContext(**delivery["owner"]) if delivery["owner"] else None)
        self.actor = DeferredAuthorization(AuthorizationContext(**delivery["actor"]) if delivery["actor"] else None)

    def check(self) -> None:
        """Refresh the registrant and approver, and reject a fenced or replaced coordinator attempt."""
        with self.actor.scope(), self.owner.scope():
            with self.runtime.store.connection() as connection:
                row = connection.execute("SELECT state,attempt FROM agent_dag_batches WHERE id=?",
                                         (self.started["batch_id"],)).fetchone()
        if row is None or row["state"] != "running" or row["attempt"] != self.started["attempt"]:
            raise AgentTaskError("background DAG attempt is inactive")

    def call(self, operation: str, body: dict | None = None, *, timeout: float = 30) -> dict:
        """Use only the closed coordinator protocol on this owning runtime."""
        del timeout
        if operation != "dag" or not isinstance(body, dict) or set(body) != {"operation", "request"}:
            raise AgentTaskError("background coordinator accepts only DAG operations")
        self.check()
        with self.actor.scope():
            return self.runtime.batches.control(body["operation"], body["request"])

    def task_call(self, operation: str, body: dict, timeout: float) -> dict:
        """Route finite destination operations locally; owned pause remains available for retirement."""
        del timeout
        if operation not in {"submit", "get", "lookup", "pause"}:
            raise AgentTaskError("unsupported local background DAG task operation")
        if operation != "pause":
            self.check()
        # pylint: disable-next=import-outside-toplevel  # reason: route dispatch depends on runtime construction
        from je_auto_control.utils.agent_runtime.routes import dispatch
        with self.owner.scope():
            return dispatch(self.runtime, operation, body, body.get("task_id"))

    def completed(self) -> bool:
        """Only the same finished durable attempt can settle this delivery as successful."""
        with self.runtime.store.connection() as connection:
            row = connection.execute("SELECT state,attempt FROM agent_dag_batches WHERE id=?",
                                     (self.started["batch_id"],)).fetchone()
        return row is not None and row["state"] == "succeeded" and row["attempt"] == self.started["attempt"]
