"""Portal cancellation must wake the existing connection without stale socket access."""
import socket
import threading
import time

import pytest

from je_auto_control.linux_wayland import _dbus_client as dbus


def test_abort_wakes_pending_read_without_socket_owner_race():
    connection, peer = socket.socketpair()
    bus = dbus.SessionBus(address='unused')
    bus._socket = connection
    started = threading.Event()
    failures = []

    def read():
        started.set()
        try:
            bus.read_message(time.monotonic() + 5)
        except Exception as failure:
            failures.append(failure)

    worker = threading.Thread(target=read)
    try:
        worker.start()
        assert started.wait(1)
        bus.abort()
        worker.join(1)
        assert not worker.is_alive()
        assert len(failures) == 1 and isinstance(failures[0], dbus.DBusError)
        assert bus._socket is None
        bus.abort()
    finally:
        bus.close()
        peer.close()
        worker.join(6)


def test_take_pending_transfers_messages_in_order():
    bus = dbus.SessionBus(address='unused')
    first, second = dbus.Message(4, 1, {}, []), dbus.Message(4, 2, {}, [])
    bus._queued.extend([first, second])
    assert bus.take_pending_messages() == [first, second]
    assert bus.take_pending_messages() == []


@pytest.mark.parametrize('operation', ['read', 'write'])
def test_abort_keeps_descriptor_owned_until_inflight_io_returns(operation):
    entered, released, finish = (threading.Event() for _ in range(3))

    class PausedSocket(socket.socket):
        def recv(self, size):
            entered.set()
            try:
                return super().recv(size)
            finally:
                released.set()
                if not finish.wait(5):
                    raise TimeoutError('test did not release the socket read')

        def sendall(self, data):
            super().sendall(data)
            entered.set()
            released.set()
            if not finish.wait(5):
                raise TimeoutError('test did not release the socket write')

    original, peer = socket.socketpair()
    connection = PausedSocket(fileno=original.detach())
    bus = dbus.SessionBus(address='unused')
    bus._socket = connection
    failures = []

    def perform_io():
        try:
            if operation == 'read':
                bus.read_message(time.monotonic() + 5)
            else:
                bus._send_raw(b'payload')
        except dbus.DBusError as error:
            failures.append(error)

    worker = threading.Thread(target=perform_io)
    try:
        worker.start()
        assert entered.wait(1)
        bus.abort()
        assert released.wait(1), 'shutdown must wake the pending read'
        assert bus._socket is None
        assert connection.fileno() >= 0, 'in-flight operation still owns this descriptor'
        replacement, replacement_peer = socket.socketpair()
        try:
            with pytest.raises(dbus.DBusError, match='has not drained'):
                bus._socket = replacement
            assert replacement.fileno() == -1
            assert connection.fileno() >= 0
        finally:
            replacement.close()
            replacement_peer.close()
        bus.abort()
        assert connection.fileno() >= 0
        finish.set()
        worker.join(1)
        assert not worker.is_alive()
        assert connection.fileno() == -1, 'last operation must reclaim the retired descriptor'
        assert len(failures) == 1, 'cancelled operations cannot publish late completion'
    finally:
        finish.set()
        bus.close()
        peer.close()
        worker.join(6)
        connection.close()


def test_read_poll_timeout_preserves_request_deadline_and_can_receive_later():
    class PollingSocket(socket.socket):
        polls = 0

        def recv(self, size):
            self.polls += 1
            if self.polls <= 2:
                raise socket.timeout('poll interval expired')
            return super().recv(size)

    original, peer = socket.socketpair()
    connection = PollingSocket(fileno=original.detach())
    bus = dbus.SessionBus(address='unused')
    bus._socket = connection
    try:
        peer.sendall(b'later payload')
        bus._fill(0.3)
        assert bus._buffer == b'later payload'
        assert connection.polls == 3
        assert connection.gettimeout() <= 0.1
    finally:
        bus.close()
        peer.close()


def test_empty_read_expires_at_original_deadline_and_closes_normally():
    connection, peer = socket.socketpair()
    bus = dbus.SessionBus(address='unused')
    bus._socket = connection
    started = time.monotonic()
    try:
        with pytest.raises(dbus.DBusTimeout):
            bus.read_message(started + 0.15)
        assert time.monotonic() - started < 1
        assert connection.fileno() >= 0
    finally:
        bus.close()
        peer.close()
    assert connection.fileno() == -1
