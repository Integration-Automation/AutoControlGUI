"""SDK calls need exact ACK/settlement evidence; malformed proofs poison their controller."""
import io
import json
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.remote_effect import PreparedRemoteAction, RemoteEffectController
from je_auto_control.utils.agent_runtime.remote_worker import RemoteWorker
from je_auto_control.utils.agent_runtime import remote_worker

DEVICE = {'platform': 'android', 'physical_id': 'fixture-device'}
GUARD = {'controller': 'fixture-controller', 'device': DEVICE, 'next_sequence': 1}


def action(calls, *, proof=None):
    settled = {'device': DEVICE, 'epoch': 'fixture-epoch', 'inputs_released': True, 'queue_empty': True}
    return PreparedRemoteAction(DEVICE, 'fixture-epoch', lambda: calls.append('invoke'),
                                lambda: settled if proof is None else proof)


def test_begin_ack_is_required_before_call_and_end_ack_before_next_sequence():
    controller, calls = RemoteEffectController(GUARD, DEVICE), []

    def notify(event):
        assert event['sequence'] == 1
        if event['kind'] == 'remote_begin':
            assert calls == []
        else:
            assert calls == ['remote_begin', 'invoke']
            assert controller.sequence == 1
        calls.append(event['kind'])

    controller.perform(action(calls), notify, lambda: None)
    assert calls == ['remote_begin', 'invoke', 'remote_end']
    assert controller.sequence == 2


@pytest.mark.parametrize('proof', [
    {}, {'device': DEVICE, 'epoch': 'fixture-epoch'},
    {'device': DEVICE, 'epoch': 'fixture-epoch', 'inputs_released': 1, 'queue_empty': True},
    {'device': DEVICE, 'epoch': 'fixture-epoch', 'inputs_released': True, 'queue_empty': False},
    {'device': DEVICE, 'epoch': 'foreign', 'inputs_released': True, 'queue_empty': True},
    {'device': {**DEVICE, 'physical_id': 'foreign'}, 'epoch': 'fixture-epoch',
     'inputs_released': True, 'queue_empty': True},
    {'device': DEVICE, 'epoch': 'fixture-epoch', 'inputs_released': True, 'queue_empty': True, 'extra': True},
])
def test_wrong_incomplete_or_coerced_settlement_never_emits_end_or_allows_reuse(proof):
    controller, calls, events = RemoteEffectController(GUARD, DEVICE), [], []
    with pytest.raises(AgentTaskError):
        controller.perform(action(calls, proof=proof), events.append, lambda: None)
    assert calls == ['invoke']
    assert [event['kind'] for event in events] == ['remote_begin']
    with pytest.raises(AgentTaskError, match='recovery'):
        controller.perform(action(calls), events.append, lambda: None)
    assert calls == ['invoke']


@pytest.mark.parametrize('sequence', [True, False, 1.0, '1', 0, -1, 2**53])
def test_controller_never_coerces_sequence_types_or_bounds(sequence):
    with pytest.raises(AgentTaskError):
        RemoteEffectController({**GUARD, 'next_sequence': sequence}, DEVICE)
    assert not RemoteEffectController(GUARD, DEVICE).matches({**GUARD, 'next_sequence': sequence})


@pytest.mark.parametrize('fail_phase', ['remote_begin', 'remote_end'])
def test_lost_ack_never_replays_and_only_begin_ack_can_allow_one_invocation(fail_phase):
    controller, calls = RemoteEffectController(GUARD, DEVICE), []

    def notify(event):
        if event['kind'] == fail_phase:
            raise AgentTaskError('fixture lost ACK')

    with pytest.raises(AgentTaskError, match='ACK'):
        controller.perform(action(calls), notify, lambda: None)
    assert calls == ([] if fail_phase == 'remote_begin' else ['invoke'])
    with pytest.raises(AgentTaskError, match='recovery'):
        controller.perform(action(calls), notify, lambda: None)


class Adapter:
    device = DEVICE

    def __init__(self):
        self.calls = []

    def set_takeover_handler(self, callback):
        self.callback = callback

    def ready(self, _spec):
        return True, ''

    def checkpoint(self):
        pass

    def prepare(self, _name, _arguments):
        return action(self.calls)


def request(operation, payload):
    return {'id': '0' * 32, 'operation': operation, 'payload': payload}


@pytest.mark.parametrize('ack', [{'ack': 1}, {'ack': False}, {'ack': True, 'extra': True}, {}, []])
def test_real_worker_stream_requires_exact_boolean_ack_before_sdk(ack):
    spec = AgentTaskSpec.from_dict({'goal': 'fixture', 'target': 'fixture', 'allowed_tools': ['AC_increment'],
        'success_criteria': [{'kind': 'result_equals', 'key': 'value', 'value': 1}]})
    packets = [request('configure', {'spec': spec.to_dict(), 'owner': {}, 'remote_guard': GUARD}),
               request('perform', {'tool': 'AC_increment', 'arguments': {}}), ack]
    source = io.BytesIO(b''.join(json.dumps(packet).encode() + b'\n' for packet in packets))
    sink, adapter = io.BytesIO(), Adapter()
    RemoteWorker(source, sink, adapter).run()
    assert not adapter.calls
    replies = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert [reply['event']['kind'] for reply in replies if 'event' in reply] == ['remote_begin']
    assert 'error' in replies[-1]


@pytest.mark.parametrize('value', [True, 1.0])
def test_child_configuration_cannot_equate_json_boolean_or_float_to_integer(value):
    spec = AgentTaskSpec.from_dict({'goal': 'fixture', 'target': 'fixture', 'inputs': {'number': 1},
        'allowed_tools': ['AC_increment'],
        'success_criteria': [{'kind': 'result_equals', 'key': 'value', 'value': 1}]})
    config = {'spec': spec.to_dict(), 'owner': {}, 'remote_guard': GUARD}
    changed = {**config, 'spec': {**config['spec'], 'inputs': {'number': value}}}
    packets = [request('configure', config), request('configure', changed)]
    source = io.BytesIO(b''.join(json.dumps(packet).encode() + b'\n' for packet in packets))
    sink, adapter = io.BytesIO(), Adapter()
    RemoteWorker(source, sink, adapter).run()
    replies = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert replies[0]['result']['ready'] is True and 'error' in replies[1]
    assert not adapter.calls


def test_parent_watch_starts_before_sdk_factory_and_empty_stream_does_no_work(monkeypatch):
    calls = []
    monkeypatch.setattr(remote_worker, 'start_parent_watch', lambda: calls.append('watch'))
    monkeypatch.setattr(remote_worker.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO()))
    monkeypatch.setattr(remote_worker.sys, 'stdout', SimpleNamespace(buffer=io.BytesIO()))

    def factory():
        calls.append('factory')
        return Adapter()

    remote_worker.serve_remote_worker(factory)
    assert calls == ['watch', 'factory']
