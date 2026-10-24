"""Bounded no-replay ADB smart-socket transport; never starts, kills or upgrades a server."""
from __future__ import annotations

import ipaddress
import re
import socket
import struct
import time
from dataclasses import dataclass
from typing import Callable

from je_auto_control.android.adb_client import AndroidDevice, _parse_devices
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint
from je_auto_control.utils.rbac.authorization import AuthorizationError

_HEX = re.compile(b"[0-9a-fA-F]{4}")
_LIMIT = 1_000_000


def _integer(value: object, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= maximum


def _deadline(timeout: float) -> float:
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 3600):
        raise AgentTaskError("managed ADB deadline must be finite and within 3600 seconds")
    return time.monotonic() + timeout


def _shell_service(command: str) -> bytes:
    if not isinstance(command, str) or not command or len(command) > 8192 or "\0" in command:
        raise AgentTaskError("managed ADB command must be bounded nonempty text")
    try:
        service = b"shell,v2,raw:" + command.encode("utf-8")
    except UnicodeError:
        raise AgentTaskError("managed ADB command must be valid UTF-8 text") from None
    if len(service) > 8192:
        raise AgentTaskError("managed ADB command exceeds its byte limit")
    return service


@dataclass(frozen=True)
class AdbShellResult:
    """Raw bounded stream evidence; a transport exit is not application completion or input retirement."""

    stdout: bytes
    stderr: bytes
    returncode: int


class _Stream:
    def __init__(self, connection: socket.socket, deadline: float, check: Callable[[], None]) -> None:
        self.connection = connection
        self.deadline = deadline
        self.check = check

    def _poll(self) -> None:
        self.check()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTaskError("managed ADB deadline exhausted; remote outcome may be unknown")
        self.connection.settimeout(min(0.1, remaining))

    def read(self, size: int, *, eof: bool = False) -> bytes:
        """Read exact framing within the original deadline, refreshing authority while stalled."""
        data = bytearray()
        while len(data) < size:
            self._poll()
            try:
                part = self.connection.recv(size - len(data))
            except socket.timeout:
                continue
            if not part:
                if eof and not data:
                    return b""
                raise AgentTaskError("managed ADB closed before confirmed protocol completion")
            data.extend(part)
        return bytes(data)

    def write(self, packet: bytes) -> None:
        """Finish a single write without reconnecting or resetting its deadline."""
        offset = 0
        while offset < len(packet):
            self._poll()
            try:
                count = self.connection.send(packet[offset:])
            except socket.timeout:
                continue
            if not count:
                raise AgentTaskError("managed ADB request could not be completely sent")
            offset += count

    def request(self, service: bytes) -> None:
        """Send one framed service; never publish device-provided failure diagnostics."""
        if not service or len(service) > 65535:
            raise AgentTaskError("managed ADB service exceeds its protocol bound")
        self.write(f"{len(service):04x}".encode("ascii") + service)
        status = self.read(4)
        if status == b"FAIL":
            # Read a bounded diagnostic only to settle framing. It can contain typed secrets.
            self.read(self.length())
            raise AgentTaskError("managed ADB service was refused; no diagnostic content is published")
        if status != b"OKAY":
            raise AgentTaskError("managed ADB returned an invalid service status")

    def length(self) -> int:
        """Decode exactly four hexadecimal length bytes, refusing permissive int prefixes."""
        prefix = self.read(4)
        if _HEX.fullmatch(prefix) is None:
            raise AgentTaskError("managed ADB returned an invalid length prefix")
        return int(prefix, 16)

    def end(self) -> None:
        """Require stream closure with no late data after the terminal protocol record."""
        if self.read(1, eof=True):
            raise AgentTaskError("managed ADB sent data after protocol completion")


def _shell_reply(stream: _Stream, limit: int) -> AdbShellResult:
    outputs = {1: bytearray(), 2: bytearray()}
    total = 0
    for _ in range(4096):
        kind, size = struct.unpack("<BI", stream.read(5))
        if kind == 3:
            if size != 1:
                raise AgentTaskError("managed ADB exit packet must contain exactly one byte")
            exit_code = stream.read(1)[0]
            stream.end()
            return AdbShellResult(bytes(outputs[1]), bytes(outputs[2]), exit_code)
        if kind not in outputs or size > limit - total:
            raise AgentTaskError("managed ADB shell output exceeds its closed protocol or byte limit")
        outputs[kind].extend(stream.read(size))
        total += size
    raise AgentTaskError("managed ADB shell packet count exceeds its bound")


class ManagedAdbServer:
    """Internal host-only endpoint; selecting a transport ID alone does not prove physical-device identity.

    The adapter must check device, boot and app scope on the same selected command connection.
    A server restart may reuse numeric transport IDs. No default/first-device selection, CLI process,
    server version replacement, automatic retry or legacy shell fallback is performed here.
    """

    def __init__(self, host: str, port: int) -> None:
        if not isinstance(host, str) or "%" in host:
            raise AgentTaskError("managed ADB requires a literal loopback server address")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise AgentTaskError("managed ADB requires a literal loopback server address") from None
        if not address.is_loopback or not _integer(port, 65535):
            raise AgentTaskError("managed ADB requires a reviewed loopback address and port")
        self._endpoint = (str(address), port)

    def _connect(self, deadline: float, check: Callable[[], None]) -> socket.socket:
        check()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTaskError("managed ADB deadline exhausted before connection")
        # One connect attempt. No CLI is invoked if the host-configured server is absent.
        return socket.create_connection(self._endpoint, timeout=remaining)

    def list_devices(self, *, timeout: float = 5,
                     check: Callable[[], None] = cancellation_checkpoint) -> list[AndroidDevice]:
        """Query only devices-l on the explicit server, without creating or repairing that server."""
        deadline = _deadline(timeout)
        try:
            with self._connect(deadline, check) as connection:
                stream = _Stream(connection, deadline, check)
                stream.request(b"host:devices-l")
                output = stream.read(stream.length())
                stream.end()
                return _parse_devices(output)
        except AuthorizationError:
            raise
        except OSError:
            raise AgentTaskError("managed ADB connection failed; server state was not changed") from None

    def shell(self, transport_id: int, command: str, *, timeout: float = 30, limit: int = _LIMIT,
              check: Callable[[], None] = cancellation_checkpoint) -> AdbShellResult:
        """Run one host-built command with shell-v2 exit evidence; ambiguous failures are never retried.

        Only a future finite, scoped device adapter may build commands for this internal transport.
        Do not expose this raw shell method to a task/model command catalog.
        """
        if not _integer(transport_id, 2**64 - 1) or not _integer(limit, _LIMIT):
            raise AgentTaskError("managed ADB transport ID or output limit is invalid")
        service = _shell_service(command)
        deadline = _deadline(timeout)
        try:
            with self._connect(deadline, check) as connection:
                stream = _Stream(connection, deadline, check)
                stream.request(f"host:transport-id:{transport_id}".encode("ascii"))
                stream.request(service)
                stream.write(struct.pack("<BI", 4, 0))  # Close remote stdin, never allocate a PTY.
                return _shell_reply(stream, limit)
        except AuthorizationError:
            raise
        except OSError:
            raise AgentTaskError("managed ADB transport failed; remote outcome may be unknown") from None
