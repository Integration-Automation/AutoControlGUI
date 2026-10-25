"""Existing recovered evidence crosses callers only through an explicit revocable local DAG handoff."""
from contextlib import ExitStack
from types import SimpleNamespace
import json

import pytest

from headless.test_agent_skill_versions import Editor
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


def edit(value):
    return {'tool': 'AC_edit', 'arguments': {
        'selector': {'name': 'Reviewed field', 'role': 'Edit', 'app_name': 'Editor'}, 'value': value}}


def perform(runtime, identifier, action):
    frame = runtime.observe(identifier)
    return runtime.act(identifier, {**action, 'observation_id': frame.observation_id})


@pytest.fixture
def handoff(tmp_path, request):
    users = UserStore(tmp_path / 'users.json')
    users.add_user(user_id='owner', display_name='Owner', role='operator')
    users.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
    owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
    reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
    target = Editor()
    runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'editor': target})
    runtime.background = SimpleNamespace(start=lambda _task_id: None)
    spec = {'goal': 'Independently finish the original reviewed field', 'target': 'editor', 'mode': 'skill',
            'apps': ['Editor'], 'allowed_tools': ['AC_edit'],
            'actions': [edit('partial'), edit('done')], 'success_criteria': [{'kind': 'actions_complete'},
                {'kind': 'result_equals', 'key': 'value', 'value': 'done'}]}
    definition = {'nodes': [{'id': 'a', 'host': 'local', 'task': {
        'spec': spec, 'idempotency_key': 'owned-legacy-handoff', 'wait_seconds': 20}}]}
    scopes = ExitStack()
    scopes.enter_context(authorization_scope(owner))
    try:
        batch = runtime.batches.control('register', {'definition': definition})
        with authorization_scope(reviewer):
            started = runtime.batches.control('begin', {'batch_id': batch['batch_id'],
                                                       'definition': definition, 'max_parallel': 4})
            claim = {'batch_id': batch['batch_id'], 'attempt': started['attempt'], 'node_id': 'a'}
            runtime.batches.control('claim', claim)
            node = started['definition']['nodes'][0]['task']
            source = runtime.batches.control('local_task', {**claim, 'operation': 'submit', 'body': {
                'spec': node['spec'], 'idempotency_key': node['idempotency_key']}})['task_id']
            perform(runtime, source, edit('partial'))
            runtime.pause(source)
            runtime.batches.control('pause_batch', {'batch_id': batch['batch_id']})
            preview = runtime.recovery.control('preview', {'task_id': source})
            child = runtime.recovery.control('create', {'task_id': source, 'snapshot': preview['snapshot'],
                'spec': preview['draft'], 'note': 'Reviewed remaining semantic field update'})['task_id']
            for _index in range(1, getattr(request, 'param', 1)):
                runtime.pause(child)
                preview = runtime.recovery.control('preview', {'task_id': child})
                child = runtime.recovery.control('create', {'task_id': child, 'snapshot': preview['snapshot'],
                    'spec': preview['draft'], 'note': 'Reviewed separate retired continuation'})['task_id']
            perform(runtime, child, edit('done'))
            assert runtime.finish(child).state == 'succeeded'
        yield SimpleNamespace(runtime=runtime, users=users, owner=owner, reviewer=reviewer, target=target,
                              batch_id=batch['batch_id'], source=source, child=child, definition=definition)
    finally:
        with authorization_scope(None):
            runtime.close()
        scopes.close()


def request_for(value):
    return {'task_id': value.child, 'batch_id': value.batch_id, 'node_id': 'a'}


def grant_for(value):
    with authorization_scope(value.reviewer):
        review = value.runtime.recovery.control('review_handoff', request_for(value))
        return value.runtime.recovery.control('create_handoff', {**request_for(value),
            'review': review['handoff_review'], 'note': 'Explicit evidence-only transfer'})['handoff']


def test_revocation_in_the_consuming_transaction_prevents_a_completion_reply(handoff, monkeypatch):
    from je_auto_control.utils.agent_runtime.evidence_handoff import EvidenceHandoffs
    grant = grant_for(handoff)
    original = EvidenceHandoffs._proof
    def revoked(self, connection, request, actor, **options):
        result = original(self, connection, request, actor, **options)
        connection.execute("UPDATE agent_evidence_handoffs SET state='revoked' WHERE id=?", (grant['id'],))
        return result
    monkeypatch.setattr(EvidenceHandoffs, '_proof', revoked)
    with pytest.raises(AgentTaskError, match='revoked'):
        handoff.runtime.recovery.handoff_evidence(handoff.batch_id, 'a', handoff.source, handoff.child, grant['id'])


def test_explicit_handoff_allows_completion_adoption_without_general_task_reads_or_input(handoff, monkeypatch):
    runtime = handoff.runtime
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(handoff.child)
    calls = list(handoff.target.calls)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Handoff and adoption may not probe or execute a target')
    for method in ('ready', 'observe', 'perform'):
        monkeypatch.setattr(handoff.target, method, forbidden)
    with authorization_scope(handoff.reviewer):
        review = runtime.recovery.control('review_handoff', request_for(handoff))
        assert review['approval_required'] is True
        grant = runtime.recovery.control('create_handoff', {**request_for(handoff),
            'review': review['handoff_review'], 'note': 'Share only this original DAG completion evidence'})['handoff']
    assert 'store_path' not in json.dumps(review) and 'arguments' not in json.dumps(grant)
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(handoff.child)
    decision = {'node_id': 'a', 'action': 'successor', 'task_id': handoff.child, 'handoff_id': grant['id']}
    reviewed = runtime.batches.control('review_continuation', {'batch_id': handoff.batch_id,
        'definition': handoff.definition, 'decisions': [decision]})
    assert reviewed['can_approve'], reviewed
    approved = runtime.batches.control('approve_continuation', {
        **{key: reviewed[key] for key in ('batch_id', 'definition', 'snapshot', 'decisions')},
        'note': 'Reviewed explicit immutable completion handoff'})
    started = runtime.batches.control('start_continuation', {'batch_id': handoff.batch_id,
        'definition': handoff.definition, 'approval_id': approved['approval_id'], 'max_parallel': 4})
    completed = runtime.batches.control('validate_node', {'batch_id': handoff.batch_id,
        'node_id': 'a', 'attempt': started['attempt']})
    assert completed['outcome'] == 'completed' and completed['task_id'] == handoff.child
    assert runtime.get(handoff.source).state == 'paused' and handoff.target.calls == calls
    for operation in (runtime.get, runtime.receipts, runtime.observe, runtime.resume):
        with pytest.raises(AgentTaskError, match='another caller'):
            operation(handoff.child)
    runtime.recovery.control('revoke_handoff', {'handoff_id': grant['id']})
    with pytest.raises(AgentTaskError):
        runtime.batches.control('validate_node', {'batch_id': handoff.batch_id,
            'node_id': 'a', 'attempt': started['attempt']})
