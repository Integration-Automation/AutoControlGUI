"""Fresh capability checks and finite reader/watch retirement without native desktop observation."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_protocol import PresenceProtocol
from je_auto_control.utils.exception.exceptions import AutoControlException
from .presence_test_support import Source
from .test_agent_native_ack_boundary import Boundary


class Harness:
    def __init__(self, monkeypatch):
        from je_auto_control.utils.agent_runtime import presence_reader
        self.source = Source()
        self.source.start()
        self.source.advance(60)
        self.issuer = PresenceProtocol(self.source)
        self.binding = self.issuer.request({'request_id': 1, 'operation': 'acquire', 'body': {}})['result']
        self.protocol = PresenceProtocol(self.source)
        self.events, self.sent, self.threads = [], [], set()
        self.notice, self.entered, self.allow = threading.Event(), threading.Event(), threading.Event()
        self.allow.set()
        self.block = None
        self.live, self.peer_closed, self.connection_closed, self.fail_close = True, False, False, False
        self.transform = lambda value: value
        self.module = presence_reader
        monkeypatch.setattr(presence_reader, 'client_handshake', self.handshake)
        self.reader = presence_reader.PresenceReader(self.binding, self.takeover, pipe=self, security=object())

    def takeover(self):
        self.events.append('notice')
        self.notice.set()

    def step(self, stage):
        self.events.append(stage)
        self.threads.add(threading.get_ident())
        if self.block == stage:
            self.entered.set()
            if not self.allow.wait(2):
                raise AgentTaskError('test gate did not unblock')

    def connect(self):
        self.step('connect')
        return Connection(self)

    def handshake(self, _connection, _security):
        self.step('handshake')
        return self.binding['generation'], Peer(self)

    def pause(self, stage):
        self.block = stage
        self.entered.clear()
        self.allow.clear()

    def cleanup(self):
        self.allow.set()
        self.fail_close = False
        self.reader.close()


class Peer:
    def __init__(self, harness):
        self.harness = harness

    def alive(self):
        self.harness.step('alive')
        return self.harness.live and not self.harness.peer_closed

    def close(self):
        self.harness.step('peer-close')
        if self.harness.fail_close:
            raise AgentTaskError('query handle retirement failed')
        self.harness.peer_closed = True


class Connection:
    def __init__(self, harness):
        self.harness = harness

    def send_bytes(self, raw):
        self.harness.step('send')
        self.harness.sent.append(json.loads(raw))

    def recv_bytes(self, bound):
        assert bound == 4096
        self.harness.step('receive')
        result = self.harness.protocol.request(self.harness.sent[-1])
        result = self.harness.transform(result)
        return result if isinstance(result, bytes) else json.dumps(result).encode('utf-8')

    def close(self):
        self.harness.step('connection-close')
        self.harness.connection_closed = True


@pytest.fixture
def harness(monkeypatch):
    value = Harness(monkeypatch)
    try:
        yield value
    finally:
        value.cleanup()


def test_reader_construction_status_check_before_ready_and_unstarted_close_are_inert(harness):
    reader = harness.reader
    assert reader.retired
    with pytest.raises(AgentTaskError):
        reader.check()
    reader.close()
    reader.close()
    with pytest.raises(AgentTaskError):
        reader.ready()
    assert not harness.events and reader.retired


@pytest.mark.parametrize('binding', [{}, {'generation': 'a' * 32}, {'generation': True, 'lease_id': 'b' * 32},
    {'generation': 'a' * 32, 'lease_id': 'b' * 32, 'pid': 42},
    {'generation': 'a' * 32, 'lease_id': 'not-an-id'}, None])
def test_reader_rejects_task_selected_or_invalid_capabilities_at_construction(harness, binding):
    with pytest.raises(AgentTaskError):
        harness.module.PresenceReader(binding, harness.takeover, pipe=harness, security=object())
    assert not harness.events


def test_each_ready_and_check_is_fresh_serial_io_for_the_same_detached_capability(harness):
    harness.reader.ready()
    original = dict(harness.binding)
    harness.binding['lease_id'] = 'f' * 32
    harness.reader.ready()
    harness.reader.check()
    assert len(harness.sent) >= 3
    assert [item['request_id'] for item in harness.sent] == list(range(1, len(harness.sent) + 1))
    assert all(item['operation'] == 'check' and item['body'] == original for item in harness.sent)
    harness.reader.close()
    assert len(harness.threads) == 1 and threading.get_ident() not in harness.threads
    assert harness.reader.retired and harness.peer_closed and harness.connection_closed
    assert not harness.notice.is_set()
    assert harness.issuer.request({'request_id': 2, 'operation': 'check', 'body': original})['status'] == 'ok'


def test_physical_revision_revokes_reader_between_actions_and_never_rearms(harness):
    harness.reader.ready()
    harness.source.state.physical()
    assert harness.notice.wait(0.6)
    harness.source.advance(60)
    with pytest.raises(AgentTaskError):
        harness.reader.check()
    with pytest.raises(AgentTaskError):
        harness.reader.ready()
    assert harness.events.count('notice') == 1 and harness.events.count('connect') == 1


def mutate(value, change):
    if change in {'busy', 'lease_lost', 'source_lost'}:
        return {**value, 'status': change, 'result': None}
    if change == 'oversize':
        return b'x' * 4097
    if change == 'locked':
        value['result'].update(interactive=False, state='locked')
        return value
    target, key, replacement = {
        'sequence': (value, 'request_id', value['request_id'] - 1),
        'generation': (value['result'], 'generation', 'f' * 32),
        'revision': (value['result'], 'revision', value['result']['revision'] + 1),
        'unknown': (value, 'pid', 42),
    }[change]
    target[key] = replacement
    return value


@pytest.mark.parametrize('change', ['busy', 'lease_lost', 'source_lost', 'sequence', 'generation',
                                  'revision', 'locked', 'unknown', 'oversize'])
def test_gate_refuses_revoked_malformed_stale_or_changed_source_replies_once(harness, change):
    harness.reader.ready()
    harness.transform = lambda value: mutate(value, change)
    with pytest.raises(AgentTaskError):
        harness.reader.check()
    assert harness.notice.wait(0.3)
    harness.transform = lambda value: value
    with pytest.raises(AgentTaskError):
        harness.reader.ready()
    assert harness.events.count('notice') == 1 and harness.events.count('connect') == 1


def test_existing_lease_may_keep_its_owned_held_input_without_new_acquisition(harness):
    harness.reader.ready()

    def held(value):
        value['result']['held'], value['result']['state'] = True, 'waiting_idle'
        return value

    harness.transform = held
    harness.reader.check()
    assert not harness.notice.is_set()


@pytest.mark.parametrize('stage', ['connect', 'handshake', 'send', 'receive', 'alive'])
def test_first_bind_blocks_are_bounded_and_late_replies_never_authorize(harness, stage):
    harness.pause(stage)
    start = time.monotonic()
    with pytest.raises(AgentTaskError):
        harness.reader.ready()
    assert time.monotonic() - start < 0.7 and harness.entered.is_set()
    assert harness.notice.wait(0.3) and not harness.reader.retired
    start = time.monotonic()
    with pytest.raises(AgentTaskError):
        harness.reader.close()
    assert time.monotonic() - start < 0.7
    harness.allow.set()
    harness.reader.close()
    assert harness.reader.retired
    with pytest.raises(AgentTaskError):
        harness.reader.ready()
    assert harness.events.count('notice') == 1


def test_background_watch_detects_blocked_io_without_a_subsequent_action(harness):
    harness.reader.ready()
    harness.pause('receive')
    assert harness.entered.wait(0.3)
    assert harness.notice.wait(0.4)
    assert not harness.reader.retired
    with pytest.raises(AgentTaskError):
        harness.reader.check()
    harness.allow.set()
    harness.reader.close()
    assert harness.reader.retired


def test_close_during_late_connect_retires_only_owned_resources_without_handshake(harness):
    harness.pause('connect')
    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting = executor.submit(harness.reader.ready)
        assert harness.entered.wait(0.3)
        with pytest.raises(AgentTaskError):
            harness.reader.close()
        harness.allow.set()
        with pytest.raises(AgentTaskError):
            waiting.result(timeout=1)
    harness.reader.close()
    assert harness.reader.retired and harness.connection_closed
    assert 'handshake' not in harness.events and not harness.sent


def test_failed_native_close_retains_handle_and_explicit_retry_never_reconnects(harness):
    harness.reader.ready()
    harness.fail_close = True
    with pytest.raises(AgentTaskError):
        harness.reader.close()
    assert harness.connection_closed and not harness.peer_closed and not harness.reader.retired
    harness.fail_close = False
    harness.reader.close()
    assert harness.peer_closed and harness.reader.retired and harness.events.count('connect') == 1
    assert not harness.notice.is_set()


@pytest.mark.parametrize('name', ['PresenceReaderIO', 'PresenceReaderWatch'])
def test_reader_thread_start_failure_is_typed_and_cannot_leave_a_live_or_unjoinable_reader(harness, monkeypatch, name):
    original = threading.Thread.start

    def start(thread):
        if thread.name == name:
            raise RuntimeError('thread admission failed')
        original(thread)

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, 'start', start)
        with pytest.raises(AgentTaskError, match='thread'):
            harness.reader.ready()
    harness.reader.close()
    assert harness.reader.retired and not harness.sent and harness.events.count('notice') == 1


def test_cleanup_thread_start_failure_retains_unknown_query_handle_for_explicit_retry(harness, monkeypatch):
    harness.reader.ready()
    harness.fail_close = True
    with pytest.raises(AgentTaskError):
        harness.reader.close()
    harness.fail_close = False

    def start(_thread):
        raise RuntimeError('cleanup admission failed')

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, 'start', start)
        with pytest.raises(AgentTaskError, match='thread'):
            harness.reader.close()
    assert not harness.reader.retired and not harness.peer_closed
    harness.reader.close()
    assert harness.reader.retired and harness.events.count('connect') == 1


def test_reader_checks_actual_peer_liveness_without_connecting_to_another_process(harness):
    harness.reader.ready()
    harness.live = False
    with pytest.raises(AgentTaskError):
        harness.reader.check()
    assert harness.notice.wait(0.3)
    assert harness.events.count('notice') == 1 and harness.events.count('connect') == 1


@pytest.mark.parametrize('boundary_name', ['on_ack', 'on_prepare'])
def test_actual_reader_revision_checks_fence_worker_ack_and_pointer_preparation(harness, monkeypatch, boundary_name):
    boundary = Boundary(monkeypatch)
    harness.reader.ready()
    boundary.worker._activity = harness.reader
    setattr(boundary, boundary_name, harness.source.state.physical)
    with pytest.raises(AutoControlException):
        if boundary_name == 'on_prepare':
            boundary.worker._input({'kind': 'mouse_press', 'keycode': 'left', 'move_before_press': True})
        else:
            boundary.press()
    assert 'pressed' not in boundary.events
    assert harness.notice.wait(0.3)
    assert harness.events.count('connect') == 1


def test_reader_loss_does_not_block_worker_owned_release_only_ack_cleanup(harness, monkeypatch):
    boundary = Boundary(monkeypatch)
    harness.reader.ready()
    boundary.worker._activity = harness.reader
    harness.source.state.physical()
    assert harness.notice.wait(0.6)
    result = boundary.worker._release_owned({'keys': [{'keycode': 65, 'is_shift': False}], 'buttons': []})
    assert result == {'cleaned': True} and 'released' in boundary.events and 'cleaned' in boundary.events
    with pytest.raises(AgentTaskError):
        harness.reader.check()
