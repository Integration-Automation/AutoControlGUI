"""Closed byte frames and per-connection presence ownership without native observation."""
import json

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_state import PresenceState


class Source:
    def __init__(self, ready=True):
        self.now = 0.0
        self.state = PresenceState(lambda: self.now)
        self.calls, self.releases = [], []
        self.state.refresh(True, False)
        if ready:
            self.advance(60)

    def advance(self, seconds):
        end = self.now + seconds
        while self.now < end:
            self.now = min(self.now + 0.125, end)
            self.state.refresh(True, False)

    def status(self):
        return self.state.inspect()

    def request(self, operation, body):
        self.calls.append((operation, dict(body)))
        self.state.refresh(True, False)
        methods = {'inspect': self.state.inspect, 'acquire': self.state.acquire, 'check': self.state.check}
        return methods[operation](**body)

    def release(self, **body):
        self.releases.append(dict(body))
        self.state.release(**body)


def frames():
    from je_auto_control.utils.agent_runtime import presence_frames
    return presence_frames


def protocol(source):
    from je_auto_control.utils.agent_runtime.presence_protocol import PresenceProtocol
    return PresenceProtocol(source)


def request(connection, sequence, operation, body=None):
    return connection.request({'request_id': sequence, 'operation': operation, 'body': body or {}})


@pytest.mark.parametrize('raw', [b'', b'[]', b'true', b'{"x":1,"x":2}',
    b'{"body":{"x":1,"x":2}}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e309}',
    b'{"x":"\xff"}', b'{"x":"\\ud800"}', b'{' + b'x' * 4096])
def test_wire_rejects_nonobjects_duplicates_nonfinite_unicode_and_oversized_data(raw):
    with pytest.raises(AgentTaskError):
        frames().decode_frame(raw)


def test_exact_frame_bound_and_nested_finite_roundtrip():
    value = {'padding': 'x' * 4082}
    encoded = frames().encode_frame(value)
    assert len(encoded) == 4096
    assert frames().decode_frame(encoded) == value
    with pytest.raises(AgentTaskError):
        frames().encode_frame({'padding': 'x' * 4083})
    value = {'values': [1, 0.25, True, '中文', None]}
    assert frames().decode_frame(frames().encode_frame(value)) == value


@pytest.mark.parametrize('value', [[], {'x': float('nan')}, {'x': float('inf')}, {'x': object()}])
def test_wire_encoder_does_not_serialize_objects_or_nonfinite_values(value):
    with pytest.raises(AgentTaskError):
        frames().encode_frame(value)


@pytest.mark.parametrize('sequence', [True, False, 0, -1, 1.0, '1', 2 ** 63])
def test_request_sequence_requires_a_bounded_positive_integer(sequence):
    with pytest.raises(AgentTaskError):
        frames().validate_request({'request_id': sequence, 'operation': 'inspect', 'body': {}})


@pytest.mark.parametrize('mutation', [{'pid': 123}, {'operation': 'stop'}, {'body': {'idle_seconds': 60}},
    {'operation': 'check', 'body': {'generation': True, 'lease_id': 'a' * 32}}, {'body': None}])
def test_closed_request_cannot_select_processes_methods_or_fake_idle(mutation):
    value = {'request_id': 1, 'operation': 'inspect', 'body': {}}
    value.update(mutation)
    with pytest.raises(AgentTaskError):
        frames().validate_request(value)


def test_busy_is_a_normal_result_and_source_survives_until_it_is_idle():
    source = Source(ready=False)
    connection = protocol(source)
    assert request(connection, 1, 'acquire') == {'request_id': 1, 'status': 'busy', 'result': None}
    first = request(connection, 2, 'inspect')['result']
    source.advance(60)
    lease = request(connection, 3, 'acquire')['result']
    assert lease['generation'] == first['generation']
    assert request(connection, 4, 'check', lease)['status'] == 'ok'
    connection.close()


def test_disconnect_releases_only_issued_tokens_and_does_not_stop_source():
    source = Source()
    first, second = protocol(source), protocol(source)
    owned = request(first, 1, 'acquire')['result']
    foreign = request(second, 1, 'acquire')['result']
    first.close()
    first.close()
    with pytest.raises(AgentTaskError):
        source.state.check(**owned)
    assert request(second, 2, 'check', foreign)['status'] == 'ok'
    assert source.releases == [owned]
    second.close()


def test_reader_capability_can_check_but_not_release_another_connections_lease():
    source = Source()
    issuer, reader = protocol(source), protocol(source)
    lease = request(issuer, 1, 'acquire')['result']
    assert request(reader, 1, 'check', lease)['status'] == 'ok'
    assert request(reader, 2, 'release', lease)['status'] == 'lease_lost'
    reader.close()
    assert request(issuer, 2, 'check', lease)['status'] == 'ok'
    assert source.releases == []
    issuer.close()


@pytest.mark.parametrize('sequence', [1, 3])
def test_replay_or_skipped_sequence_closes_only_its_connection_and_revokes_issued_token(sequence):
    source = Source()
    connection = protocol(source)
    lease = request(connection, 1, 'acquire')['result']
    with pytest.raises(AgentTaskError):
        request(connection, sequence, 'inspect')
    with pytest.raises(AgentTaskError):
        source.state.check(**lease)
    assert source.status()['state'] == 'monitoring'


def test_physical_takeover_is_lease_loss_without_source_retirement():
    source = Source()
    connection = protocol(source)
    lease = request(connection, 1, 'acquire')['result']
    source.state.physical()
    assert request(connection, 2, 'check', lease) == {
        'request_id': 2, 'status': 'lease_lost', 'result': None}
    assert request(connection, 3, 'inspect')['result']['state'] == 'waiting_idle'
    connection.close()


def test_native_source_failure_is_distinct_and_never_serializes_exception_details():
    source = Source()
    connection = protocol(source)
    lease = request(connection, 1, 'acquire')['result']
    source.state.fail()
    value = request(connection, 2, 'check', lease)
    assert value == {'request_id': 2, 'status': 'source_lost', 'result': None}
    assert set(value) == {'request_id', 'status', 'result'}
    connection.close()


def test_explicit_release_and_disconnect_do_not_release_a_token_twice():
    source = Source()
    connection = protocol(source)
    lease = request(connection, 1, 'acquire')['result']
    assert request(connection, 2, 'release', lease)['result'] == {'released': True}
    connection.close()
    assert source.releases == [lease]


@pytest.mark.parametrize('field,value', [('state', 'fake'), ('generation', 'b' * 32),
    ('idle_seconds', True), ('idle_seconds', -1), ('idle_seconds', float('inf')),
    ('revision', True), ('revision', -1), ('interactive', 1), ('held', 0), ('native_evidence', True)])
def test_response_snapshot_is_closed_typed_and_bound_to_the_live_generation(field, value):
    snapshot = Source().status()
    generation = snapshot['generation']
    snapshot[field] = value
    response = {'request_id': 1, 'status': 'ok', 'result': snapshot}
    with pytest.raises(AgentTaskError):
        frames().validate_response(response, 'inspect', 1, generation)


@pytest.mark.parametrize('response', [
    {'request_id': True, 'status': 'busy', 'result': None},
    {'request_id': 2, 'status': 'busy', 'result': None},
    {'request_id': 1, 'status': 'busy', 'result': {}},
    {'request_id': 1, 'status': 'unexpected', 'result': None},
    {'request_id': 1, 'status': 'busy', 'result': None, 'input_authorized': True}])
def test_response_status_sequence_and_fields_cannot_forge_authority(response):
    with pytest.raises(AgentTaskError):
        frames().validate_response(response, 'inspect', 1, 'a' * 32)


def test_release_success_requires_actual_true_and_acquire_token_shape_is_exact():
    for value in (1, 1.0, False):
        with pytest.raises(AgentTaskError):
            frames().validate_response({'request_id': 1, 'status': 'ok', 'result': {'released': value}},
                                       'release', 1, 'a' * 32)
    result = {'generation': 'a' * 32, 'lease_id': 'b' * 32}
    response = {'request_id': 1, 'status': 'ok', 'result': result}
    assert frames().validate_response(response, 'acquire', 1, 'a' * 32) == response
    assert frames().decode_frame(json.dumps(response).encode()) == response


def test_expected_busy_result_preserves_the_actual_owned_helper_and_source_generation():
    from pathlib import Path
    import sys
    import je_auto_control
    from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
    origin = Path(je_auto_control.__file__).resolve().parent.parent
    code = '''
import json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from je_auto_control.utils.agent_runtime import presence_protocol
from je_auto_control.utils.agent_runtime.presence_state import PresenceState
assert pathlib.Path(presence_protocol.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]))
class Source:
 def __init__(self):
  self.now=0.0; self.state=PresenceState(lambda:self.now); self.state.refresh(True,False)
 def status(self): return self.state.inspect()
 def release(self,**body): self.state.release(**body)
 def request(self,operation,body):
  self.state.refresh(True,False)
  return getattr(self.state,operation)(**body)
source=Source(); protocol=presence_protocol.PresenceProtocol(source)
for line in sys.stdin.buffer:
 value=json.loads(line)
 if value['operation']=='bootstrap': result={'protocol':1}
 elif value['operation']=='advance':
  for step in range(480): source.now+=0.125; source.state.refresh(True,False)
  result=source.status()
 else: result=protocol.request(value['payload'])
 print(json.dumps({'id':value['id'],'result':result}),flush=True)
'''
    channel = OwnedChannel([sys.executable, '-u', '-c', code, str(origin)])
    try:
        assert channel.request('bootstrap', {}, timeout=15) == {'protocol': 1}
        body = {'request_id': 1, 'operation': 'acquire', 'body': {}}
        assert channel.request('wire', body, timeout=2)['status'] == 'busy'
        assert not channel.retired
        first = channel.request('advance', {}, timeout=2)
        body['request_id'] = 2
        token = channel.request('wire', body, timeout=2)['result']
        assert token['generation'] == first['generation']
        assert not channel.retired
    finally:
        channel.close()
    assert channel.retired
