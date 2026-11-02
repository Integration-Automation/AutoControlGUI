"""Source owners and actual renewal reviewers remain live through private admission and later chains."""
from contextvars import Context

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, reviewed, create
from je_auto_control.utils.agent_runtime import AgentTaskError, origin_policy, task_authority
from je_auto_control.utils.rbac.authorization import AuthorizationError, authorization_scope

renewal = _renewal


@pytest.mark.parametrize('renewal', ['named'], indirect=True)
@pytest.mark.parametrize('principal', ['owner', 'reviewer'])
def test_principal_revocation_after_private_sql_leaves_no_renewed_reader(renewal, monkeypatch, principal):
    check = task_authority._check_pair
    def revoked(value):
        if 'source_snapshot' in value:
            renewal.users.remove_user(principal)
        check(value)
    monkeypatch.setattr(task_authority, '_check_pair', revoked)
    with authorization_scope(renewal.reviewer):
        _preview, request = reviewed(renewal, owner_policy='source_owner')
        with pytest.raises((AuthorizationError, AgentTaskError)):
            renewal.runtime.recovery.control('create_authorized_completion', request)
    with renewal.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_tasks').fetchone()[0] == 1
        for table in ('agent_task_recoveries', 'agent_readonly_completions', 'agent_task_authorizations',
                      'agent_recovery_owners'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


@pytest.mark.parametrize('renewal', ['named'], indirect=True)
def test_actual_renewal_reviewer_revocation_invalidates_current_completion_evidence(renewal):
    with authorization_scope(renewal.reviewer):
        child = create(renewal, owner_policy='source_owner')
        assert renewal.runtime.finish(child).state == 'succeeded'
    assert renewal.runtime.get(child).metadata['completion_contract'] == 1
    renewal.users.remove_user('reviewer')
    result = renewal.runtime.get(child)
    assert result.state == 'succeeded' and result.metadata['completion_contract'] == 0


@pytest.mark.parametrize('renewal', ['named'], indirect=True)
def test_new_reviewer_cannot_launder_a_revoked_previous_reader_issuer(renewal):
    with authorization_scope(renewal.reviewer):
        child = create(renewal, owner_policy='source_owner')
    renewal.runtime.pause(child)
    renewal.users.remove_user('reviewer')
    renewal.current.revoke()
    current = origin_policy.OriginWitness((renewal.allowed,))
    try:
        def next_review():
            with authorization_scope(renewal.owner), origin_policy.origin_scope(current.identifier):
                with pytest.raises((AuthorizationError, AgentTaskError)):
                    reviewed(renewal, child)
        Context().run(next_review)
    finally:
        origin_policy._path(current.identifier).unlink(missing_ok=True)
