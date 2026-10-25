"""Renewed evidence keeps its actual issuer, historical principals and issuing-session ceilings live."""
from contextvars import Context

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal
from headless.test_agent_completion_handoff import completed as _completed, issue
from je_auto_control.utils.agent_runtime import AgentTaskError, origin_policy
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope

renewal = _renewal
completed = _completed
pytestmark = pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)


def test_a_broader_issuing_session_is_retained_and_cannot_replace_the_readers_narrower_ceiling(completed):
    witness = origin_policy.OriginWitness((completed.allowed,))
    try:
        def issued():
            with authorization_scope(completed.reviewer), origin_policy.origin_scope(witness.identifier):
                return issue(completed)
        preview, _request, grant = Context().run(issued)
        summary = preview['evidence']['completion_authorization']
        assert completed.current.identifier in summary['retained_origins']
        assert witness.identifier in summary['current_origins']
        reply, _chain = completed.runtime.recovery.handoff_evidence(completed.batch_id, 'a', completed.source,
                                                                  completed.child, grant['id'])
        assert reply['state'] == 'succeeded'
        witness.revoke()
        with pytest.raises(AgentTaskError):
            completed.runtime.recovery.handoff_evidence(completed.batch_id, 'a', completed.source,
                                                        completed.child, grant['id'])
    finally:
        origin_policy._path(witness.identifier).unlink(missing_ok=True)


def test_another_admin_cannot_launder_the_actual_readonly_reviewers_revocation(completed):
    _preview, _request, grant = issue(completed)
    completed.users.add_user(user_id='other', display_name='Another manager', role='admin')
    other = AuthorizationContext('other', 'admin', store_path=str(completed.users.path))
    completed.users.remove_user('reviewer')
    with authorization_scope(other), pytest.raises(AgentTaskError):
        completed.runtime.recovery.handoff_evidence(completed.batch_id, 'a', completed.source,
                                                    completed.child, grant['id'])


@pytest.mark.parametrize('change', ['origin', 'reviewer'])
def test_post_insert_authority_change_rolls_back_a_new_grant(completed, monkeypatch, change):
    from je_auto_control.utils.agent_runtime.evidence_handoff import EvidenceHandoffs
    inserted = EvidenceHandoffs._insert
    def revoked(connection, row):
        inserted(connection, row)
        if change == 'origin':
            completed.current.revoke()
        else:
            completed.users.remove_user('reviewer')
    monkeypatch.setattr(EvidenceHandoffs, '_insert', staticmethod(revoked))
    with pytest.raises(AgentTaskError):
        issue(completed)
    with completed.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoffs').fetchone()[0] == 0


@pytest.mark.parametrize('change', ['missing', 'corrupt'])
def test_unavailable_original_witness_is_never_restored_by_handoff(completed, change):
    path = origin_policy._path(completed.old.identifier)
    if change == 'missing':
        path.unlink()
    else:
        path.write_text('{', encoding='utf-8')
    _preview, _request, grant = issue(completed)
    reply, _chain = completed.runtime.recovery.handoff_evidence(completed.batch_id, 'a', completed.source,
                                                              completed.child, grant['id'])
    assert reply['state'] == 'succeeded'
    assert not path.exists() if change == 'missing' else path.read_text(encoding='utf-8') == '{'
