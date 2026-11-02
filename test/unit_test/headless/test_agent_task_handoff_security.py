"""Non-DAG grants reject stale private bindings and roll back actual writer-side mutations."""
import json

import pytest

from headless.test_agent_task_handoff import recording as _recording, issue
from headless.test_agent_skill_recording_completion import request_for
from headless.test_agent_completion_handoff import completed as _completed, renewal as _renewal
from headless.test_agent_completion_authorization import create
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.evidence_handoff import _digest
from je_auto_control.utils.rbac.authorization import authorization_scope

recording = _recording
renewal = _renewal
completed = _completed


def no_draft(value):
    with value.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_candidates').fetchone()[0] == 0


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
@pytest.mark.parametrize('field', ['policy', 'scope', 'completion_authorization', 'owner_policy'])
def test_public_task_handoff_requests_cannot_supply_authority(recording, field):
    with authorization_scope(recording.reviewer), pytest.raises(AgentTaskError, match='fields'):
        recording.runtime.recovery.control('review_handoff', {
            'source_task': recording.task_id, 'task_id': recording.child_id, field: {}})


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
def test_source_mutation_inside_grant_insert_rolls_back_the_actual_task_grant(recording):
    runtime = recording.runtime
    with runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TRIGGER owned_task_grant AFTER INSERT ON agent_task_handoffs '
                           "BEGIN UPDATE agent_tasks SET reason='changed within grant SQL' "
                           'WHERE id=NEW.source_task; END')
    with pytest.raises(AgentTaskError):
        issue(recording, recording.task_id, recording.child_id)
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_task_handoffs').fetchone()[0] == 0
    assert runtime.get(recording.task_id).reason != 'changed within grant SQL'


@pytest.mark.parametrize('recording', ['named_caller_request'], indirect=True)
def test_real_accepted_request_change_after_grant_sql_cannot_leave_a_stale_grant(recording):
    runtime = recording.runtime
    with runtime.store.connection(write=True) as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_request_keys WHERE task_id=?',
                                  (recording.task_id,)).fetchone()[0] == 1
        connection.execute('CREATE TRIGGER owned_request_change AFTER INSERT ON agent_task_handoffs '
                           "BEGIN UPDATE agent_request_keys SET spec_hash='changed' "
                           'WHERE task_id=NEW.source_task; END')
    with pytest.raises(AgentTaskError):
        issue(recording, recording.task_id, recording.child_id)
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_task_handoffs').fetchone()[0] == 0


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
def test_revocation_during_draft_sql_rolls_back_the_draft_and_tombstone(recording):
    runtime = recording.runtime
    grant = issue(recording, recording.task_id, recording.child_id)
    with runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TRIGGER owned_draft_revoke AFTER INSERT ON agent_skill_candidates '
                           "BEGIN UPDATE agent_task_handoffs SET state='revoked'; "
                           "INSERT INTO agent_task_handoff_revocations SELECT id,'{}',0 FROM agent_task_handoffs; END")
    with pytest.raises(AgentTaskError, match='revoked'):
        runtime.skills.control('record', request_for(recording, handoff_id=grant['id']))
    no_draft(recording)
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_task_handoff_revocations').fetchone()[0] == 0
    assert runtime.recovery.control('get_handoff', {'handoff_id': grant['id']})['handoff']['state'] == 'active'


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
@pytest.mark.parametrize('field', ['contract', 'binding', 'leaf_owner', 'segments', 'issuer', 'unrecognized'])
def test_matching_private_digest_cannot_supply_different_completion_authority(recording, field):
    runtime = recording.runtime
    grant = issue(recording, recording.task_id, recording.child_id)
    with runtime.store.connection(write=True) as connection:
        row = connection.execute('SELECT details FROM agent_task_handoffs WHERE id=?', (grant['id'],)).fetchone()
        proof = json.loads(row[0])
        if field == 'contract':
            proof[field] = True
        elif field == 'binding':
            proof[field]['kind'] = 'invented-dag'
        elif field in {'leaf_owner', 'issuer'}:
            proof[field]['user_id'] = 'owner'
        elif field == 'segments':
            proof[field] = []
        else:
            proof[field] = {'input_authorized': True}
        connection.execute('UPDATE agent_task_handoffs SET details=?,review=? WHERE id=?',
                           (json.dumps(proof), _digest(proof), grant['id']))
    with pytest.raises(AgentTaskError):
        runtime.skills.control('record', request_for(recording, handoff_id=grant['id']))
    no_draft(recording)


@pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)
@pytest.mark.parametrize('root', ['original', 'reader'])
def test_real_dag_ancestry_cannot_escape_its_batch_through_a_task_handoff(completed, root):
    source, leaf = completed.source, completed.child
    if root == 'reader':
        source = leaf
        with authorization_scope(completed.reviewer):
            leaf = create(completed, source)
            assert completed.runtime.finish(leaf).state == 'succeeded'
        assert 'dag_batch' not in completed.runtime.store.get(source)['spec']['options']
    with pytest.raises(AgentTaskError, match='DAG evidence'):
        issue(completed, source, leaf)
