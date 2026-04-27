"""End-to-end tests for the WebSocket-transport remote-desktop variant."""
import socket
import time

import pytest

from je_auto_control.utils.remote_desktop import (
    RemoteDesktopHost, RemoteDesktopViewer,
    WebSocketDesktopHost, WebSocketDesktopViewer,
)
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError, MessageType, encode_frame,
)
from je_auto_control.utils.remote_desktop.ws_protocol import (
    WsProtocolError, client_handshake, recv_message, send_binary,
    server_handshake,
)


def _wait_until(predicate, timeout: float = 10.0,
                interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# --- ws_protocol smoke tests ---------------------------------------------


def _make_socketpair():
    """Return a pair of connected TCP sockets via loopback (cross-platform)."""
    listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen.bind(("127.0.0.1", 0))
    listen.listen(1)
    port = listen.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    server, _ = listen.accept()
    listen.close()
    return server, client


def test_handshake_round_trip():
    server, client = _make_socketpair()
    try:
        import threading
        path = {}

        def server_side():
            path["value"] = server_handshake(server)

        thread = threading.Thread(target=server_side)
        thread.start()
        client_handshake(client, "127.0.0.1", 1234, path="/rd")
        thread.join(timeout=1.0)
        assert path["value"] == "/rd"
    finally:
        server.close()
        client.close()


def test_binary_frame_round_trip_unmasked_then_masked():
    server, client = _make_socketpair()
    try:
        # Unmasked server -> client
        send_binary(server, b"hello world", mask=False)
        assert recv_message(client) == b"hello world"
        # Masked client -> server (RFC 6455 mandates client masking)
        send_binary(client, b"\x01\x02\x03", mask=True)
        assert recv_message(server) == b"\x01\x02\x03"
    finally:
        server.close()
        client.close()


def test_recv_handles_extended_payload_length():
    server, client = _make_socketpair()
    try:
        big = b"A" * 70_000  # forces 64-bit length encoding
        send_binary(server, big, mask=False)
        assert recv_message(client) == big
    finally:
        server.close()
        client.close()


def test_handshake_rejects_non_websocket_request():
    server, client = _make_socketpair()
    try:
        client.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
        with pytest.raises(WsProtocolError):
            server_handshake(server)
    finally:
        server.close()
        client.close()


# --- end-to-end host <-> viewer over WS ----------------------------------


def _start_ws_host(token: str = "tok",
                   host_id: str = "100200300") -> WebSocketDesktopHost:
    captured = []
    host = WebSocketDesktopHost(
        token=token, bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"ws-frame",
        input_dispatcher=captured.append,
        host_id=host_id,
    )
    host.start()
    host._test_captured_input = captured  # noqa: SLF001  # test helper
    return host


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_ws_viewer_authenticates_and_receives_frames():
    host = _start_ws_host()
    try:
        received = []
        viewer = WebSocketDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            on_frame=received.append,
        )
        viewer.connect(timeout=30.0)
        assert _wait_until(lambda: len(received) >= 2, timeout=30.0)
        assert all(frame == b"ws-frame" for frame in received)
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_ws_viewer_with_wrong_token_is_rejected():
    host = _start_ws_host(token="right")
    try:
        viewer = WebSocketDesktopViewer(
            host="127.0.0.1", port=host.port, token="wrong",
        )
        with pytest.raises(AuthenticationError):
            viewer.connect(timeout=30.0)
        assert host.connected_clients == 0
    finally:
        host.stop(timeout=1.0)


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_ws_viewer_input_reaches_host_dispatcher():
    host = _start_ws_host()
    try:
        viewer = WebSocketDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        viewer.connect(timeout=30.0)
        viewer.send_input({"action": "mouse_move", "x": 42, "y": 24})
        viewer.send_input({"action": "type", "text": "hi"})
        captured = host._test_captured_input  # noqa: SLF001
        # Bigger budget: under heavy suite load the WS server thread can
        # take longer than the default _wait_until budget to dispatch.
        assert _wait_until(lambda: len(captured) >= 2, timeout=30.0)
        assert {"action": "mouse_move", "x": 42, "y": 24} in captured
        assert {"action": "type", "text": "hi"} in captured
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_ws_host_announces_host_id():
    host = _start_ws_host(host_id="700800900")
    try:
        viewer = WebSocketDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            expected_host_id="700800900",
        )
        viewer.connect(timeout=30.0)
        assert viewer.remote_host_id == "700800900"
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_plain_tcp_viewer_against_ws_host_is_rejected():
    host = _start_ws_host()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        with pytest.raises((OSError, AuthenticationError)):
            viewer.connect(timeout=30.0)
        assert _wait_until(lambda: host.connected_clients == 0)
    finally:
        host.stop(timeout=1.0)


def test_ws_viewer_against_plain_host_fails():
    host = RemoteDesktopHost(
        token="tok", bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"plain",
        input_dispatcher=lambda *_a, **_k: None,
        host_id="111222333",
    )
    host.start()
    try:
        viewer = WebSocketDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        with pytest.raises((OSError, ConnectionError, WsProtocolError,
                            AuthenticationError)):
            viewer.connect(timeout=30.0)
    finally:
        host.stop(timeout=1.0)


def test_ws_viewer_path_validation():
    with pytest.raises(ValueError):
        WebSocketDesktopViewer(
            host="127.0.0.1", port=1, token="t", path="no-leading-slash",
        )
