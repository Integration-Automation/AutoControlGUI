"""Versioned action events and conservative JSON serialization."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union, cast

from je_auto_control.utils.exception.exceptions import AutoControlException

JSONValue = Union[None, bool, int, float, str, List['JSONValue'], Dict[str, 'JSONValue']]
_STATUSES = frozenset({'incomplete', 'ok', 'error', 'control', 'cancelled'})


class JournalError(AutoControlException, ValueError):
    """A journal has malformed or unsupported records."""


def safe_payload(value: object) -> Tuple[JSONValue, List[str]]:
    """Copy JSON-compatible values without invoking unknown repr/str hooks."""
    return _safe(value, set(), 0)


def _safe(value: object, active: set[int], depth: int) -> Tuple[JSONValue, List[str]]:
    if value is None or type(value) in (bool, int, str):
        return cast(JSONValue, value), []
    # pylint: disable-next=unidiomatic-typecheck  # reason: subclasses may run custom conversion hooks
    if type(value) is float:
        return (value, []) if math.isfinite(value) else (None, ['nonfinite number'])
    if depth >= 32 or id(value) in active:
        return None, ['recursive or excessive-depth payload']
    if type(value) not in (dict, list, tuple):
        return None, ['unsupported payload type: ' + type(value).__name__]
    active.add(id(value))
    try:
        return _container(value, active, depth + 1)
    finally:
        active.remove(id(value))


def _container(value: object, active: set[int], depth: int) -> Tuple[JSONValue, List[str]]:
    reasons: List[str] = []
    if isinstance(value, dict):
        mapping: Dict[str, JSONValue] = {}
        for key, item in value.items():
            # pylint: disable-next=unidiomatic-typecheck  # reason: reject non-builtin keys without invoking hooks
            if type(key) is not str:
                reasons.append('non-string mapping key omitted')
                continue
            mapping[key], found = _safe(item, active, depth)
            reasons.extend(found)
        return mapping, reasons
    sequence: List[JSONValue] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            converted, found = _safe(item, active, depth)
            sequence.append(converted)
            reasons.extend(found)
    return sequence, reasons


def _validate_identity(run_id: str, step_id: str, parent_id: Optional[str], command: str) -> None:
    for value in (run_id, step_id, command):
        # pylint: disable-next=unidiomatic-typecheck  # reason: wire identities require exact strings
        if type(value) is not str or not value:
            raise JournalError('run, step and command must be nonempty strings')
    # pylint: disable-next=unidiomatic-typecheck  # reason: wire identities require exact strings
    if parent_id is not None and (type(parent_id) is not str or not parent_id):
        raise JournalError('parent_id must be a nonempty string or null')
    if not command.startswith('AC_'):
        raise JournalError('journal command must use the AC_ namespace')


def _validate_timing(start: float, end: Optional[float], status: str) -> None:
    if type(start) not in (float, int):
        raise JournalError('started_at must be a finite number')
    for value in (start, end):
        if value is not None and (type(value) not in (float, int) or not math.isfinite(value)):
            raise JournalError('timestamps must be finite numbers')
    if end is not None and end < start:
        raise JournalError('finished_at precedes started_at')
    if (status == 'incomplete') != (end is None):
        raise JournalError('incomplete events require no finished_at; terminal events require one')


@dataclass(frozen=True)
class ActionEvent:  # pylint: disable=too-many-instance-attributes  # reason: frozen wire schema stores explicit metadata
    """One append-only start or terminal record of an executor step."""
    run_id: str
    step_id: str
    parent_id: Optional[str]
    sequence: int
    command: str
    arguments: JSONValue
    started_at: float
    finished_at: Optional[float] = None
    status: str = 'incomplete'
    outcome: JSONValue = None
    error: Optional[str] = None
    replayable: bool = True
    replay_reasons: Tuple[str, ...] = ()
    device: Optional[str] = None
    session: Optional[str] = None
    source: Optional[str] = None
    source_index: Optional[int] = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        # pylint: disable-next=unidiomatic-typecheck  # reason: reject bool where the schema requires int
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise JournalError('unsupported action journal schema version')
        _validate_identity(self.run_id, self.step_id, self.parent_id, self.command)
        # pylint: disable-next=unidiomatic-typecheck  # reason: reject bool where the schema requires int
        if type(self.sequence) is not int or self.sequence < 1:
            raise JournalError('invalid sequence or status')
        # pylint: disable-next=unidiomatic-typecheck  # reason: require exact JSON string metadata
        if type(self.status) is not str or self.status not in _STATUSES:
            raise JournalError('invalid sequence or status')
        _validate_timing(self.started_at, self.finished_at, self.status)
        self._validate_payloads()
        # pylint: disable-next=unidiomatic-typecheck  # reason: reject bool where the schema requires int
        if self.source_index is not None and (type(self.source_index) is not int or self.source_index < 0):
            raise JournalError('source_index must be a nonnegative integer or null')

    def _validate_payloads(self) -> None:
        for value in (self.arguments, self.outcome):
            _, reasons = safe_payload(value)
            if reasons:
                raise JournalError('event payload must already be JSON-compatible')
        for value in (self.error, self.device, self.session, self.source):
            # pylint: disable-next=unidiomatic-typecheck  # reason: require exact JSON string metadata
            if value is not None and type(value) is not str:
                raise JournalError('event metadata must be strings or null')
        # pylint: disable-next=unidiomatic-typecheck  # reason: require exact JSON boolean and string metadata
        if type(self.replayable) is not bool or any(type(reason) is not str for reason in self.replay_reasons):
            raise JournalError('invalid replayability metadata')

    def to_dict(self) -> Dict[str, JSONValue]:
        """Return wire fields without dataclass deepcopy or custom conversion hooks."""
        return {
            'schema_version': self.schema_version, 'run_id': self.run_id,
            'step_id': self.step_id, 'parent_id': self.parent_id, 'sequence': self.sequence,
            'command': self.command, 'arguments': self.arguments, 'started_at': self.started_at,
            'finished_at': self.finished_at, 'status': self.status, 'outcome': self.outcome,
            'error': self.error, 'replayable': self.replayable, 'replay_reasons': list(self.replay_reasons),
            'device': self.device, 'session': self.session, 'source': self.source,
            'source_index': self.source_index,
        }

    @classmethod
    def from_dict(cls, value: object) -> ActionEvent:
        """Validate a wire object before materializing an event."""
        if not isinstance(value, dict):
            raise JournalError('journal records must be JSON objects')
        if value.get('schema_version') != 1:
            raise JournalError('unsupported action journal schema version')
        fields = dict(value)
        reasons = fields.get('replay_reasons', [])
        if not isinstance(reasons, list):
            raise JournalError('replay_reasons must be an array')
        fields['replay_reasons'] = tuple(reasons)
        try:
            return cls(**fields)
        except (TypeError, KeyError) as error:
            raise JournalError('invalid journal fields') from error
