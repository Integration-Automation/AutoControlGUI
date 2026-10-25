"""Grant approval, expiry, actual principals and immutable binding constrain every evidence-only read."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import json

import pytest

from headless.test_agent_evidence_handoff import handoff as _handoff, request_for, grant_for
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.evidence_handoff import EvidenceHandoffs
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope

handoff = _handoff


def consume(value, identifier, **changes):
    fields = {'batch_id': value.batch_id, 'node_id': 'a', 'source_task': value.source,
              'task_id': value.child, 'handoff_id': identifier, **changes}
    return value.runtime.recovery.handoff_evidence(**fields)


@pytest.mark.parametrize('identifier', [None, [], {}, '', 'missing', True])
def test_missing_or_invalid_grant_is_never_implicit_authority(handoff, identifier):
    with pytest.raises(AgentTaskError):
        consume(handoff, identifier)


@pytest.mark.parametrize('field', ['batch_id', 'node_id', 'source_task', 'task_id'])
def test_grant_never_applies_to_another_binding(handoff, field):
    grant = grant_for(handoff)
    with pytest.raises(AgentTaskError, match='identity differs'):
        consume(handoff, grant['id'], **{field: 'another-binding'})


def test_recipient_cannot_issue_its_own_grant_using_an_admins_review_token(handoff):
    with authorization_scope(handoff.reviewer):
        review = handoff.runtime.recovery.control('review_handoff', request_for(handoff))
    with pytest.raises(AgentTaskError, match='another caller'):
        handoff.runtime.recovery.control('create_handoff', {**request_for(handoff),
            'review': review['handoff_review'], 'note': 'Cannot approve someone else\'s evidence'})
    with handoff.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoffs').fetchone()[0] == 0


@pytest.mark.parametrize('change', ['owner', 'reviewer', 'reviewer_role'])
def test_real_owner_and_legacy_admitting_reviewer_stay_live(handoff, change):
    grant = grant_for(handoff)
    if change == 'reviewer_role':
        handoff.users.set_role('reviewer', 'operator')
    else:
        handoff.users.remove_user(change)
    with pytest.raises(AgentTaskError, match='authority changed'):
        consume(handoff, grant['id'])


@pytest.mark.parametrize('principal', ['owner', 'reviewer'])
def test_revocation_after_grant_sql_rolls_back_the_new_grant(handoff, monkeypatch, principal):
    insert = EvidenceHandoffs._insert
    def revoked(connection, row):
        insert(connection, row)
        handoff.users.remove_user(principal)
    monkeypatch.setattr(EvidenceHandoffs, '_insert', staticmethod(revoked))
    with pytest.raises(AgentTaskError, match='authority changed'):
        grant_for(handoff)
    with handoff.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoffs').fetchone()[0] == 0


def test_an_independent_admin_cannot_launder_a_revoked_original_admitting_actor(handoff):
    handoff.users.add_user(user_id='manager', display_name='Manager', role='admin')
    manager = AuthorizationContext('manager', 'admin', store_path=str(handoff.users.path))
    with authorization_scope(manager):
        preview = handoff.runtime.recovery.control('review_handoff', request_for(handoff))
        grant = handoff.runtime.recovery.control('create_handoff', {**request_for(handoff),
            'review': preview['handoff_review'], 'note': 'Independent manager evidence consent'})['handoff']
    handoff.users.remove_user('reviewer')
    with pytest.raises(AgentTaskError, match='authority changed'):
        consume(handoff, grant['id'])


def test_issuing_session_origin_revocation_invalidates_the_durable_consent(handoff, tmp_path):
    from je_auto_control.utils.agent_runtime import origin_policy
    witness = origin_policy.OriginWitness((tmp_path,))
    try:
        with origin_policy.origin_scope(witness.identifier):
            grant = grant_for(handoff)
        assert consume(handoff, grant['id'])[0]['task_id'] == handoff.child
        witness.revoke()
        with pytest.raises(AgentTaskError, match='origin'):
            consume(handoff, grant['id'])
    finally:
        origin_policy._path(witness.identifier).unlink(missing_ok=True)


def test_revoked_ids_stay_revoked_after_a_new_explicit_grant(handoff):
    first = grant_for(handoff)
    handoff.runtime.recovery.control('revoke_handoff', {'handoff_id': first['id']})
    second = grant_for(handoff)
    assert second['id'] != first['id']
    with pytest.raises(AgentTaskError, match='revoked'):
        consume(handoff, first['id'])
    assert consume(handoff, second['id'])[0]['task_id'] == handoff.child
    with handoff.runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_evidence_handoffs SET state='active' WHERE id=?", (first['id'],))
    with pytest.raises(AgentTaskError, match='revoked'):
        consume(handoff, first['id'])


def test_a_consent_record_never_extends_the_terminal_evidence_deadline(handoff, monkeypatch):
    from je_auto_control.utils.agent_runtime import evidence_handoff
    grant = grant_for(handoff)
    assert grant['expires'] == handoff.runtime.store.get(handoff.child)['updated'] + 30 * 86400
    monkeypatch.setattr(evidence_handoff, 'time', SimpleNamespace(time=lambda: grant['expires'] + 1))
    assert handoff.runtime.recovery.control('get_handoff', {'handoff_id': grant['id']})['handoff']['state'] == 'expired'
    with pytest.raises(AgentTaskError, match='expired'):
        consume(handoff, grant['id'])
    with authorization_scope(handoff.reviewer), pytest.raises(AgentTaskError, match='expired'):
        handoff.runtime.recovery.control('review_handoff', request_for(handoff))


def test_grants_require_private_original_admission_not_the_existing_public_tags(handoff):
    with handoff.runtime.store.connection(write=True) as connection:
        connection.execute('DELETE FROM agent_dag_local_tasks WHERE task_id=?', (handoff.source,))
    with authorization_scope(handoff.reviewer), pytest.raises(AgentTaskError, match='real bound local DAG admission'):
        handoff.runtime.recovery.control('review_handoff', request_for(handoff))


@pytest.mark.parametrize('field', ['budget', 'inputs', 'roots', 'success_criteria'])
def test_changed_scope_cannot_issue_a_handoff_even_when_the_child_succeeded(handoff, field):
    row = handoff.runtime.store.get(handoff.child)
    if field == 'budget':
        row['spec']['budget']['max_steps'] += 1
    elif field == 'inputs':
        row['spec']['inputs']['unexpected'] = 'value'
    elif field == 'roots':
        row['spec']['roots'] = [str(handoff.users.path.parent)]
    else:
        row['spec']['success_criteria'][-1]['value'] = 'a different goal'
    with handoff.runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET spec=? WHERE id=?', (json.dumps(row['spec']), handoff.child))
    with authorization_scope(handoff.reviewer), pytest.raises(AgentTaskError):
        handoff.runtime.recovery.control('review_handoff', request_for(handoff))


@pytest.mark.parametrize('participant', ['source', 'child'])
def test_unwinding_input_never_supplies_handoff_evidence(handoff, participant):
    identifier = getattr(handoff, participant)
    handoff.runtime._executing.add(identifier)
    try:
        with authorization_scope(handoff.reviewer), pytest.raises(AgentTaskError, match='input has not retired'):
            handoff.runtime.recovery.control('review_handoff', request_for(handoff))
    finally:
        handoff.runtime._executing.discard(identifier)


@pytest.mark.parametrize('handoff', [16, 17], indirect=True)
def test_grant_chain_bound_is_sixteen_real_links(handoff):
    with authorization_scope(handoff.reviewer):
        links = 0
        current = handoff.child
        with handoff.runtime.store.connection() as connection:
            while current != handoff.source:
                current = connection.execute('SELECT source_task FROM agent_task_recoveries WHERE task_id=?',
                                              (current,)).fetchone()[0]
                links += 1
        if links == 16:
            assert handoff.runtime.recovery.control('review_handoff', request_for(handoff))['approval_required']
        else:
            with pytest.raises(AgentTaskError, match='bounded real recovery chain'):
                handoff.runtime.recovery.control('review_handoff', request_for(handoff))


def test_exact_concurrent_consent_retries_create_one_active_grant(handoff):
    def grant(_index):
        return grant_for(handoff)['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(grant, range(2)))) == 1
    with handoff.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoffs').fetchone()[0] == 1
