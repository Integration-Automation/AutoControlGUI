"""Select completed observed leaf actions without inventing branches or retries."""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Set, Tuple

from je_auto_control.utils.action_journal.events import ActionEvent, JSONValue
from je_auto_control.utils.action_journal.privacy import private_input
from je_auto_control.utils.executor.action_schema import FLOW_BODY_KEYS, FLOW_BRANCH_LIST_KEYS
from je_auto_control.utils.script_vars.interpolate import _PLACEHOLDER

_CONTAINERS = frozenset(FLOW_BODY_KEYS) | frozenset(FLOW_BRANCH_LIST_KEYS) | {
    'AC_execute_action', 'AC_execute_files', 'AC_execute_journaled', 'AC_call_macro',
    'AC_break', 'AC_continue',
}


def _reason(event: ActionEvent, parents: Set[str]) -> Optional[str]:
    if event.status != 'ok':
        return 'not replayed: observed status ' + event.status
    if not event.replayable:
        return 'not replayed: non-replayable input requires review or a secret reference'
    if event.command in _CONTAINERS or event.step_id in parents:
        return 'observed children only; control flow not reconstructed: ' + event.command
    return None


def _retry_parent(event: ActionEvent, by_id: Dict[str, ActionEvent]) -> Optional[str]:
    parent = event.parent_id
    visited: Set[str] = set()
    while parent is not None and parent not in visited:
        visited.add(parent)
        ancestor = by_id.get(parent)
        if ancestor is None:
            return None
        if ancestor.command == 'AC_retry':
            return ancestor.step_id
        parent = ancestor.parent_id
    return None


def _step_row(event: ActionEvent, reason: Optional[str], retry: Optional[str], attempt: Optional[int]
              ) -> Dict[str, JSONValue]:
    return {'step_id': event.step_id, 'parent_id': event.parent_id, 'sequence': event.sequence,
            'command': event.command, 'status': event.status, 'source': event.source,
            'source_index': event.source_index, 'device': event.device, 'session': event.session,
            'started_at': event.started_at, 'finished_at': event.finished_at,
            'included': reason is None, 'omission_reason': reason,
            'retry_parent_id': retry, 'observed_attempt': attempt}


def _requires_binding(value: JSONValue) -> bool:
    """Recognize runtime references using the executor's interpolation grammar."""
    if isinstance(value, str):
        return any(not match.group(1).startswith('secrets.') for match in _PLACEHOLDER.finditer(value))
    if isinstance(value, dict):
        return any(_requires_binding(item) for item in value.values())
    if isinstance(value, list):
        return any(_requires_binding(item) for item in value)
    return False


def _replay_input(event: ActionEvent, parents: Set[str]) -> Tuple[JSONValue, Optional[str]]:
    arguments, privacy_reasons = private_input(event.command, event.arguments)
    reason = _reason(event, parents)
    if reason is None and privacy_reasons:
        reason = 'not replayed: ' + '; '.join(privacy_reasons)
    if reason is None and _requires_binding(arguments):
        reason = 'not replayed: runtime variable input lacks a recorded resolved binding'
    return arguments, reason


def observed_actions(events: Sequence[ActionEvent]
                     ) -> Tuple[List[List[JSONValue]], List[Dict[str, JSONValue]], List[str]]:
    """Return sanitized actions and all provenance rows in observed start order."""
    parents = {event.parent_id for event in events if event.parent_id is not None}
    by_id = {event.step_id: event for event in events}
    actions: List[List[JSONValue]] = []
    rows: List[Dict[str, JSONValue]] = []
    warnings: List[str] = []
    occurrences: Dict[Tuple[Optional[str], str, Optional[int], str], int] = {}
    for event in events:
        arguments, reason = _replay_input(event, parents)
        retry = _retry_parent(event, by_id)
        key = (retry, event.command, event.source_index, json.dumps(arguments, sort_keys=True))
        occurrences[key] = occurrences.get(key, 0) + 1
        attempt = occurrences[key] if retry is not None else None
        rows.append(_step_row(event, reason, retry, attempt))
        if reason is not None:
            warnings.append(event.step_id + ': ' + reason)
        else:
            actions.append([event.command] if arguments is None else [event.command, arguments])
    return actions, rows, warnings
