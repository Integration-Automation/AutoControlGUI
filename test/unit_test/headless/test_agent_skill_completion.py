"""Publish the actual pinned skill trial through separate owned-file completion evidence, without replay."""
import json
from contextlib import ExitStack
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@pytest.fixture
def trial(tmp_path, monkeypatch, request):
    scopes = ExitStack()
    kind = getattr(request, 'param', '')
    users = owner = reviewer = None
    if kind in {'named', 'named_caller'}:
        users = UserStore(tmp_path / 'users.json')
        users.add_user(user_id='owner', display_name='Owner', role='operator')
        users.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
    scopes.enter_context(authorization_scope(owner))
    output = tmp_path / 'result.txt'
    output.write_text('complete', encoding='utf-8')
    manifest = tmp_path / 'manifest.json'
    arguments = {'directory': str(tmp_path), 'path': str(manifest), 'names': ['result.txt']}
    definition = {'goal': 'Record actual owned-file workflow', 'target': 'local-files', 'mode': 'skill',
                  'roots': [str(tmp_path)], 'allowed_tools': ['AC_workflow_manifest'],
                  'actions': [{'tool': 'AC_workflow_manifest', 'arguments': arguments}],
                  'success_criteria': [{'kind': 'actions_complete'}, {'kind': 'file_exists', 'path': str(manifest)},
                                       {'kind': 'file_text', 'path': str(output), 'value': 'complete'}]}
    target = NativeDesktopTarget(resource_path=tmp_path / 'owned-input.lock')
    runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'local-files': target})
    try:
        source = runtime.submit(definition)
        assert run_task(runtime, source.task_id).state == 'succeeded'
        candidate = runtime.skills.control('record', {'task_id': source.task_id, 'name': 'Owned manifest'})
        task = runtime.skills.control('validate', {'candidate_id': candidate['id']})
        frame = runtime.observe(task['task_id'])
        runtime.act(task['task_id'], {'tool': 'AC_workflow_manifest', 'arguments': arguments,
                                      'observation_id': frame.observation_id})
        runtime.pause(task['task_id'])
        def forbidden(*_args, **_kwargs):
            raise AssertionError('confirmed workflow must not be replayed or the original target observed')
        monkeypatch.setattr(target, 'perform', forbidden)
        monkeypatch.setattr(target, 'observe', forbidden)
        with authorization_scope(reviewer):
            policy = {'owner_policy': 'source_owner'} if kind == 'named' else {}
            preview = runtime.recovery.control('preview_completion', {'task_id': task['task_id'], **policy})
            if policy:
                policy['ownership_review'] = preview['ownership']['review']
            child = runtime.recovery.control('create_completion', {
                'task_id': task['task_id'], 'snapshot': preview['snapshot'],
                'note': 'Reviewed actual file effects', **policy})
            if kind == 'retry':
                runtime.cancel(child['task_id'])
                retry = runtime.recovery.control('preview_completion', {'task_id': child['task_id']})
                child = runtime.recovery.control('create_completion', {
                    'task_id': child['task_id'], 'snapshot': retry['snapshot'], 'note': 'Reviewed new reader attempt'})
            assert runtime.finish(child['task_id']).state == 'succeeded'
        yield SimpleNamespace(runtime=runtime, candidate=candidate, task_id=task['task_id'], source_id=source.task_id,
                              child_id=child['task_id'], manifest=manifest, output=output,
                              users=users, owner=owner, reviewer=reviewer)
    finally:
        with authorization_scope(None):
            runtime.close()
        scopes.close()


def acceptance(trial):
    return {'candidate_id': trial.candidate['id'], 'task_id': trial.task_id,
            'completion_task_id': trial.child_id, 'expected_version': 0,
            'note': 'Reviewed original trial effects and independent completion'}


def test_publish_keeps_actual_validation_trial_and_separate_completion_provenance(trial):
    runtime = trial.runtime
    receipts = runtime.store.actions(trial.task_id)
    manifest = trial.manifest.read_bytes()
    accepted = runtime.skills.control('accept', acceptance(trial))
    assert accepted['state'] == 'accepted' and accepted['version'] == 1
    assert accepted['publication']['task_id'] == trial.task_id
    review = accepted['publication']['completion_review']
    assert review['task_id'] == trial.child_id and review['effect_task'] == trial.task_id
    assert runtime.get(trial.task_id).state == 'paused'
    assert runtime.store.actions(trial.task_id) == receipts and runtime.store.actions(trial.child_id) == []
    assert trial.manifest.read_bytes() == manifest
    assert runtime.get(trial.child_id).metadata['completion_contract'] == 1
    with runtime.store.connection() as connection:
        trials = connection.execute('SELECT task_id,purpose FROM agent_skill_trials').fetchall()
    assert [(item['task_id'], item['purpose']) for item in trials] == [(trial.task_id, 'validation')]
    assert 'store_path' not in json.dumps(review)


def test_changed_candidate_before_write_admission_cannot_commit_a_publication(trial, monkeypatch):
    from contextlib import contextmanager
    from je_auto_control.utils.agent_runtime import AgentTaskError
    runtime = trial.runtime
    original = runtime.store.connection
    armed = [True]
    @contextmanager
    def changed(*, write=False):
        if write and armed[0]:
            armed[0] = False
            with original(write=True) as connection:
                value = dict(trial.candidate['spec'], goal='Changed before publication admission')
                connection.execute('UPDATE agent_skill_candidates SET spec=? WHERE id=?',
                                   (json.dumps(value), trial.candidate['id']))
        with original(write=write) as connection:
            yield connection
    monkeypatch.setattr(runtime.store, 'connection', changed)
    with pytest.raises(AgentTaskError):
        runtime.skills.control('accept', acceptance(trial))
    with original() as connection:
        state = connection.execute('SELECT state FROM agent_skill_candidates WHERE id=?',
                                   (trial.candidate['id'],)).fetchone()[0]
        publications = connection.execute('SELECT COUNT(*) FROM agent_skill_publications').fetchone()[0]
    assert state == 'draft' and publications == 0


@pytest.mark.parametrize('trial', ['retry'], indirect=True)
def test_retried_reader_chain_retains_the_original_execution_trial(trial):
    value = trial.runtime.skills.control('accept', acceptance(trial))
    review = value['publication']['completion_review']
    assert review['effect_task'] == trial.task_id and review['source_task'] != trial.task_id
    assert trial.runtime.get(review['source_task']).state == 'cancelled'
    assert value['publication']['task_id'] == trial.task_id


def test_published_adoption_survives_restart_and_reader_retention_as_historical_audit(trial):
    runtime = trial.runtime
    value = runtime.skills.control('accept', acceptance(trial))
    proof = value['publication']['completion_review']
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET updated=0 WHERE id=?', (trial.child_id,))
    assert trial.child_id in runtime.prune()['deleted']
    runtime.close()
    reopened = AgentRuntime(runtime.store.path, targets={'local-files': NativeDesktopTarget()})
    try:
        current = reopened.skills.control('get', {'candidate_id': value['id']})
        assert current['publication']['completion_review'] == proof
        pinned = reopened.skills.control('run', {'skill_id': value['skill_id'], 'version': 1})
        assert reopened.get(pinned['task_id']).metadata['skill_pin']['version'] == 1
        assert reopened.store.actions(pinned['task_id']) == []
    finally:
        reopened.close()


def test_concurrent_requests_cannot_publish_two_versions_from_the_same_completion(trial):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from je_auto_control.utils.agent_runtime import AgentTaskError
    barrier = threading.Barrier(2)
    def publish(runtime):
        barrier.wait(timeout=10)
        try:
            return runtime.skills.control('accept', acceptance(trial))['version']
        except AgentTaskError:
            return 0
    with ThreadPoolExecutor(max_workers=2) as workers:
        values = list(workers.map(publish, (trial.runtime, trial.runtime)))
    assert sorted(values) == [0, 1]
    with trial.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_publications').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_completions').fetchone()[0] == 1
