"""Renewed evidence grants keep real reader lineage, restart, retry and writer-revocation bounds."""
import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, create
from headless.test_agent_completion_handoff import completed as _completed, issue
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.rbac.authorization import authorization_scope

renewal = _renewal
completed = _completed
pytestmark = pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)


@pytest.mark.parametrize('count', [2, 16])
def test_real_reader_chain_keeps_successful_intermediate_readers_and_sixteen_link_bound(completed, count):
    with authorization_scope(completed.reviewer):
        for index in range(1, count):
            completed.child = create(completed, completed.child)
            if index < count - 1:
                completed.runtime.pause(completed.child)
        assert completed.runtime.finish(completed.child).state == 'succeeded'
    review, _request, grant = issue(completed)
    assert len(review['evidence']['segments']) == count
    reply, chain = completed.runtime.recovery.handoff_evidence(completed.batch_id, 'a', completed.source,
                                                              completed.child, grant['id'])
    assert reply['state'] == 'succeeded' and len(chain) == count
    assert all(not completed.runtime.store.actions(item['task_id']) for item in chain)


def test_existing_renewed_grant_survives_real_runtime_restart(completed):
    _review, _request, grant = issue(completed)
    completed.runtime.close()
    reopened = AgentRuntime(completed.runtime.store.path, targets={'local-files': completed.target})
    try:
        reply, _chain = reopened.recovery.handoff_evidence(completed.batch_id, 'a', completed.source,
                                                         completed.child, grant['id'])
        assert reply['state'] == 'succeeded' and reopened.get(completed.source).state == 'paused'
        with pytest.raises(AgentTaskError, match='another caller'):
            reopened.get(completed.child)
    finally:
        reopened.close()


def test_active_retry_requires_the_exact_review_note_and_revoked_ids_do_not_reactivate(completed):
    _review, request, grant = issue(completed)
    with authorization_scope(completed.reviewer):
        with pytest.raises(AgentTaskError, match='note'):
            completed.runtime.recovery.control('create_handoff', {**request, 'note': 'Changed review intent'})
    completed.runtime.recovery.control('revoke_handoff', {'handoff_id': grant['id']})
    with pytest.raises(AgentTaskError, match='revoked'):
        completed.runtime.recovery.handoff_evidence(completed.batch_id, 'a', completed.source,
                                                    completed.child, grant['id'])


def test_revocation_inside_the_consuming_writer_prevents_a_renewed_completion_reply(completed, monkeypatch):
    from je_auto_control.utils.agent_runtime.evidence_handoff import EvidenceHandoffs
    _review, _request, grant = issue(completed)
    original = EvidenceHandoffs._proof
    def revoked(self, connection, request, actor, **options):
        proof = original(self, connection, request, actor, **options)
        connection.execute("UPDATE agent_evidence_handoffs SET state='revoked' WHERE id=?", (grant['id'],))
        return proof
    monkeypatch.setattr(EvidenceHandoffs, '_proof', revoked)
    with pytest.raises(AgentTaskError, match='revoked'):
        completed.runtime.recovery.handoff_evidence(completed.batch_id, 'a', completed.source,
                                                    completed.child, grant['id'])
