"""Explicit local DAG grants adopt renewed read-only evidence without transferring task ownership."""
import json

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, create
from je_auto_control.utils.agent_runtime import AgentTaskError, origin_policy
from je_auto_control.utils.rbac.authorization import authorization_scope

renewal = _renewal


@pytest.fixture
def completed(renewal):
    with authorization_scope(renewal.reviewer):
        renewal.child = create(renewal)
        assert renewal.runtime.finish(renewal.child).state == 'succeeded'
    return renewal


def request_for(value):
    return {'task_id': value.child, 'batch_id': value.batch_id, 'node_id': 'a'}


def issue(value):
    with authorization_scope(value.reviewer):
        review = value.runtime.recovery.control('review_handoff', request_for(value))
        request = {**request_for(value), 'review': review['handoff_review'],
                   'note': 'Explicitly adopt only this renewed independent completion'}
        grant = value.runtime.recovery.control('create_handoff', request)['handoff']
    return review, request, grant


@pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)
def test_original_owner_adopts_renewed_other_caller_completion_without_reviving_old_input(completed, monkeypatch):
    from je_auto_control.utils.agent_runtime.readonly_target import ReadOnlyNativeTarget
    runtime = completed.runtime
    before = runtime.store.actions(completed.source)
    manifest = completed.manifest.read_bytes()
    old_path = origin_policy._path(completed.old.identifier)
    old_bytes = old_path.read_bytes()
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(completed.child)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Evidence handoff may not launch a helper or replay input')
    monkeypatch.setattr(ReadOnlyNativeTarget, '_launch', forbidden)
    review, request, grant = issue(completed)
    authorization = review['evidence']['completion_authorization']
    assert authorization['completion_task'] == completed.child
    assert authorization['approved_root_count'] == 1
    assert completed.old.identifier in authorization['replaced_origins']
    public = json.dumps([review, grant])
    assert 'store_path' not in public and 'arguments' not in public and str(completed.reports) not in public
    with authorization_scope(completed.reviewer):
        assert runtime.recovery.control('create_handoff', request)['handoff']['id'] == grant['id']
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(completed.child)
    decisions = [{'node_id': 'a', 'action': 'successor', 'task_id': completed.child, 'handoff_id': grant['id']}]
    preview = runtime.batches.control('review_continuation', {
        'batch_id': completed.batch_id, 'definition': completed.definition, 'decisions': decisions})
    assert preview['can_approve'] is True
    approved = runtime.batches.control('approve_continuation', {
        **{key: preview[key] for key in ('batch_id', 'definition', 'snapshot', 'decisions')},
        'note': 'Use exactly the newly authorized read-only evidence grant'})
    started = runtime.batches.control('start_continuation', {
        'batch_id': completed.batch_id, 'definition': completed.definition,
        'approval_id': approved['approval_id'], 'max_parallel': 4})
    validation = {'batch_id': completed.batch_id, 'node_id': 'a', 'attempt': started['attempt']}
    assert runtime.batches.control('validate_node', validation)['outcome'] == 'completed'
    assert runtime.get(completed.source).state == 'paused'
    assert runtime.store.actions(completed.source) == before and runtime.store.actions(completed.child) == []
    assert completed.manifest.read_bytes() == manifest and old_path.read_bytes() == old_bytes
    runtime.recovery.control('revoke_handoff', {'handoff_id': grant['id']})
    with pytest.raises(AgentTaskError):
        runtime.batches.control('validate_node', validation)
