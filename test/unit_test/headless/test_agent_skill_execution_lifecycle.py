"""Full original semantic effects remain bounded, retained and distinct from rebuilt session state."""
import json

import pytest

from headless.test_agent_skill_execution import execution as _execution, accept_request, review_request, successor
from headless.test_agent_skill_execution_security import assert_unpublished
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.retention import prune_tasks
from je_auto_control.utils.agent_runtime.runner import run_task

execution = _execution


@pytest.mark.parametrize('execution', ['capture'], indirect=True)
def test_actual_capture_receipts_can_match_fresh_reviewed_literals_without_restoring_old_captures(execution):
    accepted = execution.runtime.skills.control('accept', accept_request(execution))
    assert accepted['publication']['task_id'] == execution.task_id
    leaf = execution.runtime.store.get(execution.child_id)['spec']
    assert '$capture' not in json.dumps(leaf['actions'])
    assert len(execution.runtime.store.actions(execution.task_id)) == 1


@pytest.mark.parametrize('execution', ['capture_mismatch'], indirect=True)
def test_fresh_literal_recovery_cannot_claim_different_original_capture_semantics(execution):
    assert execution.runtime.get(execution.child_id).state == 'succeeded'
    with pytest.raises(AgentTaskError, match='semantic plan'):
        execution.runtime.skills.control('review_execution', review_request(execution))
    assert_unpublished(execution)


@pytest.mark.parametrize('length', [16, 17])
def test_only_at_most_sixteen_actual_executable_recovery_links_can_be_reviewed(execution, length):
    runtime = execution.runtime
    trial = runtime.skills.control('validate', {'candidate_id': execution.candidate['id']})
    identifier = trial['task_id']
    for _index in range(length):
        runtime.pause(identifier)
        identifier = successor(runtime, identifier)['task_id']
    assert run_task(runtime, identifier).state == 'succeeded'
    request = {**review_request(execution), 'task_id': trial['task_id'], 'execution_task_id': identifier}
    if length == 16:
        review = runtime.skills.control('review_execution', request)
        assert len(review['evidence']['segments']) == 16
    else:
        with pytest.raises(AgentTaskError, match='bounded real recovery chain'):
            runtime.skills.control('review_execution', request)
    assert_unpublished(execution)


@pytest.mark.parametrize('published', [False, True])
def test_expired_execution_evidence_is_not_authority_but_published_audit_survives(execution, published):
    runtime = execution.runtime
    request = accept_request(execution)
    accepted = runtime.skills.control('accept', request) if published else None
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET updated=1 WHERE id=?', (execution.child_id,))
    deleted = prune_tasks(runtime)['deleted']
    assert execution.child_id in deleted
    if published:
        current = runtime.skills.control('get', {'candidate_id': execution.candidate['id']})
        assert current['publication'] == accepted['publication']
    else:
        with pytest.raises(AgentTaskError):
            runtime.skills.control('accept', request)
        assert_unpublished(execution)
