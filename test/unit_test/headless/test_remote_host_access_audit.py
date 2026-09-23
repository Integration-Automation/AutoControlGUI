"""Remote-desktop host access defects from the 2026-09-24 audit.

A failed login only closed its handler, which the host never reaps, so a
couple of bad attempts filled ``max_clients`` for good; an approval callback
raising outside a narrow tuple did the same; a view-only viewer could still
write files and set the clipboard; and an allowlist whose every entry was a
typo admitted everyone. No real input or capture runs.
"""
import socket
import time

import pytest

from je_auto_control.utils.remote_desktop import host_access
from je_auto_control.utils.remote_desktop.auth import compute_response
from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.host_client import _ClientHandler
from je_auto_control.utils.remote_desktop.protocol import (
    MessageType, encode_frame, read_message,
)

TOKEN = "test-token-1"


def _host(**kwargs):
    kwargs.setdefault("frame_provider", lambda: b"\xff\xd8fake")
    kwargs.setdefault("input_dispatcher", lambda _message: None)
    kwargs.setdefault("enable_cursor_broadcast", False)
    host = RemoteDesktopHost(TOKEN, bind="127.0.0.1", port=0, host_id="123456789", **kwargs)
    host.start()
    return host


def _connect(host, token=TOKEN):
    sock = socket.create_connection(("127.0.0.1", host.port), timeout=5)
    kind, nonce = read_message(sock)
    assert kind is MessageType.AUTH_CHALLENGE
    sock.sendall(encode_frame(MessageType.AUTH_RESPONSE, compute_response(token, nonce)))
    kind, _payload = read_message(sock)
    return sock, kind


def _wait_until(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_failed_logins_do_not_use_up_the_client_slots():
    host = _host(max_clients=2)
    try:
        for _ in range(3):
            sock, kind = _connect(host, token="wrong-token")
            assert kind is MessageType.AUTH_FAIL
            sock.close()
        assert _wait_until(lambda: not host._clients or all(
            client._shutdown.is_set() for client in host._clients))
        sock, kind = _connect(host)
        assert kind is MessageType.AUTH_OK
        sock.close()
    finally:
        host.stop()


def test_an_approval_callback_that_raises_denies_and_frees_the_slot():
    host = _host(max_clients=1, on_pending_viewer=lambda _pending: {}["missing"])
    try:
        sock, kind = _connect(host)
        assert kind is MessageType.AUTH_FAIL
        sock.close()
        assert _wait_until(lambda: all(client._shutdown.is_set() for client in host._clients))
    finally:
        host.stop()


@pytest.mark.parametrize("kind", [MessageType.CLIPBOARD, MessageType.FILE_BEGIN])
def test_a_view_only_viewer_cannot_send_control_messages(kind, monkeypatch):
    handled = []
    handler = object.__new__(_ClientHandler)
    handler.permission = host_access.PERMISSION_VIEW_ONLY
    handler._address = ("127.0.0.1", 1)
    monkeypatch.setattr(_ClientHandler, "_handle_clipboard_payload",
                        lambda self, payload: handled.append("clipboard"))
    monkeypatch.setattr(_ClientHandler, "_handle_file_payload",
                        lambda self, msg_type, payload: handled.append("file"))
    handler._route_incoming(kind, b"{}")
    assert handled == []


def test_an_allowlist_of_typos_admits_nobody():
    compiled = host_access._compile_ip_allowlist(["192.168.1.300"])
    assert host_access._ip_in_allowlist(compiled, "8.8.8.8") is False
    assert host_access._compile_ip_allowlist(["", "  "]) is None
