"""Linux owner-service channel: one lease per helper, relayed JSON lines, fenced close."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from typing import Any, Callable, Protocol, Sequence

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.native_channel import classify_reply, require_event_owner
from je_auto_control.utils.agent_runtime import owner_service_wire as wire
from je_auto_control.utils.agent_runtime.owner_service_nested import NestedGrant
from je_auto_control.utils.agent_runtime.wire_data import detached, positive
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint

_LINE_LIMIT = 1_100_000
_CALL_SECONDS = 2.0
_RETIRE_SECONDS = 3.0
_POLL_SECONDS = 0.02
_FINAL = (wire.REPORT_RETIRED, wire.REPORT_SETTLED_WITHOUT_SCOPE)


class ServiceTransport(Protocol):
    """One authenticated connection to the owner service, used by one channel only."""

    def send(self, frame: bytes) -> None:
        """Send one whole frame."""

    def receive(self, timeout: float) -> bytes | None:
        """Return one whole frame, or None when nothing arrived within ``timeout``."""

    def close(self) -> None:
        """Release the connection; the service then closes every lease it carried."""


class SeqpacketTransport:
    """AF_UNIX SOCK_SEQPACKET connection; the kernel attaches sender credentials to every packet."""

    def __init__(self, endpoint: str) -> None:
        family = getattr(socket, "AF_UNIX", None)
        kind = getattr(socket, "SOCK_SEQPACKET", None)
        if family is None or kind is None:
            raise AgentTaskError("the owner service needs AF_UNIX sequenced packets")
        self._socket = socket.socket(family, kind | getattr(socket, "SOCK_CLOEXEC", 0))
        try:
            # The service enables SO_PASSCRED/SO_PASSPIDFD on its end; the kernel then
            # attaches this process's credentials and pidfd to every packet it sends.
            self._socket.connect(os.fspath(endpoint))
        except OSError as error:
            self._socket.close()
            raise AgentTaskError(f"owner service is unreachable: {type(error).__name__}") from error

    def send(self, frame: bytes) -> None:
        """Send one frame; a short send is a broken connection."""
        try:
            sent = self._socket.send(frame)
        except OSError as error:
            raise AgentTaskError(f"owner service connection failed: {type(error).__name__}") from error
        if sent != len(frame):
            raise AgentTaskError("owner service connection accepted a partial frame")

    def receive(self, timeout: float) -> bytes | None:
        """Receive one frame within ``timeout``; EOF is a closed connection."""
        self._socket.settimeout(max(timeout, 0.001))
        try:
            frame = self._socket.recv(wire.REPLY_SIZE + 1)
        except TimeoutError:
            return None
        except OSError as error:
            raise AgentTaskError(f"owner service connection failed: {type(error).__name__}") from error
        if not frame:
            raise AgentTaskError("owner service closed the connection")
        return frame

    def close(self) -> None:
        """Close the socket; the service closes this channel's lease on EOF."""
        self._socket.close()


def _nonce() -> wire.Identifier:
    value = uuid.uuid4().int
    return value >> 64, value & ((1 << 64) - 1)


def _refusal(reply: wire.ServiceReply, action: str) -> AgentTaskError:
    if reply.status == wire.STATUS_CAPACITY:
        return AgentControlBusy(f"owner service has no capacity to {action}")
    if reply.status == wire.STATUS_UNAVAILABLE:
        return AgentTaskError(f"owner service is unavailable and cannot {action}")
    return AgentTaskError(f"owner service refused to {action} (status {reply.status}, error {reply.error[0]})")


class OwnerServiceChannel:
    """``OwnedChannel`` surface over the owner service: ``request``, ``close`` and ``retired``.

    Construction allocates only. The first request opens this channel's own lease and
    starts the helper under a fixed request ID, so a lost acknowledgment is retried
    without a second launch. ``close`` sets a monotone stop intent, waits at most for
    one in-flight call, closes the lease and reports retired only after the service
    observes the helper settled. No reply is delivered once close has begun.
    """

    def __init__(self, transport: ServiceTransport, policy: int, arguments: Sequence[str] = (), *,
                 on_control: Callable[[str], None] | None = None, parent: NestedGrant | None = None) -> None:
        self._transport = transport
        self._parent = parent
        self._policy = policy
        self._arguments = tuple(arguments)
        self._on_control = on_control
        self._request_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._stop = threading.Event()
        self._open_nonce = _nonce()
        self._start_id = _nonce()
        self._lease: wire.Identifier | None = None
        self._ticket: wire.Ticket | None = None
        self._pending = bytearray()
        self._retired = False

    @property
    def retired(self) -> bool:
        """True only after the service observed this channel's helper settled, or none was ever started."""
        return self._retired

    def _fenced(self) -> None:
        if self._stop.is_set():
            raise AgentTaskError("owner service channel was closed while a request was waiting")

    def _call(self, request: wire.ServiceRequest, deadline: float) -> wire.ServiceReply:
        """One frame out, its own reply back. Replies to earlier timed-out calls are skipped."""
        with self._io_lock:
            self._transport.send(request.pack())
            call_end = min(deadline, time.monotonic() + _CALL_SECONDS)
            while True:
                remaining = call_end - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                frame = self._transport.receive(remaining)
                if frame is None:
                    continue
                reply = wire.unpack_reply(frame)
                if reply.nonce == request.nonce and reply.opcode == request.opcode:
                    return reply

    def _retried(self, request: wire.ServiceRequest, deadline: float) -> wire.ServiceReply:
        """Repeat an idempotent call with the same nonce until a reply arrives or the deadline passes."""
        while True:
            self._fenced()
            try:
                return self._call(request, deadline)
            except TimeoutError:
                if time.monotonic() >= deadline:
                    raise AgentTaskError("owner service did not answer before the deadline") from None

    def _open_request(self) -> wire.ServiceRequest:
        """A nested helper's channels are child leases of the record that started it."""
        if self._parent is None:
            return wire.ServiceRequest(wire.OP_OPEN_TOP, self._open_nonce, policy=self._policy)
        return wire.ServiceRequest(wire.OP_OPEN_CHILD, self._open_nonce, policy=self._policy,
                                   parent=self._parent.parent, capability=self._parent.capability)

    def _ensure_started(self, deadline: float) -> None:
        if self._lease is None:
            reply = self._retried(self._open_request(), deadline)
            if reply.status not in (wire.STATUS_OK, wire.STATUS_EXISTING):
                raise _refusal(reply, "open a lease")
            self._lease = reply.lease
        if self._ticket is None:
            start = wire.ServiceRequest(wire.OP_START, self._start_id, lease=self._lease, request=self._start_id,
                                        arguments=self._arguments)
            reply = self._retried(start, deadline)
            if reply.status not in (wire.STATUS_OK, wire.STATUS_EXISTING):
                raise _refusal(reply, "start the helper")
            self._ticket = reply.ticket

    def _relay(self, opcode: int, deadline: float, data: bytes = b"") -> wire.ServiceReply:
        request = wire.ServiceRequest(opcode, _nonce(), lease=self._lease, ticket=self._ticket, data=data)
        try:
            reply = self._call(request, deadline)
        except TimeoutError:
            # Relay calls are not idempotent; a lost reply leaves the stream unknown.
            raise AgentTaskError("owner service relay reply was lost") from None
        if reply.status != wire.STATUS_OK:
            self._fenced()  # A lease this channel's own close just ended is a close, not a refusal.
            raise _refusal(reply, "relay helper traffic")
        return reply

    def _write(self, payload: bytes, deadline: float) -> None:
        offset = 0
        while offset < len(payload):
            self._fenced()
            if time.monotonic() >= deadline:
                raise AgentTaskError("owner service relay is full past the deadline")
            chunk = payload[offset:offset + wire.DATA_BYTES]
            accepted = self._relay(wire.OP_WRITE, deadline, chunk).data_length
            if accepted > len(chunk):
                raise AgentTaskError("owner service accepted more than it was sent")
            offset += accepted
            if not accepted:
                time.sleep(_POLL_SECONDS)

    def _send_line(self, value: Any, deadline: float) -> None:
        line = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        if len(line) > _LINE_LIMIT:
            raise AgentTaskError("native helper request exceeds its bound")
        self._write(line, deadline)

    def _next_line(self, deadline: float, check: Callable[[], None]) -> Any:
        while time.monotonic() < deadline:
            self._fenced()
            check()
            self._fenced()
            end = self._pending.find(b"\n")
            if end >= 0:
                line = bytes(self._pending[:end + 1])
                del self._pending[:end + 1]
                try:
                    return json.loads(line)
                except ValueError as error:
                    raise AgentTaskError("native helper reply is not JSON") from error
            if len(self._pending) > _LINE_LIMIT:
                raise AgentTaskError("native helper reply exceeds its bound")
            reply = self._relay(wire.OP_READ, deadline)
            self._fenced()
            self._pending.extend(reply.data)
            if reply.flags & wire.REPLY_EOF and b"\n" not in self._pending:
                raise AgentTaskError("native helper closed its reply stream")
            if not reply.data:
                time.sleep(_POLL_SECONDS)
        raise TimeoutError

    def _receive(self, request_id: str, deadline: float, check: Callable[[], None],
                 on_event: Callable[[dict], None] | None, operation: str) -> Any:
        try:
            while True:
                message = self._next_line(deadline, check)
                if isinstance(message, dict) and "control" in message:
                    if message["control"] != "physical_input" or self._on_control is None:
                        raise AgentTaskError("unexpected native control notification")
                    self._on_control(message["control"])
                    continue
                is_event, value = classify_reply(message, request_id)
                if not is_event:
                    check()
                    self._fenced()
                    return value
                require_event_owner(value, on_event)
                check()
                on_event(detached(value))
                self._fenced()
                self._send_line({"ack": True}, deadline)
        except TimeoutError:
            raise AgentTaskError(f"native helper {operation} deadline exhausted") from None

    def request(self, operation: str, payload: Any, *, timeout: float,
                check: Callable[[], None] = cancellation_checkpoint,
                on_event: Callable[[dict], None] | None = None) -> Any:
        """Validate one proposal, wait within its deadline, and retire the helper on every failed operation."""
        positive(timeout, "native deadline", 3600)
        deadline = time.monotonic() + timeout
        with self._request_lock:
            if self._retired or self._stop.is_set():
                raise AgentTaskError("native helper has retired")
            try:
                check()
                self._ensure_started(deadline)
                request_id = uuid.uuid4().hex
                self._send_line({"id": request_id, "operation": operation, "payload": detached(payload)}, deadline)
                return self._receive(request_id, deadline, check, on_event, operation)
            except BaseException as primary:  # reason: every failed/cancelled RPC must retire its helper
                try:
                    self.close()
                except AgentTaskError as cleanup:
                    raise primary from cleanup
                raise

    def _observe_settled(self, deadline: float) -> bool:
        while time.monotonic() < deadline:
            request = wire.ServiceRequest(wire.OP_OBSERVE, _nonce(), lease=self._lease, ticket=self._ticket)
            try:
                reply = self._call(request, deadline)
            except TimeoutError:
                return False
            if reply.status == wire.STATUS_OK and reply.report_kind in _FINAL:
                return True
            if reply.status != wire.STATUS_OK or reply.report_kind != wire.REPORT_PENDING:
                return False
            time.sleep(_POLL_SECONDS)
        return False

    def close(self) -> None:
        """Close this channel's lease and wait for the service to settle its helper.

        Safe from any thread, including while another thread waits in ``request``;
        that request then fails instead of returning a reply. Pending or sticky
        cleanup raises and leaves the channel unretired, so a later close retries.
        """
        self._stop.set()
        with self._close_lock:
            if self._retired:
                return
            deadline = time.monotonic() + _RETIRE_SECONDS
            if self._lease is not None:
                try:
                    self._call(wire.ServiceRequest(wire.OP_CLOSE, _nonce(), lease=self._lease), deadline)
                except TimeoutError:
                    raise AgentTaskError("owner service did not acknowledge the lease close") from None
            if self._ticket is not None and not self._observe_settled(deadline):
                raise AgentTaskError("owner service has not retired the native helper")
            self._transport.close()
            self._retired = True
