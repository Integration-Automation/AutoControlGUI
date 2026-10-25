"""Grant creation and exact retries must honor same-writer irrevocable revocation witnesses."""
import pytest

from headless.test_agent_task_handoff import recording as _recording, issue
from headless.test_agent_skill_completion import trial as _trial, acceptance
from headless.test_agent_completion_handoff import completed as _completed, renewal as _renewal, issue as dag_issue
from je_auto_control.utils.agent_runtime import AgentTaskError

recording = _recording
renewal = _renewal
completed = _completed
trial = _trial


def revoke_inside_insert(runtime, table, revocations):
    with runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TRIGGER owned_grant_revoke AFTER INSERT ON ' + table + ' BEGIN UPDATE ' +
                           table + " SET state='revoked' WHERE id=NEW.id; INSERT INTO " + revocations +
                           " VALUES (NEW.id,'{}',0); END")


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
def test_task_grant_revoked_by_its_insert_cannot_return_active_consent(recording):
    runtime = recording.runtime
    revoke_inside_insert(runtime, 'agent_task_handoffs', 'agent_task_handoff_revocations')
    with pytest.raises(AgentTaskError, match='revoked'):
        issue(recording, recording.task_id, recording.child_id)
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_task_handoffs').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_task_handoff_revocations').fetchone()[0] == 0


@pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)
def test_dag_grant_revoked_by_its_insert_cannot_return_active_consent(completed):
    runtime = completed.runtime
    revoke_inside_insert(runtime, 'agent_evidence_handoffs', 'agent_evidence_handoff_revocations')
    with pytest.raises(AgentTaskError, match='revoked'):
        dag_issue(completed)
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoffs').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_evidence_handoff_revocations').fetchone()[0] == 0


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
def test_exact_retry_cannot_resurrect_a_grant_with_a_durable_revocation_tombstone(recording):
    runtime = recording.runtime
    grant = issue(recording, recording.task_id, recording.child_id)
    runtime.recovery.control('revoke_handoff', {'handoff_id': grant['id']})
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_task_handoffs SET state='active' WHERE id=?", (grant['id'],))
    with pytest.raises(AgentTaskError, match='revoked'):
        issue(recording, recording.task_id, recording.child_id)


@pytest.mark.parametrize('trial', ['named_caller'], indirect=True)
def test_revocation_inside_publication_sql_rolls_back_acceptance_and_its_provenance(trial):
    runtime = trial.runtime
    grant = issue(trial, trial.task_id, trial.child_id)
    with runtime.store.connection(write=True) as connection:
        connection.execute('CREATE TRIGGER owned_publication_revoke AFTER INSERT ON agent_skill_publications '
                           "BEGIN UPDATE agent_task_handoffs SET state='revoked'; "
                           "INSERT INTO agent_task_handoff_revocations SELECT id,'{}',0 FROM agent_task_handoffs; END")
    with pytest.raises(AgentTaskError, match='revoked'):
        runtime.skills.control('accept', {**acceptance(trial), 'handoff_id': grant['id']})
    candidate = runtime.skills.control('get', {'candidate_id': trial.candidate['id']})
    assert candidate['state'] == 'draft' and candidate['publication'] is None
    with runtime.store.connection() as connection:
        for table in ('agent_skill_publications', 'agent_skill_completions', 'agent_task_handoff_revocations'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
