"""Private read-only evidence for skill recording and publication preserves original workflow identity."""
from __future__ import annotations

import json
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.completion_contract import (
    validate_recorded_completion, decode_completion_binding,
)


def _decode_binding(value: str) -> dict:
    return decode_completion_binding(value)


def publication_details(connection: Any, publication: Any) -> dict | None:
    """Expose historical adoption IDs and hashes, never private principal stores or live-evidence claims."""
    if publication is None:
        return None
    result = dict(publication)
    proof = connection.execute('SELECT details FROM agent_skill_completions WHERE candidate_id=?',
                               (result['candidate_id'],)).fetchone()
    if proof is not None:
        result['completion_review'] = json.loads(proof[0])
    execution = connection.execute('SELECT details FROM agent_skill_executions WHERE candidate_id=?',
                                   (result['candidate_id'],)).fetchone()
    if execution is not None:
        result['execution_review'] = json.loads(execution[0])
    return result


def _binding(connection: Any, task_id: str, trial_id: str) -> dict:
    row = connection.execute('SELECT c.details,r.source_task,r.snapshot FROM agent_readonly_completions c '
        'JOIN agent_task_recoveries r ON r.task_id=c.task_id WHERE c.task_id=?', (task_id,)).fetchone()
    if row is None:
        raise AgentTaskError('skill completion requires private reviewed recovery provenance')
    details = _decode_binding(row['details'])
    if (details.get('source_task') != row['source_task'] or details.get('source_snapshot') != row['snapshot']
            or details.get('effect_task') != trial_id):
        raise AgentTaskError('skill completion does not belong to the original workflow')
    return details


def _lineage(connection: Any, task_id: str, trial_id: str) -> dict:
    details = _binding(connection, task_id, trial_id)
    current, seen = details['source_task'], {task_id}
    for _index in range(16):
        if current == trial_id:
            return details
        if current in seen:
            break
        seen.add(current)
        current = _binding(connection, current, trial_id)['source_task']
    raise AgentTaskError('skill completion has no bounded verified recovery chain')


def _verification_scope(runtime: Any, connection: Any, trial: dict, task_id: str,
                        authority_check: Callable, verification_spec: Callable) -> tuple[dict, str | None]:
    renewed = connection.execute('SELECT 1 FROM agent_task_authorizations WHERE task_id=?', (task_id,)).fetchone()
    scope = (authority_check(runtime, task_id, connection=connection) if renewed is not None
             else authority_check(runtime, task_id))
    if isinstance(scope, dict):
        return scope['verification_spec'], scope['authorization_review']
    return verification_spec(runtime, trial).to_dict(), None


def check_skill_completion(runtime: Any, connection: Any, trial: dict, task_id: Any,
                           authority_check: Callable, verification_spec: Callable, snapshot_digest: Callable) -> dict:
    """Revalidate a separately succeeded reader under the skill library's SQLite write transaction."""
    if not isinstance(task_id, str) or not 1 <= len(task_id) <= 256 or task_id == trial['id']:
        raise AgentTaskError('completion_task_id must identify a separate reviewed completion task')
    # pylint: disable-next=protected-access  # reason: retain the caller's ordinary task ownership boundary
    row = runtime._row(task_id)
    details = _lineage(connection, task_id, trial['id'])
    expected, authorization_review = _verification_scope(runtime, connection, trial, task_id,
                                                        authority_check, verification_spec)
    if row['spec'] != expected:
        raise AgentTaskError('skill completion verification scope changed')
    # pylint: disable-next=protected-access  # reason: publication cannot adopt live or unwinding input ownership
    with runtime._mutex:
        identifiers = (task_id, trial['id'])
        # pylint: disable-next=protected-access  # reason: inspect only this runtime's private task lifecycle witnesses
        if any(identifier in runtime._leases or identifier in runtime._executing for identifier in identifiers):
            raise AgentTaskError('skill completion input has not retired')
    if runtime.store.actions(task_id):
        raise AgentTaskError('read-only skill completion cannot contain executable action receipts')
    validate_recorded_completion(runtime.get(task_id).to_dict(), trial['spec'])
    completion = connection.execute('SELECT confirmed FROM agent_completion WHERE task_id=?', (task_id,)).fetchone()
    result = {'contract': 1, 'task_id': task_id, 'source_task': details['source_task'], 'effect_task': trial['id'],
              'source_snapshot': details['source_snapshot'], 'effect_snapshot': details['effect_snapshot'],
              'verification_snapshot': snapshot_digest({'spec': row['spec'], 'verification': row['verification'],
                                                        'confirmed': completion[0]})}
    if authorization_review is not None:
        result['authorization_review'] = authorization_review
    return result
