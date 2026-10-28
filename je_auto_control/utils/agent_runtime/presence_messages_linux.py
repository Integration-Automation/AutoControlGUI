"""Authenticate each Linux packet and retire every received descriptor before delivery."""
from __future__ import annotations

from dataclasses import dataclass
import os
import socket
import struct

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import decode_frame
from je_auto_control.utils.agent_runtime.presence_peer_linux import (
    LinuxPeerProcess, _RetirementUnconfirmed, _snapshot, _socket_constant,
)


@dataclass(frozen=True)
class _AncillaryABI:
    credentials: int
    pidfd: int
    rights: int


def _ancillary_abi() -> _AncillaryABI:
    return _AncillaryABI(*(_socket_constant(name) for name in ('SCM_CREDENTIALS', 'SCM_PIDFD', 'SCM_RIGHTS')))


def _configure(connection: socket.socket, *, verify: bool = False) -> None:
    supported = hasattr(connection, 'recvmsg') and hasattr(socket, 'CMSG_SPACE')
    if not supported or not getattr(socket, 'MSG_CMSG_CLOEXEC', 0):
        raise AgentTaskError('Linux atomic descriptor inheritance protection is unavailable')
    _ancillary_abi()
    if connection.family != getattr(socket, 'AF_UNIX') or connection.getsockopt(
            socket.SOL_SOCKET, socket.SO_TYPE) != getattr(socket, 'SOCK_SEQPACKET', None):
        raise AgentTaskError('Linux channel requires Unix sequenced packets')
    for option in (_socket_constant('SO_PASSCRED'), _socket_constant('SO_PASSPIDFD')):
        if not verify:
            connection.setsockopt(socket.SOL_SOCKET, option, 1)
        if connection.getsockopt(socket.SOL_SOCKET, option) != 1:
            raise AgentTaskError('Linux per-message credential options are unavailable')
    connection.setblocking(False)
    if connection.get_inheritable():
        raise AgentTaskError('Linux channel descriptor must be noninheritable')


def _owned_descriptors(ancillary: list[tuple[int, int, bytes]], abi: _AncillaryABI) -> set[int]:
    result: set[int] = set()
    for level, kind, body in ancillary:
        if level == socket.SOL_SOCKET and kind in {abi.rights, abi.pidfd}:
            size = struct.calcsize('i')
            complete = body[:len(body) // size * size]
            result.update(item[0] for item in struct.iter_unpack('i', complete) if item[0] >= 0)
    return result


def _release(descriptors: set[int]) -> None:
    failed = False
    while descriptors:
        descriptor = descriptors.pop()
        try:
            os.close(descriptor)
        except OSError:
            failed = True
    if failed:
        raise _RetirementUnconfirmed('Linux packet descriptor retirement is unconfirmed')


def _sender(ancillary: list[tuple[int, int, bytes]], abi: _AncillaryABI) -> tuple[int, int, int, int]:
    expected = sorted(((socket.SOL_SOCKET, abi.credentials, struct.calcsize('iII')),
                       (socket.SOL_SOCKET, abi.pidfd, struct.calcsize('i'))))
    if sorted((level, kind, len(body)) for level, kind, body in ancillary) != expected:
        raise AgentTaskError('Linux packet credential control schema is invalid')
    controls = {kind: body for _level, kind, body in ancillary}
    pid, uid, gid = struct.unpack('iII', controls[abi.credentials])
    descriptor, = struct.unpack('i', controls[abi.pidfd])
    if pid <= 0 or descriptor < 0:
        raise AgentTaskError('Linux packet sender pidfd or credentials are unavailable')
    if os.get_inheritable(descriptor):
        raise AgentTaskError('Linux packet sender descriptor inheritance is unconfirmed')
    return descriptor, pid, uid, gid


def _receive(connection: socket.socket, peer: LinuxPeerProcess) -> dict:
    """Consume once under the channel's exclusive lease; EAGAIN preserves that lease."""
    abi = _ancillary_abi()
    truncation = getattr(socket, 'MSG_TRUNC') | getattr(socket, 'MSG_CTRUNC')
    control_bound = getattr(socket, 'CMSG_SPACE')(struct.calcsize('iII')) + getattr(socket, 'CMSG_SPACE')(4)
    raw, ancillary, flags, _address = getattr(connection, 'recvmsg')(
        4097, control_bound, getattr(socket, 'MSG_CMSG_CLOEXEC'))
    descriptors = _owned_descriptors(ancillary, abi)
    try:
        if not raw or len(raw) > 4096 or flags & truncation:
            raise AgentTaskError('Linux packet is empty, oversized or truncated')
        descriptor, pid, uid, gid = _sender(ancillary, abi)
        if _snapshot(descriptor, pid, uid, gid) != peer.identity or not peer.alive():
            raise AgentTaskError('Linux packet writer is not the live original peer')
        return decode_frame(raw)
    except AgentTaskError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise AgentTaskError('Linux packet writer evidence cannot be verified') from None
    finally:
        _release(descriptors)
