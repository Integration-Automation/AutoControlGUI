"""USB/IP wire-format packers + unpackers.

References:
- https://www.kernel.org/doc/html/latest/usb/usbip_protocol.html
- linux/drivers/usb/usbip/usbip_common.h

Numbers are network byte order (big-endian) for OP_* headers and for
USBIP_CMD_*/USBIP_RET_* alike. Fixed-width strings (``path``, ``busid``)
are null-padded to their declared size.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


PROTOCOL_VERSION = 0x0111  # kernel constant; stable since 2010

# Operation codes (OP_REQ_*/OP_REP_*): "request" bit 0x8000 is set in
# the high half on requests and cleared on responses.
OP_REQ_DEVLIST = 0x8005
OP_REP_DEVLIST = 0x0005
OP_REQ_IMPORT = 0x8003
OP_REP_IMPORT = 0x0003

# URB-mode commands carried after a successful OP_REQ_IMPORT.
USBIP_CMD_SUBMIT = 0x00000001
USBIP_CMD_UNLINK = 0x00000002
USBIP_RET_SUBMIT = 0x00000003
USBIP_RET_UNLINK = 0x00000004

_OP_HEADER_FMT = "!HHI"  # version, command, status
_OP_HEADER_SIZE = struct.calcsize(_OP_HEADER_FMT)

# Device descriptor on the wire — 312 bytes when no interfaces follow.
# Layout (kernel ``usbip_usb_device``):
#   char path[256]; char busid[32];
#   uint32 busnum; uint32 devnum; uint32 speed;
#   uint16 idVendor; uint16 idProduct; uint16 bcdDevice;
#   uint8 bDeviceClass; uint8 bDeviceSubClass; uint8 bDeviceProtocol;
#   uint8 bConfigurationValue; uint8 bNumConfigurations;
#   uint8 bNumInterfaces;
_DEV_FMT = "!256s32sIII HHH BBB BBB"
_DEV_FMT_CLEAN = _DEV_FMT.replace(" ", "")
_DEV_SIZE = struct.calcsize(_DEV_FMT_CLEAN)

# Interface descriptor (4 bytes each).
_INTF_FMT = "!BBBB"
_INTF_SIZE = struct.calcsize(_INTF_FMT)

# CMD_SUBMIT header — 48 bytes, follows the URB framing header (16 bytes).
_URB_HEADER_FMT = "!IIIII"  # command, seqnum, devid, direction, ep
_URB_HEADER_SIZE = struct.calcsize(_URB_HEADER_FMT)
# Field order: transfer_flags, transfer_buffer_length, start_frame,
# number_of_packets, interval, setup[8]
_CMD_SUBMIT_FMT = "!IIiII8s"
_CMD_SUBMIT_SIZE = struct.calcsize(_CMD_SUBMIT_FMT)
_RET_SUBMIT_FMT = "!iIiII8s"  # status (__s32, signed), actual_length,
                              # start_frame, number_of_packets, error_count,
                              # setup[8]
_RET_SUBMIT_SIZE = struct.calcsize(_RET_SUBMIT_FMT)
# RET_UNLINK body: __s32 status + padding to fill the 28-byte body union.
_RET_UNLINK_FMT = "!i24x"
_RET_UNLINK_SIZE = struct.calcsize(_RET_UNLINK_FMT)


class UsbIpError(ValueError):
    """Raised when the wire bytes don't match the expected layout."""


@dataclass
class UsbIpInterface:
    """One interface descriptor exposed by a device.

    Field names follow the USB 2.0 spec; renaming them to snake_case
    would diverge from every USB tooling reader.
    """
    bInterfaceClass: int  # NOSONAR python:S116  # reason: USB 2.0 spec name
    bInterfaceSubClass: int  # NOSONAR python:S116  # reason: USB 2.0 spec name
    bInterfaceProtocol: int  # NOSONAR python:S116  # reason: USB 2.0 spec name


@dataclass
class UsbIpDevice:
    """Exportable USB device. Used by OP_REP_DEVLIST and OP_REP_IMPORT."""
    path: str
    busid: str
    busnum: int
    devnum: int
    speed: int
    vendor_id: int
    product_id: int
    bcd_device: int
    device_class: int
    device_subclass: int
    device_protocol: int
    configuration_value: int
    num_configurations: int
    num_interfaces: int
    interfaces: List[UsbIpInterface] = field(default_factory=list)

    def encode(self) -> bytes:
        return struct.pack(
            _DEV_FMT_CLEAN,
            self.path.encode("ascii")[:256].ljust(256, b"\x00"),
            self.busid.encode("ascii")[:32].ljust(32, b"\x00"),
            self.busnum, self.devnum, self.speed,
            self.vendor_id, self.product_id, self.bcd_device,
            self.device_class, self.device_subclass, self.device_protocol,
            self.configuration_value, self.num_configurations,
            self.num_interfaces,
        )

    def encode_interfaces(self) -> bytes:
        return b"".join(
            struct.pack(
                _INTF_FMT, i.bInterfaceClass, i.bInterfaceSubClass,
                i.bInterfaceProtocol, 0,  # padding
            )
            for i in self.interfaces
        )


# --- OP request unpackers -------------------------------------------

@dataclass
class OpRequest:
    """Parsed OP_REQ_* header. ``command`` distinguishes devlist / import."""
    version: int
    command: int
    status: int
    busid: Optional[str] = None  # only set for OP_REQ_IMPORT


def decode_op_request(raw: bytes) -> OpRequest:
    """Parse a fresh-from-the-socket OP_REQ_* header (+busid for import)."""
    if len(raw) < _OP_HEADER_SIZE:
        raise UsbIpError(
            f"OP header needs {_OP_HEADER_SIZE} bytes, got {len(raw)}",
        )
    version, command, status = struct.unpack(_OP_HEADER_FMT, raw[:_OP_HEADER_SIZE])
    if version != PROTOCOL_VERSION:
        raise UsbIpError(
            f"unsupported protocol version 0x{version:04x}",
        )
    request = OpRequest(version=version, command=command, status=status)
    if command == OP_REQ_IMPORT:
        # busid is a 32-byte null-padded ASCII string following the header.
        if len(raw) < _OP_HEADER_SIZE + 32:
            raise UsbIpError("OP_REQ_IMPORT missing busid")
        busid_bytes = raw[_OP_HEADER_SIZE:_OP_HEADER_SIZE + 32]
        # errors="replace": a non-ASCII byte in the busid must not raise
        # UnicodeDecodeError (a ValueError, outside the server's
        # (OSError, UsbIpError) catch) and kill the client worker thread.
        # A mangled busid simply won't match any device -> clean not-found.
        request.busid = busid_bytes.rstrip(b"\x00").decode("ascii", errors="replace")
    elif command != OP_REQ_DEVLIST:
        raise UsbIpError(f"unknown OP command 0x{command:04x}")
    return request


# --- OP response packers --------------------------------------------

def _op_header(command: int, status: int = 0) -> bytes:
    return struct.pack(_OP_HEADER_FMT, PROTOCOL_VERSION, command, status)


def encode_op_rep_devlist(devices: List[UsbIpDevice]) -> bytes:
    """Serialize the device list response."""
    body = _op_header(OP_REP_DEVLIST)
    body += struct.pack("!I", len(devices))
    for dev in devices:
        body += dev.encode()
        body += dev.encode_interfaces()
    return body


def encode_op_rep_import(device: Optional[UsbIpDevice]) -> bytes:
    """Serialize an OP_REP_IMPORT (status 0 = ok, 1 = reject)."""
    if device is None:
        return _op_header(OP_REP_IMPORT, status=1)
    return _op_header(OP_REP_IMPORT, status=0) + device.encode()


# --- URB request decoder --------------------------------------------

@dataclass
class CmdSubmit:
    """Decoded USBIP_CMD_SUBMIT — one URB to forward to the real device."""
    seqnum: int
    devid: int
    # direction: 0 = OUT (host→device), 1 = IN (device→host)
    direction: int
    ep: int
    transfer_flags: int
    transfer_buffer_length: int
    start_frame: int
    number_of_packets: int
    interval: int
    setup: bytes
    transfer_buffer: bytes


def decode_cmd_submit(raw: bytes) -> CmdSubmit:
    """Parse a full ``USBIP_CMD_SUBMIT`` message (header + body + buffer)."""
    expected = _URB_HEADER_SIZE + _CMD_SUBMIT_SIZE
    if len(raw) < expected:
        raise UsbIpError(
            f"CMD_SUBMIT needs at least {expected} bytes, got {len(raw)}",
        )
    cmd, seqnum, devid, direction, ep = struct.unpack(
        _URB_HEADER_FMT, raw[:_URB_HEADER_SIZE],
    )
    if cmd != USBIP_CMD_SUBMIT:
        raise UsbIpError(
            f"expected USBIP_CMD_SUBMIT, got 0x{cmd:08x}",
        )
    body = raw[_URB_HEADER_SIZE:_URB_HEADER_SIZE + _CMD_SUBMIT_SIZE]
    flags, tlen, sframe, npkt, interval, setup = struct.unpack(
        _CMD_SUBMIT_FMT, body,
    )
    # OUT transfers carry the bytes-to-send straight after the header.
    buffer = b""
    if direction == 0 and tlen > 0:
        start = _URB_HEADER_SIZE + _CMD_SUBMIT_SIZE
        buffer = raw[start:start + tlen]
        if len(buffer) != tlen:
            raise UsbIpError(
                f"CMD_SUBMIT advertised {tlen} bytes but only "
                f"{len(buffer)} available",
            )
    return CmdSubmit(
        seqnum=seqnum, devid=devid, direction=direction, ep=ep,
        transfer_flags=flags, transfer_buffer_length=tlen,
        start_frame=sframe, number_of_packets=npkt, interval=interval,
        setup=setup, transfer_buffer=buffer,
    )


def peek_transfer_length(header: bytes, body: bytes) -> Tuple[int, int]:
    """Return ``(direction, transfer_buffer_length)`` from a CMD_SUBMIT.

    Lets a server learn how many transfer-buffer bytes to read *before*
    calling :func:`decode_cmd_submit`, which requires the OUT buffer to
    already be present. ``header`` is the 20-byte URB header, ``body``
    the 28-byte CMD_SUBMIT body.
    """
    if len(header) < _URB_HEADER_SIZE:
        raise UsbIpError(
            f"CMD_SUBMIT header needs {_URB_HEADER_SIZE} bytes, "
            f"got {len(header)}",
        )
    if len(body) < _CMD_SUBMIT_SIZE:
        raise UsbIpError(
            f"CMD_SUBMIT body needs {_CMD_SUBMIT_SIZE} bytes, "
            f"got {len(body)}",
        )
    _cmd, _seqnum, _devid, direction, _ep = struct.unpack(
        _URB_HEADER_FMT, header[:_URB_HEADER_SIZE],
    )
    _flags, tlen, _sframe, _npkt, _interval, _setup = struct.unpack(
        _CMD_SUBMIT_FMT, body[:_CMD_SUBMIT_SIZE],
    )
    return direction, tlen


# --- URB response encoder ------------------------------------------

def encode_ret_submit(*, seqnum: int, devid: int, direction: int,
                      ep: int, status: int, actual_length: int,
                      data: bytes = b"",
                      start_frame: int = 0,
                      number_of_packets: int = 0,
                      error_count: int = 0,
                      setup: bytes = b"\x00" * 8) -> bytes:
    """Serialize a USBIP_RET_SUBMIT (URB completion).

    ``data`` is the IN-transfer payload — empty on OUT replies. Status
    is 0 on success, negative errno on failure (kernel convention).
    """
    if len(setup) != 8:
        raise UsbIpError("setup must be exactly 8 bytes")
    header = struct.pack(
        _URB_HEADER_FMT,
        USBIP_RET_SUBMIT, seqnum, devid, direction, ep,
    )
    body = struct.pack(
        _RET_SUBMIT_FMT,
        status, actual_length, start_frame, number_of_packets,
        error_count, setup,
    )
    return header + body + bytes(data)


def encode_ret_unlink(*, seqnum: int, devid: int, direction: int,
                      ep: int, status: int) -> bytes:
    """Serialize a USBIP_RET_UNLINK (URB-cancel completion).

    Sent in reply to USBIP_CMD_UNLINK. ``status`` is 0 when the target
    URB was found and unlinked, negative errno otherwise (kernel
    convention, so the field is signed). The body is a single ``__s32``
    status padded out to the 28-byte URB body union.
    """
    header = struct.pack(
        _URB_HEADER_FMT,
        USBIP_RET_UNLINK, seqnum, devid, direction, ep,
    )
    return header + struct.pack(_RET_UNLINK_FMT, status)


def parse_op_header(raw: bytes) -> Tuple[int, int, int]:
    """Lower-level helper: return ``(version, command, status)``."""
    if len(raw) < _OP_HEADER_SIZE:
        raise UsbIpError("OP header truncated")
    return struct.unpack(_OP_HEADER_FMT, raw[:_OP_HEADER_SIZE])


__all__ = [
    "PROTOCOL_VERSION",
    "OP_REQ_DEVLIST", "OP_REP_DEVLIST",
    "OP_REQ_IMPORT", "OP_REP_IMPORT",
    "USBIP_CMD_SUBMIT", "USBIP_CMD_UNLINK",
    "USBIP_RET_SUBMIT", "USBIP_RET_UNLINK",
    "UsbIpDevice", "UsbIpInterface", "UsbIpError", "OpRequest",
    "CmdSubmit",
    "decode_op_request", "decode_cmd_submit", "peek_transfer_length",
    "encode_op_rep_devlist", "encode_op_rep_import", "encode_ret_submit",
    "encode_ret_unlink", "parse_op_header",
]
