"""Executable skill adoption keeps snapshots, callers, effects and atomic publication authority live."""
from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from headless.test_agent_skill_execution import execution as _execution, accept_request, review_request
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.task_skills import AgentSkills
from je_auto_control.utils.rbac.authorization import authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationContext

execution = _execution


def assert_unpublished(value):
    with value.runtime.store.connection() as connection:
        for table in ('agent_skill_publications', 'agent_skill_executions'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
        row = connection.execute('SELECT state,version FROM agent_skill_candidates WHERE id=?',
                                 (value.candidate['id'],)).fetchone()
    assert tuple(row) == ('draft', 0)


@pytest.mark.parametrize('execution', ['zero'], indirect=True)
def test_zero_effect_original_trial_can_adopt_its_complete_actual_successor(execution):
    assert execution.runtime.store.actions(execution.task_id) == []
    accepted = execution.runtime.skills.control('accept', accept_request(execution))
    assert accepted['publication']['task_id'] == execution.task_id and accepted['version'] == 1


@pytest.mark.parametrize('execution', ['named'], indirect=True)
def test_named_owner_can_adopt_explicit_source_owned_successor(execution):
    accepted = execution.runtime.skills.control('accept', accept_request(execution))
    assert accepted['owner']['user_id'] == 'owner'
    assert 'store_path' not in json.dumps(accepted['publication']['execution_review'])


@pytest.mark.parametrize('execution', ['legacy_owner'], indirect=True)
def test_original_owner_cannot_implicitly_adopt_an_admin_owned_successor(execution):
    with pytest.raises(AgentTaskError, match='another caller'):
        execution.runtime.skills.control('review_execution', review_request(execution))
    assert_unpublished(execution)


@pytest.mark.parametrize('execution', ['named'], indirect=True)
@pytest.mark.parametrize('change', ['owner', 'reviewer', 'reviewer_role'])
def test_current_owner_and_actual_admission_reviewer_are_required(execution, change):
    request = accept_request(execution)
    if change == 'reviewer_role':
        execution.users.set_role('reviewer', 'operator')
    else:
        execution.users.remove_user(change)
    with pytest.raises(AgentTaskError, match='authority changed'):
        execution.runtime.skills.control('accept', request)
    assert_unpublished(execution)


@pytest.mark.parametrize('execution', ['named'], indirect=True)
@pytest.mark.parametrize('principal', ['owner', 'reviewer'])
def test_revocation_after_publication_sql_rolls_back_version_and_all_evidence(execution, monkeypatch, principal):
    request = accept_request(execution)
    publish = AgentSkills._record_publication
    def revoked(*arguments):
        publish(*arguments)
        execution.users.remove_user(principal)
    monkeypatch.setattr(AgentSkills, '_record_publication', staticmethod(revoked))
    with pytest.raises(AgentTaskError, match='authority changed'):
        execution.runtime.skills.control('accept', request)
    assert_unpublished(execution)


@pytest.mark.parametrize('identifier', [None, [], {}, '', 'missing', 1, True])
def test_invalid_or_missing_executable_identity_does_not_publish(execution, identifier):
    with pytest.raises(AgentTaskError):
        execution.runtime.skills.control('review_execution', {**review_request(execution),
                                                               'execution_task_id': identifier})
    assert_unpublished(execution)


@pytest.mark.parametrize('corruption', ['missing', 'snapshot', 'cycle'])
def test_actual_private_recovery_chain_is_required(execution, corruption):
    with execution.runtime.store.connection(write=True) as connection:
        if corruption == 'missing':
            connection.execute('DELETE FROM agent_task_recoveries WHERE task_id=?', (execution.child_id,))
        elif corruption == 'snapshot':
            connection.execute('UPDATE agent_task_recoveries SET snapshot=? WHERE task_id=?',
                               ('not-the-source', execution.child_id))
        else:
            connection.execute('UPDATE agent_task_recoveries SET source_task=? WHERE task_id=?',
                               (execution.child_id, execution.child_id))
    with pytest.raises(AgentTaskError):
        execution.runtime.skills.control('review_execution', review_request(execution))
    assert_unpublished(execution)


@pytest.mark.parametrize('status', ['uncertain', 'dispatched', 'prepared', 'not_applied'])
def test_unknown_or_incomplete_final_effects_are_never_complete(execution, status):
    with execution.runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_actions SET status=? WHERE task_id=?', (status, execution.child_id))
    with pytest.raises(AgentTaskError, match='semantic plan'):
        execution.runtime.skills.control('review_execution', review_request(execution))
    assert_unpublished(execution)


@pytest.mark.parametrize('field', ['verification', 'retirement'])
def test_final_independent_completion_and_retirement_are_mandatory(execution, field):
    with execution.runtime.store.connection(write=True) as connection:
        if field == 'verification':
            connection.execute('UPDATE agent_tasks SET verification=? WHERE id=?', ('[]', execution.child_id))
        else:
            connection.execute('DELETE FROM agent_completion WHERE task_id=?', (execution.child_id,))
    with pytest.raises(AgentTaskError, match='completion'):
        execution.runtime.skills.control('review_execution', review_request(execution))
    assert_unpublished(execution)


def test_two_concurrent_acceptances_publish_only_one_version(execution):
    request = accept_request(execution)
    def accept(_index):
        with authorization_scope(None):
            try:
                return execution.runtime.skills.control('accept', request)['version']
            except AgentTaskError:
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(accept, range(2)), key=lambda item: item is None) == [1, None]
    with execution.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_executions').fetchone()[0] == 1


def test_published_execution_audit_survives_runtime_restart(execution):
    runtime = execution.runtime
    accepted = runtime.skills.control('accept', accept_request(execution))
    runtime.close()
    reopened = AgentRuntime(runtime.store.path, targets={'editor': execution.target})
    try:
        current = reopened.skills.control('get', {'candidate_id': execution.candidate['id']})
        assert current['publication'] == accepted['publication']
        assert reopened.get(execution.task_id).state == 'paused'
    finally:
        reopened.close()


@pytest.mark.parametrize('execution', ['named'], indirect=True)
@pytest.mark.parametrize('damage', ['json', 'contract', 'principal', 'review'])
def test_malformed_private_ownership_evidence_is_a_typed_refusal(execution, damage):
    with execution.runtime.store.connection(write=True) as connection:
        value = json.loads(connection.execute('SELECT details FROM agent_recovery_owners WHERE task_id=?',
                                              (execution.child_id,)).fetchone()[0])
        if damage == 'contract':
            value['contract'] = 1.0
        elif damage == 'principal':
            value['actor'] = {'store_path': str(execution.users.path)}
        elif damage == 'review':
            value['review'] = 'not-the-review'
        connection.execute('UPDATE agent_recovery_owners SET details=? WHERE task_id=?',
                           ('{' if damage == 'json' else json.dumps(value), execution.child_id))
    with pytest.raises(AgentTaskError):
        execution.runtime.skills.control('review_execution', review_request(execution))
    assert_unpublished(execution)


@pytest.mark.parametrize('execution', ['legacy_owner'], indirect=True)
def test_legacy_admission_reviewer_must_remain_live_for_an_independent_current_admin(execution):
    execution.users.add_user(user_id='manager', display_name='Manager', role='admin')
    manager = AuthorizationContext('manager', 'admin', store_path=str(execution.users.path))
    with authorization_scope(manager):
        request = accept_request(execution)
        execution.users.remove_user('reviewer')
        with pytest.raises(AgentTaskError, match='authority changed'):
            execution.runtime.skills.control('accept', request)
    assert_unpublished(execution)


@pytest.mark.parametrize('participant', ['root', 'leaf'])
def test_inflight_input_witness_prevents_passive_review(execution, participant):
    identifier = execution.task_id if participant == 'root' else execution.child_id
    execution.runtime._executing.add(identifier)
    try:
        with pytest.raises(AgentTaskError, match='input has not retired'):
            execution.runtime.skills.control('review_execution', review_request(execution))
    finally:
        execution.runtime._executing.discard(identifier)
    assert_unpublished(execution)
