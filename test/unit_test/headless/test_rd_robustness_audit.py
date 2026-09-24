"""Regression tests for the remote-desktop robustness defects of the 2026-09-23 audit.

A malformed INPUT message or WebSocket frame killed the host's receive thread
without ``stop()``, leaving a handler that held a client slot; the viewer's
thread died the same way without telling the GUI. The TLS / WS / auth
handshake ran on the one accept thread, so a slow peer blocked every other
viewer, and the signaling client let a timeout or a hang-up out as something
other than ``SignalingError``.
"""
import socket
import threading
import time

import pytest

from je_auto_control.utils.remote_desktop import signaling_client
from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.input_dispatch import InputDispatchError, dispatch_input
from je_auto_control.utils.remote_desktop.protocol import ProtocolError
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.remote_desktop.ws_protocol import WsProtocolError


@pytest.mark.parametrize("message", [
    {"action": "key_press"},                               # KeyError
    {"action": "mouse_move", "x": float("inf"), "y": 1},   # OverflowError
    {"action": "mouse_move", "x": "abc", "y": 1},          # ValueError
    {"action": "mouse_scroll", "amount": None},            # TypeError
], ids=["missing-field", "infinite", "not-a-number", "none"])
def test_a_malformed_input_message_is_an_input_error(message):
    # Every case fails while converting the message, before any wrapper call.
    with pytest.raises(InputDispatchError):
        dispatch_input(message)


def test_a_websocket_protocol_error_is_a_protocol_error():
    assert issubclass(WsProtocolError, ProtocolError)


def test_a_slow_handshake_does_not_block_other_viewers():
    host = RemoteDesktopHost(token="t", bind="127.0.0.1", port=0, frame_provider=lambda: None)
    host.start()
    silent = socket.create_connection(("127.0.0.1", host.port), timeout=5)  # never authenticates
    try:
        time.sleep(0.2)
        viewer = RemoteDesktopViewer(host="127.0.0.1", port=host.port, token="t",
                                     on_frame=lambda _frame: None, on_error=lambda _error: None)
        started = time.monotonic()
        viewer.connect(timeout=3.0)
        assert time.monotonic() - started < 3.0
        viewer.disconnect()
    finally:
        silent.close()
        host.stop(timeout=1.0)


def _one_shot_server(behaviour):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve():
        connection, _ = listener.accept()
        with connection:
            connection.recv(4096)
            behaviour(connection)
        listener.close()

    threading.Thread(target=serve, daemon=True).start()
    return f"http://127.0.0.1:{listener.getsockname()[1]}/sessions/h/offer"


def test_a_signaling_server_that_hangs_up_is_a_signaling_error():
    url = _one_shot_server(lambda _connection: None)
    with pytest.raises(signaling_client.SignalingError):
        signaling_client._request("GET", url, timeout=3)


def test_a_signaling_read_timeout_is_a_signaling_error():
    url = _one_shot_server(lambda _connection: time.sleep(1.0))
    with pytest.raises(signaling_client.SignalingError):
        signaling_client._request("GET", url, timeout=0.3)
