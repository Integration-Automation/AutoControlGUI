"""Version-one action event records and strict wire-schema validation."""
from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Literal, Optional, cast

from je_auto_control.utils.exception.exceptions import AutoControlException

EventStatus = Literal["incomplete", "ok", "error", "cancelled", "skipped", "dry_run"]
_STATUSES = frozenset({"incomplete", "ok", "error", "cancelled", "skipped", "dry_run"})
OUTCOME_TYPES = frozenset({"none", "boolean", "integer", "number", "text", "object", "array", "unsupported"})


class ActionJournalError(AutoControlException, ValueError):
    """A journal event, schema or storage operation is invalid."""


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ActionJournalError("journal identifiers must be non-empty strings")
    return value


def _optional_text(value: object) -> Optional[str]:
    return None if value is None else _text(value)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2 ** 63 - 1:
        raise ActionJournalError("journal sequence/version must be a nonnegative 64-bit integer")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ActionJournalError("journal timestamps must be finite numbers")
    try:
        number = float(value)
    except OverflowError:
        raise ActionJournalError("journal timestamps must be finite numbers") from None
    if not math.isfinite(number):
        raise ActionJournalError("journal timestamps must be finite numbers")
    return number


def _optional_number(value: object) -> Optional[float]:
    return None if value is None else _number(value)


def _status(value: object) -> EventStatus:
    if not isinstance(value, str) or value not in _STATUSES:
        raise ActionJournalError("unknown journal action status")
    return cast(EventStatus, value)


def _parameters(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ActionJournalError("journal parameters must be a string-keyed object")
    return dict(value)


def _reasons(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ActionJournalError("non-replayable reasons must be a string list")
    return tuple(_text(item) for item in value)


@dataclass(frozen=True)
class ActionEvent:  # pylint: disable=too-many-instance-attributes  # reason: fixed versioned wire record
    """An action lifecycle snapshot; unfinished actions default to incomplete.

    ``sequence`` is assigned by storage under its interprocess lock. Start and
    completion snapshots reuse a step ID and receive separate append sequences.
    Parameters and outcomes are copied/sanitized at append time, never via repr.
    """

    run_id: str
    step_id: str
    command: str
    parameters: dict[str, object]
    started_at: float
    parent_id: Optional[str] = None
    finished_at: Optional[float] = None
    status: EventStatus = "incomplete"
    outcome: object = None
    outcome_type: Optional[str] = None
    error: Optional[str] = None
    artifact: Optional[str] = None
    device_id: Optional[str] = None
    session_id: Optional[str] = None
    sequence: int = 0
    schema_version: int = 1
    non_replayable: tuple[str, ...] = ()

    def validate(self) -> None:
        """Reject malformed metadata before storage opens or creates any file."""
        for identifier in (self.run_id, self.step_id, self.command):
            _text(identifier)
        for metadata in (self.parent_id, self.error, self.artifact, self.device_id, self.session_id):
            _optional_text(metadata)
        if _integer(self.schema_version) != 1:
            raise ActionJournalError("unsupported action journal schema version")
        _integer(self.sequence)
        _parameters(self.parameters)
        _reasons(self.non_replayable)
        outcome_type = _optional_text(self.outcome_type)
        if outcome_type is not None and outcome_type not in OUTCOME_TYPES:
            raise ActionJournalError("unknown journal outcome type")
        started, finished = _number(self.started_at), _optional_number(self.finished_at)
        incomplete = _status(self.status) == "incomplete"
        if incomplete != (finished is None) or (finished is not None and finished < started):
            raise ActionJournalError("action status and timestamps disagree")
        if self.parent_id == self.step_id:
            raise ActionJournalError("a journal step cannot be its own parent")

    def to_dict(self) -> dict[str, object]:
        """Return field references for sanitization, without deep-copying payloads."""
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_dict(cls, value: object) -> ActionEvent:
        """Validate a persisted event; unknown fields/versions fail closed."""
        if not isinstance(value, dict) or set(value) != {field.name for field in fields(cls)}:
            raise ActionJournalError("invalid action journal event fields")
        event = cls(
            run_id=_text(value["run_id"]), step_id=_text(value["step_id"]),
            command=_text(value["command"]), parameters=_parameters(value["parameters"]),
            started_at=_number(value["started_at"]), parent_id=_optional_text(value["parent_id"]),
            finished_at=_optional_number(value["finished_at"]), status=_status(value["status"]),
            outcome=value["outcome"], outcome_type=_optional_text(value["outcome_type"]),
            error=_optional_text(value["error"]),
            artifact=_optional_text(value["artifact"]), device_id=_optional_text(value["device_id"]),
            session_id=_optional_text(value["session_id"]), sequence=_integer(value["sequence"]),
            schema_version=_integer(value["schema_version"]), non_replayable=_reasons(value["non_replayable"]),
        )
        event.validate()
        if event.sequence < 1:
            raise ActionJournalError("persisted journal sequences must be positive")
        return event
