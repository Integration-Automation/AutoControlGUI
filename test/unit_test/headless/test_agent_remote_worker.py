"""Actual owned helpers exercise SDK ACK/settlement boundaries without touching a real device."""
import json
import sys
import threading
from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path

import pytest

from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.remote_journal import RemoteInputJournal
from je_auto_control.utils.agent_runtime.remote_target import NativeRemoteTarget
from je_auto_control.utils.rbac.authorization import AuthorizationContext
from je_auto_control.utils.rbac.users import UserStore

HELPER = '''
import json, sys, threading
from pathlib import Path
from je_auto_control.utils.agent_runtime.remote_effect import PreparedRemoteAction
from je_auto_control.utils.agent_runtime.remote_worker import serve_remote_worker
from je_auto_control.utils.executor.dispatch import dispatch_checkpoint
from je_auto_control.utils.rbac.authorization import current_authorization

class Adapter:
    device = {'platform': 'android', 'physical_id': 'fixture-device'}
    def set_takeover_handler(self, callback): self.takeover = callback
    def ready(self, spec): self.spec = spec; return True, ''
    def checkpoint(self): pass
    def observe(self):
        owner = current_authorization()
        return {'user': owner.user_id if owner else None, 'role': owner.role if owner else None}
    def prepare(self, name, arguments):
        mode = arguments.get('mode', '')
        if mode == 'nested': dispatch_checkpoint('AC_shell', {})
        if mode == 'takeover': self.takeover()
        def invoke():
            witness = json.loads(Path(sys.argv[1]).read_text())
            assert witness['remote_effect']['kind'] == 'remote_begin'
            assert witness['in_flight'] == 'perform'
            with Path(sys.argv[2]).open('a') as sink: sink.write('invoke\\n')
            if mode == 'hang': threading.Event().wait(30)
            if mode == 'secret': raise RuntimeError('private-password-and-command')
            return {'value': 1}
        def settle():
            proof = {'device': self.device, 'epoch': 'fixture-epoch', 'inputs_released': True, 'queue_empty': True}
            if mode == 'unsettled': proof['queue_empty'] = False
            if mode == 'wrong-epoch': proof['epoch'] = 'another-epoch'
            if mode == 'boolean': proof['inputs_released'] = 1
            return proof
        device = self.device if mode != 'wrong-device' else {**self.device, 'physical_id': 'foreign'}
        return PreparedRemoteAction(device, 'fixture-epoch', invoke, settle)

serve_remote_worker(Adapter)
'''


@pytest.fixture
def fixture_scope(monkeypatch):
    monkeypatch.setenv('PYTHONPATH', str(Path(__file__).resolve().parents[3]))
    spec = AgentTaskSpec.from_dict({'goal': 'owned SDK fixture', 'target': 'fixture',
        'allowed_tools': ['AC_increment'], 'budget': {'action_seconds': 3},
        'success_criteria': [{'kind': 'result_equals', 'key': 'value', 'value': 1}]})
    with operation_scope(TaskOperation(spec, lambda: None, None)):
        yield spec


def make_target(tmp_path):
    return NativeRemoteTarget(argv=[sys.executable, '-u', '-c', HELPER,
        str(tmp_path / 'device.lock.journal'), str(tmp_path / 'effects')],
        platform='android', physical_id='fixture-device', resource_path=tmp_path / 'device.lock')


def release_fixture(adapter):
    if adapter._journal is not None and adapter._journal.pending:
        epoch = ['fixture-baseline']
        adapter._probe = lambda: {'device': adapter._device, 'epoch': epoch[0], 'writers_retired': True}
        adapter.recover('test-owned writer retired; sample baseline', actor='fixture')
        epoch[0] = 'fixture-invalidating-epoch'
        adapter.recover('test-only retirement certificate', actor='fixture')
    adapter.cleanup()


def test_real_worker_brackets_single_sdk_calls_and_refreshes_sequence(tmp_path, fixture_scope):
    adapter = make_target(tmp_path)
    try:
        assert adapter.ready(fixture_scope) == (True, '')
        assert adapter.perform('AC_increment', {}) == {'value': 1}
        assert adapter.ready(fixture_scope) == (True, '')
        assert adapter.perform('AC_increment', {}) == {'value': 1}
        assert (tmp_path / 'effects').read_text().splitlines() == ['invoke', 'invoke']
        assert adapter._journal.sequence == 3 and not adapter._journal.pending
        assert adapter.observe() == {'user': None, 'role': None}
    finally:
        release_fixture(adapter)


def test_no_begin_ack_after_fsync_failure_never_invokes_sdk(tmp_path, fixture_scope, monkeypatch):
    adapter = make_target(tmp_path)
    adapter.ready(fixture_scope)
    original = RemoteInputJournal._write

    def fail(journal):
        if journal.pending:
            raise AgentTaskError('fixture fsync failed')
        original(journal)

    try:
        monkeypatch.setattr(RemoteInputJournal, '_write', fail)
        with pytest.raises(AgentTaskError, match='fsync'):
            adapter.perform('AC_increment', {})
        assert not (tmp_path / 'effects').exists()
        assert adapter._channel.retired
    finally:
        monkeypatch.setattr(RemoteInputJournal, '_write', original)
        release_fixture(adapter)


@pytest.mark.parametrize('mode', ['unsettled', 'wrong-epoch', 'boolean', 'secret'])
def test_local_return_or_failure_cannot_clear_unproved_remote_effect(tmp_path, fixture_scope, mode):
    adapter = make_target(tmp_path)
    try:
        adapter.ready(fixture_scope)
        with pytest.raises(AgentTaskError) as error:
            adapter.perform('AC_increment', {'mode': mode})
        assert 'private-password-and-command' not in str(error.value)
        assert (tmp_path / 'effects').read_text().splitlines() == ['invoke']
        assert adapter._channel.retired and adapter._journal.pending
        with pytest.raises(AgentTaskError, match='quarantined'):
            adapter.cleanup()
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('mode', ['wrong-device', 'nested'])
def test_unreviewed_prepared_scope_and_nested_command_are_refused_before_begin(tmp_path, fixture_scope, mode):
    adapter = make_target(tmp_path)
    try:
        adapter.ready(fixture_scope)
        with pytest.raises(AgentTaskError):
            adapter.perform('AC_increment', {'mode': mode})
        assert not (tmp_path / 'effects').exists()
        assert not adapter._journal.pending
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('cancel', [False, True])
def test_timeout_or_cancel_after_ack_keeps_effect_quarantined(tmp_path, fixture_scope, cancel):
    adapter = make_target(tmp_path)
    short = replace(fixture_scope, budget=replace(fixture_scope.budget, action_seconds=0.7))

    def checkpoint():
        if cancel and (tmp_path / 'effects').exists():
            raise CancelledError('fixture cancellation')

    try:
        with operation_scope(TaskOperation(short, checkpoint, None)):
            adapter.ready(short)
            with pytest.raises((CancelledError, AgentTaskError)):
                adapter.perform('AC_increment', {'mode': 'hang'})
        assert (tmp_path / 'effects').read_text().splitlines() == ['invoke']
        assert adapter._journal.pending and adapter._channel.retired
        assert not adapter.can_reobserve
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('changed_owner', [None, AuthorizationContext('fixture-user', 'admin', 'unreviewed-store')])
def test_host_owner_binding_and_child_authorization_cannot_be_replaced(tmp_path, fixture_scope, changed_owner):
    adapter = make_target(tmp_path)
    owner = AuthorizationContext('fixture-user', 'admin')
    try:
        with operation_scope(TaskOperation(fixture_scope, lambda: None, owner)):
            adapter.ready(fixture_scope)
            assert adapter.observe() == {'user': 'fixture-user', 'role': 'admin'}
        with operation_scope(TaskOperation(fixture_scope, lambda: None, changed_owner)):
            with pytest.raises(AgentTaskError, match='owner'):
                adapter.perform('AC_increment', {})
            with pytest.raises(AgentTaskError, match='owner'):
                adapter.ready(fixture_scope)
        assert not (tmp_path / 'effects').exists()
    finally:
        release_fixture(adapter)


def test_physical_takeover_notifies_owner_and_never_invokes_prepared_call(tmp_path, fixture_scope):
    adapter, noticed = make_target(tmp_path), threading.Event()
    try:
        with operation_scope(TaskOperation(fixture_scope, lambda: None, None, noticed.set)):
            adapter.ready(fixture_scope)
            with pytest.raises(AgentTaskError):
                adapter.perform('AC_increment', {'mode': 'takeover'})
        assert noticed.wait(2)
        assert not (tmp_path / 'effects').exists()
        assert not adapter._journal.pending
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('changed', [True, 1.0])
def test_host_scope_binding_distinguishes_json_boolean_integer_and_float(tmp_path, fixture_scope, changed):
    adapter = make_target(tmp_path)
    original = replace(fixture_scope, inputs={'number': 1})
    different = replace(fixture_scope, inputs={'number': changed})
    try:
        with operation_scope(TaskOperation(original, lambda: None, None)):
            adapter.ready(original)
        with operation_scope(TaskOperation(different, lambda: None, None)):
            with pytest.raises(AgentTaskError, match='owner'):
                adapter.perform('AC_increment', {})
        assert not (tmp_path / 'effects').exists()
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('change', ['remove', 'viewer'])
def test_child_refreshes_revocation_after_begin_persistence_before_sdk(tmp_path, fixture_scope, monkeypatch, change):
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='fixture', display_name='Fixture', role='operator')
    owner = AuthorizationContext('fixture', 'operator', str(store.path.resolve()))
    adapter = make_target(tmp_path)
    original = RemoteInputJournal.consume

    def revoke(journal, event):
        original(journal, event)
        if event['kind'] == 'remote_begin':
            if change == 'remove':
                store.remove_user('fixture')
            else:
                store.set_role('fixture', 'viewer')

    try:
        monkeypatch.setattr(RemoteInputJournal, 'consume', revoke)
        with operation_scope(TaskOperation(fixture_scope, lambda: None, owner)):
            adapter.ready(fixture_scope)
            with pytest.raises(AgentTaskError):
                adapter.perform('AC_increment', {})
        assert not (tmp_path / 'effects').exists()
        assert adapter._journal.pending and adapter._channel.retired
    finally:
        release_fixture(adapter)
