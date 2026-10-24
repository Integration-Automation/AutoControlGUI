"""Closed immutable managed-task payloads for existing DAG surfaces."""
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached, freeze, positive
from je_auto_control.utils.agent_runtime.verification import validate_criteria


def task_contract(value: Any) -> Mapping[str, Any]:
    """Validate without interpreting destination roots on the coordinator's filesystem."""
    data = detached(value)
    if not isinstance(data, dict) or not {"spec", "idempotency_key"} <= data.keys():
        raise AgentTaskError("DAG task requires spec and idempotency_key")
    if data.keys() - {"spec", "idempotency_key", "wait_seconds"}:
        raise AgentTaskError("unknown DAG task fields")
    key = data["idempotency_key"]
    if not isinstance(key, str) or not key.strip() or len(key) > 256:
        raise AgentTaskError("DAG task idempotency_key requires one to 256 characters")
    spec = AgentTaskSpec.from_dict(data["spec"])
    if spec.mode == "external":
        raise AgentTaskError("DAG task must use skill or explicitly configured local-model mode")
    validate_criteria(spec.success_criteria)
    wait = data.get("wait_seconds", min(86_400, spec.budget.wall_seconds + 30))
    positive(wait, "DAG task wait_seconds", 86_400)
    return freeze({"spec": spec.to_dict(), "idempotency_key": key, "wait_seconds": wait})
