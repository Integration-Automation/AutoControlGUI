"""Fresh challenges bind bounded byte frames to already opened, query-only native peer objects."""
import json
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

GENERATION = 'a' * 32
REMOTE_NONCE = 'b' * 32


class Peer:
    def __init__(self, events):
        self.identity = SimpleNamespace(birth=22)
        self.events = events
        self.live, self.closed = True, False

    def alive(self):
        self.events.append('alive')
        return self.live and not self.closed

    def close(self):
        self.events.append('peer-close')
        self.closed = True


class Security:
    def __init__(self):
        self.events = []
        self.process = Peer(self.events)

    def peer(self, handle, *, server):
        assert handle == 123
        self.events.append(('peer-open', server))
        return self.process

    def current(self):
        self.events.append('current')
        return SimpleNamespace(birth=11)


class Channel:
    def __init__(self, security, incoming):
        self.security, self.incoming = security, list(incoming)
        self.sent, self.closed = [], False

    def fileno(self):
        return 123

    def send_bytes(self, raw):
        self.security.events.append('send')
        assert isinstance(raw, bytes) and len(raw) <= 4096
        self.sent.append(json.loads(raw))

    def recv_bytes(self, maximum):
        self.security.events.append('receive')
        assert maximum == 4096
        value = self.incoming.pop(0)
        if callable(value):
            value = value(self)
        return value if isinstance(value, bytes) else json.dumps(value).encode()

    def close(self):
        self.security.events.append('connection-close')
        self.closed = True


def hello():
    return dict(protocol=1, challenge=REMOTE_NONCE, birth=22, generation=GENERATION)


def client_final(channel):
    return dict(protocol=1, challenge=channel.sent[0]['challenge'], birth=22, generation=GENERATION)


def server_proof(channel):
    return dict(protocol=1, server_challenge=channel.sent[0]['challenge'], challenge=REMOTE_NONCE, birth=22)


def module():
    from je_auto_control.utils.agent_runtime import presence_handshake
    return presence_handshake


def test_client_opens_actual_peer_before_read_and_retains_query_handle_through_both_challenges():
    security = Security()
    channel = Channel(security, [hello(), client_final])
    generation, peer = module().client_handshake(channel, security)
    assert generation == GENERATION and peer is security.process
    assert security.events[0] == ('peer-open', False)
    assert not peer.closed and not channel.closed
    assert len(channel.sent) == 1
    proof, = channel.sent
    assert set(proof) == {'protocol', 'server_challenge', 'challenge', 'birth'}
    assert proof['protocol'] == 1 and proof['birth'] == 11 and proof['server_challenge'] == REMOTE_NONCE
    assert len(proof['challenge']) == 32 and proof['challenge'] != REMOTE_NONCE


def test_server_opens_actual_peer_before_issuing_challenge_and_echoes_only_fresh_client_proof():
    security = Security()
    channel = Channel(security, [server_proof])
    peer = module().server_handshake(channel, security, GENERATION)
    assert peer is security.process and not peer.closed and not channel.closed
    assert security.events[0] == ('peer-open', True)
    first, last = channel.sent
    assert set(first) == set(last) == {'protocol', 'challenge', 'birth', 'generation'}
    assert first['challenge'] != REMOTE_NONCE and len(first['challenge']) == 32
    assert first['birth'] == last['birth'] == 11
    assert first['generation'] == last['generation'] == GENERATION
    assert last['challenge'] == REMOTE_NONCE


@pytest.mark.parametrize('field,value', [('protocol', True), ('protocol', 2), ('birth', True), ('birth', 23),
    ('birth', 0), ('birth', 1 << 64), ('challenge', 'old'), ('generation', 'old'), ('pid', 123)])
def test_client_refuses_invalid_first_frame_without_disclosing_proof(field, value):
    security = Security()
    frame = hello()
    frame[field] = value
    channel = Channel(security, [frame])
    with pytest.raises(AgentTaskError):
        module().client_handshake(channel, security)
    assert not channel.sent and channel.closed and security.process.closed


@pytest.mark.parametrize('field,value', [('challenge', REMOTE_NONCE), ('birth', 23),
    ('generation', 'c' * 32), ('protocol', True), ('extra', 123)])
def test_client_refuses_buffered_or_changed_final_proof(field, value):
    security = Security()

    def forged(channel):
        frame = client_final(channel)
        frame[field] = value
        return frame

    channel = Channel(security, [hello(), forged])
    with pytest.raises(AgentTaskError):
        module().client_handshake(channel, security)
    assert channel.closed and security.process.closed


@pytest.mark.parametrize('field,value', [('server_challenge', REMOTE_NONCE), ('birth', 23),
    ('birth', True), ('challenge', ''), ('protocol', True), ('generation', GENERATION)])
def test_server_refuses_old_challenge_wrong_native_birth_and_unknown_fields(field, value):
    security = Security()

    def forged(channel):
        frame = server_proof(channel)
        frame[field] = value
        return frame

    channel = Channel(security, [forged])
    with pytest.raises(AgentTaskError):
        module().server_handshake(channel, security, GENERATION)
    assert len(channel.sent) == 1 and channel.closed and security.process.closed


@pytest.mark.parametrize('server', [True, False])
def test_peer_that_exits_during_challenge_cannot_authenticate(server):
    security = Security()

    def dying(channel):
        security.process.live = False
        return server_proof(channel) if server else client_final(channel)

    channel = Channel(security, [dying] if server else [hello(), dying])
    with pytest.raises(AgentTaskError):
        if server:
            module().server_handshake(channel, security, GENERATION)
        else:
            module().client_handshake(channel, security)
    assert channel.closed and security.process.closed


@pytest.mark.parametrize('raw', [b'\xff', b'{"protocol":1,"protocol":1}', b' ' * 4097],
                         ids=['invalid-utf8', 'duplicate-fields', 'oversized'])
def test_handshake_uses_closed_bounded_json_frames_and_closes_on_parse_failure(raw):
    security = Security()
    channel = Channel(security, [raw])
    with pytest.raises(AgentTaskError):
        module().client_handshake(channel, security)
    assert channel.closed and security.process.closed
