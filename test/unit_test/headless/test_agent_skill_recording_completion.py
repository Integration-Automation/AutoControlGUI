"""Record real stopped owned-file workflows from separately reviewed read-only completion evidence."""
from contextlib import ExitStack
from types import SimpleNamespace
import json

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@pytest.fixture
def recording(tmp_path, monkeypatch, request):
    scopes = ExitStack()
    kind = getattr(request, 'param', 'skill')
    users = owner = reviewer = None
    if kind in {'named', 'named_caller'}:
        users = UserStore(tmp_path / 'users.json')
        users.add_user(user_id='owner', display_name='Owner', role='operator')
        users.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
    scopes.enter_context(authorization_scope(owner))
    witness = None
    if kind == 'origin':
        from je_auto_control.utils.agent_runtime import origin_policy
        # Real helpers must read the same private host witness; clean up only this test-owned UUID.
        witness = origin_policy.OriginWitness((tmp_path,))
        scopes.callback(origin_policy._path(witness.identifier).unlink, missing_ok=True)
        scopes.enter_context(origin_policy.origin_scope(witness.identifier))
    output = tmp_path / 'result.txt'
    output.write_text('complete', encoding='utf-8')
    manifest = tmp_path / 'manifest.json'
    arguments = {'directory': str(tmp_path), 'path': str(manifest), 'names': ['result.txt']}
    action = {'tool': 'AC_workflow_manifest', 'arguments': arguments}
    definition = {'goal': 'Record a stopped original workflow', 'target': 'local-files',
                  'mode': 'external' if kind == 'external' else 'skill',
                  'roots': [str(tmp_path)], 'allowed_tools': ['AC_workflow_manifest'],
                  'actions': [] if kind == 'external' else [action],
                  'success_criteria': [{'kind': 'file_exists', 'path': str(manifest)},
                                       {'kind': 'file_text', 'path': str(output), 'value': 'complete'}]}
    if kind != 'external':
        definition['success_criteria'].insert(0, {'kind': 'actions_complete'})
    target = NativeDesktopTarget(resource_path=tmp_path / 'owned-input.lock')
    runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'local-files': target})
    try:
        source = runtime.submit(definition)
        frame = runtime.observe(source.task_id)
        runtime.act(source.task_id, {**action, 'observation_id': frame.observation_id})
        runtime.pause(source.task_id)
        def forbidden(*_args, **_kwargs):
            raise AssertionError('recording must not replay or observe the original workflow')
        monkeypatch.setattr(target, 'perform', forbidden)
        monkeypatch.setattr(target, 'observe', forbidden)
        with authorization_scope(reviewer):
            policy = {'owner_policy': 'source_owner'} if kind == 'named' else {}
            preview = runtime.recovery.control('preview_completion', {'task_id': source.task_id, **policy})
            if policy:
                policy['ownership_review'] = preview['ownership']['review']
            child = runtime.recovery.control('create_completion', {
                'task_id': source.task_id, 'snapshot': preview['snapshot'],
                'note': 'Reviewed stopped workflow effects', **policy})
            assert runtime.finish(child['task_id']).state == 'succeeded'
        yield SimpleNamespace(runtime=runtime, task_id=source.task_id, child_id=child['task_id'], action=action,
                              manifest=manifest, output=output, users=users, owner=owner, reviewer=reviewer,
                              origin=witness)
    finally:
        with authorization_scope(None):
            runtime.close()
        scopes.close()


def request_for(value, **changes):
    return {'task_id': value.task_id, 'completion_task_id': value.child_id,
            'name': 'Reviewed stopped workflow', **changes}


def test_record_original_semantic_actions_without_replay_or_trial_fabrication(recording):
    runtime = recording.runtime
    receipts = runtime.store.actions(recording.task_id)
    manifest = recording.manifest.read_bytes()
    candidate = runtime.skills.control('record', request_for(recording))
    assert candidate['state'] == 'draft' and candidate['version'] == 0 and candidate['publication'] is None
    assert candidate['spec']['mode'] == 'skill' and candidate['spec']['actions'] == [recording.action]
    assert candidate['provenance']['source_task'] == recording.task_id
    proof = candidate['provenance']['completion_review']
    assert proof['task_id'] == recording.child_id and proof['effect_task'] == recording.task_id
    assert 'skill_pin' not in candidate['spec']['options']
    assert runtime.get(recording.task_id).state == 'paused'
    assert runtime.store.actions(recording.task_id) == receipts and runtime.store.actions(recording.child_id) == []
    assert recording.manifest.read_bytes() == manifest
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_trials').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_publications').fetchone()[0] == 0
    with pytest.raises(AgentTaskError, match='exact candidate'):
        runtime.skills.control('accept', {'candidate_id': candidate['id'], 'task_id': recording.child_id,
                                         'expected_version': 0, 'note': 'Reader is not a new trial'})


@pytest.mark.parametrize('recording', ['external'], indirect=True)
def test_external_source_records_actual_receipts_without_inventing_a_validation_trial(recording):
    candidate = recording.runtime.skills.control('record', request_for(recording))
    assert candidate['spec']['actions'] == [recording.action]
    assert {'kind': 'actions_complete'} in candidate['spec']['success_criteria']
    with recording.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_trials').fetchone()[0] == 0


def test_stopped_source_still_requires_explicit_completion_selection(recording):
    request = request_for(recording)
    request.pop('completion_task_id')
    with pytest.raises(AgentTaskError, match='verified success'):
        recording.runtime.skills.control('record', request)


def test_draft_publishes_only_after_its_own_new_validation(recording, monkeypatch):
    from je_auto_control.utils.agent_runtime.runner import run_task
    runtime = recording.runtime
    candidate = runtime.skills.control('record', request_for(recording))
    trial = runtime.skills.control('validate', {'candidate_id': candidate['id']})
    assert trial['task_id'] not in {recording.task_id, recording.child_id}
    monkeypatch.undo()
    assert run_task(runtime, trial['task_id']).state == 'succeeded'
    accepted = runtime.skills.control('accept', {'candidate_id': candidate['id'], 'task_id': trial['task_id'],
                                               'expected_version': 0, 'note': 'Reviewed the new exact trial'})
    assert accepted['version'] == 1 and accepted['publication']['task_id'] == trial['task_id']
    assert runtime.get(recording.task_id).state == 'paused'
    with runtime.store.connection() as connection:
        identifiers = connection.execute('SELECT task_id FROM agent_skill_trials').fetchall()
        assert [row[0] for row in identifiers] == [trial['task_id']]


def test_added_criteria_do_not_inherit_the_readers_verified_result(recording, monkeypatch):
    from je_auto_control.utils.agent_runtime.runner import run_task
    runtime = recording.runtime
    candidate = runtime.skills.control('record', request_for(recording, validation_criteria=[
        {'kind': 'file_text', 'path': str(recording.output), 'value': 'not independently verified'}]))
    assert runtime.get(recording.child_id).state == 'succeeded' and candidate['publication'] is None
    trial = runtime.skills.control('validate', {'candidate_id': candidate['id']})
    monkeypatch.undo()
    assert run_task(runtime, trial['task_id']).state != 'succeeded'
    with pytest.raises(AgentTaskError):
        runtime.skills.control('accept', {'candidate_id': candidate['id'], 'task_id': trial['task_id'],
                                         'expected_version': 0, 'note': 'Old reader cannot verify added criteria'})
    assert runtime.skills.control('get', {'candidate_id': candidate['id']})['state'] == 'draft'


def test_reader_retention_and_restart_preserve_only_historical_draft_provenance(recording):
    runtime = recording.runtime
    candidate = runtime.skills.control('record', request_for(recording))
    proof = candidate['provenance']['completion_review']
    assert 'store_path' not in json.dumps(proof)
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET updated=0 WHERE id=?', (recording.child_id,))
    assert recording.child_id in runtime.prune()['deleted']
    runtime.close()
    reopened = AgentRuntime(runtime.store.path, targets={'local-files': NativeDesktopTarget()})
    try:
        current = reopened.skills.control('get', {'candidate_id': candidate['id']})
        assert current['state'] == 'draft' and current['provenance']['completion_review'] == proof
        fresh = reopened.skills.control('validate', {'candidate_id': candidate['id']})
        assert reopened.store.actions(fresh['task_id']) == []
        with pytest.raises(AgentTaskError):
            reopened.skills.control('record', request_for(recording))
    finally:
        reopened.close()
