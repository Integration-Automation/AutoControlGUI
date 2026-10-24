"""Owned SDK/runtime tests prove semantic grounding and fresh app readback without native devices."""
import json
from dataclasses import replace

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.errors import AgentObservationStale, AgentTaskError
from je_auto_control.utils.agent_runtime.observation_refs import resolve_action
from je_auto_control.utils.agent_runtime.remote_journal import RemoteInputJournal

from .test_agent_android_adapter import android_sdk  # noqa: F401  # reason: shared owned SDK pytest fixture
from .test_agent_android_adapter import release_fixture, target
from .test_agent_android_hierarchy import semantic_tree


def configure(sdk, spec):
    (sdk.directory / 'hierarchy.xml').write_bytes(semantic_tree())
    (sdk.directory / 'grants.json').write_text(json.dumps(['0/0', '0/1', '0/2']))
    return replace(spec, budget=replace(spec.budget, action_seconds=15))


def test_semantic_observation_is_stable_masked_and_resolves_reviewed_tap(android_sdk):
    sdk, spec = android_sdk
    current, adapter = configure(sdk, spec), target(sdk)
    try:
        with operation_scope(TaskOperation(current, lambda: None, None)):
            adapter.ready(current)
            first, second = adapter.observe(), adapter.observe()
            assert first == second
            assert first['text'] == 'Save' and 'private-' not in json.dumps(first)
            args, _ground = resolve_action('AC_android_tap', {}, {'element_index': 1}, first)
            adapter.perform('AC_android_tap', args)
        assert (sdk.directory / 'actions').read_text().splitlines() == ['-d', '0', 'tap', '25', '25']
        assert not adapter._journal.pending and not sdk.errors
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('change', ['label', 'hidden_value', 'capture_nonce'])
def test_changed_semantic_content_or_capture_identity_refuses_input_before_begin(android_sdk, change):
    sdk, spec = android_sdk
    current, adapter = configure(sdk, spec), target(sdk)
    try:
        with operation_scope(TaskOperation(current, lambda: None, None)):
            adapter.ready(current)
            adapter.observe()
            if change == 'capture_nonce':
                (sdk.directory / 'wrong_capture').touch()
            else:
                old, new = (b'Save', b'Delete') if change == 'label' else (b'private-password', b'other-secret')
                (sdk.directory / 'hierarchy.xml').write_bytes(semantic_tree().replace(old, new))
            with pytest.raises(AgentTaskError):
                adapter.perform('AC_android_tap', {'x': 25, 'y': 25})
        assert not (sdk.directory / 'actions').exists() and not adapter._journal.pending
    finally:
        release_fixture(adapter)


def test_semantic_change_after_begin_ack_is_rechecked_inside_the_device_fence(android_sdk, monkeypatch):
    sdk, spec = android_sdk
    current, adapter = configure(sdk, spec), target(sdk)
    original = RemoteInputJournal.consume

    def change(journal, event):
        original(journal, event)
        if event['kind'] == 'remote_begin':
            (sdk.directory / 'hierarchy.xml').write_bytes(semantic_tree().replace(b'Save', b'Delete'))

    try:
        with operation_scope(TaskOperation(current, lambda: None, None)):
            adapter.ready(current)
            adapter.observe()
            monkeypatch.setattr(RemoteInputJournal, 'consume', change)
            with pytest.raises(AgentTaskError):
                adapter.perform('AC_android_tap', {'x': 25, 'y': 25})
        assert not (sdk.directory / 'actions').exists()
        assert adapter._journal.pending and adapter._channel.retired
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('after', [False, True])
def test_runtime_completion_uses_fresh_reviewed_app_state_instead_of_the_shell_phase(android_sdk, after):
    sdk, spec = android_sdk
    current = configure(sdk, spec)
    adapter = target(sdk)
    runtime = AgentRuntime(sdk.directory / 'semantic-runtime.sqlite', targets={'fixture': adapter})
    if after:
        changed = semantic_tree().replace(b'Save', b'Saved')
        (sdk.directory / 'after_hierarchy.xml').write_bytes(changed)
    value = {**current.to_dict(), 'success_criteria': [{'kind': 'screen', 'spec': {'text_present': 'Saved'}}]}
    try:
        task = runtime.submit(value)
        observed = runtime.observe(task.task_id)
        result = runtime.act(task.task_id, {'tool': 'AC_android_tap', 'arguments': {},
                                          'reference': {'element_index': 1},
                                          'observation_id': observed.observation_id})
        assert result.result['android_phase'] == 'input_returned'
        finished = runtime.finish(task.task_id)
        assert finished.state == ('succeeded' if after else 'waiting_user')
        assert finished.verification[0]['status'] == ('passed' if after else 'unknown')
    finally:
        release_fixture(adapter)
        runtime.close()


@pytest.mark.parametrize('mode', ['no_reader', 'redacted', 'known_present'])
def test_unavailable_or_masked_content_never_proves_text_absent(android_sdk, mode):
    sdk, spec = android_sdk
    current = spec if mode == 'no_reader' else configure(sdk, spec)
    if mode == 'known_present':
        (sdk.directory / 'hierarchy.xml').write_bytes(semantic_tree().replace(b'Save', b'Saved'))
    adapter = target(sdk)
    runtime = AgentRuntime(sdk.directory / 'absence-runtime.sqlite', targets={'fixture': adapter})
    value = {**current.to_dict(), 'success_criteria': [{'kind': 'screen', 'spec': {'text_absent': 'Saved'}}]}
    try:
        task = runtime.submit(value)
        finished = runtime.finish(task.task_id)
        assert finished.state == 'waiting_user'
        assert finished.verification[0]['status'] == ('failed' if mode == 'known_present' else 'unknown')
        assert not (sdk.directory / 'actions').exists()
    finally:
        release_fixture(adapter)
        runtime.close()


def test_public_revision_does_not_reveal_private_value_equality_or_action_noops(android_sdk):
    sdk, spec = android_sdk
    current, adapter = configure(sdk, spec), target(sdk)
    try:
        with operation_scope(TaskOperation(current, lambda: None, None)):
            adapter.ready(current)
            first = adapter.observe()
            (sdk.directory / 'hierarchy.xml').write_bytes(semantic_tree().replace(b'private-password', b'other-secret'))
            second = adapter.observe()
            (sdk.directory / 'hierarchy.xml').write_bytes(semantic_tree())
            third = adapter.observe()
            revisions = {item['identity']['hierarchy'] for item in (first, second, third)}
            assert len(revisions) == 3
            assert first['text'] == second['text'] == third['text'] == 'Save'
            adapter.perform('AC_android_tap', {'x': 25, 'y': 25})
            fourth = adapter.observe()
            assert fourth['identity']['hierarchy'] not in revisions
            assert adapter.observe() == fourth
    finally:
        release_fixture(adapter)


def test_runtime_discards_a_changed_observation_before_preparing_any_effect(android_sdk):
    sdk, spec = android_sdk
    current = configure(sdk, spec)
    adapter = target(sdk)
    runtime = AgentRuntime(sdk.directory / 'stale-runtime.sqlite', targets={'fixture': adapter})
    try:
        task = runtime.submit(current.to_dict())
        observed = runtime.observe(task.task_id)
        (sdk.directory / 'hierarchy.xml').write_bytes(semantic_tree().replace(b'Save', b'Delete'))
        with pytest.raises(AgentObservationStale):
            runtime.act(task.task_id, {'tool': 'AC_android_tap', 'arguments': {},
                                      'reference': {'element_index': 1},
                                      'observation_id': observed.observation_id})
        assert runtime.store.actions(task.task_id) == []
        assert not (sdk.directory / 'actions').exists()
    finally:
        release_fixture(adapter)
        runtime.close()
