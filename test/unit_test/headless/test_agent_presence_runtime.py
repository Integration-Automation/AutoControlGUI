"""Actual runtime/store/target lifetimes with virtual source/channel seams and no desktop input."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from contextlib import closing
import copy
import time
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.presence_pool import PresencePool
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from .test_agent_presence_pool import Channel


def spec(target='local-desktop'):
    return {'goal': 'reviewed fixture', 'target': target, 'apps': ['fixture'],
            'allowed_tools': ['AC_workflow_control'], 'success_criteria': [{'kind': 'actions_complete'}]}


class Helper:
    def __init__(self, argv, **_kwargs):
        self.argv, self.calls, self.retired = tuple(argv), [], False
        self.control = _kwargs.get('on_control')

    def request(self, operation, payload, *, timeout, check, **_kwargs):
        check()
        self.calls.append((operation, copy.deepcopy(payload), timeout))
        if operation == 'bootstrap':
            return {'protocol': 1}
        if operation == 'configure':
            return {'ready': True}
        return {'identity': 'fixture', 'value': 0}

    def close(self):
        self.retired = True


class Fixture:
    def __init__(self, monkeypatch, tmp_path):
        from je_auto_control.utils.agent_runtime import presence_host, native_target
        self.source, self.helpers = Channel(), []
        self.pool = PresencePool(channel_factory=lambda _argv: self.source)
        self.host, self.tmp_path = presence_host, tmp_path
        monkeypatch.setattr(presence_host, 'require_windows', lambda: None)
        monkeypatch.setattr(presence_host, 'shared_reference', self.pool.reference)
        monkeypatch.setattr(native_target, 'OwnedChannel', self.helper)

    def helper(self, argv, **kwargs):
        result = Helper(argv, **kwargs)
        self.helpers.append(result)
        return result

    def runtime(self, name, *, argv=None):
        target = NativeDesktopTarget(argv=argv, resource_path=self.tmp_path / 'input.lock')
        return AgentRuntime(self.tmp_path / (name + '.sqlite'), targets={'local-desktop': target})

    def bindings(self):
        return [payload['presence'] for helper in self.helpers for operation, payload, _timeout in helper.calls
                if operation == 'configure' and 'presence' in payload]


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    return Fixture(monkeypatch, tmp_path)


def test_two_runtime_databases_keep_one_source_across_input_task_and_borrower_replacement(fixture):
    first, second = fixture.runtime('one'), fixture.runtime('two')
    try:
        left, right = first.submit(spec()), second.submit(spec())
        assert not fixture.source.calls and not fixture.helpers
        first.observe(left.task_id)
        first.pause(left.task_id)
        second.observe(right.task_id)
        bindings = fixture.bindings()
        assert len(bindings) == 2 and bindings[0]['generation'] == bindings[1]['generation']
        assert bindings[0]['lease_id'] != bindings[1]['lease_id']
        assert sum(name == 'bootstrap' for name, _body in fixture.source.calls) == 1
        first.close()
        assert not fixture.source.retired
        second.observe(right.task_id)
        assert fixture.bindings()[-1] == bindings[-1]
        assert sum(name == 'acquire' for name, _body in fixture.source.calls) == 2
    finally:
        first.close()
        second.close()
    assert fixture.source.retired and fixture.pool.retired and all(helper.retired for helper in fixture.helpers)


def test_new_task_uses_a_new_lease_without_resetting_runtime_source_idle(fixture):
    with closing(fixture.runtime('one')) as runtime:
        first = runtime.submit(spec())
        runtime.observe(first.task_id)
        runtime.pause(first.task_id)
        second = runtime.submit(spec())
        runtime.observe(second.task_id)
        left, right = fixture.bindings()
        assert left['generation'] == right['generation'] and left['lease_id'] != right['lease_id']
        assert len(fixture.helpers) == 2 and fixture.helpers[0].retired


def test_custom_reviewed_worker_and_passive_runtime_paths_never_bind_presence(fixture):
    with closing(fixture.runtime('custom', argv=['reviewed-custom-worker'])) as runtime:
        task = runtime.submit(spec())
        runtime.list()
        runtime.get(task.task_id)
        runtime.observe(task.task_id)
        assert not fixture.source.calls and not fixture.bindings()


def test_failed_source_retirement_keeps_runtime_and_store_owned_for_explicit_retry(fixture, monkeypatch):
    runtime = fixture.runtime('one')
    task = runtime.submit(spec())
    runtime.observe(task.task_id)
    reference = runtime._presence.reference()
    original = reference.close

    def fail():
        raise AgentTaskError('owned source retirement is unproven')

    try:
        monkeypatch.setattr(reference, 'close', fail)
        with pytest.raises(AgentTaskError, match='unproven'):
            runtime.close()
        assert not runtime._closed and not runtime._leases
        assert all(helper.retired for helper in fixture.helpers)
        with pytest.raises(AgentControlBusy):
            fixture.runtime('one')
    finally:
        monkeypatch.setattr(reference, 'close', original)
        runtime.close()
    assert runtime._closed and fixture.pool.retired


def test_runtime_close_during_first_acquire_cancels_caller_before_final_source_closure(fixture):
    runtime = fixture.runtime('one')
    task = runtime.submit(spec())
    fixture.source.allow.clear()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting = executor.submit(runtime.observe, task.task_id)
            assert fixture.source.entered.wait(1)
            with pytest.raises(AgentTaskError, match='active input'):
                runtime.close()
            with pytest.raises(CancelledError):
                waiting.result(timeout=1)
            assert not fixture.source.retired and not runtime._closed
    finally:
        fixture.source.allow.set()
        runtime.close()
    assert fixture.pool.retired and all(helper.retired for helper in fixture.helpers)


def test_cancelled_host_scope_never_opens_input_resource_or_helper_before_bind(fixture):
    adapter = NativeDesktopTarget(resource_path=fixture.tmp_path / 'cancelled.lock')
    definition = AgentTaskSpec.from_dict(spec())

    def cancelled():
        raise CancelledError()

    with operation_scope(TaskOperation(definition, cancelled, None)):
        with pytest.raises(CancelledError):
            adapter.ready(definition)
    try:
        assert adapter._resource is None and adapter._channel is None and not fixture.helpers
        assert not fixture.source.calls
    finally:
        adapter.cleanup()


def test_passive_target_description_exposes_coarse_presence_without_creating_a_source(fixture):
    with closing(fixture.runtime('status')) as runtime:
        summary, = runtime.target_profiles.describe()['targets']
        assert summary['presence']['state'] in {'not_bound', 'not_supported'}
        assert summary['presence']['native_evidence'] == 'not_recorded'
        assert not fixture.source.calls and not fixture.helpers


def test_unsupported_default_desktop_refuses_before_helper_or_input_journal(fixture, monkeypatch):
    from je_auto_control.utils.agent_runtime import presence_host
    monkeypatch.undo()
    monkeypatch.setattr(presence_host, 'sys', SimpleNamespace(platform='linux'))
    with closing(fixture.runtime('unsupported')) as runtime:
        task = runtime.submit(spec())
        with pytest.raises(AgentControlBusy, match='Windows'):
            runtime.observe(task.task_id)
        assert not fixture.helpers and not fixture.source.calls


def test_named_owner_takeover_is_negative_only_and_old_helper_notice_cannot_stop_resumed_lease(fixture):
    with authorization_scope(AuthorizationContext('alice', 'operator')), closing(fixture.runtime('named')) as runtime:
        task = runtime.submit(spec())
        runtime.observe(task.task_id)
        old = fixture.helpers[-1]
        runtime.pause(task.task_id)
        runtime.resume(task.task_id)
        runtime.observe(task.task_id)
        current = fixture.helpers[-1]
        assert current is not old
        with authorization_scope(None):
            old.control('physical_input')
        assert runtime.get(task.task_id).state == 'running'
        assert current.control is not None
        with authorization_scope(None):
            current.control('physical_input')
        deadline = time.monotonic() + 1
        while runtime.get(task.task_id).state != 'paused' and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.get(task.task_id).state == 'paused' and not runtime._leases


def test_task_options_cannot_select_source_provider_or_presence_capability(fixture):
    with closing(fixture.runtime('forged')) as runtime:
        definition = {**spec(), 'options': {'presence': {'generation': 'f' * 32, 'lease_id': 'e' * 32},
                                           'namespace': 'untrusted', 'role': 'owner'}}
        task = runtime.submit(definition)
        runtime.observe(task.task_id)
        binding, = fixture.bindings()
        assert binding != definition['options']['presence']
        assert fixture.source.calls[0] == ('bootstrap', {})
