"""A task's first action waits until a fresh observation passes every declared resume condition.

A successor resumes work another session started: a login, half-filled fields,
arranged windows. Its history cannot prove that state still holds, so a spec may
declare ``resume_conditions`` — the same clauses completion uses, limited to the
ones a fresh observation decides (``screen``, ``browser`` and the ``file_*``
checks). Until a task has any action receipt, an action is admitted only on an
observation for which every resume condition passed; a failed or unknown
condition leaves the task waiting for a person instead of acting.
"""
from __future__ import annotations

import threading
from typing import Any, Mapping, Sequence

from je_auto_control.utils.agent_runtime.errors import AgentHumanReview, AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.agent_runtime.verification import validate_criteria, verify_clauses

RESUME_KINDS = frozenset({"screen", "browser", "file_exists", "file_sha256", "file_text", "file_manifest"})
_REFUSED = "resume state is not re-established; observe again until every resume condition passes"


def validate_resume_conditions(conditions: Sequence[Mapping[str, Any]]) -> None:
    """Allow only clauses a fresh observation decides; receipts are history, never current state."""
    if len(conditions) > 32:
        raise AgentTaskError("a task may declare at most 32 resume conditions")
    for clause in conditions:
        if clause.get("kind") not in RESUME_KINDS:
            raise AgentTaskError("resume conditions must be screen, browser or file checks on fresh state")
    validate_criteria(conditions)


def validate_task_conditions(spec: AgentTaskSpec) -> None:
    """Validate completion criteria and resume conditions before a task is admitted."""
    validate_criteria(spec.success_criteria)
    validate_resume_conditions(spec.resume_conditions)


class ResumeGate:
    """Remember, per task, the one observation on which every resume condition last passed."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._mutex = threading.Lock()
        self._passed: dict[str, str] = {}
        self._reports: dict[str, list[dict[str, Any]]] = {}

    def _pending(self, row: Mapping[str, Any]) -> bool:
        return bool(row["spec"].get("resume_conditions")) and not self._store.actions(row["id"])

    def record(self, row: Mapping[str, Any], observation: Any, target: Any) -> None:
        """Evaluate resume conditions against this observation while the task still holds its lease."""
        if not self._pending(row):
            return
        spec = AgentTaskSpec.from_dict(row["spec"])
        reports = verify_clauses(spec.resume_conditions, TaskPolicy(spec), [], observation.data,
                                 browser_read=getattr(target, "verify_browser", None))
        with self._mutex:
            self._reports[row["id"]] = reports
            if all(item["status"] == "passed" for item in reports):
                self._passed[row["id"]] = observation.observation_id
            else:
                self._passed.pop(row["id"], None)

    def require(self, row: Mapping[str, Any], observation_id: str) -> None:
        """Refuse a first action unless its observation passed every resume condition."""
        if not self._pending(row):
            return
        with self._mutex:
            admitted = self._passed.get(row["id"]) == observation_id
            reports = list(self._reports.get(row["id"], []))
        if not admitted:
            self._store.update(row["id"], "waiting_user", reason=_REFUSED, verification=reports)
            raise AgentHumanReview(_REFUSED)
