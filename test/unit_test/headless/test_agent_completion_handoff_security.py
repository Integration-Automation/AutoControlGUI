"""Renewed handoffs refuse stale, revoked or malformed consent without broadening task access."""
import json

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, create
from headless.test_agent_completion_handoff import completed as _completed, issue, request_for
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.evidence_handoff import _digest
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.rbac.authorization import authorization_scope

renewal = _renewal
completed = _completed
pytestmark = pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)


@pytest.mark.parametrize('field', ['scope', 'completion_authorization', 'owner_policy', 'spec'])
def test_public_requests_cannot_supply_private_completion_authority(completed, field):
    with authorization_scope(completed.reviewer), pytest.raises(AgentTaskError, match='fields'):
        completed.runtime.recovery.control('review_handoff', {**request_for(completed), field: {}})


@pytest.mark.parametrize('change', ['source', 'origin', 'reviewer'])
def test_review_cannot_survive_changed_source_or_current_authority(completed, change):
    runtime = completed.runtime
    with authorization_scope(completed.reviewer):
        preview = runtime.recovery.control('review_handoff', request_for(completed))
        if change == 'source':
            with runtime.store.connection(write=True) as connection:
                connection.execute("UPDATE agent_tasks SET reason='changed after review' WHERE id=?",
                                   (completed.source,))
        elif change == 'origin':
            completed.current.revoke()
        else:
            completed.users.remove_user('reviewer')
        with pytest.raises(AgentTaskError):
            runtime.recovery.control('create_handoff', {**request_for(completed),
                'review': preview['handoff_review'], 'note': 'Do not accept a stale completion grant'})
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoffs').fetchone()[0] == 0


def test_source_change_after_grant_sql_rolls_back_the_grant_and_trigger_change(completed):
    runtime = completed.runtime
    with runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TRIGGER owned_handoff_source AFTER INSERT ON agent_evidence_handoffs '
            "BEGIN UPDATE agent_tasks SET reason='changed inside grant SQL' WHERE id=NEW.source_task; END")
    with pytest.raises(AgentTaskError):
        issue(completed)
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoffs').fetchone()[0] == 0
    assert runtime.store.get(completed.source)['reason'] != 'changed inside grant SQL'


@pytest.mark.parametrize('witness', ['submission', 'accepted_request'])
def test_original_request_witness_change_inside_grant_sql_cannot_issue_a_stale_grant(completed, witness):
    runtime = completed.runtime
    statement = ("UPDATE agent_task_submissions SET spec_digest='changed' WHERE task_id=NEW.source_task;"
                 if witness == 'submission' else
                 "UPDATE agent_request_keys SET spec_hash='changed' WHERE task_id=NEW.source_task;")
    with runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TRIGGER owned_request_witness AFTER INSERT ON agent_evidence_handoffs '
                           'BEGIN ' + statement + ' END')
    with pytest.raises(AgentTaskError):
        issue(completed)
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoffs').fetchone()[0] == 0


@pytest.mark.parametrize('witness', ['submission', 'accepted_request'])
def test_readonly_admission_also_rechecks_original_request_witness_on_its_writer(renewal, witness):
    statement = ("UPDATE agent_task_submissions SET spec_digest='changed' "
                 if witness == 'submission' else "UPDATE agent_request_keys SET spec_hash='changed' ")
    statement += 'WHERE task_id=(SELECT source_task FROM agent_task_recoveries WHERE task_id=NEW.task_id);'
    with renewal.runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TRIGGER owned_readonly_request AFTER INSERT ON agent_readonly_completions '
                           'BEGIN ' + statement + ' END')
    with pytest.raises(AgentTaskError):
        create(renewal)
    with renewal.runtime.store.connection() as connection:
        for table, count in (('agent_tasks', 1), ('agent_task_recoveries', 0), ('agent_readonly_completions', 0)):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == count


@pytest.mark.parametrize('field', ['contract', 'kind', 'binding', 'completion_task', 'segments',
                                  'segment_order', 'segment_actor', 'context_lists', 'approved_roots'])
def test_matching_grant_digest_cannot_make_invalid_private_renewal_authoritative(completed, field):
    runtime = completed.runtime
    _review, _request, grant = issue(completed)
    with runtime.store.connection(write=True) as connection:
        proof = json.loads(connection.execute('SELECT details FROM agent_evidence_handoffs WHERE id=?',
                                              (grant['id'],)).fetchone()[0])
        bundle = proof['completion_authorization']
        if field == 'contract':
            bundle['contract'] = True
        elif field in {'kind', 'binding', 'completion_task'}:
            bundle[field] = 'invalid'
        elif field == 'segments':
            bundle['segments'] = None
        elif field == 'segment_order':
            bundle['segments'].reverse()
        elif field == 'segment_actor':
            bundle['segments'][0]['authorization']['actor'] = 'owner'
        elif field == 'context_lists':
            bundle['segments'][0]['authorization']['context']['current_origins'] = None
        else:
            bundle['segments'][0]['authorization']['approved_roots'] = [str(completed.allowed)]
        for segment in bundle['segments'] or []:
            authorization = segment['authorization']
            authorization['review'] = request_spec_digest(authorization['context'])
        connection.execute('UPDATE agent_evidence_handoffs SET details=?,review=? WHERE id=?',
                           (json.dumps(proof), _digest(proof), grant['id']))
    with pytest.raises(AgentTaskError):
        runtime.recovery.handoff_evidence(completed.batch_id, 'a', completed.source, completed.child, grant['id'])


def test_issuing_origin_revocation_blocks_consumption_but_keeps_history_and_revoke_available(completed):
    _review, _request, grant = issue(completed)
    completed.current.revoke()
    with pytest.raises(AgentTaskError):
        completed.runtime.recovery.handoff_evidence(completed.batch_id, 'a', completed.source,
                                                    completed.child, grant['id'])
    historical = completed.runtime.recovery.control('get_handoff', {'handoff_id': grant['id']})
    assert historical['handoff']['id'] == grant['id']
    listed = completed.runtime.recovery.control('list_handoffs', {'batch_id': completed.batch_id, 'node_id': 'a'})
    assert [item['id'] for item in listed['handoffs']] == [grant['id']]
    revoked = completed.runtime.recovery.control('revoke_handoff', {'handoff_id': grant['id']})
    assert revoked['handoff']['state'] == 'revoked'
