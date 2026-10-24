"""Owned smart-socket servers test managed ADB without a CLI, daemon or real device."""
import socket
import socketserver
import struct
import subprocess
import threading
import traceback
from concurrent.futures import CancelledError
from contextlib import contextmanager

import pytest

from je_auto_control.utils.agent_runtime.android_transport import ManagedAdbServer
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.rbac.authorization import AuthorizationError


def read_exact(connection, size):
    data = bytearray()
    while len(data) < size:
        part = connection.recv(size - len(data))
        assert part, "client closed before the fixture request finished"
        data.extend(part)
    return bytes(data)


def request(connection):
    return read_exact(connection, int(read_exact(connection, 4), 16))


def packet(kind, payload):
    return struct.pack("<BI", kind, len(payload)) + payload


@contextmanager
def server(dialogue):
    failures, connections = [], []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            connections.append(True)
            try:
                dialogue(self.request)
            except (ConnectionResetError, BrokenPipeError):
                pass
            except Exception as error:  # reason: report owned fixture thread failures to its test
                failures.append(error)

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    owned = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: owned.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield ManagedAdbServer("127.0.0.1", owned.server_address[1]), connections
    finally:
        owned.shutdown()
        owned.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert not failures


def accept_shell(connection, *, transport=42, command=b"input tap 10 20"):
    assert request(connection) == f"host:transport-id:{transport}".encode("ascii")
    connection.sendall(b"OKAY")
    assert request(connection) == b"shell,v2,raw:" + command
    connection.sendall(b"OKAY")
    assert read_exact(connection, 5) == packet(4, b"")


def test_device_query_reuses_legacy_parser_without_spawning_cli(monkeypatch):
    def reject_cli(*_args, **_kwargs):
        raise AssertionError("a managed transport must not start an ADB client or daemon")

    monkeypatch.setattr(subprocess, "run", reject_cli)
    content = (b"pixel device product:sample model:Pixel transport_id:42\n"
               b"locked unauthorized transport_id:9\nno-access no permissions (check group)\n")

    def dialogue(connection):
        assert request(connection) == b"host:devices-l"
        connection.sendall(b"OKAY" + f"{len(content):04x}".encode("ascii") + content)

    with server(dialogue) as (client, connections):
        devices = client.list_devices()
    assert len(connections) == 1
    assert [(row.serial, row.state) for row in devices] == [
        ("pixel", "device"), ("locked", "unauthorized"), ("no-access", "no permissions")]
    assert devices[0].transport_id == "42"
    assert devices[0].model == "Pixel"


def test_shell_v2_accepts_fragmented_binary_stdout_stderr_and_unsigned_exit():
    def dialogue(connection):
        accept_shell(connection)
        reply = packet(1, b"png\x00\xff") + packet(2, b"warning\n") + packet(1, b"tail") + packet(3, b"\xff")
        for byte in reply:
            connection.sendall(bytes([byte]))

    with server(dialogue) as (client, connections):
        result = client.shell(42, "input tap 10 20")
    assert result.stdout == b"png\x00\xfftail"
    assert result.stderr == b"warning\n"
    assert result.returncode == 255
    assert len(connections) == 1


@pytest.mark.parametrize("host,port", [
    ("localhost", 5037), ("192.0.2.1", 5037), ("0.0.0.0", 5037), ("::", 5037),
    ("127.0.0.1", True), ("127.0.0.1", 0), ("127.0.0.1", 65536),
    ("127.0.0.1", "5037"), (2130706433, 5037), ("::1%eth0", 5037),
])
def test_nonliteral_or_unreviewable_endpoints_fail_before_connection(host, port, monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: pytest.fail("must not connect"))
    with pytest.raises(AgentTaskError):
        ManagedAdbServer(host, port)


@pytest.mark.parametrize("transport,command,changes", [
    (True, "input tap 1 2", {}), (0, "input tap 1 2", {}), (-1, "input tap 1 2", {}),
    (2**64, "input tap 1 2", {}), ("42", "input tap 1 2", {}), (42, "", {}),
    (42, "x\0y", {}), (42, "\ud800", {}), (42, "x" * 8192, {}), (42, "字" * 3000, {}),
    (42, "read", {"limit": True}), (42, "read", {"limit": 1_000_001}),
    (42, "read", {"timeout": float("inf")}), (42, "read", {"timeout": float("nan")}),
    (42, "read", {"timeout": False}), (42, "read", {"timeout": 0}),
    (42, "read", {"timeout": 10**1000}),
])
def test_invalid_shell_bounds_never_open_a_connection(transport, command, changes, monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: pytest.fail("must not connect"))
    with pytest.raises(AgentTaskError):
        ManagedAdbServer("127.0.0.1", 5037).shell(transport, command, **changes)


def test_server_failure_message_cannot_publish_typed_secret():
    secret = b"private-value-supplied-to-input"

    def dialogue(connection):
        assert request(connection) == b"host:transport-id:42"
        connection.sendall(b"FAIL" + f"{len(secret):04x}".encode("ascii") + secret)

    with server(dialogue) as (client, connections):
        with pytest.raises(AgentTaskError) as caught:
            client.shell(42, "input text " + secret.decode())
    assert secret.decode() not in "".join(traceback.format_exception(caught.value))
    assert len(connections) == 1


@pytest.mark.parametrize("response", [
    b"NOPE", b"FAILzzzz", b"FAIL-001", b"OKAY0005ab", b"OKAY+001x", b"OKAY0x01x",
    b"OKAY0001xtrailing", b"", b"OK", b"FAIL0005x",
])
def test_bad_device_framing_is_never_treated_as_an_empty_device_list(response):
    def dialogue(connection):
        assert request(connection) == b"host:devices-l"
        connection.sendall(response)

    with server(dialogue) as (client, connections):
        with pytest.raises(AgentTaskError):
            client.list_devices()
    assert len(connections) == 1


@pytest.mark.parametrize("response", [
    b"", packet(1, b"result-with-no-exit"), packet(3, b""), packet(3, b"\0\0"),
    packet(3, b"\0") + packet(3, b"\0"), packet(3, b"\0") + packet(1, b"late"),
    packet(0, b"stdin-from-server"), packet(5, b"resize"), struct.pack("<BI", 1, 2**32 - 1),
    packet(1, b"1234") + packet(2, b"1234"), packet(255, b"unexpected"),
])
def test_partial_oversize_or_unclosed_shell_evidence_is_refused(response):
    def dialogue(connection):
        accept_shell(connection)
        connection.sendall(response)

    with server(dialogue) as (client, connections):
        with pytest.raises(AgentTaskError):
            client.shell(42, "input tap 10 20", limit=5)
    assert len(connections) == 1


def test_packet_count_is_bounded_even_for_zero_length_output():
    def dialogue(connection):
        accept_shell(connection)
        connection.sendall(packet(1, b"") * 4096 + packet(3, b"\0"))

    with server(dialogue) as (client, _connections):
        with pytest.raises(AgentTaskError, match="packet count"):
            client.shell(42, "input tap 10 20")


def test_disconnect_after_remote_dispatch_is_not_replayed():
    effects = []

    def dialogue(connection):
        accept_shell(connection)
        effects.append("remote-effect-applied-before-lost-exit")

    with server(dialogue) as (client, connections):
        with pytest.raises(AgentTaskError, match="before confirmed"):
            client.shell(42, "input tap 10 20")
    assert len(connections) == 1
    assert effects == ["remote-effect-applied-before-lost-exit"]


def test_missing_server_is_not_started_or_repaired_and_error_chain_is_redacted(monkeypatch):
    calls = []

    def fail_connect(*_args, **_kwargs):
        calls.append(True)
        raise OSError("untrusted diagnostic with private-value")

    monkeypatch.setattr(socket, "create_connection", fail_connect)
    with pytest.raises(AgentTaskError, match="server state was not changed") as caught:
        ManagedAdbServer("127.0.0.1", 5037).list_devices()
    assert calls == [True]
    assert "private-value" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("error_type", [CancelledError, AuthorizationError])
def test_read_control_failure_closes_connection_and_preserves_control_exception(error_type):
    entered, closed = threading.Event(), threading.Event()

    def dialogue(connection):
        accept_shell(connection)
        entered.set()
        assert connection.recv(1) == b""
        closed.set()

    def checkpoint():
        if entered.is_set():
            raise error_type("fixture control revoked")

    with server(dialogue) as (client, connections):
        with pytest.raises(error_type):
            client.shell(42, "input tap 10 20", check=checkpoint)
        assert closed.wait(timeout=1)
    assert len(connections) == 1


def test_stalled_shell_exhausts_deadline_without_assuming_success():
    release = threading.Event()

    def dialogue(connection):
        accept_shell(connection)
        release.wait(timeout=1)

    try:
        with server(dialogue) as (client, connections):
            with pytest.raises(AgentTaskError, match="deadline"):
                client.shell(42, "input tap 10 20", timeout=0.1)
            release.set()
        assert len(connections) == 1
    finally:
        release.set()
