"""Original skill trials may be reviewed against complete real recovery effects without replay."""
from contextlib import ExitStack
from types import SimpleNamespace
import json

import pytest

from headless.test_agent_skill_versions import Editor
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


def edit(name, value):
    return {'tool': 'AC_edit', 'arguments': {
        'selector': {'name': name, 'role': 'Edit', 'app_name': 'Editor'}, 'value': value}}


class CapturingEditor(Editor):
    def perform(self, tool, arguments):
        super().perform(tool, arguments)
        return arguments['value']


def successor(runtime, task_id, *, source_owner=False, extra=False):
    policy = {'owner_policy': 'source_owner'} if source_owner else {}
    review = runtime.recovery.control('preview', {'task_id': task_id, **policy})
    if policy:
        policy['ownership_review'] = review['ownership']['review']
    spec = review['draft']
    if extra:
        spec['actions'].insert(0, edit('Unplanned', 'extra'))
    return runtime.recovery.control('create', {'task_id': task_id, 'snapshot': review['snapshot'],
        'spec': spec, 'note': 'Reviewed fresh state and the remaining semantic actions', **policy})


@pytest.fixture
def execution(tmp_path, request):
    kind = getattr(request, 'param', '')
    users = owner = reviewer = None
    scopes = ExitStack()
    if kind in {'named', 'legacy_owner'}:
        users = UserStore(tmp_path / 'users.json')
        users.add_user(user_id='owner', display_name='Owner', role='operator')
        users.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
    scopes.enter_context(authorization_scope(owner))
    target = CapturingEditor() if kind.startswith('capture') else Editor()
    runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'editor': target})
    actions = [edit('First', 'first'), edit('Last', 'done')]
    if kind == 'chain':
        actions.insert(1, edit('Middle', 'middle'))
    definition = {'goal': 'Verify the full original semantic candidate', 'target': 'editor', 'mode': 'skill',
                  'apps': ['Editor'], 'allowed_tools': ['AC_edit'], 'actions': actions,
                  'success_criteria': [{'kind': 'actions_complete'},
                                       {'kind': 'result_equals', 'key': 'value', 'value': 'done'}]}
    if kind.startswith('capture'):
        actions[0]['capture'] = 'copied'
        actions[1]['arguments']['value'] = {'$capture': 'copied'}
        witness = tmp_path / 'independent.txt'
        witness.write_text('reviewed', encoding='utf-8')
        definition['roots'] = [str(tmp_path)]
        definition['success_criteria'][1] = {'kind': 'file_text', 'path': str(witness), 'value': 'reviewed'}
    try:
        source = runtime.submit(definition)
        assert run_task(runtime, source.task_id).state == 'succeeded'
        candidate = runtime.skills.control('record', {'task_id': source.task_id, 'name': 'Whole semantic flow'})
        trial = runtime.skills.control('validate', {'candidate_id': candidate['id']})
        if kind != 'zero':
            frame = runtime.observe(trial['task_id'])
            runtime.act(trial['task_id'], {'tool': actions[0]['tool'], 'arguments': actions[0]['arguments'],
                                         'observation_id': frame.observation_id})
        runtime.pause(trial['task_id'])
        with authorization_scope(reviewer):
            if kind.startswith('capture'):
                preview = runtime.recovery.control('preview', {'task_id': trial['task_id']})
                assert preview['draft'] is None and 'fresh_capture_required' in preview['issues']
                reviewed = runtime.store.get(trial['task_id'])['spec']
                reviewed['options'].pop('skill_pin')
                reviewed['actions'] = [edit('Last', 'different' if kind == 'capture_mismatch' else 'first')]
                child = runtime.recovery.control('create', {'task_id': trial['task_id'],
                    'snapshot': preview['snapshot'], 'spec': reviewed, 'note': 'Reviewed fresh literal semantic input'})
            else:
                child = successor(runtime, trial['task_id'], source_owner=kind == 'named', extra=kind == 'extra')
            if kind == 'chain':
                frame = runtime.observe(child['task_id'])
                runtime.act(child['task_id'], {**actions[1], 'observation_id': frame.observation_id})
                runtime.pause(child['task_id'])
                child = successor(runtime, child['task_id'])
            assert run_task(runtime, child['task_id']).state == 'succeeded'
        yield SimpleNamespace(runtime=runtime, target=target, candidate=candidate, task_id=trial['task_id'],
                              child_id=child['task_id'], users=users, owner=owner, reviewer=reviewer)
    finally:
        with authorization_scope(None):
            runtime.close()
        scopes.close()


def review_request(value):
    return {'candidate_id': value.candidate['id'], 'task_id': value.task_id,
            'execution_task_id': value.child_id}


def test_reviewed_complete_recovery_publishes_original_trial_without_replaying_or_fabricating(execution, monkeypatch):
    runtime = execution.runtime
    receipts = runtime.store.actions(execution.task_id)
    calls = list(execution.target.calls)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Review and publication must not probe or execute a target')
    monkeypatch.setattr(execution.target, 'ready', forbidden)
    monkeypatch.setattr(execution.target, 'observe', forbidden)
    monkeypatch.setattr(execution.target, 'perform', forbidden)
    request = review_request(execution)
    review = runtime.skills.control('review_execution', request)
    assert review['approval_required'] is True and review['publication_inherited'] is False
    assert runtime.skills.control('get', {'candidate_id': execution.candidate['id']})['state'] == 'draft'
    accepted = runtime.skills.control('accept', {**request, 'execution_review': review['execution_review'],
        'expected_version': 0, 'note': 'Reviewed the exact full semantic effect chain'})
    assert accepted['version'] == 1 and accepted['publication']['task_id'] == execution.task_id
    proof = accepted['publication']['execution_review']
    assert proof['task_id'] == execution.child_id and proof['source_task'] == execution.task_id
    assert proof['verification_task'] == execution.child_id and len(proof['segments']) == 1
    assert 'store_path' not in json.dumps(proof) and 'arguments' not in json.dumps(proof)
    assert runtime.get(execution.task_id).state == 'paused'
    assert runtime.store.actions(execution.task_id) == receipts and execution.target.calls == calls
    with runtime.store.connection() as connection:
        trials = connection.execute('SELECT task_id FROM agent_skill_trials').fetchall()
        assert [row[0] for row in trials] == [execution.task_id]


def accept_request(value, **changes):
    review = value.runtime.skills.control('review_execution', review_request(value))
    return {**review_request(value), 'execution_review': review['execution_review'], 'expected_version': 0,
            'note': 'Reviewed complete original effects and fresh final completion', **changes}


@pytest.mark.parametrize('execution', ['chain'], indirect=True)
def test_multiple_real_recovery_segments_match_the_complete_original_plan(execution):
    accepted = execution.runtime.skills.control('accept', accept_request(execution))
    proof = accepted['publication']['execution_review']
    assert len(proof['segments']) == 2 and proof['source_task'] == execution.task_id
    assert accepted['publication']['task_id'] == execution.task_id


@pytest.mark.parametrize('execution', ['extra'], indirect=True)
def test_a_successful_different_recovery_plan_cannot_publish_the_original_candidate(execution):
    assert execution.runtime.get(execution.child_id).state == 'succeeded'
    with pytest.raises(AgentTaskError, match='outside the original candidate'):
        execution.runtime.skills.control('review_execution', review_request(execution))
    assert execution.runtime.skills.control('get', {'candidate_id': execution.candidate['id']})['state'] == 'draft'


def test_execution_review_is_stable_passive_and_does_not_publish(execution):
    runtime = execution.runtime
    rows = [runtime.store.get(identifier) for identifier in (execution.task_id, execution.child_id)]
    first = runtime.skills.control('review_execution', review_request(execution))
    assert first == runtime.skills.control('review_execution', review_request(execution))
    assert rows == [runtime.store.get(identifier) for identifier in (execution.task_id, execution.child_id)]
    assert runtime.skills.control('get', {'candidate_id': execution.candidate['id']})['publication'] is None


@pytest.mark.parametrize('token', [None, [], '', 'not-the-reviewed-chain'])
def test_missing_or_invalid_review_token_has_no_publication(execution, token):
    request = {**review_request(execution), 'expected_version': 0, 'note': 'Must require the actual review'}
    if token is not None:
        request['execution_review'] = token
    with pytest.raises(AgentTaskError):
        execution.runtime.skills.control('accept', request)
    with execution.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_publications').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_executions').fetchone()[0] == 0


def test_leaf_changed_after_review_cannot_publish_stale_evidence(execution):
    request = accept_request(execution)
    reports = execution.runtime.store.get(execution.child_id)['verification']
    execution.runtime.store.update(execution.child_id, 'succeeded', reason='new completion review',
                                   verification=reports)
    with pytest.raises(AgentTaskError, match='review changed'):
        execution.runtime.skills.control('accept', request)
    assert execution.runtime.skills.control('get', {'candidate_id': execution.candidate['id']})['state'] == 'draft'
