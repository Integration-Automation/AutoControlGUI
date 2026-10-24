"""Real owned worker/ADB framing/POSIX shell fixtures exercise the checked Android SDK adapter."""
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from je_auto_control.utils.agent_runtime.android_adapter import AndroidRemoteAdapter
from je_auto_control.utils.agent_runtime.android_commands import AndroidActionProposal, compile_android_action
from je_auto_control.utils.agent_runtime.android_input_evidence import parse_android_input_evidence
from je_auto_control.utils.agent_runtime.android_session import AndroidDeviceSession
from je_auto_control.utils.agent_runtime.android_transport import ManagedAdbServer
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.remote_journal import RemoteInputJournal
from je_auto_control.utils.agent_runtime.remote_target import NativeRemoteTarget

from .android_sdk_fixture import AndroidSdkFixture
from .test_agent_android_scope import BOOT, DEVICE, PACKAGE, WM, Server, evidence, input_dump, policy_dump
from je_auto_control.utils.agent_runtime.android_scope import parse_android_snapshot

HELPER = '''
import json, sys
from contextlib import contextmanager
from pathlib import Path
from je_auto_control.utils.agent_runtime.android_adapter import AndroidRemoteAdapter
from je_auto_control.utils.agent_runtime.android_control import AndroidCommandLease
from je_auto_control.utils.agent_runtime.android_session import AndroidDeviceSession
from je_auto_control.utils.agent_runtime.android_transport import ManagedAdbServer
from je_auto_control.utils.agent_runtime.remote_worker import serve_remote_worker

directory = Path(sys.argv[2])
class Control:
    def set_takeover_handler(self, handler): self.takeover = handler
    def ready(self, snapshot, evidence, spec): return True, ''
    def checkpoint(self, binding):
        if (directory / 'deny').exists(): raise ValueError('fixture authority revoked')
    def lease(self, proposal, request_id):
        @contextmanager
        def fence():
            witness = json.loads((directory / 'device.lock.journal').read_text())
            assert witness['remote_effect']['kind'] == 'remote_begin'
            state = {'active': True, 'request_id': request_id}
            (directory / 'fence.json').write_text(json.dumps(state))
            try: yield
            finally:
                state['active'] = False
                (directory / 'fence.json').write_text(json.dumps(state))
        def settle(result):
            proof = json.loads((directory / 'settlement.json').read_text())
            if (directory / 'stale_nonce').exists(): proof['request_id'] = '0' * 32
            if (directory / 'wrong_boot').exists(): proof['boot_id'] = 'wrong-boot'
            if (directory / 'queue_busy').exists(): proof['queue_empty'] = False
            return proof
        nonce = '0' * 32 if (directory / 'wrong_lease').exists() else request_id
        return AndroidCommandLease(proposal, nonce, 'fixture-epoch', fence, lambda: None, settle)

def factory():
    server = ManagedAdbServer('127.0.0.1', int(sys.argv[1]))
    session = AndroidDeviceSession(server, serial='reviewed-endpoint', physical_id='reviewed-device',
                                   package='org.example.app')
    return AndroidRemoteAdapter(session, control=Control())
serve_remote_worker(factory)
'''


@pytest.fixture
def android_sdk(tmp_path, monkeypatch):
    monkeypatch.setenv('PYTHONPATH', str(Path(__file__).resolve().parents[3]))
    snapshot = parse_android_snapshot(evidence(), DEVICE, PACKAGE)
    spec = AgentTaskSpec.from_dict({'goal': 'fixture Android tap', 'target': 'fixture', 'apps': [PACKAGE],
        'allowed_tools': ['AC_android_tap'], 'budget': {'action_seconds': 5},
        'success_criteria': [{'kind': 'result_equals', 'key': 'value', 'value': 1}]})
    with AndroidSdkFixture(tmp_path, snapshot, input_dump(), policy_dump()) as sdk:
        with operation_scope(TaskOperation(spec, lambda: None, None)):
            yield sdk, spec


def target(sdk):
    return NativeRemoteTarget(argv=[sys.executable, '-u', '-c', HELPER, str(sdk.port), str(sdk.directory)],
        platform='android', physical_id=DEVICE, resource_path=sdk.directory / 'device.lock')


def release_fixture(adapter):
    if adapter._journal is not None and adapter._journal.pending:
        epoch = ['baseline']
        adapter._probe = lambda: {'device': adapter._device, 'epoch': epoch[0], 'writers_retired': True}
        adapter.recover('retired test-only writer', actor='fixture')
        epoch[0] = 'invalidating-fixture-epoch'
        adapter.recover('test-only independent reset certificate', actor='fixture')
    adapter.cleanup()


def test_actual_worker_and_sdk_only_invoke_finite_input_after_durable_begin_ack(android_sdk):
    sdk, spec = android_sdk
    adapter = target(sdk)
    try:
        assert adapter.ready(spec) == (True, '')
        observed = adapter.observe()
        assert observed['identity']['physical_id'] == DEVICE
        assert observed['elements'] == [] and observed['text'] == ''
        assert not any('/system/bin/input -d 0 ' in command for command in sdk.services)
        assert adapter.perform('AC_android_tap', {'x': 10, 'y': 20}) == {
            'android_phase': 'input_returned', 'may_have_effect': True}
        assert (sdk.directory / 'actions').read_text().splitlines() == ['-d', '0', 'tap', '10', '20']
        assert not adapter._journal.pending and adapter._journal.sequence == 2
        assert json.loads((sdk.directory / 'fence.json').read_text())['active'] is False
        assert not sdk.errors
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('apps,tools', [([PACKAGE], ['AC_android_tap']), (['org.other.app'], ['AC_android_tap']),
                                      ([PACKAGE], ['AC_shell'])])
def test_missing_provider_or_unreviewed_scope_never_contacts_adb(android_sdk, apps, tools):
    sdk, spec = android_sdk
    session = AndroidDeviceSession(ManagedAdbServer('127.0.0.1', sdk.port), serial='reviewed-endpoint',
                                   physical_id=DEVICE, package=PACKAGE)
    adapter = AndroidRemoteAdapter(session)
    changed = replace(spec, apps=tuple(apps), allowed_tools=tuple(tools))
    with operation_scope(TaskOperation(changed, lambda: None, None)):
        assert adapter.ready(changed)[0] is False
    assert sdk.services == []


@pytest.mark.parametrize('flag', ['stale_nonce', 'wrong_boot', 'queue_busy'])
def test_bad_independent_settlement_keeps_effect_quarantined(android_sdk, flag):
    sdk, spec = android_sdk
    adapter = target(sdk)
    try:
        adapter.ready(spec)
        adapter.observe()
        (sdk.directory / flag).touch()
        with pytest.raises(AgentTaskError):
            adapter.perform('AC_android_tap', {'x': 10, 'y': 20})
        assert (sdk.directory / 'actions').exists()
        assert adapter._journal.pending and adapter._channel.retired
    finally:
        release_fixture(adapter)


def test_lost_shell_exit_stays_unknown_even_after_fixture_writer_settles(android_sdk):
    sdk, spec = android_sdk
    adapter = target(sdk)
    try:
        adapter.ready(spec)
        adapter.observe()
        sdk.mode = 'drop_exit'
        with pytest.raises(AgentTaskError):
            adapter.perform('AC_android_tap', {'x': 10, 'y': 20})
        assert json.loads((sdk.directory / 'settlement.json').read_text())['queue_empty'] is True
        assert adapter._journal.pending and adapter._channel.retired
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('change', ['geometry', 'wrong_lease', 'missing_observation'])
def test_stale_scope_or_unmatched_lease_cannot_begin_input(android_sdk, change):
    sdk, spec = android_sdk
    adapter = target(sdk)
    try:
        adapter.ready(spec)
        if change != 'missing_observation':
            adapter.observe()
        if change == 'geometry':
            (sdk.directory / 'input').write_bytes(input_dump().replace(b'frame=[0,0][100,200]', b'frame=[0,0][99,200]'))
        elif change == 'wrong_lease':
            (sdk.directory / 'wrong_lease').touch()
        with pytest.raises(AgentTaskError):
            adapter.perform('AC_android_tap', {'x': 10, 'y': 20})
        assert not adapter._journal.pending and not (sdk.directory / 'actions').exists()
        assert not any('/system/bin/input -d 0 ' in command for command in sdk.services)
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('when,expected,effect', [('before', 'pre_input_refused', False),
                                               ('after', 'post_input_refused', True)])
def test_same_scope_exit_is_classified_on_the_correct_side_of_input(android_sdk, monkeypatch, when, expected, effect):
    sdk, spec = android_sdk
    adapter = target(sdk)
    original = RemoteInputJournal.consume

    def mutate(journal, event):
        original(journal, event)
        if event['kind'] == 'remote_begin':
            path = 'wm' if when == 'before' else 'after'
            (sdk.directory / path).write_text(WM.replace(PACKAGE, 'org.other.app'), encoding='utf-8', newline='')

    try:
        adapter.ready(spec)
        adapter.observe()
        monkeypatch.setattr(RemoteInputJournal, 'consume', mutate)
        assert adapter.perform('AC_android_tap', {'x': 10, 'y': 20}) == {
            'android_phase': expected, 'may_have_effect': effect}
        assert (sdk.directory / 'actions').exists() is effect
        assert not adapter._journal.pending
    finally:
        release_fixture(adapter)


def test_new_input_requires_a_new_observation_instead_of_reusing_the_prepared_prefix(android_sdk):
    sdk, spec = android_sdk
    adapter = target(sdk)
    try:
        adapter.ready(spec)
        adapter.observe()
        adapter.perform('AC_android_tap', {'x': 10, 'y': 20})
        with pytest.raises(AgentTaskError):
            adapter.perform('AC_android_tap', {'x': 10, 'y': 20})
        assert (sdk.directory / 'actions').read_text().splitlines().count('tap') == 1
        assert not adapter._journal.pending
    finally:
        release_fixture(adapter)


@pytest.mark.parametrize('change', ['unchecked', 'command', 'arguments', 'boot', 'app', 'unpinned'])
def test_sdk_dispatch_rejects_unchecked_altered_and_foreign_proposals_before_transport(change):
    server = Server()
    session = AndroidDeviceSession(server, serial='reviewed-endpoint', physical_id=DEVICE, package=PACKAGE)
    _, snapshot = session.inspect()
    proof = parse_android_input_evidence(input_dump(), policy_dump(), snapshot)
    arguments = {'x': 10, 'y': 20}
    command = compile_android_action(snapshot, 'AC_android_tap', arguments, input_evidence=proof)
    proposal = AndroidActionProposal(42, snapshot, command, proof)
    if change == 'unchecked':
        proposal = replace(proposal, input_evidence=None)
    elif change == 'command':
        proposal = replace(proposal, command=command + '; arbitrary-command')
    elif change == 'arguments':
        arguments = {'x': 11, 'y': 20}
    elif change == 'boot':
        proposal = replace(proposal, snapshot=replace(snapshot, boot_id=BOOT.replace('1', '2')))
    elif change == 'app':
        foreign = replace(snapshot, package='org.other.app', window=snapshot.window.replace(PACKAGE, 'org.other.app'),
                          activity=snapshot.activity.replace(PACKAGE, 'org.other.app'))
        other_proof = replace(proof, snapshot=foreign)
        proposal = AndroidActionProposal(42, foreign,
            compile_android_action(foreign, 'AC_android_tap', arguments, input_evidence=other_proof), other_proof)
    else:
        session = AndroidDeviceSession(server, serial='reviewed-endpoint', physical_id=DEVICE, package=PACKAGE)
    before = list(server.calls)
    with pytest.raises(AgentTaskError):
        session.dispatch_checked(proposal, 'AC_android_tap', arguments, timeout=1, check=lambda: None)
    assert server.calls == before


def test_provider_revocation_after_begin_ack_prevents_actual_sdk_dispatch(android_sdk, monkeypatch):
    sdk, spec = android_sdk
    adapter = target(sdk)
    original = RemoteInputJournal.consume

    def revoke(journal, event):
        original(journal, event)
        if event['kind'] == 'remote_begin':
            (sdk.directory / 'deny').touch()

    try:
        adapter.ready(spec)
        adapter.observe()
        monkeypatch.setattr(RemoteInputJournal, 'consume', revoke)
        with pytest.raises(AgentTaskError):
            adapter.perform('AC_android_tap', {'x': 10, 'y': 20})
        assert not (sdk.directory / 'actions').exists()
        assert not any('/system/bin/input -d 0 ' in command for command in sdk.services)
        assert adapter._journal.pending and adapter._channel.retired
    finally:
        release_fixture(adapter)
