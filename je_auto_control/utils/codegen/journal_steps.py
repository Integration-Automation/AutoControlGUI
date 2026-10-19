"""Reconcile lifecycle snapshots and retain parent hierarchy without inferring successful actions."""
from dataclasses import dataclass
from typing import Optional

from je_auto_control.utils.action_journal.events import ActionEvent
from je_auto_control.utils.codegen.candidate_models import CandidateGenerationError
from je_auto_control.utils.codegen.journal_source import JournalRow, JournalSource

_INPUT_FIELDS = ("run_id", "step_id", "command", "parameters", "started_at", "parent_id", "device_id", "session_id")


@dataclass(frozen=True)
class JournalStep:
    """One invocation with at most one durable start and one durable terminal snapshot."""

    rows: tuple[JournalRow, ...]

    @property
    def event(self) -> ActionEvent:
        """Use terminal status when present, never treating a start as completion."""
        return self.rows[-1].event

    @property
    def started(self) -> Optional[JournalRow]:
        """A completion-only external/partial journal has no proven start snapshot."""
        return self.rows[0] if self.rows[0].event.status == "incomplete" else None

    def evidence(self) -> dict[str, object]:
        """Return source indices and categorical status without opaque outcomes/errors."""
        return {"step_id": self.event.step_id, "parent_id": self.event.parent_id,
                "command": self.event.command, "status": self.event.status,
                "sequences": [row.event.sequence for row in self.rows],
                "line_numbers": [row.line for row in self.rows], "emission": "excluded", "reasons": [],
                "retry_attempts": None}


def reconcile(source: JournalSource) -> dict[str, JournalStep]:
    """Reject duplicate/mutated lifecycle records, invalid parent spans and cyclic/deep hierarchies."""
    grouped: dict[str, list[JournalRow]] = {}
    for row in source.rows:
        grouped.setdefault(row.event.step_id, []).append(row)
        if len(grouped) > 10000:
            raise CandidateGenerationError("selected run exceeds 10000 steps")
    steps = {}
    for identity, rows in grouped.items():
        _lifecycle(rows)
        steps[identity] = JournalStep(tuple(rows))
    for step in steps.values():
        _parents(step, steps)
    return steps


def _lifecycle(rows: list[JournalRow]) -> None:
    if len(rows) == 1:
        return
    if len(rows) != 2 or rows[0].event.status != "incomplete" or rows[1].event.status == "incomplete":
        raise CandidateGenerationError("duplicate or reversed journal step lifecycle")
    first, last = (row.event for row in rows)
    if any(getattr(first, key) != getattr(last, key) for key in _INPUT_FIELDS):
        raise CandidateGenerationError("journal completion changed its source inputs")


def _parents(step: JournalStep, steps: dict[str, JournalStep]) -> None:
    seen = {step.event.step_id}
    child = step
    while child.event.parent_id in steps:
        parent = steps[child.event.parent_id]
        if parent.event.step_id in seen or len(seen) >= 64:
            raise CandidateGenerationError("cyclic or over-deep journal parent hierarchy")
        seen.add(parent.event.step_id)
        if parent.started is not None and parent.started.event.sequence >= child.rows[0].event.sequence:
            raise CandidateGenerationError("journal child precedes its parent's start")
        if parent.event.status != "incomplete" and child.event.sequence >= parent.event.sequence:
            raise CandidateGenerationError("journal child extends past its parent's completion")
        child = parent
