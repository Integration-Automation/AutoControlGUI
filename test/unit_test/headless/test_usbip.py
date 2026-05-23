"""Phase 8.2: USB/IP protocol + server tests."""
import socket
import struct
import threading

import pytest

from je_auto_control.utils.usbip import (
    FakeUrbBackend, OP_REP_DEVLIST, OP_REP_IMPORT, OP_REQ_DEVLIST,
    OP_REQ_IMPORT, PROTOCOL_VERSION, USBIP_CMD_SUBMIT, UrbRequest,
    UrbResponse, UsbIpError, UsbIpServer, decode_cmd_submit,
    decode_op_request, encode_op_rep_devlist, encode_op_rep_import,
    encode_ret_submit, default_port,
)
from je_auto_control.utils.usbip.protocol import (
    UsbIpDevice, UsbIpInterface,
)


def _device(busid: str = "1-1") -> UsbIpDevice:
    return UsbIpDevice(
        path=f"/sys/devices/pci0000:00/{busid}",
        busid=busid, busnum=1, devnum=2, speed=3,
        vendor_id=0x046D, product_id=0xC52B, bcd_device=0x0200,
        device_class=0, device_subclass=0, device_protocol=0,
        configuration_value=1, num_configurations=1, num_interfaces=1,
        interfaces=[UsbIpInterface(3, 0, 0)],  # HID class
    )


# --- protocol round-trip --------------------------------------------

def test_default_port_is_3240():
    assert default_port() == 3240


def test_decode_op_request_devlist():
    raw = struct.pack("!HHI", PROTOCOL_VERSION, OP_REQ_DEVLIST, 0)
    req = decode_op_request(raw)
    assert req.version == PROTOCOL_VERSION
    assert req.command == OP_REQ_DEVLIST
    assert req.busid is None


def test_decode_op_request_import_extracts_busid():
    header = struct.pack("!HHI", PROTOCOL_VERSION, OP_REQ_IMPORT, 0)
    busid = b"1-1".ljust(32, b"\x00")
    req = decode_op_request(header + busid)
    assert req.command == OP_REQ_IMPORT
    assert req.busid == "1-1"


def test_decode_op_request_rejects_wrong_version():
    raw = struct.pack("!HHI", 0x9999, OP_REQ_DEVLIST, 0)
    with pytest.raises(UsbIpError, match="protocol"):
        decode_op_request(raw)


def test_decode_op_request_rejects_short_header():
    with pytest.raises(UsbIpError):
        decode_op_request(b"\x01\x11")


def test_decode_op_request_import_without_busid_raises():
    raw = struct.pack("!HHI", PROTOCOL_VERSION, OP_REQ_IMPORT, 0)
    with pytest.raises(UsbIpError, match="busid"):
        decode_op_request(raw)


def test_encode_op_rep_devlist_includes_every_device():
    body = encode_op_rep_devlist([_device("1-1"), _device("1-2")])
    # Header: 8 bytes, then n_devices (4 bytes) = 0x00000002
    n_devices = struct.unpack("!I", body[8:12])[0]
    assert n_devices == 2
    # Each device record is 312 bytes + 4 bytes per interface.
    expected_size = 8 + 4 + 2 * (312 + 4)
    assert len(body) == expected_size


def test_encode_op_rep_import_status_0_when_device_found():
    body = encode_op_rep_import(_device("1-1"))
    _version, command, status = struct.unpack("!HHI", body[:8])
    assert command == OP_REP_IMPORT
    assert status == 0


def test_encode_op_rep_import_status_1_when_device_missing():
    body = encode_op_rep_import(None)
    _version, command, status = struct.unpack("!HHI", body[:8])
    assert command == OP_REP_IMPORT
    assert status == 1


# --- CMD_SUBMIT round trip -----------------------------------------

def _build_cmd_submit(*, direction: int = 1, ep: int = 0,
                     transfer_length: int = 0,
                     buffer: bytes = b"") -> bytes:
    header = struct.pack(
        "!IIIII",
        USBIP_CMD_SUBMIT, 99, 0x10002, direction, ep,
    )
    body = struct.pack(
        "!IIiII8s",
        0, transfer_length, 0, 0, 0, b"\x00" * 8,
    )
    return header + body + buffer


def test_decode_cmd_submit_in_direction():
    raw = _build_cmd_submit(direction=1, ep=1, transfer_length=64)
    cmd = decode_cmd_submit(raw)
    assert cmd.seqnum == 99
    assert cmd.direction == 1  # IN
    assert cmd.transfer_buffer == b""
    assert cmd.transfer_buffer_length == 64


def test_decode_cmd_submit_out_direction_attaches_payload():
    payload = b"hello-out"
    raw = _build_cmd_submit(
        direction=0, ep=2,
        transfer_length=len(payload), buffer=payload,
    )
    cmd = decode_cmd_submit(raw)
    assert cmd.direction == 0
    assert cmd.transfer_buffer == payload


def test_decode_cmd_submit_out_short_buffer_raises():
    raw = _build_cmd_submit(
        direction=0, ep=2, transfer_length=10, buffer=b"oops",
    )
    with pytest.raises(UsbIpError, match="advertised"):
        decode_cmd_submit(raw)


def test_encode_ret_submit_round_trip_with_payload():
    body = encode_ret_submit(
        seqnum=99, devid=1, direction=1, ep=1,
        status=0, actual_length=4, data=b"DATA",
    )
    # First 20 bytes = URB header; tail starts with 28-byte body then data.
    cmd = int.from_bytes(body[:4], "big")
    assert cmd == 0x3  # USBIP_RET_SUBMIT
    assert body[-4:] == b"DATA"


def test_encode_ret_submit_rejects_bad_setup():
    with pytest.raises(UsbIpError, match="setup"):
        encode_ret_submit(
            seqnum=1, devid=1, direction=1, ep=1,
            status=0, actual_length=0, setup=b"\x00",
        )


# --- end-to-end via the TCP server ---------------------------------

def _connect(port: int) -> socket.socket:
    return socket.create_connection(("127.0.0.1", port), timeout=5.0)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_server_returns_devlist():
    backend = FakeUrbBackend(devices=[_device("1-1"), _device("1-2")])
    server = UsbIpServer(backend, host="127.0.0.1", port=_free_port())
    server.start()
    try:
        sock = _connect(server.port)
        sock.sendall(struct.pack("!HHI", PROTOCOL_VERSION,
                                 OP_REQ_DEVLIST, 0))
        # Read OP header.
        header = _recv(sock, 8)
        version, command, status = struct.unpack("!HHI", header)
        assert version == PROTOCOL_VERSION
        assert command == OP_REP_DEVLIST
        assert status == 0
        n = struct.unpack("!I", _recv(sock, 4))[0]
        assert n == 2
        sock.close()
    finally:
        server.stop()


def test_server_import_unknown_busid_returns_status_1():
    backend = FakeUrbBackend(devices=[_device("1-1")])
    server = UsbIpServer(backend, host="127.0.0.1", port=_free_port())
    server.start()
    try:
        sock = _connect(server.port)
        header = struct.pack("!HHI", PROTOCOL_VERSION, OP_REQ_IMPORT, 0)
        sock.sendall(header + b"ghost".ljust(32, b"\x00"))
        reply = _recv(sock, 8)
        _v, _c, status = struct.unpack("!HHI", reply)
        assert status == 1
        sock.close()
    finally:
        server.stop()


def test_server_forwards_urb_to_backend():
    backend = FakeUrbBackend(devices=[_device("1-1")])
    backend.script_urb(devid=2, direction=1, ep=1,
                       response=UrbResponse(status=0, actual_length=4,
                                            data=b"PONG"))
    server = UsbIpServer(backend, host="127.0.0.1", port=_free_port())
    server.start()
    try:
        sock = _connect(server.port)
        header = struct.pack("!HHI", PROTOCOL_VERSION, OP_REQ_IMPORT, 0)
        sock.sendall(header + b"1-1".ljust(32, b"\x00"))
        _ = _recv(sock, 8)  # OP_REP_IMPORT header
        _ = _recv(sock, 312)  # device descriptor body
        # Send a CMD_SUBMIT for devid=2 direction=1 ep=1.
        cmd = struct.pack(
            "!IIIII",
            USBIP_CMD_SUBMIT, 77, 2, 1, 1,
        )
        body = struct.pack(
            "!IIiII8s",
            0, 4, 0, 0, 0, b"\x00" * 8,
        )
        sock.sendall(cmd + body)
        # Server should reply USBIP_RET_SUBMIT + 4 data bytes.
        _recv(sock, 20)  # URB header
        _recv(sock, 28)  # RET_SUBMIT body
        data = _recv(sock, 4)
        assert data == b"PONG"
        # And the backend recorded the call.
        assert len(backend.received) == 1
        recorded = backend.received[0]
        assert recorded.devid == 2
        assert recorded.direction == 1
        sock.close()
    finally:
        server.stop()


# --- helpers ---------------------------------------------------------

def _recv(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)
