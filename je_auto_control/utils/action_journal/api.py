"""Headless recording and wire adapters for version-one action journals."""
import json
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Union

from je_auto_control.utils.action_journal.events import ActionEvent, JSONValue, JournalError
from je_auto_control.utils.action_journal.store import ActionJournal, read_events
from je_auto_control.utils.run_history.history_store import (
    SOURCE_MANUAL, STATUS_ERROR, STATUS_OK, default_history_store,
)
from je_auto_control.utils.script_vars.scope import execution_scope


def _run_status(events: List[ActionEvent]) -> str:
    roots = [event for event in events if event.parent_id is None]
    if any(event.status == 'incomplete' for event in events):
        return 'incomplete'
    return 'error' if any(event.status in {'error', 'cancelled'} for event in roots) else 'ok'


def _action_input(actions: Union[Sequence[object], Mapping[str, object], str]
                  ) -> Union[List[object], Dict[str, object]]:
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except json.JSONDecodeError as error:
            raise JournalError('actions must be a valid JSON action list') from error
    if isinstance(actions, Mapping):
        return dict(actions)
    if isinstance(actions, Sequence) and not isinstance(actions, (str, bytes, bytearray)):
        return list(actions)
    raise JournalError('actions must be an action list or script object')


def execute_journaled(actions: Union[Sequence[object], Mapping[str, object], str], path: str, *,
                      run_id: Optional[str] = None, raise_on_error: bool = False,
                      device: Optional[str] = None, session: Optional[str] = None) -> Dict[str, JSONValue]:
    """Execute actions with a journal and linked run history; return safe run metadata.

    An interrupted run keeps its pending history row and incomplete step. This
    function executes actions; reading or converting its journal does not.
    """
    # pylint: disable-next=import-outside-toplevel  # reason: executor registers this adapter; defer the import cycle
    from je_auto_control.utils.executor.action_executor import executor
    actions = _action_input(actions)
    journal = ActionJournal(path)
    with journal.run(run_id=run_id, device=device, session=session, source='manual') as identifier:
        history_id = default_history_store.start_run(SOURCE_MANUAL, identifier, '<journalled actions>')
        default_history_store.attach_artifact(history_id, str(journal.path))
        try:
            with execution_scope():
                executor.execute_action(actions, raise_on_error=raise_on_error)
        except Exception as error:  # reason: update history with a generic error, then re-raise
            default_history_store.finish_run(history_id, STATUS_ERROR, type(error).__name__,
                                             artifact_path=str(journal.path))
            raise
        events = read_events(journal.path, run_id=identifier)
        status = _run_status(events)
        if status != 'incomplete':
            default_history_store.finish_run(history_id, STATUS_OK if status == 'ok' else STATUS_ERROR,
                                             artifact_path=str(journal.path))
        return {'run_id': identifier, 'journal_path': str(journal.path), 'status': status,
                'steps': len(events), 'history_id': history_id}


def read_action_journal(path: str, run_id: Optional[str] = None) -> List[Dict[str, JSONValue]]:
    """Return validated, materialized step records for a selected run or all runs."""
    return [event.to_dict() for event in read_events(Path(path), run_id=run_id)]


def list_journal_runs(path: str) -> List[Dict[str, JSONValue]]:
    """List recorded runs with status, timing and step denominators."""
    grouped: Dict[str, List[ActionEvent]] = {}
    for event in read_events(Path(path)):
        grouped.setdefault(event.run_id, []).append(event)
    return [_run_metadata(identifier, events) for identifier, events in grouped.items()]


def _run_metadata(identifier: str, events: List[ActionEvent]) -> Dict[str, JSONValue]:
    finished = [event.finished_at for event in events if event.finished_at is not None]
    status = _run_status(events)
    return {'run_id': identifier, 'steps': len(events), 'status': status,
            'started_at': min(event.started_at for event in events),
            'finished_at': max(finished) if finished and status != 'incomplete' else None,
            'device': events[0].device, 'session': events[0].session, 'source': events[0].source}
