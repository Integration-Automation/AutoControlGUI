"""Approval transactions, historical privacy and restart cannot weaken explicit evidence consent."""
from types import SimpleNamespace
import json

import pytest

from headless.test_agent_evidence_handoff import handoff as _handoff, request_for, grant_for
from headless.test_agent_evidence_handoff_security import consume
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.dag_continuation import DagContinuation
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope

handoff = _handoff


def review_for(value, grant):
    return value.runtime.batches.control('review_continuation', {'batch_id': value.batch_id,
        'definition': value.definition, 'decisions': [{'node_id': 'a', 'action': 'successor',
            'task_id': value.child, 'handoff_id': grant['id']}]})


def approval(value, review):
    return value.runtime.batches.control('approve_continuation', {
        **{key: review[key] for key in ('batch_id', 'definition', 'snapshot', 'decisions')},
        'note': 'Reviewed immutable consent for this exact original node'})


def test_revocation_after_review_prevents_approval(handoff):
    grant = grant_for(handoff)
    review = review_for(handoff, grant)
    handoff.runtime.recovery.control('revoke_handoff', {'handoff_id': grant['id']})
    with pytest.raises(AgentTaskError, match='evidence or decisions changed'):
        approval(handoff, review)
    assert handoff.runtime.batches.control('get', {'batch_id': handoff.batch_id})['state'] == 'waiting_review'


def test_actual_reviewer_revocation_after_adoption_sql_rolls_back_every_batch_change(handoff, monkeypatch):
    grant = grant_for(handoff)
    review = review_for(handoff, grant)
    apply = DagContinuation._apply
    def revoked(connection, batch, identifier, reports):
        apply(connection, batch, identifier, reports)
        handoff.users.remove_user('reviewer')
    monkeypatch.setattr(DagContinuation, '_apply', staticmethod(revoked))
    with pytest.raises(AgentTaskError, match='authority changed'):
        approval(handoff, review)
    with handoff.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_dag_approvals').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_dag_adoptions').fetchone()[0] == 0
        assert connection.execute('SELECT phase FROM agent_dag_nodes').fetchone()[0] == 'claimed'


def test_revoked_grant_inside_start_transaction_never_releases_a_batch(handoff):
    grant = grant_for(handoff)
    approved = approval(handoff, review_for(handoff, grant))
    with handoff.runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER owned_revoke BEFORE UPDATE OF state ON agent_dag_batches "
                           "WHEN NEW.state='running' BEGIN UPDATE agent_evidence_handoffs "
                           "SET state='revoked'; END")
    with pytest.raises(AgentTaskError, match='revoked'):
        handoff.runtime.batches.control('start_continuation', {'batch_id': handoff.batch_id,
            'definition': handoff.definition, 'approval_id': approved['approval_id'], 'max_parallel': 4})
    with handoff.runtime.store.connection() as connection:
        assert connection.execute('SELECT state FROM agent_dag_batches').fetchone()[0] == 'approved'
        assert connection.execute('SELECT state FROM agent_dag_approvals').fetchone()[0] == 'ready'


def test_later_recipient_session_can_add_a_stricter_origin_without_changing_the_consent(handoff, tmp_path):
    from je_auto_control.utils.agent_runtime import origin_policy
    grant = grant_for(handoff)
    witness = origin_policy.OriginWitness((tmp_path,))
    try:
        with origin_policy.origin_scope(witness.identifier):
            assert consume(handoff, grant['id'])[0]['task_id'] == handoff.child
    finally:
        origin_policy._path(witness.identifier).unlink(missing_ok=True)


def test_another_user_store_namespace_has_no_access_even_with_the_same_user_name(handoff, tmp_path):
    from je_auto_control.utils.rbac.users import UserStore
    grant = grant_for(handoff)
    other = UserStore(tmp_path / 'other-users.json')
    other.add_user(user_id='owner', display_name='Different identity', role='operator')
    identity = AuthorizationContext('owner', 'operator', store_path=str(other.path))
    with authorization_scope(identity), pytest.raises(AgentTaskError, match='another caller'):
        handoff.runtime.recovery.control('get_handoff', {'handoff_id': grant['id']})


def test_completion_projection_and_public_consent_omit_private_task_fields(handoff):
    secret = 'private-leaf-diagnostic-value'
    row = handoff.runtime.store.get(handoff.child)
    for report in row['verification']:
        report['private_diagnostic'] = secret
    with handoff.runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET verification=? WHERE id=?',
                           (json.dumps(row['verification']), handoff.child))
    grant = grant_for(handoff)
    result = consume(handoff, grant['id'])
    combined = json.dumps([grant, result])
    assert secret not in combined and 'store_path' not in combined and 'arguments' not in combined
    assert all(set(report) == {'kind', 'status'} for report in result[0]['verification'])


def test_consent_survives_restart_but_does_not_reassign_or_replay_tasks(handoff):
    grant = grant_for(handoff)
    original = handoff.runtime
    original.close()
    reopened = AgentRuntime(original.store.path, targets={'editor': handoff.target})
    reopened.background = SimpleNamespace(start=lambda _task_id: None)
    try:
        reply = reopened.recovery.handoff_evidence(handoff.batch_id, 'a', handoff.source, handoff.child, grant['id'])
        assert reply[0]['task_id'] == handoff.child
        with pytest.raises(AgentTaskError, match='another caller'):
            reopened.get(handoff.child)
        assert len(reopened.store.actions(handoff.source)) == len(reopened.store.actions(handoff.child)) == 1
    finally:
        reopened.close()


def test_malformed_historical_admitting_actor_is_a_typed_refusal(handoff):
    with handoff.runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_dag_local_tasks SET actor=? WHERE task_id=?', ('{', handoff.source))
    with authorization_scope(handoff.reviewer), pytest.raises(AgentTaskError):
        handoff.runtime.recovery.control('review_handoff', request_for(handoff))


@pytest.mark.parametrize(('field', 'value'), [('issuer', []), ('leaf_owner', None),
                                            ('binding', []), ('contract', True)])
def test_malformed_private_consent_is_a_typed_refusal_even_with_a_matching_digest(handoff, field, value):
    import hashlib
    grant = grant_for(handoff)
    with handoff.runtime.store.connection(write=True) as connection:
        proof = json.loads(connection.execute('SELECT details FROM agent_evidence_handoffs WHERE id=?',
                                              (grant['id'],)).fetchone()[0])
        proof[field] = value
        digest = hashlib.sha256(json.dumps(proof, sort_keys=True, allow_nan=False).encode()).hexdigest()
        connection.execute('UPDATE agent_evidence_handoffs SET details=?,review=? WHERE id=?',
                           (json.dumps(proof), digest, grant['id']))
    with pytest.raises(AgentTaskError):
        handoff.runtime.recovery.control('get_handoff', {'handoff_id': grant['id']})


def test_changed_original_admission_after_grant_sql_rolls_back_consent(handoff, monkeypatch):
    from dataclasses import asdict
    from je_auto_control.utils.agent_runtime.evidence_handoff import EvidenceHandoffs
    insert = EvidenceHandoffs._insert
    def changed(connection, row):
        insert(connection, row)
        connection.execute('UPDATE agent_dag_local_tasks SET actor=? WHERE task_id=?',
                           (json.dumps(asdict(handoff.owner)), handoff.source))
    monkeypatch.setattr(EvidenceHandoffs, '_insert', staticmethod(changed))
    with pytest.raises(AgentTaskError, match='changed'):
        grant_for(handoff)
    with handoff.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoffs').fetchone()[0] == 0
