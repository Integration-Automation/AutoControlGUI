"""A source owns its listener; each borrowed connection owns only its issued presence tokens."""
import queue
import threading
import time
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import decode_frame, encode_frame
from .presence_test_support import Source


class Connection:
    def __init__(self):
        self.incoming, self.outgoing = queue.Queue(), queue.Queue()
        self.closed, self.peer_closed = threading.Event(), threading.Event()
        self.live = True

    def recv_bytes(self, maximum):
        assert maximum == 4096
        value = self.incoming.get(timeout=2)
        if value is None:
            raise EOFError
        return value

    def send_bytes(self, value):
        if self.closed.is_set():
            raise EOFError
        self.outgoing.put(value)

    def close(self):
        self.closed.set()
        self.incoming.put(None)

    def request(self, sequence, operation, body=None):
        self.incoming.put(encode_frame({'request_id': sequence, 'operation': operation, 'body': body or {}}))
        return decode_frame(self.outgoing.get(timeout=2))


class Pipe:
    def __init__(self, events):
        self.events, self.pending = events, queue.Queue()
        self.occupied = False

    def listen(self):
        self.events.append('reserve')
        if self.occupied:
            raise AgentControlBusy('already owned')
        return self

    def accept(self):
        connection = self.pending.get(timeout=2)
        if connection is None:
            raise EOFError
        return connection

    def close(self):
        self.events.append('listener-close')
        self.pending.put(None)


def service(monkeypatch):
    from je_auto_control.utils.agent_runtime import presence_server
    events = []
    source, pipe = Source(events), Pipe(events)

    def construct():
        events.append('construct')
        return source

    def handshake(connection, _security, generation):
        assert generation == source.status()['generation']
        return SimpleNamespace(alive=lambda: connection.live, close=connection.peer_closed.set)

    monkeypatch.setattr(presence_server, 'server_handshake', handshake)
    server = presence_server.PresenceServer(construct, pipe=pipe, security=object())
    return server, source, pipe, events


def connected(pipe):
    connection = Connection()
    pipe.pending.put(connection)
    return connection


def test_constructor_close_and_status_do_not_reserve_or_construct_an_observer(monkeypatch):
    server, _source, _pipe, events = service(monkeypatch)
    assert not server.status()['running'] and not events
    server.close()
    assert not events
    with pytest.raises(AgentTaskError):
        server.start()


def test_first_instance_loser_never_constructs_or_closes_the_winning_source(monkeypatch):
    server, _source, pipe, events = service(monkeypatch)
    pipe.occupied = True
    assert server.start() == {'ready': False, 'occupied': True}
    server.close()
    assert events == ['reserve']


def test_reservation_precedes_observation_and_failed_start_keeps_no_ready_service(monkeypatch):
    server, source, _pipe, events = service(monkeypatch)
    source.fail_start = True
    with pytest.raises(AgentTaskError):
        server.start()
    assert events[:3] == ['reserve', 'construct', 'start']
    assert 'listener-close' in events and 'source-close' in events
    assert not server.status()['running']


def test_busy_preserves_shared_source_and_disconnect_revokes_only_issued_tokens(monkeypatch):
    server, source, pipe, events = service(monkeypatch)
    ready = server.start()
    try:
        first, second = connected(pipe), connected(pipe)
        assert first.request(1, 'acquire')['status'] == 'busy'
        source.advance(60)
        lease = first.request(2, 'acquire')['result']
        assert lease['generation'] == ready['generation']
        assert second.request(1, 'check', lease)['status'] == 'ok'
        first.close()
        assert source.released.wait(1) and first.peer_closed.wait(1)
        assert second.request(2, 'check', lease)['status'] == 'lease_lost'
        assert second.request(3, 'inspect')['result']['generation'] == ready['generation']
        assert 'source-close' not in events and server.status()['running']
    finally:
        server.close()


def test_malformed_connection_cannot_stop_another_client_or_release_its_token(monkeypatch):
    server, source, pipe, _events = service(monkeypatch)
    server.start()
    source.advance(60)
    try:
        first, bad = connected(pipe), connected(pipe)
        lease = first.request(1, 'acquire')['result']
        bad.incoming.put(b'{"request_id":1,"request_id":1}')
        assert bad.closed.wait(1)
        assert first.request(2, 'check', lease)['status'] == 'ok'
        assert server.status()['running']
    finally:
        server.close()


def test_sixteen_connections_bound_acceptance_until_a_connection_exits(monkeypatch):
    server, _source, pipe, _events = service(monkeypatch)
    server.start()
    clients = [connected(pipe) for _index in range(17)]
    try:
        for client in clients[:16]:
            assert client.request(1, 'inspect')['status'] == 'ok'
        clients[16].incoming.put(encode_frame({'request_id': 1, 'operation': 'inspect', 'body': {}}))
        with pytest.raises(queue.Empty):
            clients[16].outgoing.get(timeout=0.05)
        assert server.status()['clients'] == 16
        clients[0].close()
        assert decode_frame(clients[16].outgoing.get(timeout=1))['status'] == 'ok'
    finally:
        server.close()


def test_close_fences_leases_and_retires_only_this_server_resources(monkeypatch):
    server, source, pipe, events = service(monkeypatch)
    server.start()
    source.advance(60)
    client = connected(pipe)
    lease = client.request(1, 'acquire')['result']
    started = time.monotonic()
    server.close()
    server.close()
    assert time.monotonic() - started < 2
    assert client.closed.is_set() and 'listener-close' in events
    assert not server.status()['running']
    with pytest.raises(AgentTaskError):
        source.state.check(**lease)


def test_failed_client_thread_start_retires_the_accepted_connection(monkeypatch):
    from je_auto_control.utils.agent_runtime import presence_server
    server, _source, pipe, events = service(monkeypatch)
    original = threading.Thread

    class ClientFailure(original):
        def start(self):
            if self.name == 'PresenceClient':
                raise RuntimeError('owned test thread start refused')
            return super().start()

    patch = SimpleNamespace(**vars(threading))
    patch.Thread = ClientFailure
    monkeypatch.setattr(presence_server, 'threading', patch)
    server.start()
    client = connected(pipe)
    try:
        assert client.closed.wait(1)
        assert 'source-close' in events and server.status()['failed']
    finally:
        client.close()
        with pytest.raises(AgentTaskError):
            server.close()
