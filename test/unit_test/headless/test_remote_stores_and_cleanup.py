"""Remote-desktop store and cleanup defects from the 2026-09-24 audit.

A damaged trust list, known_hosts or address book read as empty and the
next save erased every entry (and a non-UTF-8 address book raised from its
constructor); an upload interrupted by a disconnect left its ``.part`` file
and open handle behind; and ``RelayServer.stop()`` left paired sessions
forwarding.
"""
import socket
import threading
import time

import pytest

from je_auto_control.utils.remote_desktop.address_book import AddressBook
from je_auto_control.utils.remote_desktop.auth import compute_response
from je_auto_control.utils.remote_desktop.file_transfer import (
    FileReceiver, encode_begin, encode_chunk, new_transfer_id,
)
from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.protocol import (
    MessageType, encode_frame, read_message,
)
from je_auto_control.utils.remote_desktop.fingerprint import KnownHosts
from je_auto_control.utils.remote_desktop.relay import RelayServer, encode_handshake
from je_auto_control.utils.remote_desktop.trust_list import TrustList


def _damage(path):
    path.write_text(path.read_text(encoding="utf-8")[:-3], encoding="utf-8")
    return path.read_text(encoding="utf-8")


def _quarantined(directory, name):
    return [p for p in directory.iterdir() if p.name.startswith(f"{name}.corrupt-")]


def test_a_damaged_trust_list_is_kept_aside(tmp_path):
    path = tmp_path / "trusted_viewers.json"
    store = TrustList(path)
    store.add("viewer-a")
    store.add("viewer-b")
    damaged = _damage(path)
    TrustList(path).add("viewer-c")
    kept = _quarantined(tmp_path, path.name)
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == damaged


def test_a_damaged_known_hosts_is_kept_aside(tmp_path):
    path = tmp_path / "known_hosts.json"
    hosts = KnownHosts(path)
    hosts.remember("host-1", "a" * 64)
    _damage(path)
    KnownHosts(path).remember("host-2", "b" * 64)
    assert len(_quarantined(tmp_path, path.name)) == 1


@pytest.mark.parametrize("content", [b"\xff\xfe not utf-8", b'{"entries": 5}'])
def test_an_unusable_address_book_does_not_break_the_constructor(tmp_path, content):
    path = tmp_path / "address_book.json"
    path.write_bytes(content)
    book = AddressBook(path)
    assert book.list_entries() == []
    assert len(_quarantined(tmp_path, path.name)) == 1


def test_an_interrupted_upload_leaves_no_part_file(tmp_path):
    receiver = FileReceiver()
    target = tmp_path / "big.bin"
    transfer_id = new_transfer_id()
    receiver.handle_begin(encode_begin(transfer_id, str(target), 10))
    receiver.handle_chunk(encode_chunk(transfer_id, b"abc"))
    assert any(p.name.endswith(".part") for p in tmp_path.iterdir())
    receiver.abort_all("host stopped")
    assert list(tmp_path.iterdir()) == []
    assert receiver._active == {}


def test_stopping_the_relay_ends_paired_sessions():
    relay = RelayServer()
    relay.start()
    session = b"s" * 32
    host = socket.create_connection(("127.0.0.1", relay.port), timeout=5)
    viewer = socket.create_connection(("127.0.0.1", relay.port), timeout=5)
    try:
        host.sendall(encode_handshake("host", session))
        time.sleep(0.2)
        viewer.sendall(encode_handshake("viewer", session))
        time.sleep(0.3)
        relay.stop()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(
                thread.name in ("relay-h2v", "relay-v2h") for thread in threading.enumerate()):
            time.sleep(0.05)
        assert not any(thread.name in ("relay-h2v", "relay-v2h")
                       for thread in threading.enumerate())
    finally:
        host.close()
        viewer.close()


def test_a_viewer_disconnecting_mid_upload_leaves_no_part_file(tmp_path):
    host = RemoteDesktopHost("test-token-1", bind="127.0.0.1", port=0, host_id="123456789",
                             frame_provider=lambda: b"fake-jpeg",
                             input_dispatcher=lambda _message: None,
                             enable_cursor_broadcast=False)
    host.start()
    try:
        sock = socket.create_connection(("127.0.0.1", host.port), timeout=5)
        _kind, nonce = read_message(sock)
        sock.sendall(encode_frame(MessageType.AUTH_RESPONSE, compute_response("test-token-1", nonce)))
        assert read_message(sock)[0] is MessageType.AUTH_OK
        transfer_id = new_transfer_id()
        sock.sendall(encode_frame(MessageType.FILE_BEGIN,
                                  encode_begin(transfer_id, str(tmp_path / "big.bin"), 10)))
        sock.sendall(encode_frame(MessageType.FILE_CHUNK, encode_chunk(transfer_id, b"abc")))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not list(tmp_path.iterdir()):
            time.sleep(0.05)
        sock.close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and list(tmp_path.iterdir()):
            time.sleep(0.05)
        assert list(tmp_path.iterdir()) == []
    finally:
        host.stop()
