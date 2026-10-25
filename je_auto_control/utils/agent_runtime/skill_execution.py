"""Exact original skill effects across real reviewed recovery, without granting input or replacing trials."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.completion_contract import validate_recorded_completion
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.handoff_records import HandoffAccess


def _execution_row(runtime: Any, identifier: str, access: HandoffAccess | None) -> dict:
    if access is not None:
        return access.read(identifier)
    # pylint: disable-next=protected-access  # reason: ungranted evidence retains ordinary caller ownership checks
    return runtime._row(identifier)


def _chain(runtime: Any, connection: Any, root: dict, identifier: Any,
           access: HandoffAccess | None = None) -> list[tuple[dict, dict, dict]]:
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 256 or identifier == root['id']:
        raise AgentTaskError('execution_task_id must identify a separate reviewed executable successor')
    result, seen = [], {root['id']}
    for _index in range(16):
        if identifier in seen:
            break
        seen.add(identifier)
        child = _execution_row(runtime, identifier, access)
        if (connection.execute('SELECT 1 FROM agent_readonly_completions WHERE task_id=?', (identifier,)).fetchone()
                or connection.execute('SELECT 1 FROM agent_skill_trials WHERE task_id=?', (identifier,)).fetchone()):
            raise AgentTaskError('execution evidence cannot substitute a reader or another validation trial')
        row = connection.execute('SELECT * FROM agent_task_recoveries WHERE task_id=?', (identifier,)).fetchone()
        if row is None:
            break
        link = dict(row)
        parent = _execution_row(runtime, link['source_task'], access)
        result.append((parent, child, link))
        if parent['id'] == root['id']:
            return list(reversed(result))
        identifier = parent['id']
    raise AgentTaskError('execution evidence has no bounded real recovery chain to the original trial')


def _same(first: Any, second: Any) -> bool:
    return (json.dumps(first, sort_keys=True, separators=(',', ':'), allow_nan=False)
            == json.dumps(second, sort_keys=True, separators=(',', ':'), allow_nan=False))


def _scope(parent: dict, child: dict, *, renewed: bool = False) -> None:
    fixed = set(parent) - {'goal', 'actions', 'roots', 'options'}
    if set(parent) != set(child) or not _same({key: parent[key] for key in fixed},
                                           {key: child[key] for key in fixed}):
        raise AgentTaskError('execution recovery changed original scope, settings or completion criteria')
    if any(not any(Path(root).is_relative_to(Path(ceiling)) for ceiling in parent['roots'])
           for root in child['roots']):
        raise AgentTaskError('execution recovery roots exceed the original ceiling')
    _scope_options(parent['options'], child['options'], renewed=renewed)


def _scope_options(parent: dict, child: dict, *, renewed: bool) -> None:
    before, after = dict(parent), dict(child)
    before.pop('skill_pin', None)
    origins = set(before.pop('origin_policies', []))
    current = set(after.pop('origin_policies', []))
    if (not renewed and not origins <= current) or not _same(before, after):
        raise AgentTaskError('execution recovery removed original restrictions or changed fixed options')


def _execution_segments(connection: Any, links: list, root: dict, review: Callable,
                        verify_plan: Callable) -> tuple[list[dict], list[dict]]:
    combined: list[dict] = []
    segments: list[dict] = []
    actions: list[dict] = []
    for parent, child, link in links:
        evidence = review(connection, parent, child, link)
        _scope(parent['spec'], child['spec'], renewed=isinstance(review, HandoffAccess) and review.renewed)
        source_actions = verify_plan(parent['spec'], evidence['source_actions'])
        actions = verify_plan(child['spec'], evidence['actions'])
        if not segments:
            combined.extend(source_actions)
        combined.extend(actions)
        if len(combined) > len(root['spec']['actions']):
            raise AgentTaskError('execution chain contains effects outside the original candidate plan')
        segments.append({'task_id': child['id'], 'source_task': parent['id'],
                         **{key: evidence[key] for key in ('source_snapshot', 'snapshot', 'completion_snapshot')}})
    verify_plan(root['spec'], combined, complete=True)
    return segments, actions


def check_skill_execution(runtime: Any, connection: Any, root: dict, request: dict,
                          review: Callable, verify_plan: Callable, completion: Callable) -> dict:
    """Combine only exact confirmed semantic effects and independently completed final verification."""
    access = review if isinstance(review, HandoffAccess) else None
    links = _chain(runtime, connection, root, request['execution_task_id'], access)
    segments, actions = _execution_segments(connection, links, root, review, verify_plan)
    leaf = links[-1][1]
    verify_plan(leaf['spec'], actions, complete=True)
    result = {'contract': 1, 'task_id': leaf['id'], 'source_task': root['id'],
              'source_snapshot': segments[0]['source_snapshot'], 'segments': segments,
              'verification_task': leaf['id']}
    if 'completion_task_id' in request:
        result['completion_review'] = completion(connection, leaf, request['completion_task_id'])
        result['verification_task'] = request['completion_task_id']
    else:
        reply = access.reply(leaf['id']) if access is not None else runtime.get(leaf['id']).to_dict()
        validate_recorded_completion(reply, root['spec'])
    if access is not None:
        result['evidence_handoff'] = access.grant
    return result
