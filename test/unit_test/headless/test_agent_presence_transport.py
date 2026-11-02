"""Actual protected named pipes run only in contained background helpers, without observation/input."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import secrets
import sys
import time

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='actual secured named pipes are Windows-only')

WORKER = '''
import json, secrets, sys
from pathlib import Path
from je_auto_control.utils.agent_runtime import presence_pipe_windows as module
from je_auto_control.utils.agent_runtime.presence_frames import decode_frame, encode_frame
from je_auto_control.utils.agent_runtime.presence_handshake import client_handshake, server_handshake
from je_auto_control.utils.agent_runtime.presence_security_windows import WindowsPresenceSecurity

security = WindowsPresenceSecurity()
generation = secrets.token_hex(16)
listener = connection = peer = None

def handle(operation, payload):
    global listener, connection, peer
    if operation == 'ready':
        return {'ready': True}
    if operation == 'listen':
        listener = module.WindowsPresencePipe(namespace=payload['namespace']).listen()
        return {'ready': True, 'origin': str(Path(module.__file__).resolve()), 'generation': generation}
    if operation in ('accept', 'accept-raw'):
        connection = listener.accept()
        if operation == 'accept':
            peer = server_handshake(connection, security, generation)
        return {'generation': generation}
    if operation in ('connect', 'connect-raw'):
        connection = module.WindowsPresencePipe(namespace=payload['namespace']).connect()
        if operation == 'connect':
            value, peer = client_handshake(connection, security)
            return {'generation': value}
        return {'connected': True}
    if operation == 'send':
        connection.send_bytes(encode_frame(payload))
        return {'sent': True}
    if operation == 'receive':
        return decode_frame(connection.recv_bytes(4096))
    if operation == 'block-write':
        while True:
            connection.send_bytes(b' ' * 4096)
    if operation == 'alive':
        return {'alive': peer.alive()}
    if operation == 'identity':
        return {'current_pid': security.current().pid, 'peer_pid': peer.identity.pid, 'alive': peer.alive()}
    if operation == 'close':
        if peer is not None:
            peer.close()
        if connection is not None:
            connection.close()
        if listener is not None:
            listener.close()
        listener = connection = peer = None
        return {'closed': True}
    raise RuntimeError('unknown owned fixture operation')

for line in sys.stdin.buffer:
    request = json.loads(line)
    try:
        result = handle(request['operation'], request['payload'])
        response = {'id': request['id'], 'result': result}
    except Exception as error:
        response = {'id': request['id'], 'error': type(error).__name__, 'error_type': type(error).__name__}
    print(json.dumps(response), flush=True)
'''


def worker():
    return OwnedChannel([sys.executable, '-u', '-c', WORKER])


def listening(namespace):
    server = worker()
    try:
        ready = server.request('listen', {'namespace': namespace}, timeout=15)
        expected = Path(__file__).resolve().parents[3] / 'je_auto_control/utils/agent_runtime/presence_pipe_windows.py'
        assert ready['ready'] and Path(ready['origin']) == expected
        return server, ready
    except BaseException:
        server.close()
        raise


def connect(server, client, namespace):
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(server.request, 'accept', {}, timeout=15)
        connected = client.request('connect', {'namespace': namespace}, timeout=15)
        assert waiting.result(timeout=16) == connected
        return connected['generation']


@pytest.fixture
def pair():
    namespace = secrets.token_hex(16)
    server, ready = listening(namespace)
    client = worker()
    try:
        assert connect(server, client, namespace) == ready['generation']
        yield server, client
    finally:
        client.close()
        server.close()
    assert client.retired and server.retired


def test_actual_background_peer_challenges_and_bounded_bytes_round_trip(pair):
    server, client = pair
    value = {'request_id': 1, 'operation': 'inspect', 'body': {}}
    assert client.request('send', value, timeout=3) == {'sent': True}
    assert server.request('receive', {}, timeout=3) == value
    assert server.request('send', {'status': 'busy'}, timeout=3) == {'sent': True}
    assert client.request('receive', {}, timeout=3) == {'status': 'busy'}
    assert server.request('alive', {}, timeout=3) == {'alive': True}


def test_actual_first_instance_rejects_contender_without_retiring_existing_owner():
    namespace = secrets.token_hex(16)
    server, ready = listening(namespace)
    contender, client = worker(), worker()
    try:
        with pytest.raises(AgentControlBusy):
            contender.request('listen', {'namespace': namespace}, timeout=15)
        assert contender.retired and not server.retired
        assert connect(server, client, namespace) == ready['generation']
    finally:
        client.close()
        contender.close()
        server.close()


@pytest.mark.parametrize('operation', ['receive', 'block-write'])
def test_blocked_actual_read_or_write_retires_only_that_owned_helper(pair, operation):
    server, client = pair
    started = time.monotonic()
    with pytest.raises(AgentTaskError, match='deadline'):
        client.request(operation, {}, timeout=0.25)
    assert client.retired and time.monotonic() - started < 5
    assert server.request('alive', {}, timeout=3) == {'alive': False}
    assert not server.retired


def test_blocked_actual_accept_retires_owner_and_allows_new_first_instance():
    namespace = secrets.token_hex(16)
    server, old = listening(namespace)
    try:
        started = time.monotonic()
        with pytest.raises(AgentTaskError, match='deadline'):
            server.request('accept', {}, timeout=0.25)
        assert server.retired and time.monotonic() - started < 5
        replacement, new = listening(namespace)
        try:
            assert new['generation'] != old['generation']
        finally:
            replacement.close()
    finally:
        server.close()


@pytest.mark.parametrize('waiting_server', [True, False])
def test_actual_half_handshake_is_bounded_by_owned_process_retirement(waiting_server):
    namespace = secrets.token_hex(16)
    server, _ready = listening(namespace)
    client = worker()
    try:
        if waiting_server:
            assert client.request('connect-raw', {'namespace': namespace}, timeout=15) == {'connected': True}
            waiting, operation, payload = server, 'accept', {}
        else:
            assert client.request('ready', {}, timeout=15) == {'ready': True}
            with ThreadPoolExecutor(max_workers=1) as pool:
                accepted = pool.submit(server.request, 'accept-raw', {}, timeout=15)
                with pytest.raises(AgentTaskError, match='deadline'):
                    client.request('connect', {'namespace': namespace}, timeout=3)
                assert accepted.result(timeout=16)
            assert client.retired and not server.retired
            return
        with pytest.raises(AgentTaskError, match='deadline'):
            waiting.request(operation, payload, timeout=0.25)
        assert waiting.retired and not client.retired
    finally:
        client.close()
        server.close()
