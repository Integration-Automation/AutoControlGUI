"""Original DAGs adopt current independent evidence, never revive their retired input admission."""
import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, reviewed, create
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.rbac.authorization import AuthorizationError

renewal = _renewal


@pytest.mark.parametrize('renewal', ['dag'], indirect=True)
def test_original_batch_adoption_is_invalidated_when_renewed_evidence_loses_authority(renewal):
    child = create(renewal)
    assert renewal.runtime.finish(child).state == 'succeeded'
    batches = renewal.runtime.batches
    review = batches.control('review_continuation', {'batch_id': renewal.batch_id, 'definition': renewal.definition,
        'decisions': [{'node_id': 'a', 'action': 'successor', 'task_id': child}]})
    assert review['can_approve'] is True
    approved = batches.control('approve_continuation', {
        **{key: review[key] for key in ('batch_id', 'definition', 'snapshot', 'decisions')},
        'note': 'Adopt only the newly authorized independent completion evidence'})
    started = batches.control('start_continuation', {'batch_id': renewal.batch_id, 'definition': renewal.definition,
        'approval_id': approved['approval_id'], 'max_parallel': 4})
    request = {'batch_id': renewal.batch_id, 'node_id': 'a', 'attempt': started['attempt']}
    assert batches.control('validate_node', request)['outcome'] == 'completed'
    renewal.current.revoke()
    with pytest.raises(AgentTaskError, match='retirement contract'):
        batches.control('validate_node', request)
    with renewal.runtime.store.connection() as connection:
        assert connection.execute('SELECT phase FROM agent_dag_nodes WHERE batch_id=?',
                                  (renewal.batch_id,)).fetchone()[0] == 'unknown'
    assert renewal.runtime.get(renewal.source).state == 'paused'
    assert len(renewal.runtime.store.actions(renewal.source)) == 1 and renewal.runtime.store.actions(child) == []


@pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)
def test_original_dag_admitting_actor_remains_live_during_readonly_renewal(renewal):
    renewal.users.remove_user('reviewer')
    with pytest.raises((AuthorizationError, AgentTaskError)):
        reviewed(renewal)


@pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)
def test_original_dag_admission_identity_change_inside_sql_rolls_back_the_reader(renewal):
    from dataclasses import asdict
    import json
    from je_auto_control.utils.rbac.authorization import AuthorizationContext
    renewal.users.add_user(user_id='manager', display_name='Another manager', role='admin')
    actor = AuthorizationContext('manager', 'admin', store_path=str(renewal.users.path))
    _preview, request = reviewed(renewal)
    with renewal.runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TABLE owned_actor(value TEXT NOT NULL)')
        connection.execute('INSERT INTO owned_actor VALUES (?)', (json.dumps(asdict(actor)),))
        connection.execute('CREATE TRIGGER owned_actor_change AFTER INSERT ON agent_readonly_completions '
            'BEGIN UPDATE agent_dag_local_tasks SET actor=(SELECT value FROM owned_actor) '
            'WHERE task_id=(SELECT source_task FROM agent_task_recoveries WHERE task_id=NEW.task_id); END')
    with pytest.raises(AgentTaskError, match='changed'):
        renewal.runtime.recovery.control('create_authorized_completion', request)
    with renewal.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_tasks').fetchone()[0] == 1
