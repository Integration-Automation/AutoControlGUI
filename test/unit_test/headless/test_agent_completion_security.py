"""Read-only completion keeps live source authority, fresh criteria and durable cancellation/retirement."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import asdict
import json

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.input_journal import InputJournal
from je_auto_control.utils.agent_runtime.readonly_target import ReadOnlyNativeTarget
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from je_auto_control.utils.rbac.users import UserStore
from .test_agent_completion_recovery import completed as completed, approval, child


def test_changed_source_after_observation_stops_verification_and_retires_reader(completed, monkeypatch):
    runtime, identifier = completed.runtime, child(completed)
    observe = ReadOnlyNativeTarget.observe
    def changed(adapter):
        reply = observe(adapter)
        runtime.store.update(completed.task_id, 'paused', reason='new source review during observation')
        return reply
    monkeypatch.setattr(ReadOnlyNativeTarget, 'observe', changed)
    with pytest.raises(AgentTaskError, match='snapshot'):
        runtime.finish(identifier)
    result = runtime.get(identifier)
    assert result.state == 'waiting_user' and result.metadata['input_released'] is True
    assert result.metadata['completion_contract'] == 0


def test_explicit_review_retry_cannot_drop_the_original_effect_owners_live_authority(completed, tmp_path):
    runtime = completed.runtime
    users = UserStore(tmp_path / 'users.json')
    users.add_user(user_id='owner', display_name='Owner', role='operator')
    users.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
    owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
    reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET owner=? WHERE id=?',
                           (json.dumps(asdict(owner)), completed.task_id))
    with authorization_scope(reviewer):
        identifier = child(completed)
        runtime.cancel(identifier)
        users.set_role('owner', 'viewer')
        with pytest.raises(AuthorizationError):
            runtime.recovery.control('preview_completion', {'task_id': identifier})


def test_fresh_criteria_fail_then_resume_reads_current_files_without_source_replay(completed):
    runtime, identifier = completed.runtime, child(completed)
    completed.output.write_text('missing marker', encoding='utf-8')
    result = runtime.finish(identifier)
    assert result.state == 'waiting_user' and result.metadata['input_released'] is True
    assert [item['status'] for item in result.verification] == ['passed', 'failed']
    completed.output.write_text('complete', encoding='utf-8')
    runtime.resume(identifier)
    assert runtime.finish(identifier).state == 'succeeded'
    assert runtime.store.actions(identifier) == []


def test_completion_task_refuses_action_preparation_and_ordinary_executable_successors(completed):
    runtime, identifier = completed.runtime, child(completed)
    with pytest.raises(AgentTaskError, match='read-only'):
        runtime.act(identifier, {'tool': 'AC_workflow_manifest', 'arguments': {}, 'observation_id': 'untrusted'})
    assert runtime.store.actions(identifier) == []
    assert not InputJournal(completed.original._resource_path).path.exists()
    runtime.pause(identifier)
    view = runtime.recovery.control('preview', {'task_id': identifier})
    spec = view['review_template']
    spec['goal'] = 'Must not regain input through ordinary dynamic recovery'
    with pytest.raises(AgentTaskError, match='read-only'):
        runtime.recovery.control('create', {'task_id': identifier, 'snapshot': view['snapshot'],
                                            'spec': spec, 'note': 'Untrusted upgrade request'})


def test_cancel_after_fresh_observation_prevents_completion_certificate(completed, monkeypatch):
    runtime, identifier = completed.runtime, child(completed)
    observe = ReadOnlyNativeTarget.observe
    def cancelled(adapter):
        reply = observe(adapter)
        runtime.cancel(identifier)
        return reply
    monkeypatch.setattr(ReadOnlyNativeTarget, 'observe', cancelled)
    with pytest.raises(CancelledError):
        runtime.finish(identifier)
    result = runtime.get(identifier)
    assert result.state == 'cancelled' and result.metadata['input_released'] is True
    assert result.metadata['completion_contract'] == 0


def test_restart_requires_explicit_resume_and_new_independent_evidence(completed, tmp_path):
    runtime, identifier = completed.runtime, child(completed)
    runtime.observe(identifier)
    runtime.close()
    completed.output.write_text('changed after restart', encoding='utf-8')
    restored = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'local-files': completed.original})
    try:
        assert restored.get(identifier).state == 'recovering'
        with pytest.raises(AgentTaskError, match='recovering'):
            restored.finish(identifier)
        restored.resume(identifier)
        result = restored.finish(identifier)
        assert result.state == 'waiting_user' and result.metadata['completion_contract'] == 0
        assert result.metadata['input_released'] is True
    finally:
        restored.close()


def test_duplicate_approvals_create_exactly_one_private_bound_successor(completed):
    runtime, request = completed.runtime, approval(completed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: runtime.recovery.control('create_completion', request), range(2)))
    assert results[0]['task_id'] == results[1]['task_id']
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_readonly_completions').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM agent_task_recoveries').fetchone()[0] == 1


def test_stale_approval_and_unreviewed_spec_fields_never_create_a_successor(completed):
    runtime, request = completed.runtime, approval(completed)
    with pytest.raises(AgentTaskError, match='fields'):
        runtime.recovery.control('create_completion', {**request, 'spec': runtime.store.get(completed.task_id)['spec']})
    runtime.store.update(completed.task_id, 'paused', reason='changed after preview')
    with pytest.raises(AgentTaskError, match='snapshot'):
        runtime.recovery.control('create_completion', request)
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_readonly_completions').fetchone()[0] == 0


def test_existing_unknown_input_witness_is_not_cleared_to_verify_completion(completed):
    runtime, identifier = completed.runtime, child(completed)
    journal = InputJournal(completed.original._resource_path)
    journal.acquire()
    original = journal.path.read_bytes()
    with pytest.raises(AgentTaskError, match='recovery'):
        runtime.finish(identifier)
    assert journal.path.read_bytes() == original
    assert runtime.get(identifier).metadata['completion_contract'] == 0


def test_cancelled_readonly_child_can_only_create_another_reviewed_readonly_successor(completed):
    runtime, identifier = completed.runtime, child(completed)
    runtime.cancel(identifier)
    retry = child(completed, identifier)
    result = runtime.finish(retry)
    assert result.state == 'succeeded' and result.metadata['completion_review']['effect_task'] == completed.task_id
    assert result.metadata['recovery']['source_task'] == identifier
    assert runtime.get(identifier).state == 'cancelled' and runtime.store.actions(retry) == []


@pytest.mark.parametrize('revoked', ['owner', 'reviewer'])
def test_source_owned_completion_keeps_both_principals_live_during_maintenance(completed, tmp_path, revoked):
    runtime = completed.runtime
    users = UserStore(tmp_path / 'users.json')
    users.add_user(user_id='owner', display_name='Owner', role='operator')
    users.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
    owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
    reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET owner=? WHERE id=?',
                           (json.dumps(asdict(owner)), completed.task_id))
    with authorization_scope(reviewer):
        review = runtime.recovery.control('preview_completion', {
            'task_id': completed.task_id, 'owner_policy': 'source_owner'})
        request = {'task_id': completed.task_id, 'snapshot': review['snapshot'], 'note': 'Keep source ownership',
                   'owner_policy': 'source_owner', 'ownership_review': review['ownership']['review']}
        identifier = runtime.recovery.control('create_completion', request)['task_id']
    with authorization_scope(owner):
        assert runtime.get(identifier).metadata['recovery']['ownership']['actor'] == 'reviewer'
        runtime.observe(identifier)
    users.set_role(revoked, 'viewer')
    runtime.maintain()
    result = runtime.get(identifier)
    assert result.state == 'cancelled' and result.metadata['input_released'] is True
    assert result.metadata['completion_contract'] == 0
