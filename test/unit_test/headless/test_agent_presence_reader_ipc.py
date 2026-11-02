"""Actual contained readers use secured native pipes and an explicitly virtual source, never desktop input."""
from pathlib import Path
import sys
import time

import pytest

from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
from .test_agent_presence_service_ipc import create, setup

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='actual Windows owned reader/pipe integration')
ROOT = Path(__file__).resolve().parents[3]


def reader_script(namespace, gate, mode):
    return f'''
import sys, threading, time
from pathlib import Path
from je_auto_control.utils.agent_runtime import presence_reader
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_owner import read_request, send_result
from je_auto_control.utils.agent_runtime.presence_pipe_windows import WindowsPresencePipe
expected = Path({str(ROOT / 'je_auto_control/utils/agent_runtime/presence_reader.py')!r})
assert Path(presence_reader.__file__).resolve() == expected
gate = Path({str(gate)!r})
mode = {mode!r}
notice = threading.Event()
held = []

def block(stage):
    if mode == stage and gate.exists():
        threading.Event().wait()

class Connection:
    def __init__(self, connection):
        self.connection = connection
    def fileno(self):
        return self.connection.fileno()
    def send_bytes(self, raw):
        block('send')
        self.connection.send_bytes(raw)
    def recv_bytes(self, bound):
        block('receive')
        return self.connection.recv_bytes(bound)
    def close(self):
        self.connection.close()

class Pipe:
    def connect(self):
        block('connect')
        return Connection(WindowsPresencePipe(namespace={namespace!r}).connect())

real_handshake = presence_reader.client_handshake
def handshake(connection, security):
    generation, peer = real_handshake(connection, security)
    held.append(peer)
    raise AgentTaskError('test handoff failed before native query cleanup was proven')
if mode == 'handoff_error':
    presence_reader.client_handshake = handshake

reader = None
while True:
    request = read_request(sys.stdin.buffer)
    if request is None:
        break
    result = {{}}
    start = time.monotonic()
    try:
        if request['operation'] == 'bootstrap':
            reader = presence_reader.PresenceReader(request['payload'], notice.set, pipe=Pipe())
            reader.ready()
        elif request['operation'] == 'check':
            reader.check()
        elif request['operation'] == 'close':
            reader.close()
        result['ok'] = True
    except AgentTaskError:
        result['ok'] = False
    result.update(notice=notice.is_set(), retired=reader.retired, elapsed=time.monotonic()-start)
    send_result(sys.stdout.buffer, request['id'], result)
'''


def reader(namespace, gate, mode='healthy'):
    return OwnedChannel([sys.executable, '-u', '-c', reader_script(namespace, gate, mode)])


def acquire(owner, clock):
    owner.request('bootstrap', {}, timeout=15)
    clock.write_text('60', encoding='utf-8')
    return owner.request('acquire', {}, timeout=3)['result']


def wait_notice(child):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        value = child.request('status', {}, timeout=max(0.001, deadline - time.monotonic()))
        if value['notice']:
            return value
    pytest.fail('owned reader did not report failed background watch within3seconds')


def test_actual_reader_replacement_checks_same_capability_and_never_releases_issuers_token(tmp_path):
    namespace, clock, instances = setup(tmp_path)
    owner = create(namespace, clock, instances)
    first, second = None, None
    try:
        binding = acquire(owner, clock)
        first = reader(namespace, tmp_path / 'gate')
        assert first.request('bootstrap', binding, timeout=15)['ok']
        assert first.request('check', {}, timeout=3)['ok']
        assert first.request('close', {}, timeout=3)['retired']
        first.close()
        assert owner.request('check', binding, timeout=3)['status'] == 'ok'
        second = reader(namespace, tmp_path / 'gate')
        assert second.request('bootstrap', binding, timeout=15)['ok']
        assert len(instances.read_text().splitlines()) == 1
        owner.close()
        assert wait_notice(second)['notice']
        assert not second.request('check', {}, timeout=3)['ok']
        assert not second.request('check', {}, timeout=3)['ok']
    finally:
        for child in (first, second, owner):
            if child is not None:
                child.close()
    assert first.retired and second.retired and owner.retired


@pytest.mark.parametrize('mode', ['send', 'receive'])
def test_actual_blocked_watch_retires_owned_reader_job_without_stopping_source(tmp_path, mode):
    namespace, clock, instances = setup(tmp_path)
    owner = create(namespace, clock, instances)
    child, gate = None, tmp_path / 'gate'
    try:
        binding = acquire(owner, clock)
        child = reader(namespace, gate, mode)
        assert child.request('bootstrap', binding, timeout=15)['ok']
        gate.write_text('block', encoding='utf-8')
        assert not wait_notice(child)['retired']
        closing = child.request('close', {}, timeout=3)
        assert not closing['ok'] and not closing['retired'] and closing['elapsed'] < 0.7
        child.close()
        assert child.retired and not owner.retired
        assert owner.request('check', binding, timeout=3)['status'] == 'ok'
        assert len(instances.read_text().splitlines()) == 1
    finally:
        if child is not None:
            child.close()
        owner.close()


@pytest.mark.parametrize('mode', ['connect', 'send', 'receive', 'handoff_error'])
def test_actual_first_bind_and_uncertain_handoff_never_claim_reader_retirement(tmp_path, mode):
    namespace, clock, instances = setup(tmp_path)
    owner = create(namespace, clock, instances)
    child, gate = None, tmp_path / 'gate'
    try:
        binding = acquire(owner, clock)
        gate.write_text('block', encoding='utf-8')
        child = reader(namespace, gate, mode)
        initial = child.request('bootstrap', binding, timeout=15)
        assert not initial['ok'] and initial['notice'] and initial['elapsed'] < 0.7
        assert not initial['retired']
        closing = child.request('close', {}, timeout=3)
        assert not closing['ok'] and not closing['retired'] and closing['elapsed'] < 0.7
        child.close()
        assert child.retired and not owner.retired
        assert owner.request('check', binding, timeout=3)['status'] == 'ok'
    finally:
        if child is not None:
            child.close()
        owner.close()
