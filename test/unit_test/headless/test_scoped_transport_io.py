"""Scoped polls preserve partial messages, partial writes, total deadlines and primary controls."""
from concurrent.futures import CancelledError
import errno
from io import BytesIO
import socket
from types import SimpleNamespace
import time

import pytest

from headless.test_wayland_dbus_client import _bus
from je_auto_control.utils import cancellable_process
from je_auto_control.utils.dbus_client import cancellable_io, session_bus
from je_auto_control.utils.exception.cancellation import (
    CancellationToken, cancellation_scope, current_cancellation_token,
)


class ChunkSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def recv(self, _count):
        value = self.chunks.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def test_scoped_read_retains_fragmented_message_bytes_across_poll_timeouts():
    encoder = _bus()
    encoder.send(session_bus.SIGNAL, {
        session_bus.FIELD_PATH: ('o', '/controlled'), session_bus.FIELD_MEMBER: ('s', 'Response'),
        session_bus.FIELD_INTERFACE: ('s', 'controlled.Interface'), session_bus.FIELD_SIGNATURE: ('g', 's'),
    }, 's', ['controlled payload'])
    raw = encoder._socket.written
    incoming = ChunkSocket([raw[:7], socket.timeout(), raw[7:19], socket.timeout(), raw[19:]])
    reader = session_bus.SessionBus(address='unix:path=/controlled')
    reader._socket = incoming
    with cancellation_scope(CancellationToken(1)):
        message = reader.read_message(time.monotonic()+1)
    assert message.body == ['controlled payload'] and reader._buffer == b''
    assert all(0 < value <= 0.1 for value in incoming.timeouts)


def test_partial_send_retries_only_unsent_bytes_and_restores_the_call_timeout():
    sent, attempted = [], []

    class PartialSender:
        timeout = 1.0

        def gettimeout(self):
            return self.timeout

        def settimeout(self, timeout):
            self.timeout = timeout

        def send(self, data):
            attempted.append(bytes(data))
            if len(attempted) == 2:
                raise socket.timeout()
            count = 2 if len(attempted) == 1 else len(data)
            sent.append(bytes(data[:count]))
            return count

    sender = PartialSender()
    with cancellation_scope(CancellationToken(1)):
        cancellable_io.send(sender, b'abcdef')
    assert b''.join(sent) == b'abcdef'
    assert attempted == [b'abcdef', b'cdef', b'cdef'] and sender.timeout == 1.0


def test_repeated_receive_polls_do_not_restart_the_total_deadline(monkeypatch):
    clock = iter([0.0, 0.0, 0.04, 0.04, 0.08, 0.08, 0.12])
    monkeypatch.setattr(cancellable_io, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    incoming = ChunkSocket([socket.timeout(), socket.timeout(), socket.timeout()])
    with cancellation_scope(CancellationToken(1)), pytest.raises(socket.timeout):
        cancellable_io.receive(incoming, 10, 0.1)
    assert len(incoming.timeouts) == 3


def test_pending_connect_cancellation_restores_socket_mode_without_waiting_for_connect_timeout(monkeypatch):
    token = CancellationToken(1)
    calls = []

    class PendingSocket:
        def settimeout(self, value):
            calls.append(('timeout', value))

        def setblocking(self, value):
            calls.append(('blocking', value))

        def connect(self, address):
            calls.append(('connect', address))
            raise BlockingIOError(errno.EINPROGRESS, 'controlled pending connect')

    def pending(_read, _write, _error, timeout):
        calls.append(('poll', timeout))
        token.cancel()
        return [], [], []

    monkeypatch.setattr(cancellable_io, 'select', SimpleNamespace(select=pending))
    with cancellation_scope(token), pytest.raises(CancelledError):
        cancellable_io.connect(PendingSocket(), '/controlled', 10)
    assert calls[-1] == ('timeout', 10)
    assert len([item for item in calls if item[0] == 'connect']) == 1
    assert 0 < next(value for kind, value in calls if kind == 'poll') <= 0.1


def test_process_stream_cleanup_cannot_replace_the_original_cancel_control(monkeypatch):
    primary = CancelledError()
    calls = []

    class FailingStream:
        def close(self):
            assert current_cancellation_token() is None
            calls.append('close')
            raise OSError('controlled close failure')

    class ControlledProcess:
        stdout, stderr = FailingStream(), BytesIO()
        returncode = None
        attempts = 0

        def communicate(self, timeout):
            self.attempts += 1
            if self.attempts == 1:
                raise primary
            self.returncode = -15
            assert current_cancellation_token() is None
            calls.append('reaped')
            return b'', b''

    process = ControlledProcess()
    monkeypatch.setattr(cancellable_process.subprocess, 'Popen', lambda *_args, **_kwargs: process)
    monkeypatch.setattr(cancellable_process, '_signal_owned', lambda *_args: calls.append('signal'))
    try:
        with cancellation_scope(CancellationToken(1)), pytest.raises(CancelledError) as caught:
            cancellable_process.run_capture_helper(['controlled'], 10)
        assert caught.value is primary
        assert calls == ['signal', 'reaped', 'close'] and process.stderr.closed
    finally:
        primary.__traceback__ = None


@pytest.mark.parametrize('hard', [False, True])
def test_a_reaped_process_never_uses_its_recyclable_pid_as_a_signal_target(hard):
    class ReapedProcess:
        returncode = 7

        @property
        def pid(self):
            pytest.fail('cleanup attempted to signal a recycled numeric process identifier')

    cancellable_process._signal_owned(ReapedProcess(), hard)
