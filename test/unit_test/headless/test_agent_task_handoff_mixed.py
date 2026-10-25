"""Original trial publication adopts exact other-caller execution and renewed reader evidence."""
from contextlib import ExitStack
from types import SimpleNamespace
import json

import pytest

from headless.test_agent_skill_execution import execution as _execution, review_request
from headless.test_agent_task_handoff import issue, no_helper, assert_no_dag
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, origin_policy
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore

execution = _execution


def publish(value, request):
    runtime = value.runtime
    review = runtime.skills.control('review_execution', request)
    return runtime.skills.control('accept', {**request, 'execution_review': review['execution_review'],
        'expected_version': 0, 'note': 'Reviewed complete exact original effects and independent task evidence'})


@pytest.mark.parametrize('execution', ['legacy_owner'], indirect=True)
def test_pure_executable_other_caller_successor_publishes_only_through_its_explicit_task_grant(execution,
                                                                                           monkeypatch):
    runtime = execution.runtime
    request = review_request(execution)
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.skills.control('review_execution', request)
    before = list(execution.target.calls)
    for method in ('ready', 'observe', 'perform'):
        monkeypatch.setattr(execution.target, method, no_helper)
    grant = issue(execution, execution.task_id, execution.child_id)
    accepted = publish(execution, {**request, 'handoff_id': grant['id']})
    proof = accepted['publication']['execution_review']
    assert accepted['publication']['task_id'] == execution.task_id
    assert proof['task_id'] == proof['verification_task'] == execution.child_id
    assert proof['evidence_handoff']['id'] == grant['id']
    assert execution.target.calls == before
    assert runtime.get(execution.task_id).state == 'paused'
    assert runtime.store.get(execution.child_id)['owner']['user_id'] == 'reviewer'
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(execution.child_id)
    assert_no_dag(runtime)


def file_definition(root):
    reports = root / 'reports'
    reports.mkdir()
    document = reports / 'result.txt'
    document.write_text('complete', encoding='utf-8')
    manifests = [reports / 'first.json', reports / 'last.json']
    actions = [{'tool': 'AC_workflow_manifest', 'arguments': {
        'directory': str(reports), 'path': str(path), 'names': ['result.txt']}} for path in manifests]
    spec = {'goal': 'Verify exact original trial effects under explicit replacement ceilings',
            'target': 'local-files', 'mode': 'skill', 'roots': [str(root)],
            'allowed_tools': ['AC_workflow_manifest'], 'actions': actions,
            'success_criteria': [{'kind': 'actions_complete'}, {'kind': 'file_exists', 'path': str(manifests[-1])},
                                 {'kind': 'file_text', 'path': str(document), 'value': 'complete'}]}
    return spec, actions, manifests, reports


@pytest.fixture
def renewed_execution(tmp_path):
    scopes = ExitStack()
    users = UserStore(tmp_path / 'users.json')
    users.add_user(user_id='owner', display_name='Owner', role='operator')
    users.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
    owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
    reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
    scopes.enter_context(authorization_scope(owner))
    spec, actions, manifests, reports = file_definition(tmp_path)
    old, current = origin_policy.OriginWitness((tmp_path,)), origin_policy.OriginWitness((reports,))
    for witness in (old, current):
        scopes.callback(origin_policy._path(witness.identifier).unlink, missing_ok=True)
    target = NativeDesktopTarget(resource_path=tmp_path / 'owned-input.lock')
    runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'local-files': target})
    try:
        with origin_policy.origin_scope(old.identifier):
            source = runtime.submit(spec)
            assert run_task(runtime, source.task_id).state == 'succeeded'
            candidate = runtime.skills.control('record', {'task_id': source.task_id, 'name': 'Actual file trial'})
            trial = runtime.skills.control('validate', {'candidate_id': candidate['id']})
            frame = runtime.observe(trial['task_id'])
            runtime.act(trial['task_id'], {**actions[0], 'observation_id': frame.observation_id})
            runtime.pause(trial['task_id'])
        old.revoke()
        with authorization_scope(reviewer), origin_policy.origin_scope(current.identifier):
            preview = runtime.recovery.control('review_authorization', {'task_id': trial['task_id']})
            tail = runtime.recovery.control('create_authorized', {'task_id': trial['task_id'],
                'snapshot': preview['snapshot'], 'authorization_review': preview['authorization_review'],
                'spec': preview['draft'], 'note': 'Explicit fresh input consent only for the remaining file action'})
            frame = runtime.observe(tail['task_id'])
            runtime.act(tail['task_id'], {**actions[1], 'observation_id': frame.observation_id})
            runtime.pause(tail['task_id'])
            review = runtime.recovery.control('review_completion_authorization', {'task_id': tail['task_id']})
            reader = runtime.recovery.control('create_authorized_completion', {'task_id': tail['task_id'],
                'snapshot': review['snapshot'], 'authorization_review': review['authorization_review'],
                'note': 'Explicit permanent read-only completion review for actual remaining file effects'})
            assert runtime.finish(reader['task_id']).state == 'succeeded'
        scopes.enter_context(origin_policy.origin_scope(current.identifier))
        yield SimpleNamespace(runtime=runtime, users=users, owner=owner, reviewer=reviewer, old=old, current=current,
                              candidate=candidate, task_id=trial['task_id'], child_id=tail['task_id'],
                              reader=reader['task_id'], manifests=manifests)
    finally:
        with authorization_scope(None):
            runtime.close()
        scopes.close()


def test_actual_renewed_mixed_file_chain_keeps_original_trial_and_old_witness_without_input(renewed_execution,
                                                                                        monkeypatch):
    value, runtime = renewed_execution, renewed_execution.runtime
    before = [path.read_bytes() for path in value.manifests]
    witness = origin_policy._path(value.old.identifier).read_bytes()
    monkeypatch.setattr(NativeDesktopTarget, '_launch', no_helper)
    grant = issue(value, value.task_id, value.reader)
    request = {'candidate_id': value.candidate['id'], 'task_id': value.task_id,
               'execution_task_id': value.child_id, 'completion_task_id': value.reader, 'handoff_id': grant['id']}
    accepted = publish(value, request)
    proof = accepted['publication']['execution_review']
    assert accepted['publication']['task_id'] == value.task_id and accepted['version'] == 1
    assert proof['task_id'] == value.child_id and proof['verification_task'] == value.reader
    assert proof['completion_review']['effect_task'] == value.child_id
    assert proof['evidence_handoff']['id'] == grant['id']
    assert runtime.get(value.task_id).state == 'paused'
    assert len(runtime.store.actions(value.task_id)) == len(runtime.store.actions(value.child_id)) == 1
    assert runtime.store.actions(value.reader) == []
    assert [path.read_bytes() for path in value.manifests] == before
    assert origin_policy._path(value.old.identifier).read_bytes() == witness
    assert 'arguments' not in json.dumps(proof) and 'store_path' not in json.dumps(proof)
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(value.child_id)
    with pytest.raises(AgentTaskError, match='managed origin'):
        runtime.skills.control('preview', {'candidate_id': value.candidate['id']})
    assert_no_dag(runtime)
