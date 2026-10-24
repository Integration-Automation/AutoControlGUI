"""Bind server-side batch evidence to its owning runtime without global client discovery."""
from contextlib import contextmanager
from typing import Any, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.dag.managed_tasks import managed_runtime_scope
from je_auto_control.utils.rbac.deferred import DeferredAuthorization


@contextmanager
def runtime_evidence_scope(runtime: Any) -> Iterator[None]:
    """Keep actual caller checks while reading under the current original-owner scope."""
    caller = DeferredAuthorization.capture()

    def check() -> None:
        with caller.scope():
            pass

    def read(operation: str, body: dict, _timeout: float) -> dict:
        check()
        if operation == "lookup":
            return runtime.lookup(body["idempotency_key"], body.get("spec"))
        if operation == "get":
            return runtime.get(body["task_id"]).to_dict()
        raise AgentTaskError("local batch evidence accepts read-only lookup/get only")

    with managed_runtime_scope(read, check):
        yield
