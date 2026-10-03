"""Append-only journal storage and run-scoped executor recording."""
from __future__ import annotations

import contextlib
import contextvars
import inspect
import json
import os
import threading
import time
import uuid
from _thread import RLock
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Union

from je_auto_control.utils.action_journal.events import ActionEvent, JSONValue, JournalError, safe_payload
from je_auto_control.utils.action_journal.privacy import private_input, private_output, scrub_payload, secret_values
from je_auto_control.utils.executor.flow_control import LoopBreak, LoopContinue
from je_auto_control.utils.json_store.json_store import _file_lock, append_json_line
from je_auto_control.utils.path_guard.policy import scoped_path

_CURRENT: contextvars.ContextVar[Optional['_Run']] = contextvars.ContextVar('action_journal_run', default=None)
_PARENT: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('action_journal_parent', default=None)
_SOURCE: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('action_journal_source', default=None)
_INDEX: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar('action_journal_index', default=None)


@dataclass
class _Run:  # pylint: disable=too-many-instance-attributes  # reason: shared run context owns ordered persistence
    journal: ActionJournal
    run_id: str
    device: Optional[str]
    session: Optional[str]
    source: Optional[str]
    sequence: int = 0
    secrets: Set[str] = field(default_factory=set)
    lock: RLock = field(default_factory=RLock)

    def emit(self, event: ActionEvent) -> ActionEvent:
        """Assign and persist an event under the shared run lock."""
        with self.lock:
            self.sequence += 1
            arguments = scrub_payload(event.arguments, self.secrets, redact_fields=False)
            changed = arguments != event.arguments
            event = replace(event, sequence=self.sequence,
                            arguments=arguments,
                            replayable=event.replayable and not changed,
                            replay_reasons=event.replay_reasons + (
                                ('masked known secret input requires a secret reference',) if changed else ()),
                            outcome=scrub_payload(event.outcome, self.secrets))
            self.journal.append(event)
            return event


class ActionJournal:
    """Append sanitized executor events to a root-checked JSONL file."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = scoped_path(path, operation='write')
        self._lock = threading.RLock()

    def append(self, event: ActionEvent) -> None:
        """Append one complete JSON line under thread and cross-process locks."""
        arguments, reasons = private_input(event.command, event.arguments)
        event = replace(event, arguments=arguments, replayable=event.replayable and not reasons,
                        replay_reasons=tuple(dict.fromkeys((*event.replay_reasons, *reasons))))
        line = json.dumps(event.to_dict(), ensure_ascii=False, allow_nan=False)
        path = scoped_path(self.path, operation='write')
        scoped_path(path.with_name(path.name + '.lock'), operation='write')
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, _file_lock(path):
            if event.sequence == 1 and path.exists() and read_events(path, run_id=event.run_id):
                raise JournalError('run_id already exists in this journal')
            append_json_line(path, line)

    @contextlib.contextmanager
    def run(self, *, run_id: Optional[str] = None, device: Optional[str] = None,
            session: Optional[str] = None, source: Optional[str] = None) -> Iterator[str]:
        """Bind one run; nested/parallel steps retain its IDs and append order."""
        identifier = uuid.uuid4().hex if run_id is None else run_id
        if not isinstance(identifier, str) or not identifier:
            raise JournalError('run_id must be a nonempty string')
        if self.path.exists() and read_events(self.path, run_id=identifier):
            raise JournalError('run_id already exists in this journal')
        state = _Run(self, identifier, device, session, source)
        token = _CURRENT.set(state)
        parent = _PARENT.set(None)
        try:
            yield identifier
        finally:
            _PARENT.reset(parent)
            _CURRENT.reset(token)


def read_events(path: Path, *, run_id: Optional[str] = None) -> List[ActionEvent]:
    """Validate JSONL and return the latest state of each step in start order."""
    source = scoped_path(path, operation='read')
    try:
        text = source.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as error:
        raise JournalError('cannot read a complete valid action journal') from error
    return events_from_text(text, run_id=run_id)


def events_from_text(text: str, *, run_id: Optional[str] = None) -> List[ActionEvent]:
    """Validate one captured JSONL snapshot using the same ordering/schema contract."""
    steps: Dict[tuple[str, str], ActionEvent] = {}
    order: Dict[tuple[str, str], int] = {}
    sequences: Dict[str, int] = {}
    try:
        for line in text.splitlines():
            if not line.strip():
                continue
            event = ActionEvent.from_dict(json.loads(line))
            _merge_event(event, steps, order, sequences)
    except json.JSONDecodeError as error:
        raise JournalError('cannot read a complete valid action journal') from error
    return [replace(event, sequence=order[key]) for key, event in steps.items()
            if run_id is None or event.run_id == run_id]


def _merge_event(event: ActionEvent, steps: Dict[tuple[str, str], ActionEvent],
                 order: Dict[tuple[str, str], int], sequences: Dict[str, int]) -> None:
    previous = sequences.get(event.run_id, 0)
    if event.sequence <= previous:
        raise JournalError('journal sequence must strictly increase within a run')
    sequences[event.run_id] = event.sequence
    key = (event.run_id, event.step_id)
    if key not in steps:
        if event.status != 'incomplete':
            raise JournalError('terminal event has no start record')
        if event.parent_id is not None and (event.run_id, event.parent_id) not in steps:
            raise JournalError('step parent has no start record')
        order[key] = event.sequence
    else:
        started = steps[key]
        if started.status != 'incomplete' or event.status == 'incomplete':
            raise JournalError('duplicate start or terminal event')
        if (event.command, event.parent_id, event.started_at) != (
                started.command, started.parent_id, started.started_at):
            raise JournalError('terminal event changed its step identity')
    steps[key] = event


@contextlib.contextmanager
def execution_journal() -> Iterator[None]:
    """Enable automatic recording only when an explicit environment path exists."""
    path = os.environ.get('JE_AUTOCONTROL_ACTION_JOURNAL')
    if _CURRENT.get() is not None or not path:
        yield
        return
    with ActionJournal(path).run(source='executor'):
        yield


def observe_resolved_arguments(command: str, raw: object, resolved: object, *,
                               event: Optional[Callable[..., object]] = None) -> None:
    """Retain confidential strings in memory for sanitizing subsequent outcomes."""
    state = _CURRENT.get()
    if state is not None:
        raw = _raw_input([command, raw], event)
        resolved = _raw_input([command, resolved], event)
        with state.lock:
            state.secrets.update(secret_values(command, raw, resolved))


def journal_log_value(value: object) -> object:
    """Scrub known run secrets from log copies without changing caller results."""
    state = _CURRENT.get()
    if state is None:
        return value
    payload, _ = safe_payload(value)
    with state.lock:
        return scrub_payload(payload, state.secrets)


def current_journal_context() -> Dict[str, JSONValue]:
    """Expose step provenance to other internal audit records, excluding secrets."""
    state = _CURRENT.get()
    if state is None:
        return {}
    return {'run_id': state.run_id, 'step_id': _PARENT.get(), 'device': state.device,
            'session': state.session, 'source': _SOURCE.get() or state.source}


def prime_journal_inputs(actions: object, handlers: Mapping[str, Callable[..., object]]) -> None:
    """Bind literal secret fields before any whole-script log is emitted."""
    if _CURRENT.get() is None:
        return
    payload, _ = safe_payload(actions)
    _prime_inputs(payload, handlers, 0)


def _prime_inputs(payload: JSONValue, handlers: Mapping[str, Callable[..., object]], depth: int) -> None:
    if depth >= 32:
        return
    if isinstance(payload, dict):
        for value in payload.values():
            _prime_inputs(value, handlers, depth + 1)
    elif isinstance(payload, list):
        _prime_sequence(payload, handlers, depth)


def _prime_sequence(payload: List[JSONValue], handlers: Mapping[str, Callable[..., object]], depth: int) -> None:
    if payload and isinstance(payload[0], str) and payload[0].startswith('AC_'):
        raw = _raw_input(payload, handlers.get(payload[0]))
        observe_resolved_arguments(payload[0], raw, raw)
        if payload[0] == 'AC_execute_journaled' and isinstance(raw, dict):
            nested = raw.get('actions')
            if isinstance(nested, str):
                try:
                    _prime_inputs(json.loads(nested), handlers, depth + 1)
                except json.JSONDecodeError:
                    return  # The executor validates the source before executing it.
    for value in payload:
        _prime_inputs(value, handlers, depth + 1)


@contextlib.contextmanager
def journal_source(source: str) -> Iterator[None]:
    """Retain the loaded action file behind every observed step."""
    token = _SOURCE.set(source)
    try:
        yield
    finally:
        _SOURCE.reset(token)


@contextlib.contextmanager
def journal_index(index: int) -> Iterator[None]:
    """Preserve the index in the originating action list, including repeated bodies."""
    token = _INDEX.set(index)
    try:
        yield
    finally:
        _INDEX.reset(token)


def _raw_input(action: Sequence[object], event: Optional[Callable[..., object]]) -> object:
    value = action[1] if len(action) > 1 else None
    if isinstance(value, list) and event is not None:
        try:
            return dict(inspect.signature(event).bind(*value).arguments)
        except (TypeError, ValueError):
            # Unknown native signatures cannot safely classify positional fields.
            return {'unbound_arguments': None}
    return value


def _start_step(state: _Run, action: Sequence[object], event: Optional[Callable[..., object]]) -> ActionEvent:
    command = action[0]
    if not isinstance(command, str):
        raise JournalError('journal command must be a string')
    raw = _raw_input(action, event)
    arguments, reasons = private_input(command, raw)
    with state.lock:
        state.secrets.update(secret_values(command, raw, raw))
    if isinstance(raw, dict) and 'unbound_arguments' in raw:
        reasons.append('positional arguments could not be bound')
    return state.emit(ActionEvent(
        run_id=state.run_id, step_id=uuid.uuid4().hex, parent_id=_PARENT.get(), sequence=1,
        command=command, arguments=arguments, started_at=time.time(),
        replayable=not reasons, replay_reasons=tuple(reasons),
        device=state.device, session=state.session, source=_SOURCE.get() or state.source,
        source_index=_INDEX.get()))


def execute_recorded(action: Sequence[object], function: Callable[[], object], *,
                     event: Optional[Callable[..., object]] = None) -> object:
    """Record before dispatch, with terminal status only after a completed step."""
    state = _CURRENT.get()
    if state is None:
        return function()
    # pylint: disable-next=import-outside-toplevel  # reason: dispatch is running after executor initialization
    from je_auto_control.utils.executor.action_executor import recorded_failures
    step = _start_step(state, action, event)
    failures_before = recorded_failures()
    parent = _PARENT.set(step.step_id)
    try:
        result = function()
    except Exception as error:  # reason: record generic failure then re-raise the original exception
        status = 'control' if isinstance(error, (LoopBreak, LoopContinue)) else 'error'
        state.emit(replace(step, finished_at=max(time.time(), step.started_at), status=status,
                           error=None if status == 'control' else type(error).__name__))
        raise
    else:
        outcome, found = safe_payload(result)
        outcome, secrets = private_output(step.command, step.arguments, outcome)
        with state.lock:
            state.secrets.update(secrets)
        failed = recorded_failures() > failures_before
        state.emit(replace(step, finished_at=max(time.time(), step.started_at),
                           status='error' if failed else 'ok', outcome=outcome,
                           error='UnhandledDescendantFailure' if failed else None,
                           replayable=step.replayable and not found,
                           replay_reasons=tuple((*step.replay_reasons, *found))))
        return result
    finally:
        _PARENT.reset(parent)
