"""Retain Linux connected-process evidence only; no desktop session or input authority."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import re
import select
import socket
import struct
import sys
import threading

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


@dataclass(frozen=True)
class LinuxPeerIdentity:
    """Private connector identity; no active-desktop or current-writer claim."""

    pid: int
    uid: int
    gid: int
    birth: int
    user_namespace: str
    pid_namespace: str


def _peer_option() -> int:
    value = getattr(socket, 'SO_PEERPIDFD', None)
    if value is None:
        # Linux asm-generic ABI; other architectures can assign another number (e.g. SPARC).
        if platform.machine() not in {'x86_64', 'aarch64'}:
            raise AgentTaskError('Linux connected-peer pidfd ABI is unavailable')
        return 77
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise AgentTaskError('Linux connected-peer pidfd option is invalid')
    return value


def _bounded(path: str, maximum: int = 65536) -> str:
    with Path(path).open('rb') as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum or b'\0' in value:
        raise AgentTaskError('Linux connected-peer metadata exceeds its bound')
    return value.decode('utf-8', errors='strict')


def _field(text: str, name: str) -> str:
    values = [line.partition(':')[2].strip() for line in text.splitlines()
              if line.startswith(name + ':')]
    if len(values) != 1:
        raise AgentTaskError('Linux connected-peer metadata field is unavailable')
    return values[0]


def _decimal(value: str, minimum: int = 0) -> int:
    if not re.fullmatch('[0-9]{1,20}', value):
        raise AgentTaskError('Linux connected-peer metadata integer is invalid')
    number = int(value)
    if not minimum <= number <= (1 << 64) - 1:
        raise AgentTaskError('Linux connected-peer metadata integer is out of range')
    return number


def _live(descriptor: int) -> bool:
    poll = getattr(select, 'poll')()
    readable, hungup = getattr(select, 'POLLIN'), getattr(select, 'POLLHUP')
    errors = getattr(select, 'POLLERR') | getattr(select, 'POLLNVAL')
    poll.register(descriptor, readable | hungup | getattr(select, 'POLLERR'))
    events = poll.poll(0)
    if not events:
        return True
    if len(events) != 1 or events[0][0] != descriptor:
        raise AgentTaskError('Linux connected-peer liveness response is invalid')
    mask = events[0][1]
    if mask & errors or mask & ~(readable | hungup):
        raise AgentTaskError('Linux connected-peer liveness is unavailable')
    return False


def _namespaces(pid: int | str) -> tuple[str, str]:
    values = tuple(os.readlink(f'/proc/{pid}/ns/{name}') for name in ('user', 'pid'))
    if not all(re.fullmatch(name + r':\[[0-9]{1,20}\]', value)
               for name, value in zip(('user', 'pid'), values)):
        raise AgentTaskError('Linux connected-peer namespace identity is invalid')
    return values[0], values[1]


def _account(pid: int | str, uid: int, gid: int) -> None:
    status = _bounded(f'/proc/{pid}/status')
    for name, expected in (('Uid', uid), ('Gid', gid)):
        values = _field(status, name).split()
        if len(values) != 4 or any(_decimal(value) != expected for value in values):
            raise AgentTaskError('Linux connected-peer credentials differ from the current account')


def _birth(pid: int) -> int:
    raw = _bounded(f'/proc/{pid}/stat', 16384)
    end = raw.rfind(')')
    if not raw.startswith(f'{pid} (') or end < len(str(pid)) + 2:
        raise AgentTaskError('Linux connected-peer process stat identity is invalid')
    fields = raw[end + 1:].split()
    if len(fields) < 20:
        raise AgentTaskError('Linux connected-peer process creation time is unavailable')
    return _decimal(fields[19], 1)


def _snapshot(descriptor: int, pid: int, uid: int, gid: int) -> LinuxPeerIdentity:
    if not _live(descriptor):
        raise AgentTaskError('Linux connected-peer process has retired')
    actual_pid = _decimal(_field(_bounded(f'/proc/self/fdinfo/{descriptor}', 4096), 'Pid'), 1)
    if actual_pid != pid or (uid, gid) != (getattr(os, 'geteuid')(), getattr(os, 'getegid')()):
        raise AgentTaskError('Linux connected-peer process or account is different')
    _account('self', uid, gid)
    _account(pid, uid, gid)
    namespaces = _namespaces(pid)
    if namespaces != _namespaces('self'):
        raise AgentTaskError('Linux connected-peer namespace differs from the current process')
    result = LinuxPeerIdentity(pid, uid, gid, _birth(pid), *namespaces)
    if not _live(descriptor):
        raise AgentTaskError('Linux connected-peer process retired during its identity query')
    return result


class LinuxPeerProcess:
    """Own one query-only original-connector pidfd; never signal or reopen a PID."""

    def __init__(self, descriptor: int, identity: LinuxPeerIdentity) -> None:
        self._descriptor: int | None = descriptor
        self.identity = identity
        self._lock = threading.Lock()

    def alive(self) -> bool:
        """Check retained liveness and current identity without granting input."""
        with self._lock:
            if self._descriptor is None:
                return False
            try:
                if not _live(self._descriptor):
                    return False
                value = self.identity
                actual = _snapshot(self._descriptor, value.pid, value.uid, value.gid)
                if actual != value:
                    raise AgentTaskError('Linux connected-peer identity has changed')
                return True
            except AgentTaskError:
                raise
            except (OSError, UnicodeError, ValueError):
                raise AgentTaskError('Linux connected-peer identity cannot be verified') from None

    def close(self) -> None:
        """Close the owned descriptor once; never retry close after Linux has reused its number."""
        with self._lock:
            descriptor, self._descriptor = self._descriptor, None
            if descriptor is not None:
                _close_descriptor(descriptor)


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        raise AgentTaskError('Linux connected-peer descriptor retirement is unconfirmed') from None


def _stream_credentials(connection: socket.socket) -> tuple[int, int, int]:
    if not isinstance(connection, socket.socket) or connection.family != getattr(socket, 'AF_UNIX'):
        raise AgentTaskError('Linux connected-peer evidence requires a Unix stream socket')
    if connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM:
        raise AgentTaskError('Linux connected-peer evidence requires a Unix stream socket')
    raw = connection.getsockopt(socket.SOL_SOCKET, getattr(socket, 'SO_PEERCRED'),
                               struct.calcsize('iII'))
    pid, uid, gid = struct.unpack('iII', raw)
    if pid <= 0:
        raise AgentTaskError('Linux connected-peer credentials are unavailable')
    return pid, uid, gid


def retain_connected_peer(connection: socket.socket) -> LinuxPeerProcess:
    """Retain the original live same-account connector without a PID-open fallback."""
    if sys.platform != 'linux':
        raise AgentTaskError('Linux connected-peer evidence is unavailable on this platform')
    descriptor = None
    retained = False
    try:
        option = _peer_option()
        pid, uid, gid = _stream_credentials(connection)
        descriptor = connection.getsockopt(socket.SOL_SOCKET, option)
        os.set_inheritable(descriptor, False)
        if os.get_inheritable(descriptor):
            raise AgentTaskError('Linux connected-peer descriptor inheritance is unconfirmed')
        identity = _snapshot(descriptor, pid, uid, gid)
        peer = LinuxPeerProcess(descriptor, identity)
        retained = True
        return peer
    except AgentTaskError:
        raise
    except (OSError, UnicodeError, ValueError, struct.error):
        raise AgentTaskError('Linux connected-peer process evidence cannot be verified') from None
    finally:
        if descriptor is not None and not retained:
            _close_descriptor(descriptor)
