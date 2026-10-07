"""Portal cancellation must wake the existing connection without stale socket access."""
import socket
import threading
import time

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
