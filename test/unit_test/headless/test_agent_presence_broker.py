"""Private brokers preserve source generations and distinguish expected gate data from fatal loss."""
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import decode_frame, encode_frame
from je_auto_control.utils.agent_runtime.presence_protocol import PresenceProtocol
from .presence_test_support import Source


class Wire:
    def __init__(self, source):
        self.protocol = PresenceProtocol(source)
        self.closed = False
        self.reply = None
        self.mutate = lambda value: value

    def send_bytes(self, raw):
        assert not self.closed
        self.reply = self.protocol.request(decode_frame(raw))

    def recv_bytes(self, maximum):
        assert maximum == 4096
        return encode_frame(self.mutate(self.reply))

    def close(self):
        self.closed = True
        self.protocol.close()


class Pipe:
    def __init__(self, source):
        self.source, self.present = source, False
        self.calls, self.connections = [], []
        self.busy = False

    def connect_if_present(self):
        self.calls.append('discover')
        if self.busy:
            raise AgentControlBusy('capacity busy')
        return self.connect() if self.present else None

    def connect(self):
        self.calls.append('connect')
        value = Wire(self.source)
        self.connections.append(value)
        return value


class Child:
    def __init__(self, pipe, occupied=False):
        self.pipe, self.occupied, self.closed = pipe, occupied, False

    def start(self):
        self.pipe.present = True
        if self.occupied:
            return {'ready': False, 'occupied': True}
        self.pipe.source.start()
        return {'ready': True, 'generation': self.pipe.source.status()['generation']}

    def close(self):
        self.closed = True
        if not self.occupied:
            self.pipe.source.close()


def setup(monkeypatch, occupied=False):
    from je_auto_control.utils.agent_runtime import presence_broker
    source, children = Source(), []
    if occupied:
        source.start()
    pipe = Pipe(source)
    peer = SimpleNamespace(alive=lambda: True, close=lambda: None)
    monkeypatch.setattr(presence_broker, 'client_handshake',
        lambda connection, _security: (connection.protocol.generation, peer))

    def launch():
        child = Child(pipe, occupied)
        children.append(child)
        return child

    def create():
        return presence_broker.PresenceBroker(pipe=pipe, security=object(), launch=launch)

    return create, source, pipe, children


def test_constructor_close_and_unbound_requests_never_discover_or_launch(monkeypatch):
    create, _source, pipe, children = setup(monkeypatch)
    broker = create()
    with pytest.raises(AgentTaskError):
        broker.request('inspect', {})
    broker.close()
    assert not pipe.calls and not children


def test_missing_source_launches_once_and_busy_is_normal_without_resetting_generation(monkeypatch):
    create, source, _pipe, children = setup(monkeypatch)
    broker = create()
    try:
        ready = broker.bootstrap()
        assert ready['ready'] and len(children) == 1
        assert broker.request('acquire', {})['status'] == 'busy'
        assert broker.bootstrap() == ready and not children[0].closed
        source.advance(60)
        assert broker.request('acquire', {})['result']['generation'] == ready['generation']
        assert len(children) == 1
    finally:
        broker.close()


def test_borrower_close_releases_only_its_tokens_and_never_stops_the_owner(monkeypatch):
    create, source, _pipe, children = setup(monkeypatch)
    owner, borrower = create(), create()
    try:
        ready = owner.bootstrap()
        source.advance(60)
        first = owner.request('acquire', {})['result']
        assert borrower.bootstrap() == ready
        second = borrower.request('acquire', {})['result']
        assert borrower.request('check', first)['status'] == 'ok'
        assert borrower.request('release', first)['status'] == 'lease_lost'
        borrower.close()
        assert not children[0].closed
        assert owner.request('check', first)['status'] == 'ok'
        assert owner.request('check', second)['status'] == 'lease_lost'
    finally:
        borrower.close()
        owner.close()


def test_owner_loss_fences_borrower_without_implicitly_launching_another_source(monkeypatch):
    create, source, _pipe, children = setup(monkeypatch)
    owner, borrower = create(), create()
    try:
        owner.bootstrap()
        source.advance(60)
        borrower.bootstrap()
        lease = borrower.request('acquire', {})['result']
        owner.close()
        with pytest.raises(AgentTaskError):
            borrower.request('check', lease)
        assert len(children) == 1
    finally:
        borrower.close()
        owner.close()


def test_losing_new_child_borrows_the_verified_winner_and_never_owns_its_source(monkeypatch):
    create, source, _pipe, children = setup(monkeypatch, occupied=True)
    broker = create()
    assert broker.bootstrap()['ready']
    assert children[0].closed
    broker.close()
    assert source.status()['state'] == 'waiting_idle'


def test_connection_capacity_busy_cannot_launch_or_retire_a_source(monkeypatch):
    create, _source, pipe, children = setup(monkeypatch)
    pipe.busy = True
    broker = create()
    assert broker.bootstrap() == {'ready': False, 'status': 'busy'}
    assert not children
    broker.close()


def test_busy_initial_inspection_keeps_the_owned_source_and_existing_connection(monkeypatch):
    create, source, _pipe, children = setup(monkeypatch)
    original = source.request
    busy = [True]

    def request(operation, body):
        if operation == 'inspect' and busy:
            busy.pop()
            raise AgentControlBusy('fresh native sample is busy')
        return original(operation, body)

    monkeypatch.setattr(source, 'request', request)
    broker = create()
    try:
        assert broker.bootstrap() == {'ready': False, 'status': 'busy'}
        assert len(children) == 1 and not children[0].closed
        assert broker.bootstrap()['generation'] == source.status()['generation']
        assert len(children) == 1
    finally:
        broker.close()


@pytest.mark.parametrize('payload', [{'namespace': 'a' * 32}, {'owner': True}, {'pid': 123}, {'source': {}}])
def test_wire_bootstrap_cannot_select_namespace_role_process_or_source(monkeypatch, payload):
    create, _source, pipe, children = setup(monkeypatch)
    broker = create()
    with pytest.raises(AgentTaskError):
        broker.dispatch('bootstrap', payload)
    broker.close()
    assert not pipe.calls and not children


@pytest.mark.parametrize('mutation', [{'request_id': True}, {'status': 'ok', 'result': {'generation': 'x'}},
                                    {'status': 'source_lost', 'result': None}])
def test_invalid_or_lost_source_response_is_fatal_and_never_replayed(monkeypatch, mutation):
    create, _source, pipe, children = setup(monkeypatch)
    broker = create()
    broker.bootstrap()

    def mutate(value):
        return {**value, **mutation}

    pipe.connections[0].mutate = mutate
    with pytest.raises(AgentTaskError):
        broker.request('inspect', {})
    broker.close()
    assert children[0].closed and len(children) == 1
