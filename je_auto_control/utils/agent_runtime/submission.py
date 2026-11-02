"""Admission witnesses bind tagged DAG requests before live scope normalization, without granting authority."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.models import AgentTaskSpec


@dataclass(frozen=True)
class TaskAdmission:
    """Trusted store envelope keeps request identity in the same transaction as task acceptance."""

    spec: dict
    submitted_digest: str
    dag: dict | None = None


def submitted_digest(value: AgentTaskSpec | Mapping[str, Any]) -> str:
    """Hash the full closed request with defaults, without interpreting destination paths or live authority."""
    spec = value if isinstance(value, AgentTaskSpec) else AgentTaskSpec.from_dict(value)
    return hashlib.sha256(json.dumps(spec.to_dict(), sort_keys=True).encode()).hexdigest()


def submission_metadata(store: Any, identifier: str) -> dict:
    """Expose historical request identity only; absence never invents a witness for a legacy task."""
    with store.connection() as connection:
        row = connection.execute("SELECT s.spec_digest,a.batch_id,a.node_id,a.actor FROM agent_task_submissions s "
                                 "LEFT JOIN agent_dag_local_tasks a ON a.task_id=s.task_id WHERE s.task_id=?",
                                 (identifier,)).fetchone()
    if row is None:
        return {}
    result: dict[str, Any] = {"submission_contract": 1, "submitted_spec_digest": row[0]}
    if row["batch_id"] is not None:
        actor = json.loads(row["actor"])
        result["local_dag_admission"] = {"contract": 1, "batch_id": row["batch_id"], "node_id": row["node_id"],
                                         "actor": actor.get("user_id", "local")}
    return result
