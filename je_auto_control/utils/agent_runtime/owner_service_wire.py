"""Exact-size frames of the Linux owner service: the client half of native_service.h."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Sequence

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

MAGIC = 0x41435356
VERSION = 1
CAPABILITY_BYTES = 32
ARGUMENT_BYTES = 1024
DATA_BYTES = 8192
REPLY_EOF = 1

OP_OPEN_TOP, OP_OPEN_CHILD, OP_START, OP_CLOSE, OP_WRITE, OP_READ, OP_OBSERVE = range(1, 8)
(STATUS_OK, STATUS_EXISTING, STATUS_REJECTED, STATUS_CLOSED, STATUS_CONFLICT, STATUS_CAPACITY,
 STATUS_UNAUTHENTICATED, STATUS_MALFORMED, STATUS_UNAVAILABLE) = range(9)
(REPORT_PENDING, REPORT_RETIRED, REPORT_STICKY_UNKNOWN, REPORT_UNKNOWN_TICKET,
 REPORT_SETTLED_WITHOUT_SCOPE) = range(5)

# Little-endian x86-64/aarch64 C layout, padding written out. native_service.h pins
# the same sizes and offsets with _Static_assert, so either side drifting fails a build.
_REQUEST = struct.Struct("<IHH16s16s16s32sII32s1024s32sI8192s4x")
_REPLY = struct.Struct("<IHHIiiI16s16sQ32sIIIIIi8192s")
REQUEST_SIZE = _REQUEST.size
REPLY_SIZE = _REPLY.size
REQUEST_OFFSETS = {"nonce": 8, "lease": 24, "request": 40, "parent": 56, "policy": 88, "capability": 96,
                   "arguments": 128, "ticket": 1152, "data_length": 1184, "data": 1188}
REPLY_OFFSETS = {"status": 8, "error": 12, "nonce": 24, "lease": 40, "lease_deadline_ns": 56, "ticket": 64,
                 "flags": 96, "data_length": 100, "report_kind": 104, "data": 120}

Identifier = tuple[int, int]
Ticket = tuple[Identifier, Identifier]
_ZERO: Identifier = (0, 0)
_NO_TICKET: Ticket = (_ZERO, _ZERO)


def _pack_id(value: Identifier) -> bytes:
    high, low = value
    return struct.pack("<QQ", high, low)


def _unpack_id(raw: bytes) -> Identifier:
    high, low = struct.unpack("<QQ", raw)
    return high, low


def _pack_ticket(ticket: Ticket) -> bytes:
    return _pack_id(ticket[0]) + _pack_id(ticket[1])


def _unpack_ticket(raw: bytes) -> Ticket:
    return _unpack_id(raw[:16]), _unpack_id(raw[16:])


def _arguments(values: Sequence[str]) -> bytes:
    encoded = b"".join(value.encode("utf-8") + b"\0" for value in values)
    if any("\0" in value for value in values) or len(encoded) >= ARGUMENT_BYTES:
        raise AgentTaskError("owner service arguments exceed their bound")
    return encoded


@dataclass(frozen=True)
class ServiceRequest:
    """One client frame; every field the service may read is explicit."""

    opcode: int
    nonce: Identifier
    lease: Identifier = _ZERO
    request: Identifier = _ZERO
    parent: Ticket = _NO_TICKET
    policy: int = 0
    arguments: tuple[str, ...] = ()
    capability: bytes = b""
    ticket: Ticket = _NO_TICKET
    data: bytes = b""

    def pack(self) -> bytes:
        """Encode exactly REQUEST_SIZE bytes, refusing anything the service would reject as malformed."""
        if len(self.data) > DATA_BYTES or len(self.capability) not in (0, CAPABILITY_BYTES):
            raise AgentTaskError("owner service frame exceeds its bound")
        return _REQUEST.pack(MAGIC, VERSION, self.opcode, _pack_id(self.nonce), _pack_id(self.lease),
                             _pack_id(self.request), _pack_ticket(self.parent), self.policy, len(self.arguments),
                             self.capability, _arguments(self.arguments), _pack_ticket(self.ticket),
                             len(self.data), self.data)


@dataclass(frozen=True)
class ServiceReply:
    """One decoded service frame."""

    opcode: int
    status: int
    error: tuple[int, int, int]
    nonce: Identifier
    lease: Identifier
    lease_deadline_ns: int
    ticket: Ticket
    flags: int
    report_kind: int
    start_kind: int
    wait: tuple[int, int]
    data_length: int  # OP_WRITE: bytes accepted. OP_READ: len(data).
    data: bytes


def unpack_reply(frame: bytes) -> ServiceReply:
    """Decode one reply, refusing a frame of the wrong size, magic, version or data length."""
    if len(frame) != REPLY_SIZE:
        raise AgentTaskError("owner service reply has the wrong size")
    (magic, version, opcode, status, kind, system_errno, operation, nonce, lease, deadline, ticket, flags,
     data_length, report_kind, start_kind, wait_kind, wait_value, data) = _REPLY.unpack(frame)
    if magic != MAGIC or version != VERSION or data_length > DATA_BYTES:
        raise AgentTaskError("owner service reply is malformed")
    return ServiceReply(opcode, status, (kind, system_errno, operation), _unpack_id(nonce), _unpack_id(lease),
                        deadline, _unpack_ticket(ticket), flags, report_kind, start_kind, (wait_kind, wait_value),
                        data_length, data[:data_length] if opcode == OP_READ else b"")
