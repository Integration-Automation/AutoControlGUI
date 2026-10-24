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


def submitted_digest(value: AgentTaskSpec | Mapping[str, Any]) -> str:
    """Hash the full closed request with defaults, without interpreting destination paths or live authority."""
    spec = value if isinstance(value, AgentTaskSpec) else AgentTaskSpec.from_dict(value)
    return hashlib.sha256(json.dumps(spec.to_dict(), sort_keys=True).encode()).hexdigest()


def submission_metadata(store: Any, identifier: str) -> dict:
    """Expose historical request identity only; absence never invents a witness for a legacy task."""
    with store.connection() as connection:
        row = connection.execute("SELECT spec_digest FROM agent_task_submissions WHERE task_id=?",
                                 (identifier,)).fetchone()
    return {"submission_contract": 1, "submitted_spec_digest": row[0]} if row is not None else {}
