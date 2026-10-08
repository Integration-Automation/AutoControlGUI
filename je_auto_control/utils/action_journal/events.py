"""The record an action journal holds: one executed ``AC_*`` action.

An :class:`ActionEvent` is what the executor knew at the action boundary --
the command, its arguments as they were written (placeholders unresolved,
secrets masked), where it sat in the run (``parent_id``, ``sequence``,
``branch``) and how it ended. The journal is JSON lines, so everything here
converts to and from plain JSON; nothing is ever read back with ``eval``.

Pure standard library; imports no ``PySide6``.
"""
import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException

#: The journal line format this module writes and reads.
SCHEMA_VERSION = 1

#: The action returned.
STATUS_OK = "ok"
#: The action raised.
STATUS_ERROR = "error"
#: The action started and no end was recorded: the process died, the run was
#: interrupted, or it is still running. Never reported as a success.
STATUS_INCOMPLETE = "incomplete"
STATUSES = frozenset({STATUS_OK, STATUS_ERROR, STATUS_INCOMPLETE})

#: ``record`` of a line holding a whole event, written when the action starts.
RECORD_START = "start"
#: ``record`` of a line holding only how a started action ended.
RECORD_END = "end"

#: What a masked or unserialisable argument is replaced by in ``params``.
MASK = "***"
UNSERIALISABLE_KEY = "$unserialisable"


class JournalFormatError(AutoControlException, ValueError):
    """A journal line is valid JSON but not a journal record this version reads."""


@dataclass(frozen=True)
class ActionEvent:
    """One action the executor ran, as the journal stores it.

    ``params`` is the action's argument value exactly as it was written
    (``${var}`` and ``${secrets.NAME}`` references kept as references) after
    masking; ``unreplayable`` maps each path in it that cannot be replayed to
    the reason. ``outcome`` describes the returned value by type and size and
    is never an input to anything.
    """

    run_id: str
    step_id: str
    sequence: int
    command: str
    parent_id: Optional[str] = None
    params: Any = None
    status: str = STATUS_INCOMPLETE
    started_at: float = 0.0
    finished_at: Optional[float] = None
    error: Optional[str] = None
    outcome: Optional[Mapping[str, Any]] = None
    unreplayable: Mapping[str, str] = field(default_factory=dict)
    branch: Optional[int] = None
    thread: Optional[int] = None
    session: Optional[str] = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """The event as a JSON-ready dict (a whole ``start`` line)."""
        data = dataclasses.asdict(self)
        data["record"] = RECORD_START
        return data

    def end_dict(self) -> Dict[str, Any]:
        """Only how the action ended (an ``end`` line for an earlier start)."""
        return {
            "schema_version": self.schema_version, "record": RECORD_END,
            "run_id": self.run_id, "step_id": self.step_id,
            "status": self.status, "finished_at": self.finished_at,
            "error": self.error, "outcome": self.outcome,
        }


_REQUIRED = {"run_id": str, "step_id": str, "sequence": int, "command": str}
_OPTIONAL = {
    "parent_id": str, "error": str, "branch": int, "thread": int,
    "session": str, "outcome": dict,
}


def _typed(data: Mapping[str, Any], name: str, kind: type, where: str) -> Any:
    value = data.get(name)
    # bool is an int: {"sequence": true} is not a sequence number.
    if not isinstance(value, kind) or isinstance(value, bool):
        raise JournalFormatError(
            f"{where}: {name!r} must be {kind.__name__}, got {type(value).__name__}")
    return value


def _number(data: Mapping[str, Any], name: str, where: str) -> Optional[float]:
    value = data.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JournalFormatError(f"{where}: {name!r} must be a number")
    return float(value)


def check_record(data: Any, where: str) -> str:
    """Validate the envelope of one journal line; return its ``record`` kind."""
    if not isinstance(data, dict):
        raise JournalFormatError(f"{where}: a journal line must be a JSON object")
    version = data.get("schema_version")
    if version != SCHEMA_VERSION or isinstance(version, bool):
        raise JournalFormatError(
            f"{where}: unsupported schema_version {version!r} (this reads {SCHEMA_VERSION})")
    record = data.get("record", RECORD_START)
    if record not in (RECORD_START, RECORD_END):
        raise JournalFormatError(f"{where}: unknown record kind {record!r}")
    status = data.get("status", STATUS_INCOMPLETE)
    if status not in STATUSES:
        raise JournalFormatError(f"{where}: unknown status {status!r}")
    for name in ("run_id", "step_id"):
        _typed(data, name, str, where)
    return record


def event_from_dict(data: Mapping[str, Any], where: str = "event") -> ActionEvent:
    """Build an :class:`ActionEvent` from a parsed ``start`` line, validating it."""
    check_record(data, where)
    values: Dict[str, Any] = {
        name: _typed(data, name, kind, where) for name, kind in _REQUIRED.items()}
    for name, kind in _OPTIONAL.items():
        if data.get(name) is not None:
            values[name] = _typed(data, name, kind, where)
    unreplayable = data.get("unreplayable") or {}
    if not isinstance(unreplayable, dict) or not all(
            isinstance(key, str) and isinstance(reason, str)
            for key, reason in unreplayable.items()):
        raise JournalFormatError(f"{where}: 'unreplayable' must map paths to reasons")
    return ActionEvent(
        params=data.get("params"), status=data.get("status", STATUS_INCOMPLETE),
        started_at=_number(data, "started_at", where) or 0.0,
        finished_at=_number(data, "finished_at", where),
        unreplayable=dict(unreplayable), **values)


def apply_end(event: ActionEvent, data: Mapping[str, Any], where: str) -> ActionEvent:
    """``event`` with the outcome an ``end`` line recorded for it."""
    outcome = data.get("outcome")
    if outcome is not None and not isinstance(outcome, dict):
        raise JournalFormatError(f"{where}: 'outcome' must be an object")
    error = data.get("error")
    if error is not None and not isinstance(error, str):
        raise JournalFormatError(f"{where}: 'error' must be a string")
    return dataclasses.replace(
        event, status=data.get("status", STATUS_INCOMPLETE),
        finished_at=_number(data, "finished_at", where), error=error, outcome=outcome)
