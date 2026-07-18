"""Audit round 3 regressions for the USB/IP server + protocol.

Covers:
* Finding 6 — an OUT CMD_SUBMIT carrying a payload must be decoded in two
  phases (peek length, read buffer, decode) so it is forwarded instead of
  dropping the connection; oversized transfers are rejected before allocating.
* Finding 7 — RET_SUBMIT status is a signed __s32: a negative errno must encode
  without raising struct.error (which used to kill the worker thread).
* Finding 8 — CMD_UNLINK must be answered with RET_UNLINK (0x4), not
  RET_SUBMIT (0x3).
"""
import socket
import struct

import pytest

from je_auto_control.utils.usbip import (
    FakeUrbBackend, PROTOCOL_VERSION, OP_REQ_IMPORT, USBIP_CMD_SUBMIT,
    USBIP_CMD_UNLINK, USBIP_RET_SUBMIT, USBIP_RET_UNLINK, UrbResponse,
    UsbIpError, UsbIpServer, encode_ret_submit,
)
from je_auto_control.utils.usbip.protocol import (
    UsbIpDevice, UsbIpInterface, peek_transfer_length,
)
from je_auto_control.utils.usbip.server import _MAX_TRANSFER_BUFFER_BYTES


def _device(busid: str = "1-1") -> UsbIpDevice:
    return UsbIpDevice(
        path=f"/sys/devices/pci0000:00/{busid}",
        busid=busid, busnum=1, devnum=2, speed=3,
        vendor_id=0x046D, product_id=0xC52B, bcd_device=0x0200,
        device_class=0, device_subclass=0, device_protocol=0,
        configuration_value=1, num_configurations=1, num_interfaces=1,
        interfaces=[UsbIpInterface(3, 0, 0)],
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _recv(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def _import_device(sock: socket.socket, busid: str = "1-1") -> None:
    header = struct.pack("!HHI", PROTOCOL_VERSION, OP_REQ_IMPORT, 0)
    sock.sendall(header + busid.encode("ascii").ljust(32, b"\x00"))
    _recv(sock, 8)    # OP_REP_IMPORT header
    _recv(sock, 312)  # device descriptor body


def _cmd_submit(*, seqnum: int, devid: int, direction: int, ep: int,
                transfer_length: int, buffer: bytes = b"") -> bytes:
    header = struct.pack("!IIIII", USBIP_CMD_SUBMIT, seqnum, devid,
                         direction, ep)
    body = struct.pack("!IIiII8s", 0, transfer_length, 0, 0, 0, b"\x00" * 8)
    return header + body + buffer


# --- Finding 6 -------------------------------------------------------

def test_peek_transfer_length_returns_direction_and_length():
    header = struct.pack("!IIIII", USBIP_CMD_SUBMIT, 1, 2, 0, 3)
    body = struct.pack("!IIiII8s", 0, 128, 0, 0, 0, b"\x00" * 8)
    direction, tlen = peek_transfer_length(header, body)
    assert direction == 0
    assert tlen == 128


def test_out_cmd_submit_with_payload_is_forwarded():
    backend = FakeUrbBackend(devices=[_device("1-1")])
    backend.script_urb(devid=2, direction=0, ep=2,
                       response=UrbResponse(status=0, actual_length=0))
    server = UsbIpServer(backend, host="127.0.0.1", port=_free_port())
    server.start()
    try:
        sock = socket.create_connection(("127.0.0.1", server.port),
                                        timeout=5.0)
        _import_device(sock)
        payload = b"hello-out-transfer"
        sock.sendall(_cmd_submit(seqnum=42, devid=2, direction=0, ep=2,
                                 transfer_length=len(payload),
                                 buffer=payload))
        # Pre-fix the first decode raised UsbIpError and the connection was
        # dropped before the URB reached the backend.
        header = _recv(sock, 20)
        assert len(header) == 20
        assert int.from_bytes(header[:4], "big") == USBIP_RET_SUBMIT
        _recv(sock, 28)  # RET_SUBMIT body
        assert len(backend.received) == 1
        assert backend.received[0].transfer_buffer == payload
        sock.close()
    finally:
        server.stop()


def test_oversized_transfer_buffer_is_rejected():
    backend = FakeUrbBackend(devices=[_device("1-1")])
    server = UsbIpServer(backend, host="127.0.0.1", port=_free_port())
    server.start()
    try:
        sock = socket.create_connection(("127.0.0.1", server.port),
                                        timeout=5.0)
        _import_device(sock)
        huge = _MAX_TRANSFER_BUFFER_BYTES + 1
        # Advertise a huge OUT transfer but send no buffer: the server must
        # reject on the length check (dropping the connection) rather than
        # try to allocate/read it.
        sock.sendall(_cmd_submit(seqnum=7, devid=2, direction=0, ep=1,
                                 transfer_length=huge))
        assert _recv(sock, 1) == b""  # connection closed, no huge alloc
        assert backend.received == []
        sock.close()
    finally:
        server.stop()


# --- Finding 7 -------------------------------------------------------

def test_ret_submit_encodes_negative_errno_status():
    # Pre-fix this raised struct.error (status packed as unsigned 'I').
    body = encode_ret_submit(seqnum=1, devid=1, direction=1, ep=1,
                             status=-19, actual_length=0)
    status = struct.unpack("!i", body[20:24])[0]
    assert status == -19


def test_server_replies_negative_status_without_killing_worker():
    # FakeUrbBackend returns status=-19 (-ENODEV) for any unscripted URB.
    backend = FakeUrbBackend(devices=[_device("1-1")])
    server = UsbIpServer(backend, host="127.0.0.1", port=_free_port())
    server.start()
    try:
        sock = socket.create_connection(("127.0.0.1", server.port),
                                        timeout=5.0)
        _import_device(sock)
        sock.sendall(_cmd_submit(seqnum=11, devid=2, direction=1, ep=5,
                                 transfer_length=0))
        header = _recv(sock, 20)
        body = _recv(sock, 28)
        # Pre-fix the worker died on struct.error and these reads got EOF.
        assert len(header) == 20 and len(body) == 28
        assert int.from_bytes(header[:4], "big") == USBIP_RET_SUBMIT
        assert struct.unpack("!i", body[:4])[0] == -19
        sock.close()
    finally:
        server.stop()


# --- Finding 8 -------------------------------------------------------

def test_cmd_unlink_replies_ret_unlink():
    backend = FakeUrbBackend(devices=[_device("1-1")])
    server = UsbIpServer(backend, host="127.0.0.1", port=_free_port())
    server.start()
    try:
        sock = socket.create_connection(("127.0.0.1", server.port),
                                        timeout=5.0)
        _import_device(sock)
        unlink = struct.pack("!IIIII", USBIP_CMD_UNLINK, 55, 2, 0, 0)
        sock.sendall(unlink + b"\x00" * 28)
        header = _recv(sock, 20)
        assert len(header) == 20
        command = int.from_bytes(header[:4], "big")
        # Pre-fix this was USBIP_RET_SUBMIT (0x3); the client's URB-cancel
        # never completed.
        assert command == USBIP_RET_UNLINK
        assert int.from_bytes(header[4:8], "big") == 55  # echoed seqnum
        body = _recv(sock, 28)
        assert len(body) == 28
        assert struct.unpack("!i", body[:4])[0] == 0  # status
        sock.close()
    finally:
        server.stop()


def test_peek_transfer_length_rejects_short_input():
    with pytest.raises(UsbIpError):
        peek_transfer_length(b"\x00" * 4, b"\x00" * 28)
