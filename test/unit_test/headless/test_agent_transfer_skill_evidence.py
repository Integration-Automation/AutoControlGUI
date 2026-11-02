"""Source-owned skill recording retains real actions and trials when selecting portable consent."""
import pytest

from headless.test_agent_skill_completion import acceptance, trial as _trial
from headless.test_agent_skill_execution import execution as _execution, review_request
from headless.test_agent_skill_recording_completion import recording as _recording, request_for
from headless.test_agent_transfer_evidence import evidence_server
from headless.test_agent_transfer_peer_security import post
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.errors import AgentControlBusy
from je_auto_control.utils.rbac.authorization import authorization_scope

recording = _recording
trial = _trial
execution = _execution


def portable_grant(value):
    with authorization_scope(value.reviewer):
        reviewed = value.runtime.transfers.control('review_evidence', {
            'source_task': value.task_id, 'task_id': value.child_id,
            'recipient_policy': 'source_owner', 'idempotency_key': 'owned-skill-evidence'})
        created = value.runtime.transfers.control('create_evidence', {
            'review': reviewed['review'], 'note': 'Share completion, retain original skill effects',
            'idempotency_key': 'owned-skill-evidence'})
    return created['evidence']['grant_id']


@pytest.mark.parametrize('recording', ['named_caller_request'], indirect=True)
def test_portable_consent_records_only_real_original_actions_without_fabricating_a_trial(recording):
    value = recording
    runtime = value.runtime
    identifier = portable_grant(value)
    receipts = runtime.store.actions(value.task_id)
    manifest = value.manifest.read_bytes()
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(value.child_id)
    candidate = runtime.skills.control('record', request_for(value, handoff_id=identifier))
    assert candidate['state'] == 'draft' and candidate['version'] == 0 and candidate['publication'] is None
    assert candidate['spec']['actions'] == [value.action]
    assert candidate['provenance']['source_task'] == value.task_id
    proof = candidate['provenance']['completion_review']
    assert proof['task_id'] == value.child_id and proof['effect_task'] == value.task_id
    assert proof['evidence_handoff']['id'] == identifier
    assert runtime.store.actions(value.task_id) == receipts and value.manifest.read_bytes() == manifest
    assert runtime.store.actions(value.child_id) == []
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_skill_trials').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM agent_task_handoffs').fetchone()[0] == 0
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(value.child_id)
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.skills.control('accept', {'candidate_id': candidate['id'], 'task_id': value.child_id,
            'expected_version': 0, 'note': 'Completion is not a validation trial'})


@pytest.mark.parametrize('trial', ['named_caller'], indirect=True)
def test_portable_completion_publishes_the_real_trial_and_preserves_its_original_version(trial):
    runtime = trial.runtime
    identifier = portable_grant(trial)
    receipts = runtime.store.actions(trial.task_id)
    manifest = trial.manifest.read_bytes()
    accepted = runtime.skills.control('accept', {**acceptance(trial), 'handoff_id': identifier})
    assert accepted['state'] == 'accepted' and accepted['version'] == 1
    assert accepted['publication']['task_id'] == trial.task_id
    proof = accepted['publication']['completion_review']
    assert proof['task_id'] == trial.child_id and proof['effect_task'] == trial.task_id
    assert proof['evidence_handoff']['id'] == identifier
    assert runtime.store.actions(trial.task_id) == receipts and trial.manifest.read_bytes() == manifest
    assert runtime.store.actions(trial.child_id) == []
    with runtime.store.connection() as connection:
        tasks = connection.execute('SELECT task_id,purpose FROM agent_skill_trials').fetchall()
        assert [(item['task_id'], item['purpose']) for item in tasks] == [(trial.task_id, 'validation')]
        assert connection.execute('SELECT count(*) FROM agent_task_handoffs').fetchone()[0] == 0
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(trial.child_id)


@pytest.mark.parametrize('recording', ['named_caller_request'], indirect=True)
def test_portable_revocation_inside_candidate_insert_rolls_back_the_entire_recording(recording):
    runtime = recording.runtime
    identifier = portable_grant(recording)
    with runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TRIGGER revoke_skill_grant AFTER INSERT ON agent_skill_candidates BEGIN '
            "UPDATE agent_transfer_grants SET state='revoked' WHERE id='" + identifier + "'; END")
    with pytest.raises(AgentTaskError):
        runtime.skills.control('record', request_for(recording, handoff_id=identifier))
    assert runtime.skills.control('list')['total'] == 0
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_skill_trials').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM agent_skill_publications').fetchone()[0] == 0


@pytest.mark.parametrize('recording', ['named_caller_request'], indirect=True)
def test_a_revoked_portable_grant_cannot_be_reinterpreted_as_an_old_local_grant(recording):
    runtime = recording.runtime
    identifier = portable_grant(recording)
    runtime.transfers.control('revoke_evidence', {'grant_id': identifier})
    with pytest.raises(AgentTaskError):
        runtime.skills.control('record', request_for(recording, handoff_id=identifier))
    assert runtime.skills.control('list')['total'] == 0


@pytest.mark.parametrize('trial', ['named_caller'], indirect=True)
def test_revocation_inside_publication_rolls_back_version_and_completion_adoption(trial):
    runtime = trial.runtime
    identifier = portable_grant(trial)
    with runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TRIGGER revoke_published_grant AFTER INSERT ON agent_skill_publications BEGIN '
            "UPDATE agent_transfer_grants SET state='revoked' WHERE id='" + identifier + "'; END")
    with pytest.raises(AgentTaskError):
        runtime.skills.control('accept', {**acceptance(trial), 'handoff_id': identifier})
    candidate = runtime.skills.control('get', {'candidate_id': trial.candidate['id']})
    assert candidate['state'] == 'draft' and candidate['version'] == 0 and candidate['publication'] is None
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_skill_completions').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM agent_skill_publications').fetchone()[0] == 0


@pytest.mark.parametrize('recording', ['named_caller_request'], indirect=True)
@pytest.mark.parametrize('change', ['issuer_role', 'expiry', 'different_completion'])
def test_changed_portable_authority_or_selection_cannot_record_a_skill(recording, change):
    value = recording
    runtime = value.runtime
    identifier = portable_grant(value)
    selected = value.child_id
    if change == 'issuer_role':
        value.users.set_role('reviewer', 'viewer')
    elif change == 'expiry':
        with runtime.store.connection(write=True) as connection:
            connection.execute('UPDATE agent_transfer_grants SET expires=0 WHERE id=?', (identifier,))
    else:
        selected = value.task_id
    with pytest.raises(AgentTaskError):
        runtime.skills.control('record', request_for(value, completion_task_id=selected, handoff_id=identifier))
    assert runtime.skills.control('list')['total'] == 0


@pytest.mark.parametrize('recording', ['named_caller_request'], indirect=True)
def test_authenticated_source_service_records_portable_completion_and_rejects_revocation(recording):
    value = recording
    identifier = portable_grant(value)
    with evidence_server(value.runtime, value.users) as server:
        token = value.users.rotate_token('owner')
        request = {'operation': 'record', 'request': request_for(value, handoff_id=identifier)}
        status, draft = post(server, '/agent/skill', request, token=token)
        assert status == 200, draft
        assert draft['state'] == 'draft' and draft['spec']['actions'] == [value.action]
        assert draft['provenance']['completion_review']['task_id'] == value.child_id
        status, revoked = post(server, '/agent/transfer', {'operation': 'revoke_evidence',
            'request': {'grant_id': identifier}}, token=token)
        assert status == 200, revoked
        status, denied = post(server, '/agent/skill', request, token=token)
        assert status == 409, denied
    assert value.runtime.skills.control('list')['total'] == 1


@pytest.mark.parametrize('execution', ['legacy_owner'], indirect=True)
def test_portable_executable_chain_retains_original_trial_effects_and_explicit_review(execution):
    value = execution
    runtime = value.runtime
    identifier = portable_grant(value)
    calls = list(value.target.calls)
    request = {**review_request(value), 'handoff_id': identifier}
    reviewed = runtime.skills.control('review_execution', request)
    accepted = runtime.skills.control('accept', {**request, 'execution_review': reviewed['execution_review'],
        'expected_version': 0, 'note': 'Review exact original effects and the granted completed successor'})
    assert accepted['version'] == 1 and accepted['publication']['task_id'] == value.task_id
    proof = accepted['publication']['execution_review']
    assert proof['source_task'] == value.task_id and proof['task_id'] == value.child_id
    assert proof['evidence_handoff']['id'] == identifier
    assert value.target.calls == calls
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_skill_trials').fetchone()[0] == 1
    with pytest.raises(AgentTaskError, match='another caller'):
        runtime.get(value.child_id)


@pytest.mark.parametrize('execution', ['legacy_owner'], indirect=True)
def test_runtime_owner_remains_held_through_portable_publication(execution, monkeypatch):
    value = execution
    runtime = value.runtime
    identifier = portable_grant(value)
    request = {**review_request(value), 'handoff_id': identifier}
    reviewed = runtime.skills.control('review_execution', request)
    original = runtime.skills._record_publication

    def during_write(*args, **kwargs):
        original(*args, **kwargs)
        with pytest.raises(AgentTaskError, match='active transfer'):
            runtime.close()
        with pytest.raises(AgentControlBusy, match='another runtime'):
            AgentRuntime(runtime.store.path, targets={})

    monkeypatch.setattr(runtime.skills, '_record_publication', during_write)
    result = runtime.skills.control('accept', {**request, 'execution_review': reviewed['execution_review'],
        'expected_version': 0, 'note': 'Retain the original owner through publication'})
    assert result['version'] == 1 and result['publication']['task_id'] == value.task_id
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_skill_publications').fetchone()[0] == 1
    runtime.close()
    reopened = AgentRuntime(runtime.store.path, targets={})
    reopened.close()


@pytest.mark.parametrize('recording', ['named_caller_request'], indirect=True)
def test_runtime_owner_remains_held_through_portable_recording(recording, monkeypatch):
    value = recording
    runtime = value.runtime
    identifier = portable_grant(value)
    original = runtime.skills._insert_candidate

    def during_write(*args, **kwargs):
        result = original(*args, **kwargs)
        with pytest.raises(AgentTaskError, match='active transfer'):
            runtime.close()
        with pytest.raises(AgentControlBusy, match='another runtime'):
            AgentRuntime(runtime.store.path, targets={})
        return result

    monkeypatch.setattr(runtime.skills, '_insert_candidate', during_write)
    result = runtime.skills.control('record', request_for(value, handoff_id=identifier))
    assert result['state'] == 'draft' and result['publication'] is None
    runtime.close()
    reopened = AgentRuntime(runtime.store.path, targets={})
    reopened.close()
