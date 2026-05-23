"""Phase 3.3: tests for the in-process TCP relay."""
import socket
import time

import pytest

from je_auto_control.utils.remote_desktop.relay import (
    RelayError, RelayServer, encode_handshake,
)


def _connect(port: int) -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", port), timeout=5.0)
    return sock


@pytest.fixture
def relay():
    server = RelayServer(bind="127.0.0.1", port=0)
    server.start()
    yield server
    server.stop(timeout=1.0)


def test_relay_pairs_two_peers_by_session_id(relay):
    session_id = b"S" * 32
    host = _connect(relay.port)
    viewer = _connect(relay.port)
    host.sendall(encode_handshake("host", session_id))
    viewer.sendall(encode_handshake("viewer", session_id))
    try:
        host.sendall(b"hello viewer")
        deadline = time.monotonic() + 2.0
        received = bytearray()
        viewer.settimeout(2.0)
        while time.monotonic() < deadline and len(received) < 12:
            chunk = viewer.recv(64)
            if not chunk:
                break
            received.extend(chunk)
        assert bytes(received) == b"hello viewer"
        # Now reverse direction.
        viewer.sendall(b"reply from viewer")
        host.settimeout(2.0)
        recv2 = bytearray()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and len(recv2) < 17:
            chunk = host.recv(64)
            if not chunk:
                break
            recv2.extend(chunk)
        assert bytes(recv2) == b"reply from viewer"
    finally:
        for s in (host, viewer):
            try:
                s.close()
            except OSError:
                pass


def test_relay_only_pairs_matching_session_ids(relay):
    host = _connect(relay.port)
    viewer = _connect(relay.port)
    host.sendall(encode_handshake("host", b"A" * 32))
    viewer.sendall(encode_handshake("viewer", b"B" * 32))
    # The peers should NOT exchange data because the IDs differ.
    try:
        host.sendall(b"this should not reach the viewer")
        viewer.settimeout(0.5)
        got = b""
        try:
            got = viewer.recv(64)
        except (socket.timeout, TimeoutError, BlockingIOError):
            pass
        assert got == b""
    finally:
        for s in (host, viewer):
            try:
                s.close()
            except OSError:
                pass


def test_relay_rejects_role_collision(relay):
    """Two hosts (or two viewers) on the same session must not pair."""
    session_id = b"X" * 32
    first = _connect(relay.port)
    second = _connect(relay.port)
    first.sendall(encode_handshake("host", session_id))
    second.sendall(encode_handshake("host", session_id))
    time.sleep(0.3)
    # The second arrival is dropped by the relay; sending should fail
    # OR the socket should be at EOF.
    second.settimeout(0.5)
    got = b""
    try:
        got = second.recv(16)
    except (socket.timeout, TimeoutError, BlockingIOError, ConnectionResetError):
        pass
    assert got == b""
    for s in (first, second):
        try:
            s.close()
        except OSError:
            pass


def test_encode_handshake_validation():
    with pytest.raises(RelayError):
        encode_handshake("unknown", b"S" * 32)
    with pytest.raises(RelayError):
        encode_handshake("host", b"too-short")


def test_relay_stops_cleanly():
    server = RelayServer(bind="127.0.0.1", port=0)
    server.start()
    assert server.is_running
    server.stop(timeout=1.0)
    assert not server.is_running
