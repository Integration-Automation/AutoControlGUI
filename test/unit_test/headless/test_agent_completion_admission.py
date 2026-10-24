"""Completion admission refuses incomplete effects, unreviewed helpers and partial durable bindings."""
from copy import deepcopy
import json
import sys
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError
from .test_agent_completion_recovery import completed as completed, approval, child


@pytest.mark.parametrize('status', ['prepared', 'dispatched', 'uncertain'])
def test_unresolved_source_effects_cannot_be_replaced_by_completion_review(completed, status):
    runtime = completed.runtime
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_actions SET status=? WHERE task_id=?', (status, completed.task_id))
    with pytest.raises(AgentTaskError, match='all finite source actions confirmed'):
        approval(completed)


def test_action_receipts_alone_never_prove_independent_application_completion(completed):
    runtime = completed.runtime
    spec = runtime.store.get(completed.task_id)['spec']
    spec['success_criteria'] = [{'kind': 'actions_complete'}]
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET spec=? WHERE id=?', (json.dumps(spec), completed.task_id))
    with pytest.raises(AgentTaskError, match='independent fresh'):
        approval(completed)


def test_custom_helper_is_never_launched_as_a_completion_fallback(completed):
    completed.original._argv = (sys.executable, '-u', '-c', "raise AssertionError('unreviewed helper launched')")
    with pytest.raises(AgentTaskError, match='supported permanent read-only'):
        approval(completed)


def test_private_proof_and_successor_link_rollback_together(completed):
    runtime, request = completed.runtime, approval(completed)
    with runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER refuse_completion BEFORE INSERT ON agent_readonly_completions "
                           "BEGIN SELECT RAISE(ABORT, 'owned rollback fixture'); END")
    with pytest.raises(AgentTaskError, match='database operation failed'):
        runtime.recovery.control('create_completion', request)
    with runtime.store.connection(write=True) as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_readonly_completions').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_task_recoveries').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_tasks').fetchone()[0] == 1
        connection.execute('DROP TRIGGER refuse_completion')
    assert runtime.recovery.control('create_completion', request)['state'] == 'queued'


def test_model_authored_options_do_not_grant_private_completion_authority(completed):
    runtime = completed.runtime
    spec = deepcopy(runtime.store.get(completed.task_id)['spec'])
    spec['options'].update(readonly_completion=True, completion_review={'effect_task': completed.task_id})
    ordinary = runtime.submit(spec)
    assert 'completion_review' not in runtime.get(ordinary.task_id).metadata
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_readonly_completions').fetchone()[0] == 0


def test_expired_completed_verifier_prunes_private_proof_and_closed_adapter_cache(completed):
    runtime, identifier = completed.runtime, child(completed)
    assert runtime.finish(identifier).state == 'succeeded'
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET updated=?', (time.time() - 32 * 86400,))
    assert runtime.prune()['deleted'] == [identifier]
    assert identifier not in runtime._completion_targets
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_readonly_completions').fetchone()[0] == 0
    with pytest.raises(AgentTaskError):
        runtime.resume(completed.task_id)


@pytest.mark.parametrize('mode', ['external', 'ollama'])
def test_dynamic_confirmed_effects_can_be_completed_by_fresh_independent_criteria(completed, mode):
    runtime = completed.runtime
    spec = runtime.store.get(completed.task_id)['spec']
    spec.update(mode=mode, actions=[])
    spec['success_criteria'] = [spec['success_criteria'][1]]
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET spec=? WHERE id=?', (json.dumps(spec), completed.task_id))
    identifier = child(completed)
    result = runtime.finish(identifier)
    assert result.state == 'succeeded' and len(result.verification) == 1
    assert runtime.store.get(identifier)['spec']['mode'] == 'external' and runtime.store.actions(identifier) == []


def test_missing_source_capture_is_a_typed_review_refusal_not_an_unhandled_lookup(completed):
    runtime = completed.runtime
    spec = runtime.store.get(completed.task_id)['spec']
    spec['actions'][0]['expect_capture'] = 'not-produced'
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET spec=? WHERE id=?', (json.dumps(spec), completed.task_id))
    with pytest.raises(AgentTaskError, match='source'):
        approval(completed)
