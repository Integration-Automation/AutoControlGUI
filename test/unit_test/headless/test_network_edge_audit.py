"""Regression tests for the USB/IP, TLS-key, signaling and relay defects of the 2026-09-23 audit.

A USB/IP client that imported one device could send URBs to any other the
backend had enumerated. TLS private keys were written under the umask before a
chmod, and in place. The signaling server compared its secret with ``!=`` and
kept any number of sessions. The relay never dropped a parked peer that had
gone, so a full pending table stayed full.
"""
import os
import socket
import struct
import sys
import time

import pytest

from je_auto_control.utils.json_store.json_store import atomic_write_bytes
from je_auto_control.utils.remote_desktop.relay import RelayServer, encode_handshake
from je_auto_control.utils.usbip import (
    OP_REQ_IMPORT, PROTOCOL_VERSION, USBIP_CMD_SUBMIT, FakeUrbBackend, UrbResponse, UsbIpServer,
)
from je_auto_control.utils.usbip.protocol import UsbIpDevice, UsbIpInterface


# --- USB/IP -------------------------------------------------------------------

def _device(busid, devnum):
    return UsbIpDevice(
        path=f"/sys/devices/{busid}", busid=busid, busnum=1, devnum=devnum, speed=3,
        vendor_id=0x046D, product_id=0xC52B, bcd_device=0x0200,
        device_class=0, device_subclass=0, device_protocol=0,
        configuration_value=1, num_configurations=1, num_interfaces=1,
        interfaces=[UsbIpInterface(3, 0, 0)])


def _recv(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("closed")
        data += chunk
    return data


def test_an_urb_for_a_device_that_was_not_imported_is_refused():
    backend = FakeUrbBackend(devices=[_device("1-1", 1), _device("1-2", 2)])
    backend.script_urb(devid=0x10002, direction=1, ep=1,
                       response=UrbResponse(status=0, actual_length=4, data=b"SECR"))
    server = UsbIpServer(backend, host="127.0.0.1", port=0)
    server.start()
    try:
        sock = socket.create_connection(("127.0.0.1", server.port), timeout=5)
        sock.sendall(struct.pack("!HHI", PROTOCOL_VERSION, OP_REQ_IMPORT, 0)
                     + b"1-1".ljust(32, b"\x00"))
        _recv(sock, 8 + 312)
        sock.sendall(struct.pack("!IIIII", USBIP_CMD_SUBMIT, 5, 0x10002, 1, 1)
                     + struct.pack("!IIiII8s", 0, 4, 0, 0, 0, b"\x00" * 8))
        header, body = _recv(sock, 20), _recv(sock, 28)
        status = struct.unpack("!i", body[:4])[0]
        assert status == -19, (header, body)
        assert backend.received == [], "the other device must not be reached"
        sock.close()
    finally:
        server.stop()


# --- TLS key file -------------------------------------------------------------

def test_key_bytes_are_written_exactly_and_privately(tmp_path):
    target = tmp_path / "key.pem"
    pem = b"line one\nline two\r\nline three\n"  # mixed endings must survive as-is
    atomic_write_bytes(target, pem)
    assert target.read_bytes() == pem, "no newline translation"
    if sys.platform != "win32":
        assert (os.stat(target).st_mode & 0o777) == 0o600


def test_saving_a_key_goes_through_the_atomic_writer(tmp_path, monkeypatch):
    keys = pytest.importorskip("je_auto_control.utils.tls_acme.keys", exc_type=ImportError)
    written = []
    monkeypatch.setattr(keys, "atomic_write_bytes", lambda path, data: written.append(path))
    material = keys.KeyMaterial(private_key=keys._generate_key(1024))
    material.save_pem(tmp_path / "k.pem")
    assert written == [tmp_path / "k.pem"]


# --- signaling server ---------------------------------------------------------

def test_the_signaling_store_caps_live_sessions(monkeypatch):
    signaling = pytest.importorskip("je_auto_control.utils.remote_desktop.signaling_server", exc_type=ImportError)
    monkeypatch.setattr(signaling, "_MAX_SESSIONS", 2)
    store = signaling._SessionStore()
    assert store.upsert_offer("a", "sdp") and store.upsert_offer("b", "sdp")
    assert store.upsert_offer("c", "sdp") is False
    assert store.upsert_offer("a", "new sdp"), "an existing session can still be updated"


def test_the_signaling_secret_is_checked(monkeypatch):
    signaling = pytest.importorskip("je_auto_control.utils.remote_desktop.signaling_server", exc_type=ImportError)
    testclient = pytest.importorskip("fastapi.testclient")
    client = testclient.TestClient(signaling.create_app(shared_secret="s3cret", serve_web_viewer=False))
    offer = {"sdp": "v=0"}
    assert client.post("/sessions/h1/offer", json=offer,
                       headers={"X-Signaling-Secret": "wrong"}).status_code == 401
    assert client.post("/sessions/h1/offer", json=offer).status_code == 401
    assert client.post("/sessions/h1/offer", json=offer,
                       headers={"X-Signaling-Secret": "s3cret"}).status_code == 200


# --- relay --------------------------------------------------------------------

def test_a_departed_parked_peer_frees_its_slot():
    relay = RelayServer(bind="127.0.0.1", port=0, max_pending_sessions=1)
    relay.start()
    try:
        gone = socket.create_connection(("127.0.0.1", relay.port), timeout=5)
        gone.sendall(encode_handshake("host", b"A" * 32))
        time.sleep(0.2)
        gone.close()
        time.sleep(0.2)
        host = socket.create_connection(("127.0.0.1", relay.port), timeout=5)
        host.sendall(encode_handshake("host", b"B" * 32))
        time.sleep(0.2)
        viewer = socket.create_connection(("127.0.0.1", relay.port), timeout=5)
        viewer.sendall(encode_handshake("viewer", b"B" * 32))
        host.sendall(b"ping")
        viewer.settimeout(3)
        assert _recv(viewer, 4) == b"ping"
        host.close()
        viewer.close()
    finally:
        relay.stop()
