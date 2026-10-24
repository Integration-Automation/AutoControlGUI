"""Executable missing-feature specification for reviewed post-effect completion, outside stage63 gates."""
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskSpec
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.readonly_target import ReadOnlyNativeTarget
from je_auto_control.utils.agent_runtime.errors import AgentTaskError


@pytest.fixture
def completed(tmp_path, monkeypatch):
    output = tmp_path / 'result.txt'
    output.write_text('complete', encoding='utf-8')
    arguments = {'directory': str(tmp_path), 'path': str(tmp_path / 'manifest.json'), 'names': ['result.txt']}
    definition = AgentTaskSpec.from_dict({
        'goal': 'Publish completion only after a fresh independent check', 'target': 'local-files', 'mode': 'skill',
        'roots': [str(tmp_path)], 'allowed_tools': ['AC_workflow_manifest'],
        'actions': [{'tool': 'AC_workflow_manifest', 'arguments': arguments}],
        'success_criteria': [{'kind': 'actions_complete'},
                             {'kind': 'file_text', 'path': str(output), 'value': 'complete'}],
        'budget': {'action_seconds': 5},
    })
    original = NativeDesktopTarget(resource_path=tmp_path / 'input.lock')
    def forbidden(*_args, **_kwargs):
        raise AssertionError('ordinary helper or confirmed action reused')
    monkeypatch.setattr(original, 'perform', forbidden)
    monkeypatch.setattr(original, 'observe', forbidden)
    with_runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'local-files': original})
    try:
        task = with_runtime.submit(definition)
        # Test-owned durable evidence simulates lost finish after the finite action was confirmed.
        action = with_runtime.store.prepare(task.task_id, 'AC_workflow_manifest', arguments)
        with_runtime.store.settle(action, 'dispatched')
        with_runtime.store.settle(action, 'confirmed', {'path': str(tmp_path / 'manifest.json')})
        with_runtime.pause(task.task_id)
        yield SimpleNamespace(runtime=with_runtime, task_id=task.task_id, output=output, original=original)
    finally:
        with_runtime.close()


def approval(value, task_id=None):
    identifier = task_id or value.task_id
    review = value.runtime.recovery.control('preview_completion', {'task_id': identifier})
    assert review['approval_required'] is True and review['source_completion_inherited'] is False
    return {'task_id': identifier, 'snapshot': review['snapshot'], 'note': 'Reviewed confirmed effects and criteria'}


def child(value, task_id=None):
    return value.runtime.recovery.control('create_completion', approval(value, task_id))['task_id']


def test_reviewed_completion_verifies_fresh_file_without_replaying_a_confirmed_action(completed):
    runtime, source = completed.runtime, completed.task_id
    historical = runtime.store.actions(source)
    ordinary = runtime.recovery.control('preview', {'task_id': source})
    assert ordinary['draft'] is None and 'no_remaining_actions' in ordinary['issues']
    identifier = child(completed)
    result = runtime.finish(identifier)
    assert result.state == 'succeeded'
    assert result.metadata['input_released'] is True and result.metadata['completion_contract'] == 1
    assert [item['status'] for item in result.verification] == ['passed', 'passed']
    assert runtime.store.actions(identifier) == []
    assert runtime.get(source).state == 'paused' and runtime.store.actions(source) == historical


def test_source_changes_during_reader_retirement_cannot_publish_stale_success(completed, monkeypatch):
    runtime, identifier = completed.runtime, child(completed)
    cleanup = ReadOnlyNativeTarget.cleanup
    def changed(adapter):
        cleanup(adapter)
        runtime.store.update(completed.task_id, 'paused', reason='new source review during retirement')
    monkeypatch.setattr(ReadOnlyNativeTarget, 'cleanup', changed)
    with pytest.raises(AgentTaskError, match='snapshot'):
        runtime.finish(identifier)
    result = runtime.get(identifier)
    assert result.state != 'succeeded' and result.metadata['completion_contract'] == 0


def test_observe_then_finish_reuses_the_same_readonly_authority_without_reconfiguration(completed):
    runtime, identifier = completed.runtime, child(completed)
    frame = runtime.observe(identifier)
    assert frame.data['identity'] == 'local-files'
    assert runtime.get(identifier).metadata['input_released'] is False
    result = runtime.finish(identifier)
    assert result.state == 'succeeded' and result.metadata['input_released'] is True
    assert runtime.store.actions(identifier) == []


@pytest.mark.parametrize('changed', ['spec', 'owner', 'profile'])
def test_existing_reader_refuses_different_scope_owner_or_host_profile(completed, changed):
    from je_auto_control.utils.agent_runtime import AgentTaskSpec
    from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
    from je_auto_control.utils.agent_runtime.target_config import AgentTargetProfile
    from je_auto_control.utils.rbac.authorization import AuthorizationContext
    runtime, identifier = completed.runtime, child(completed)
    runtime.observe(identifier)
    adapter = runtime._completion_targets[identifier]
    data = runtime.store.get(identifier)['spec']
    owner = None
    if changed == 'spec':
        data['goal'] = 'Different unreviewed specification'
    elif changed == 'owner':
        owner = AuthorizationContext('another-owner', 'operator')
    else:
        adapter._profile = AgentTargetProfile.from_dict({'name': 'other-files', 'kind': 'files',
            'roots': data['roots'], 'allowed_tools': data['allowed_tools']})
    spec = AgentTaskSpec.from_dict(data)
    with operation_scope(TaskOperation(spec, lambda: None, owner)), pytest.raises(AgentTaskError):
        adapter.ready(spec)
