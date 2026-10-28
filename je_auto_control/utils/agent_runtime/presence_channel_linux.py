"""Own authenticated Linux packet channels, bounded leases and protected listeners."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import math
from pathlib import Path
import select
import socket
import sys
import threading
import time
from typing import Generic, Iterator, TypeVar

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_endpoint_linux import LinuxEndpoint, _EndpointCheck, _EndpointFiles
from je_auto_control.utils.agent_runtime.presence_frames import encode_frame
from je_auto_control.utils.agent_runtime.presence_messages_linux import _configure, _receive
from je_auto_control.utils.agent_runtime.presence_peer_linux import (
    LinuxPeerProcess, _RetirementUnconfirmed, retain_connected_peer,
)


_R = TypeVar('_R', '_ChannelResources', '_ListenerResources')


@dataclass(frozen=True)
class _Open(Generic[_R]):
    resources: _R
    active: bool = False


@dataclass(frozen=True)
class _Retiring(Generic[_R]):
    resources: _R | None
    active: bool
    unconfirmed: bool = False


@dataclass(frozen=True)
class _Retired:
    unconfirmed: bool


def _deadline(timeout: float) -> float:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 1:
        raise AgentTaskError('Linux channel timeout must be positive and at most one second')
    if not math.isfinite(timeout):
        raise AgentTaskError('Linux channel timeout must be finite')
    return time.monotonic() + timeout


def _budget(deadline: float, cancel: threading.Event | None) -> float:
    if cancel is not None and cancel.is_set():
        raise AgentTaskError('Linux channel operation cancelled')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AgentTaskError('Linux channel operation timed out')
    return min(remaining, 0.025)


def _close_socket(connection: socket.socket) -> None:
    try:
        connection.close()
    except OSError:
        raise _RetirementUnconfirmed('Linux socket retirement is unconfirmed') from None


class _Owner(Generic[_R]):
    def __init__(self, resources: _R) -> None:
        self._condition = threading.Condition(threading.Lock())
        self._state: _Open[_R] | _Retiring[_R] | _Retired = _Open(resources)

    def _admit(self, deadline: float, cancel: threading.Event | None) -> _R:
        with self._condition:
            while isinstance(self._state, _Open):
                interval = _budget(deadline, cancel)
                if not self._state.active:
                    self._state = _Open(self._state.resources, True)
                    return self._state.resources
                self._condition.wait(interval)
            raise AgentTaskError('Linux channel has retired')

    def _revoke(self, *, unconfirmed: bool = False) -> None:
        with self._condition:
            if isinstance(self._state, _Open):
                self._state = _Retiring(self._state.resources, self._state.active, unconfirmed)
            elif isinstance(self._state, _Retiring) and unconfirmed:
                self._state = _Retiring(self._state.resources, self._state.active, True)
            self._condition.notify_all()

    def _retire_idle(self) -> None:
        with self._condition:
            state = self._state
            if not isinstance(state, _Retiring) or state.active or state.resources is None:
                return
            resources = state.resources
            self._state = _Retiring(None, False, state.unconfirmed)
        unconfirmed = True
        try:
            resources.close()
            unconfirmed = state.unconfirmed
        except (OSError, AgentTaskError):
            raise _RetirementUnconfirmed('Linux channel retirement is unconfirmed') from None
        finally:
            with self._condition:
                self._state = _Retired(unconfirmed)
                self._condition.notify_all()

    @contextmanager
    def operation(self, deadline: float, cancel: threading.Event | None) -> Iterator[_R]:
        """Admit one operation and commit delivery only while open and uncancelled."""
        admitted = False
        try:
            resources = self._admit(deadline, cancel)
            admitted = True
            yield resources
            self.check(deadline, cancel)
        except _RetirementUnconfirmed:
            self._revoke(unconfirmed=True)
            raise
        except (OSError, UnicodeError):
            self._revoke()
            raise AgentTaskError('Linux channel operation failed') from None
        except BaseException:
            self._revoke()
            raise
        finally:
            if admitted:
                self._release_lease()
            self._retire_idle()

    def _release_lease(self) -> None:
        with self._condition:
            if isinstance(self._state, _Open):
                self._state = _Open(self._state.resources)
            elif isinstance(self._state, _Retiring):
                self._state = _Retiring(self._state.resources, False, self._state.unconfirmed)
            self._condition.notify_all()

    def check(self, deadline: float, cancel: threading.Event | None) -> float:
        """Check logical admission without waiting on metadata or peer locks."""
        with self._condition:
            interval = _budget(deadline, cancel)
            if not isinstance(self._state, _Open):
                raise AgentTaskError('Linux channel has retired')
            return interval

    def ready(self, connection: socket.socket, deadline: float,
              cancel: threading.Event | None, *, write: bool = False) -> None:
        """Wait for socket readiness within the original operation deadline."""
        poll = getattr(select, 'poll')()
        event = getattr(select, 'POLLOUT') if write else getattr(select, 'POLLIN')
        poll.register(connection, event)
        while True:
            interval = self.check(deadline, cancel)
            try:
                events = poll.poll(max(1, math.ceil(interval * 1000)))
            except InterruptedError:
                continue
            self.check(deadline, cancel)
            if events:
                if events[0][1] & getattr(select, 'POLLNVAL'):
                    raise AgentTaskError('Linux channel descriptor is unavailable')
                return

    def close(self, timeout: float) -> None:
        """Choose one retirement owner without closing resources borrowed by active I/O."""
        deadline = _deadline(timeout)
        self._revoke()
        self._retire_idle()
        with self._condition:
            while not isinstance(self._state, _Retired):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _RetirementUnconfirmed('Linux channel retirement is unconfirmed; operation is still active')
                self._condition.wait(min(remaining, 0.025))
            if self._state.unconfirmed:
                raise _RetirementUnconfirmed('Linux channel retirement is unconfirmed')


@dataclass
class _ChannelResources:
    connection: socket.socket
    peer: LinuxPeerProcess

    def close(self) -> None:
        """Attempt socket and retained peer retirement even if one fails."""
        try:
            _close_socket(self.connection)
        finally:
            self.peer.close()


@dataclass
class _ListenerResources:
    connection: socket.socket
    files: _EndpointFiles

    def close(self) -> None:
        """Attempt listener and owned pathname retirement even if one fails."""
        try:
            _close_socket(self.connection)
        finally:
            self.files.close()


def _new_socket() -> socket.socket:
    if sys.platform != 'linux':
        raise AgentTaskError('Linux helper channels are unavailable on this platform')
    if not hasattr(socket, 'SOCK_SEQPACKET') or not hasattr(select, 'poll'):
        raise AgentTaskError('Linux sequenced-packet channel primitives are unavailable')
    connection = socket.socket(getattr(socket, 'AF_UNIX'), getattr(socket, 'SOCK_SEQPACKET'))
    try:
        _configure(connection)
        return connection
    except BaseException:
        _close_socket(connection)
        raise


def _capture(connection: socket.socket) -> LinuxChannel:
    peer = None
    try:
        _configure(connection, verify=True)
        peer = retain_connected_peer(connection)
        channel = object.__new__(LinuxChannel)
        # pylint: disable-next=protected-access  # reason: only this exact-socket factory installs ownership.
        channel._owner = _Owner(_ChannelResources(connection, peer))
        return channel
    except BaseException:
        try:
            _close_socket(connection)
        finally:
            if peer is not None:
                peer.close()
        raise


def _connect(connection: socket.socket, address: str, deadline: float, cancel: threading.Event | None) -> None:
    pending = {errno.EINPROGRESS, errno.EALREADY, errno.EINTR}
    while True:
        interval = _budget(deadline, cancel)
        result = connection.connect_ex(address)
        if result in {0, errno.EISCONN}:
            return
        if result == errno.EAGAIN:
            if cancel is not None:
                cancel.wait(interval)
            else:
                threading.Event().wait(interval)
            continue
        if result not in pending:
            raise AgentTaskError('Linux endpoint connection was refused')
        poll = getattr(select, 'poll')()
        poll.register(connection, getattr(select, 'POLLOUT'))
        poll.poll(max(1, math.ceil(interval * 1000)))
        _budget(deadline, cancel)
        error = connection.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if error and error not in pending:
            raise AgentTaskError('Linux endpoint connection failed')


class LinuxChannel:
    """One exact socket and original peer, with authenticated packet delivery.

    Close revokes delivery immediately. A stalled metadata query retains ownership
    until its finalizer runs; bounded close reports retirement unconfirmed meanwhile.
    This establishes ordinary kernel process identity, never physical input authority
    or protection against ptrace-equivalent, privileged or compromised-kernel actors.
    """

    _owner: _Owner[_ChannelResources]

    def __init__(self) -> None:
        raise AgentTaskError('Linux channels must be created by connect or listener accept')

    @classmethod
    def connect(cls, endpoint: LinuxEndpoint, *, timeout: float,
                cancel: threading.Event | None = None) -> LinuxChannel:
        """Connect to trusted immutable launch metadata and pin the actual listener."""
        deadline = _deadline(timeout)
        _budget(deadline, cancel)
        connection = None
        channel = None
        check = None
        try:
            connection = _new_socket()
            check = _EndpointCheck(endpoint)
            _connect(connection, check.address, deadline, cancel)
            owned, connection = connection, None
            channel = _capture(owned)
            check.verify()
            with channel._owner.operation(deadline, cancel) as resources:
                if resources.peer.identity != endpoint.listener_process or not resources.peer.alive():
                    raise AgentTaskError('Linux endpoint listener differs from the trusted launch identity')
            check.close()
            check = None
            result, channel = channel, None
            return result
        except (OSError, UnicodeError, NotImplementedError):
            raise AgentTaskError('Linux endpoint cannot be connected securely') from None
        finally:
            try:
                if check is not None:
                    check.close()
            finally:
                try:
                    if connection is not None:
                        _close_socket(connection)
                finally:
                    if channel is not None:
                        channel.close()

    def receive(self, *, timeout: float, cancel: threading.Event | None = None) -> dict:
        """Receive one finite JSON object from the still-live original writer."""
        deadline = _deadline(timeout)
        with self._owner.operation(deadline, cancel) as resources:
            while True:
                self._owner.ready(resources.connection, deadline, cancel)
                try:
                    return _receive(resources.connection, resources.peer)
                except (BlockingIOError, InterruptedError):
                    continue

    def send(self, frame: dict, *, timeout: float, cancel: threading.Event | None = None) -> None:
        """Send exactly one packet while retaining the original live peer."""
        deadline = _deadline(timeout)
        with self._owner.operation(deadline, cancel) as resources:
            raw = encode_frame(frame)
            if not resources.peer.alive():
                raise AgentTaskError('Linux channel original peer has retired')
            while True:
                self._owner.ready(resources.connection, deadline, cancel, write=True)
                try:
                    sent = resources.connection.send(raw)
                    break
                except (BlockingIOError, InterruptedError):
                    continue
            if sent != len(raw):
                raise AgentTaskError('Linux channel packet send was incomplete')
            if not resources.peer.alive():
                raise AgentTaskError('Linux channel original peer retired during send')

    def close(self, *, timeout: float = 0.25) -> None:
        """Revoke the channel and bound userspace waiting for resource retirement."""
        self._owner.close(timeout)

    def __enter__(self) -> LinuxChannel:
        return self

    def __exit__(self, *_arguments: object) -> None:
        self.close()


class LinuxListener:
    """Own a fresh protected endpoint; returned channels have independent lifetimes."""

    _owner: _Owner[_ListenerResources]
    _endpoint: LinuxEndpoint

    def __init__(self) -> None:
        raise AgentTaskError('Linux listeners must be created by create')

    @classmethod
    def create(cls, runtime_directory: str | Path) -> LinuxListener:
        """Create a new 0700 directory and 0600 sequenced-packet listener."""
        connection = None
        files = None
        try:
            connection = _new_socket()
            files = _EndpointFiles(runtime_directory)
            endpoint = files.bind(connection)
            connection.listen(8)
            listener = object.__new__(cls)
            listener._owner = _Owner(_ListenerResources(connection, files))
            listener._endpoint = endpoint
            connection, files = None, None
            return listener
        except (OSError, UnicodeError, NotImplementedError):
            raise AgentTaskError('Linux listener cannot be created securely') from None
        finally:
            try:
                if connection is not None:
                    _close_socket(connection)
            finally:
                if files is not None:
                    files.close()

    @property
    def endpoint(self) -> LinuxEndpoint:
        """Return immutable metadata for a future trusted host-owned helper launch."""
        return self._endpoint

    def accept(self, *, timeout: float, cancel: threading.Event | None = None) -> LinuxChannel:
        """Accept one channel and bind its retained peer to that exact socket."""
        deadline = _deadline(timeout)
        channel = None
        try:
            with self._owner.operation(deadline, cancel) as resources:
                while True:
                    self._owner.ready(resources.connection, deadline, cancel)
                    try:
                        connection, _address = resources.connection.accept()
                        break
                    except (BlockingIOError, InterruptedError):
                        continue
                channel = _capture(connection)
            result, channel = channel, None
            return result
        finally:
            if channel is not None:
                channel.close()

    def close(self, *, timeout: float = 0.25) -> None:
        """Revoke pending accepts and retire only listener resources and owned paths."""
        self._owner.close(timeout)

    def __enter__(self) -> LinuxListener:
        return self

    def __exit__(self, *_arguments: object) -> None:
        self.close()
