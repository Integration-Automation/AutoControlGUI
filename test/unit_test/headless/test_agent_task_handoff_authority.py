"""Explicit task grants retain real issuing/consuming ceilings and closed-service boundaries."""
import pytest

from headless.test_agent_task_handoff import recording as _recording, issue
from headless.test_agent_skill_recording_completion import request_for
from je_auto_control.utils.agent_runtime import AgentTaskError, origin_policy
from je_auto_control.utils.agent_runtime.evidence_handoff import EvidenceHandoffs
from je_auto_control.utils.rbac.authorization import authorization_scope

recording = _recording
pytestmark = pytest.mark.parametrize('recording', ['named_caller'], indirect=True)


def test_recording_retains_both_issuing_and_consuming_session_origins(recording):
    runtime = recording.runtime
    roots = tuple(runtime.store.get(recording.task_id)['spec']['roots'])
    issuer, recipient = origin_policy.OriginWitness(roots), origin_policy.OriginWitness(roots)
    try:
        with origin_policy.origin_scope(issuer.identifier):
            grant = issue(recording, recording.task_id, recording.child_id)
        with origin_policy.origin_scope(recipient.identifier):
            candidate = runtime.skills.control('record', request_for(recording, handoff_id=grant['id']))
        assert {issuer.identifier, recipient.identifier} <= set(candidate['spec']['options']['origin_policies'])
        issuer.revoke()
        with pytest.raises(AgentTaskError):
            runtime.skills.control('record', request_for(recording, handoff_id=grant['id'], name='No lost ceiling'))
        assert len(runtime.skills.control('list')['candidates']) == 1
        assert runtime.recovery.control('get_handoff', {'handoff_id': grant['id']})['handoff']['id'] == grant['id']
        listed = runtime.recovery.control('list_handoffs', {'source_task': recording.task_id})
        assert [item['id'] for item in listed['handoffs']] == [grant['id']]
    finally:
        for witness in (issuer, recipient):
            origin_policy._path(witness.identifier).unlink(missing_ok=True)


def test_closed_runtime_rejects_handoff_history_before_opening_its_store(recording, monkeypatch):
    runtime = recording.runtime
    grant = issue(recording, recording.task_id, recording.child_id)
    runtime.close()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Closed handoff control may not reopen the task store')
    monkeypatch.setattr(runtime.store, 'connection', forbidden)
    with authorization_scope(recording.owner), pytest.raises(AgentTaskError, match='closed'):
        runtime.recovery.control('get_handoff', {'handoff_id': grant['id']})


@pytest.mark.parametrize('principal', ['owner', 'reviewer', 'reviewer_role'])
def test_actual_principal_loss_after_grant_sql_rolls_back_creation(recording, monkeypatch, principal):
    original = EvidenceHandoffs._insert
    def revoked(connection, row):
        original(connection, row)
        if principal == 'reviewer_role':
            recording.users.set_role('reviewer', 'operator')
        else:
            recording.users.remove_user(principal)
    monkeypatch.setattr(EvidenceHandoffs, '_insert', staticmethod(revoked))
    with pytest.raises(AgentTaskError):
        issue(recording, recording.task_id, recording.child_id)
    with recording.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_task_handoffs').fetchone()[0] == 0
