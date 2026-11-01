"""Linux presence transport behind the Windows pipe's interface; its endpoint arrives only through the owned launch.

Windows finds a session's source by a named pipe whose first instance it owns. Linux has no such
name: each listener binds a fresh private socket, and a client may trust it only when its
``LinuxEndpoint`` came through a trusted launch. So the worker reports the endpoint in its owned
bootstrap reply, the broker hands it to :meth:`LinuxPresencePipe.use`, and ``LinuxChannel.connect``
then pins the actual listener process to the one that endpoint names.

``LinuxChannel`` revokes itself when a bounded operation runs out of time, so a byte pipe never
blocks inside one: it waits for readability with ``select`` first and only then receives.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import select
import socket
import threading
from types import SimpleNamespace
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import decode_frame, encode_frame

_FRAME_LIMIT = 4096
_WAIT = 0.25
_FILE_FIELDS = ("device", "inode", "owner", "mode")
_PEER_NUMBERS = ("pid", "uid", "gid", "birth")
_PEER_NAMESPACES = ("user_namespace", "pid_namespace")
_PEER_FIELDS = _PEER_NUMBERS + _PEER_NAMESPACES
_ENDPOINT_FIELDS = {"directory", "directory_identity", "socket_name", "socket_identity", "listener_process"}


def _whole(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < (1 << 64):
        raise AgentTaskError(f"Linux presence endpoint {name} is invalid")
    return value


def _closed_object(value: Any, fields: tuple[str, ...], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise AgentTaskError(f"Linux presence endpoint {name} fields are invalid")
    return value


def endpoint_to_wire(endpoint: Any) -> dict[str, Any]:
    """Serialize launch metadata for the owned bootstrap reply; nothing secret is in it."""
    return {"directory": endpoint.directory, "socket_name": endpoint.socket_name,
            "directory_identity": {name: getattr(endpoint.directory_identity, name) for name in _FILE_FIELDS},
            "socket_identity": {name: getattr(endpoint.socket_identity, name) for name in _FILE_FIELDS},
            "listener_process": {name: getattr(endpoint.listener_process, name) for name in _PEER_FIELDS}}


def endpoint_from_wire(value: Any) -> Any:
    """Rebuild launch metadata with closed fields and bounded values; connect still verifies all of it."""
    # pylint: disable-next=import-outside-toplevel  # reason: the Linux socket modules load only on Linux
    from je_auto_control.utils.agent_runtime.presence_endpoint_linux import FileIdentity, LinuxEndpoint
    if not isinstance(value, Mapping) or set(value) != _ENDPOINT_FIELDS:
        raise AgentTaskError("Linux presence endpoint fields are invalid")
    directory, name = _paths(value)
    identities = [FileIdentity(*(_whole(item[field], field) for field in _FILE_FIELDS))
                  for item in (_closed_object(value[key], _FILE_FIELDS, key)
                               for key in ("directory_identity", "socket_identity"))]
    return LinuxEndpoint(directory, identities[0], name, identities[1], _listener(value["listener_process"]))


def _paths(value: Mapping[str, Any]) -> tuple[str, str]:
    directory, name = value["directory"], value["socket_name"]
    if not isinstance(directory, str) or not Path(directory).is_absolute() or "\x00" in directory:
        raise AgentTaskError("Linux presence endpoint path is invalid")
    if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name) is None:
        raise AgentTaskError("Linux presence endpoint path is invalid")
    return directory, name


def _listener(value: Any) -> Any:
    # pylint: disable-next=import-outside-toplevel  # reason: the Linux socket modules load only on Linux
    from je_auto_control.utils.agent_runtime.presence_peer_linux import LinuxPeerIdentity
    peer = _closed_object(value, _PEER_FIELDS, "listener_process")
    if any(not isinstance(peer[name], str) or not peer[name] for name in _PEER_NAMESPACES):
        raise AgentTaskError("Linux presence endpoint namespaces are invalid")
    return LinuxPeerIdentity(*(_whole(peer[name], name) for name in _PEER_NUMBERS),
                             *(peer[name] for name in _PEER_NAMESPACES))


def _wait_readable(descriptor: int, cancel: threading.Event) -> None:
    while not cancel.is_set():
        readable, _write, _error = select.select([descriptor], [], [], _WAIT)
        if readable:
            return
    raise AgentTaskError("Linux presence connection was closed")


class LinuxBytePipe:
    """Bounded frames over one authenticated ``LinuxChannel``, shaped like ``PresenceBytePipe``."""

    def __init__(self, channel: Any) -> None:
        self._channel = channel
        self._cancel = threading.Event()

    def _open(self) -> Any:
        if self._channel is None:
            raise AgentTaskError("Linux presence byte pipe has closed")
        return self._channel

    def fileno(self) -> int:
        """Supply the connected descriptor to peer verification."""
        return self._open().fileno()

    def send_bytes(self, raw: bytes) -> None:
        """Send one frame of at most 4096 bytes."""
        if not isinstance(raw, bytes) or len(raw) > _FRAME_LIMIT:
            raise AgentTaskError("physical presence byte message exceeds its closed bound")
        self._open().send(decode_frame(raw), timeout=1, cancel=self._cancel)

    def recv_bytes(self, maximum: int = _FRAME_LIMIT) -> bytes:
        """Wait until a frame is readable, then receive it within one bounded operation."""
        if isinstance(maximum, bool) or maximum != _FRAME_LIMIT:
            raise AgentTaskError("physical presence byte receive bound must be4096")
        channel = self._open()
        _wait_readable(channel.fileno(), self._cancel)
        raw = encode_frame(channel.receive(timeout=1, cancel=self._cancel))
        if len(raw) > _FRAME_LIMIT:
            raise AgentTaskError("physical presence byte message exceeds its closed bound")
        return raw

    def close(self) -> None:
        """Cancel any wait first, then retire the channel."""
        self._cancel.set()
        if self._channel is not None:
            self._channel.close()
            self._channel = None


class LinuxPresenceListener:
    """Accept authenticated channels on one fresh private endpoint."""

    def __init__(self, listener: Any) -> None:
        self._listener = listener
        self._cancel = threading.Event()

    @property
    def endpoint_wire(self) -> dict[str, Any]:
        """The launch metadata the owned bootstrap reply carries to the broker."""
        return endpoint_to_wire(self._listener.endpoint)

    def accept(self) -> LinuxBytePipe:
        """Wait for a connection, then accept it within one bounded operation."""
        _wait_readable(self._listener.fileno(), self._cancel)
        return LinuxBytePipe(self._listener.accept(timeout=1, cancel=self._cancel))

    def close(self) -> None:
        """Stop waiting, then retire the listener and its private endpoint."""
        self._cancel.set()
        self._listener.close()


class LinuxPresencePipe:
    """The Linux factory behind the presence server and broker; the endpoint is never guessed."""

    def __init__(self, namespace: str | None = None, *, runtime_directory: str | None = None) -> None:
        self._namespace = namespace
        self._runtime = runtime_directory if runtime_directory is not None else os.environ.get("XDG_RUNTIME_DIR")
        self._endpoint: Any = None

    def listen(self) -> LinuxPresenceListener:
        """Bind a fresh private endpoint under the user's runtime directory."""
        # pylint: disable-next=import-outside-toplevel  # reason: the Linux socket modules load only on Linux
        from je_auto_control.utils.agent_runtime.presence_channel_linux import LinuxListener
        if not self._runtime or not Path(self._runtime).is_absolute():
            raise AgentTaskError("Linux physical presence needs a private XDG_RUNTIME_DIR")
        return LinuxPresenceListener(LinuxListener.create(self._runtime))

    def use(self, endpoint_wire: Any) -> None:
        """Adopt the endpoint an owned worker reported; only the broker's launch path calls this."""
        self._endpoint = endpoint_from_wire(endpoint_wire)

    def connect_if_present(self) -> LinuxBytePipe | None:
        """No name to look up: until an owned launch reported an endpoint, there is none."""
        return self.connect() if self._endpoint is not None else None

    def connect(self) -> LinuxBytePipe:
        """Connect to the reported endpoint; ``LinuxChannel`` pins its actual listener process."""
        # pylint: disable-next=import-outside-toplevel  # reason: the Linux socket modules load only on Linux
        from je_auto_control.utils.agent_runtime.presence_channel_linux import LinuxChannel
        if self._endpoint is None:
            raise AgentTaskError("physical presence endpoint does not exist")
        return LinuxBytePipe(LinuxChannel.connect(self._endpoint, timeout=1))


class LinuxPresenceSecurity:
    """Peer evidence from the connected socket's pidfd, shaped like ``WindowsPresenceSecurity``."""

    def current(self) -> Any:
        """This process's identity; the handshake compares births, never bare process ids."""
        # pylint: disable-next=import-outside-toplevel  # reason: the Linux socket modules load only on Linux
        from je_auto_control.utils.agent_runtime.presence_peer_linux import _birth
        return SimpleNamespace(birth=_birth(os.getpid()))

    def peer(self, descriptor: int, *, server: bool) -> Any:
        """Retain the connected peer of this exact descriptor; a duplicate is closed once retained."""
        # pylint: disable-next=import-outside-toplevel  # reason: the Linux socket modules load only on Linux
        from je_auto_control.utils.agent_runtime.presence_peer_linux import retain_connected_peer
        del server  # the same evidence serves both ends of the connection
        duplicate = socket.socket(fileno=os.dup(descriptor))
        try:
            return retain_connected_peer(duplicate)
        finally:
            duplicate.close()
