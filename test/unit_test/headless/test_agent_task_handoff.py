"""Explicit non-DAG grants adopt other-caller completion without general reads or task transfer."""
import pytest

from headless.test_agent_skill_completion import acceptance, trial as _trial
from headless.test_agent_skill_recording_completion import recording as _recording, request_for
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.rbac.authorization import authorization_scope

recording = _recording
trial = _trial


def issue(value, source, leaf):
    request = {'source_task': source, 'task_id': leaf}
    with authorization_scope(value.reviewer):
        review = value.runtime.recovery.control('review_handoff', request)
        assert review['evidence']['source_task'] == source
        assert 'batch_id' not in review['evidence'] and 'node_id' not in review['evidence']
        created = {**request, 'review': review['handoff_review'],
                   'note': 'Explicitly adopt only this actual non-DAG completion evidence'}
        return value.runtime.recovery.control('create_handoff', created)['handoff']


def no_helper(*_args, **_kwargs):
    raise AssertionError('Evidence-only grant and adoption must never start a helper or replay input')


def assert_no_dag(runtime):
    with runtime.store.connection() as connection:
        for table in ('agent_dag_batches', 'agent_dag_nodes', 'agent_dag_local_tasks'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
def test_source_owner_records_other_caller_completion_only_with_an_explicit_task_grant(recording, monkeypatch):
    runtime = recording.runtime
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.skills.control('record', request_for(recording))
    before = runtime.store.actions(recording.task_id)
    manifest = recording.manifest.read_bytes()
    monkeypatch.setattr(NativeDesktopTarget, '_launch', no_helper)
    grant = issue(recording, recording.task_id, recording.child_id)
    candidate = runtime.skills.control('record', request_for(recording, handoff_id=grant['id']))
    assert candidate['owner']['user_id'] == 'owner'
    assert candidate['state'] == 'draft' and candidate['publication'] is None
    proof = candidate['provenance']['completion_review']
    assert proof['task_id'] == recording.child_id and proof['effect_task'] == recording.task_id
    assert proof['evidence_handoff']['id'] == grant['id']
    assert runtime.get(recording.task_id).state == 'paused'
    assert runtime.store.get(recording.child_id)['owner']['user_id'] == 'reviewer'
    assert runtime.store.actions(recording.task_id) == before and recording.manifest.read_bytes() == manifest
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(recording.child_id)
    assert_no_dag(runtime)
    runtime.recovery.control('revoke_handoff', {'handoff_id': grant['id']})
    with pytest.raises(AgentTaskError):
        runtime.skills.control('record', request_for(recording, handoff_id=grant['id'], name='Revoked grant'))
    assert len(runtime.skills.control('list')['candidates']) == 1


@pytest.mark.parametrize('trial', ['named_caller'], indirect=True)
def test_original_validation_trial_publishes_with_other_caller_task_evidence_without_replay(trial, monkeypatch):
    runtime = trial.runtime
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.skills.control('accept', acceptance(trial))
    before = runtime.store.actions(trial.task_id)
    manifest = trial.manifest.read_bytes()
    monkeypatch.setattr(NativeDesktopTarget, '_launch', no_helper)
    grant = issue(trial, trial.task_id, trial.child_id)
    result = runtime.skills.control('accept', {**acceptance(trial), 'handoff_id': grant['id']})
    assert result['state'] == 'accepted' and result['version'] == 1
    assert result['owner']['user_id'] == 'owner' and result['publication']['task_id'] == trial.task_id
    proof = result['publication']['completion_review']
    assert proof['task_id'] == trial.child_id and proof['effect_task'] == trial.task_id
    assert proof['evidence_handoff']['id'] == grant['id']
    assert runtime.get(trial.task_id).state == 'paused' and runtime.store.actions(trial.task_id) == before
    assert runtime.store.get(trial.child_id)['owner']['user_id'] == 'reviewer'
    assert trial.manifest.read_bytes() == manifest
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(trial.child_id)
    assert_no_dag(runtime)
