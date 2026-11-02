"""Source workers start only after their private owner bootstrap; fake factories never observe a desktop."""
import io
import json
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import encode_frame
from .presence_test_support import Source
from .test_agent_presence_server import Pipe


def module():
    from je_auto_control.utils.agent_runtime import presence_worker
    return presence_worker


def packet(payload=None, **changes):
    value = {'id': 'a' * 32, 'operation': 'bootstrap', 'payload': {'namespace': None} if payload is None else payload}
    value.update(changes)
    return encode_frame(value) + b'\n'


def test_worker_reserves_before_constructing_source_and_owner_eof_retires_it():
    events, output = [], io.BytesIO()
    pipe = Pipe(events)

    def construct():
        events.append('construct')
        return Source(events)

    def transport(*, namespace):
        assert namespace is None
        return pipe

    module().run(io.BytesIO(packet()), output, source_factory=construct, pipe_factory=transport)
    response, = [json.loads(line) for line in output.getvalue().splitlines()]
    assert response['id'] == 'a' * 32 and response['result']['ready'] is True
    assert events[:3] == ['reserve', 'construct', 'start']
    assert 'source-close' in events and 'listener-close' in events


def test_worker_does_nothing_before_bootstrap_or_when_endpoint_is_already_owned():
    events, pipe = [], Pipe([])
    pipe.occupied = True

    def forbidden():
        raise AssertionError('occupied child constructed a second source')

    module().run(io.BytesIO(), io.BytesIO(), source_factory=forbidden,
                 pipe_factory=lambda **_kwargs: events.append('unexpected'))
    assert not events
    output = io.BytesIO()
    module().run(io.BytesIO(packet()), output, source_factory=forbidden, pipe_factory=lambda **_kwargs: pipe)
    assert json.loads(output.getvalue())['result'] == {'ready': False, 'occupied': True}


@pytest.mark.parametrize('payload', [{'namespace': True}, {'namespace': 'other'}, {'namespace': None, 'source': {}},
                                    {'namespace': None, 'pid': 1}, {'namespace': None, 'owner': True}])
def test_worker_rejects_untrusted_fields_before_any_transport_or_source_is_constructed(payload):
    calls, output = [], io.BytesIO()
    module().run(io.BytesIO(packet(payload)), output,
        source_factory=lambda: calls.append('source'), pipe_factory=lambda **_kwargs: calls.append('pipe'))
    assert not calls and json.loads(output.getvalue())['error_type'] == 'AgentTaskError'


def test_source_process_is_inert_and_uses_fixed_owned_channel_argv_before_bootstrap():
    calls = []
    fake = SimpleNamespace(request=lambda operation, payload, **options:
        calls.append((operation, payload, options)) or {'ready': False, 'occupied': True},
        close=lambda: calls.append('close'))

    def create(argv):
        calls.append(argv)
        return fake

    source = module().SourceProcess(None, channel_factory=create)
    assert not calls
    assert source.start() == {'ready': False, 'occupied': True}
    assert calls[0][-2:] == ['-m', 'je_auto_control.utils.agent_runtime.presence_worker']
    assert calls[1] == ('bootstrap', {'namespace': None}, {'timeout': 15})
    source.close()
    source.close()
    assert calls.count('close') == 1
    with pytest.raises(AgentTaskError):
        source.start()


@pytest.mark.parametrize('raw', [packet().rstrip(b'\n'), packet(id=True),
                               b'{"id":"x","id":"x"}\n', b'[]\n'])
def test_private_owner_envelope_refuses_incomplete_or_invalid_identity_before_startup(raw):
    calls = []
    with pytest.raises(AgentTaskError):
        module().run(io.BytesIO(raw), io.BytesIO(), source_factory=lambda: calls.append('source'),
                     pipe_factory=lambda **_kwargs: calls.append('pipe'))
    assert not calls
