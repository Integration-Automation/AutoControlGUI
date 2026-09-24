"""A receiver from the previous connection must not reach into the next one.

``disconnect()`` joins the receiver with a timeout; a receiver inside a slow
``on_frame`` callback outlives it. Its loop used to read the viewer's one
``_shutdown`` event, which the next ``connect()`` cleared -- so it resumed on
the old channel -- and on its way out it set ``_connected = False`` and
reported its closing socket through ``on_error``, both on the viewer's *new*
connection: the session the caller had just opened showed as down, with an
error it never had.

No sockets: the loop is driven directly with a channel we control.
"""
import threading

from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


class _ClosingChannel:
    """Blocks until released, then fails the read the way a closed socket does."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def read_typed(self):
        self.entered.set()
        self.release.wait(5.0)
        raise OSError("socket closed")


def test_old_receiver_leaves_the_new_connection_alone():
    errors = []
    viewer = RemoteDesktopViewer("127.0.0.1", 1, "tok",
                                 on_error=errors.append)
    old_channel, old_stop = _ClosingChannel(), threading.Event()
    viewer._channel = old_channel
    viewer._connected = True
    receiver = threading.Thread(target=viewer._recv_loop,
                                args=(old_channel, old_stop), daemon=True)
    receiver.start()
    assert old_channel.entered.wait(2.0)

    # disconnect() gave up on the join; connect() then installed a new
    # connection with a new run event. Model exactly that state.
    old_stop.set()
    viewer._channel = object()
    viewer._shutdown = threading.Event()
    viewer._connected = True

    old_channel.release.set()
    receiver.join(2.0)
    assert not receiver.is_alive()
    assert viewer._connected is True, (
        "the old receiver marked the new connection as down")
    assert errors == [], (
        f"the old connection's close was reported on the new one: {errors}")


def test_a_dropped_connection_is_still_reported():
    """Positive control: the current connection failing must still surface."""
    errors = []
    viewer = RemoteDesktopViewer("127.0.0.1", 1, "tok",
                                 on_error=errors.append)
    channel, stop = _ClosingChannel(), threading.Event()
    channel.release.set()
    viewer._channel = channel
    viewer._connected = True
    viewer._recv_loop(channel, stop)
    assert viewer._connected is False
    assert len(errors) == 1 and isinstance(errors[0], OSError)
