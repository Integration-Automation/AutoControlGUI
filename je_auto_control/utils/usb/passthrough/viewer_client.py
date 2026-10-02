"""Viewer-side client of the USB passthrough protocol.

The host side (:class:`UsbPassthroughSession`) accepts frames over a
WebRTC DataChannel; this module is the symmetric viewer side that
*issues* frames and blocks on the matching reply.

Transport-agnostic on purpose: pass any ``send_frame: Callable[[Frame],
None]`` (typically the DataChannel's ``send`` wrapped to call
``encode_frame``) and call ``feed_frame(frame)`` from your transport's
on-message handler. The client takes care of the synchronous request /
reply correlation and credit-based outbound flow control.

New requests use identities echoed by current hosts. After a timeout against
a legacy or unconfirmed peer, the client shuts down: create a new transport
and client before retrying. Correlated peers can continue without accepting
late replies; an orphaned late OPEN claim is closed automatically.

Public API::

    from je_auto_control.utils.usb.passthrough import (
        UsbPassthroughClient, encode_frame, decode_frame,
    )

    client = UsbPassthroughClient(send_frame=send_callable)
    handle = client.open(vendor_id="1050", product_id="0407")
    data = handle.control_transfer(
        bm_request_type=0xC0, b_request=6, length=18,
    )
    handle.close()
    client.shutdown()

Errors:

* ``UsbClientTimeout`` — peer did not reply within the timeout.
* ``UsbClientError`` — peer replied with ``{ok: false}`` or ERROR.
* ``UsbClientClosed`` — the client (or its handle) was shut down.
"""
from __future__ import annotations

import base64
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from uuid import uuid4
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.passthrough.protocol import (
    FLAG_EOF, Frame, Opcode,
)

#: Largest reassembled message: a 1 MiB endpoint transfer (the host's
#: MAX_ENDPOINT_LENGTH) base64-encoded is ~1.4 MiB, plus JSON framing.
_MAX_REASSEMBLED_BYTES = 2 * 1024 * 1024


_DEFAULT_REPLY_TIMEOUT_S = 10.0
_DEFAULT_CREDIT_TIMEOUT_S = 30.0
_INITIAL_CREDIT_GUESS = 16
_CLIENT_SHUT_DOWN_MSG = "client is shut down"


class UsbClientError(AutoControlException):
    """The host reported a transfer or open failure."""


class UsbClientTimeout(UsbClientError):
    """A reply did not arrive within the configured timeout."""


class UsbClientClosed(UsbClientError):
    """The client / handle was shut down before a reply arrived."""


@dataclass
class _PendingRequest:
    """One outstanding viewer→host request awaiting a reply.

    The reply is stored as ``(reply_op, reply_payload)`` rather than a
    :class:`Frame` because a reassembled payload (open question 2) may
    exceed the per-frame cap that :class:`Frame` enforces.
    """

    expected_op: Opcode
    event: threading.Event
    reply_op: Optional[Opcode] = None
    reply_payload: bytes = b""
    cancelled: bool = False
    request_id: str = field(default_factory=lambda: uuid4().hex)
    claim_id: int = 0


# ---------------------------------------------------------------------------
# ClientHandle — what the user actually drives once they hold a claim
# ---------------------------------------------------------------------------


class ClientHandle:
    """One open USB device claim from the viewer's perspective.

    All transfer methods are blocking — they enqueue the right request
    frame, wait for the host to send the matching reply (or ERROR),
    and return ``bytes``. Backend errors raise :class:`UsbClientError`.
    """

    def __init__(self, client: "UsbPassthroughClient", claim_id: int,
                 resume_token: str = "") -> None:  # nosec B107  # reason: resume_token is a reconnect handle, not a credential; "" means "no token yet"
        self._client = client
        self._claim_id = claim_id
        self._resume_token = resume_token
        self._closed = False
        self._lock = threading.Lock()

    @property
    def claim_id(self) -> int:
        return self._claim_id

    @property
    def resume_token(self) -> str:
        """Opaque token to re-bind this claim after a transport reconnect."""
        return self._resume_token

    @property
    def closed(self) -> bool:
        """Whether this handle or its client can no longer issue operations."""
        with self._lock:
            return self._closed or self._client.closed

    def control_transfer(self, *, bm_request_type: int, b_request: int,
                         w_value: int = 0, w_index: int = 0,
                         data: bytes = b"", length: int = 0,
                         timeout_ms: int = 1000) -> bytes:
        request: Dict[str, Any] = {
            "bm_request_type": int(bm_request_type),
            "b_request": int(b_request),
            "w_value": int(w_value), "w_index": int(w_index),
            "timeout_ms": int(timeout_ms),
        }
        if data:
            request["data"] = base64.b64encode(bytes(data)).decode("ascii")
        if length:
            request["length"] = int(length)
        return self._exchange(Opcode.CTRL, request)

    def bulk_transfer(self, *, endpoint: int, direction: str,
                      data: bytes = b"", length: int = 0,
                      timeout_ms: int = 1000) -> bytes:
        return self._exchange(Opcode.BULK, _endpoint_request(
            endpoint=endpoint, direction=direction,
            data=data, length=length, timeout_ms=timeout_ms,
        ))

    def interrupt_transfer(self, *, endpoint: int, direction: str,
                           data: bytes = b"", length: int = 0,
                           timeout_ms: int = 1000) -> bytes:
        return self._exchange(Opcode.INT, _endpoint_request(
            endpoint=endpoint, direction=direction,
            data=data, length=length, timeout_ms=timeout_ms,
        ))

    def close(self) -> None:
        """Send CLOSE; block on CLOSED. Idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._client._exchange_close(self._claim_id)
        except UsbClientClosed:
            # Client torn down concurrently; treat as success.
            pass

    def _exchange(self, op: Opcode, body: Dict[str, Any]) -> bytes:
        with self._lock:
            if self._closed:
                raise UsbClientClosed(f"handle for claim {self._claim_id} closed")
        return self._client._exchange_transfer(self._claim_id, op, body)


# ---------------------------------------------------------------------------
# UsbPassthroughClient — owns the protocol state machine and pending table
# ---------------------------------------------------------------------------


class UsbPassthroughClient:
    """Symmetric counterpart of :class:`UsbPassthroughSession`."""

    def __init__(
        self,
        *,
        send_frame: Callable[[Frame], None],
        reply_timeout_s: float = _DEFAULT_REPLY_TIMEOUT_S,
        credit_timeout_s: float = _DEFAULT_CREDIT_TIMEOUT_S,
        initial_credit_guess: int = _INITIAL_CREDIT_GUESS,
    ) -> None:
        self._send_frame = send_frame
        self._reply_timeout = float(reply_timeout_s)
        self._credit_timeout = float(credit_timeout_s)
        self._lock = threading.Lock()
        self._pending: Dict[int, _PendingRequest] = {}
        self._request_ids: Dict[str, _PendingRequest] = {}
        self._recent: OrderedDict[str, tuple[int, bool]] = OrderedDict()
        self._expired_opens: set[str] = set()
        self._supports_request_ids: Optional[bool] = None
        self._credits: Dict[int, int] = {}
        self._credit_events: Dict[int, threading.Event] = {}
        self._claim_locks: Dict[int, threading.Lock] = {}
        self._open_pending: Optional[_PendingRequest] = None
        self._list_pending: Optional[_PendingRequest] = None
        # Reassembly buffers for fragmented replies, keyed by claim_id
        # (open question 2). LIST uses claim_id 0.
        self._reasm: Dict[tuple[int, Opcode], bytearray] = {}
        self._initial_credit_guess = max(1, int(initial_credit_guess))
        self._closed = False

    # --- Lifecycle ----------------------------------------------------------

    @property
    def closed(self) -> bool:
        """Whether shutdown or an ambiguous legacy timeout requires reconnect."""
        with self._lock:
            return self._closed

    def shutdown(self) -> None:
        """Cancel every outstanding request; subsequent calls raise."""
        with self._lock:
            self._closed = True
            pending: List[_PendingRequest] = list(self._pending.values())
            if self._open_pending is not None:
                pending.append(self._open_pending)
            if self._list_pending is not None:
                pending.append(self._list_pending)
            self._pending.clear()
            self._request_ids.clear()
            self._recent.clear()
            self._expired_opens.clear()
            self._open_pending = None
            self._list_pending = None
            self._reasm.clear()
            credit_events = list(self._credit_events.values())
        for request in pending:
            request.cancelled = True
            request.event.set()
        for event in credit_events:
            event.set()

    # --- Inbound transport entry point --------------------------------------

    def feed_frame(self, frame: Frame) -> None:
        """Hand a frame received from the transport to the client."""
        if frame.op == Opcode.OPENED:
            self._on_opened(frame)
            return
        if frame.op == Opcode.CLOSED:
            self._complete_pending(frame.claim_id, frame.payload, Opcode.CLOSED)
            return
        if frame.op == Opcode.CREDIT:
            self._on_credit(frame)
            return
        if frame.op in (Opcode.CTRL, Opcode.BULK, Opcode.INT):
            assembled = self._reassemble(frame)
            if assembled is not None:
                self._complete_pending(frame.claim_id, assembled, frame.op)
            return
        if frame.op == Opcode.LIST:
            self._on_list(frame)
            return
        if frame.op == Opcode.ERROR:
            self._on_error(frame)
            return
        autocontrol_logger.debug(
            "passthrough client: ignoring incoming opcode %s", frame.op,
        )

    def _reassemble(self, frame: Frame) -> Optional[bytes]:
        """Buffer a fragment; return the full payload once EOF arrives.

        A message may not grow past :data:`_MAX_REASSEMBLED_BYTES`: a host
        sending fragments without EOF grew the buffer without limit.
        """
        cid = int(frame.claim_id)
        key = (cid, frame.op)
        with self._lock:
            if self._closed:
                return None
            buffer = self._reasm.setdefault(key, bytearray())
            if len(buffer) + len(frame.payload) > _MAX_REASSEMBLED_BYTES:
                self._reasm.pop(key, None)
                autocontrol_logger.warning(
                    "passthrough client: message on claim %d exceeds %d bytes; dropped",
                    cid, _MAX_REASSEMBLED_BYTES)
                return None
            buffer.extend(frame.payload)
            if not (frame.flags & FLAG_EOF):
                return None
            full = bytes(buffer)
            self._reasm.pop(key, None)
        return full

    # --- Outbound: open / close ---------------------------------------------

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> ClientHandle:
        """Open a device; legacy peers require reconnect after a reply timeout."""
        body: Dict[str, Any] = {"vendor_id": vendor_id, "product_id": product_id}
        if serial is not None:
            body["serial"] = serial
        reply = self._exchange_special(Opcode.OPEN, Opcode.OPENED, body)
        if not reply.get("ok"):
            raise UsbClientError(reply.get("error", "open failed"))
        return self._bind_claim(reply)

    def resume(self, resume_token: str) -> ClientHandle:
        """Rebind a held claim on a new transport using its resume token."""
        reply = self._exchange_special(Opcode.RESUME, Opcode.OPENED,
                                       {"resume_token": resume_token})
        if not reply.get("ok"):
            raise UsbClientError(reply.get("error", "resume failed"))
        return self._bind_claim(reply)

    def _exchange_special(self, op: Opcode, expected: Opcode,
                          body: Dict[str, Any]) -> Dict[str, Any]:
        request = _PendingRequest(expected_op=expected, event=threading.Event())
        slot = "_list_pending" if op == Opcode.LIST else "_open_pending"
        frame = _request_frame(op, 0, body, request)
        with self._lock:
            if self._closed:
                raise UsbClientClosed(_CLIENT_SHUT_DOWN_MSG)
            if getattr(self, slot) is not None:
                raise UsbClientError(f"another {op.name} is in progress")
            setattr(self, slot, request)
            self._request_ids[request.request_id] = request
        try:
            self._send(frame)
        except BaseException:
            self._drop_request(request)
            raise
        self._await_reply(request, op.name)
        reply = _decode_json(request.reply_payload)
        if request.reply_op == Opcode.ERROR:
            raise UsbClientError(reply.get("error", "host ERROR"))
        return reply

    def _bind_claim(self, body: Dict[str, Any]) -> ClientHandle:
        try:
            claim_id = int(body["claim_id"])
        except (KeyError, TypeError, ValueError) as error:
            raise UsbClientError(f"host reply has no valid claim_id: {body!r}") from error
        with self._lock:
            self._credits[claim_id] = self._initial_credit_guess
            self._credit_events[claim_id] = threading.Event()
        return ClientHandle(self, claim_id, str(body.get("resume_token", "")))

    def list_devices(self) -> List[Dict[str, Any]]:
        """Ask for the ACL-visible device list, correlating fragmented replies."""
        body = self._exchange_special(Opcode.LIST, Opcode.LIST, {})
        devices = body.get("devices")
        return list(devices) if isinstance(devices, list) else []

    def _exchange_close(self, claim_id: int) -> None:
        request = _PendingRequest(
            expected_op=Opcode.CLOSED, event=threading.Event(),
        )
        with self._claim_lock(claim_id):
            self._round_trip(claim_id, request,
                             _request_frame(Opcode.CLOSE, claim_id, {}, request), "CLOSE")
        self._forget_claim(claim_id)
        if request.reply_op == Opcode.ERROR:
            raise UsbClientError(_decode_json(request.reply_payload).get("error", "close failed"))

    def _claim_lock(self, claim_id: int) -> threading.Lock:
        """Serialize exchanges per claim, including compatibility with legacy peers."""
        with self._lock:
            return self._claim_locks.setdefault(int(claim_id), threading.Lock())

    def _round_trip(self, claim_id: int, request: "_PendingRequest",
                    frame: Frame, label: str) -> None:
        """Register ``request``, send ``frame`` and wait for its reply.

        The entry is removed on every failure (a failed send or a missing
        credit left it behind), and only if it is still this request's.
        """
        cid = int(claim_id)
        with self._lock:
            if self._closed:
                raise UsbClientClosed(_CLIENT_SHUT_DOWN_MSG)
            self._pending[cid] = request
            request.claim_id = cid
            self._request_ids[request.request_id] = request
        try:
            self._consume_credit(cid)
            self._send(frame)
        except BaseException:
            self._drop_pending(cid, request)
            raise
        self._await_reply(request, f"{label} for claim {cid}")

    def _await_reply(self, request: _PendingRequest, label: str) -> None:
        if not request.event.wait(timeout=self._reply_timeout):
            with self._lock:
                timed_out = request.reply_op is None and not request.cancelled
                reconnect = self._supports_request_ids is not True
                if timed_out:
                    self._forget_request_locked(request)
                    self._reasm.pop((request.claim_id, request.expected_op), None)
                    if request.expected_op == Opcode.OPENED and not reconnect:
                        self._expired_opens.add(request.request_id)
            if timed_out:
                if reconnect:
                    self.shutdown()
                raise UsbClientTimeout(f"{label} timed out")
        if request.cancelled:
            raise UsbClientClosed(f"client shut down before {label} reply")

    def _forget_request_locked(self, request: _PendingRequest) -> None:
        """Remove only this identity; retain bounded history for late credits."""
        self._request_ids.pop(request.request_id, None)
        if self._pending.get(request.claim_id) is request:
            self._pending.pop(request.claim_id, None)
        if self._open_pending is request:
            self._open_pending = None
        if self._list_pending is request:
            self._list_pending = None
        self._recent.setdefault(request.request_id, (request.claim_id, False))
        self._recent.move_to_end(request.request_id)
        if len(self._recent) > 4096:
            identity, _ = self._recent.popitem(last=False)
            self._expired_opens.discard(identity)

    def _drop_request(self, request: _PendingRequest) -> None:
        with self._lock:
            self._forget_request_locked(request)

    def _drop_pending(self, _claim_id: int, request: _PendingRequest) -> None:
        self._drop_request(request)

    # --- Outbound: transfers ------------------------------------------------

    def _exchange_transfer(self, claim_id: int, op: Opcode,
                           body: Dict[str, Any]) -> bytes:
        request = _PendingRequest(expected_op=op, event=threading.Event())
        frame = _request_frame(op, claim_id, body, request)
        # Serialised per claim: a second transfer overwrote the first's
        # pending entry, and one caller received the other's data.
        with self._claim_lock(claim_id):
            self._round_trip(claim_id, request, frame, op.name)
        if request.reply_op is None:
            raise UsbClientError("event signalled without a reply")
        if request.reply_op == Opcode.ERROR:
            err = _decode_json(request.reply_payload).get("error", "host ERROR")
            raise UsbClientError(err)
        body = _decode_json(request.reply_payload)
        if not body.get("ok"):
            raise UsbClientError(body.get("error", "transfer failed"))
        try:
            return base64.b64decode(body.get("data") or "", validate=True)
        except (TypeError, ValueError) as error:   # binascii.Error is a ValueError
            raise UsbClientError(f"host sent undecodable transfer data: {error}") from error

    # --- Inbound dispatch helpers ------------------------------------------

    def _on_opened(self, frame: Frame) -> None:
        self._complete_pending(frame.claim_id, frame.payload, Opcode.OPENED)
        body = _decode_json(frame.payload)
        identity = body.get("request_id")
        with self._lock:
            if not isinstance(identity, str) or identity not in self._expired_opens:
                return
            self._expired_opens.discard(identity)
        if not body.get("ok"):
            return
        try:
            claim_id = int(body["claim_id"])
            if not 1 <= claim_id <= 0xFFFF:
                return
            request = _PendingRequest(expected_op=Opcode.CLOSED, event=threading.Event())
            self._send(_request_frame(Opcode.CLOSE, claim_id, {}, request))
        except (KeyError, TypeError, ValueError, OverflowError, UsbClientError) as error:
            autocontrol_logger.warning("late USB claim cleanup failed: %s", error)

    def _on_list(self, frame: Frame) -> None:
        assembled = self._reassemble(frame)
        if assembled is not None:
            self._complete_pending(frame.claim_id, assembled, Opcode.LIST)

    def _on_credit(self, frame: Frame) -> None:
        try:
            body = _decode_json(frame.payload)
            grant = int(body.get("credits", 0))
        except (TypeError, ValueError, OverflowError):   # null, a list, 1e999
            return
        if grant <= 0:
            return
        with self._lock:
            if self._closed or not self._accept_credit_locked(body, int(frame.claim_id)):
                return
            self._credits[int(frame.claim_id)] = (
                self._credits.get(int(frame.claim_id), 0) + grant
            )
            event = self._credit_events.get(int(frame.claim_id))
            # Left set: a waiter clears it under the lock before it looks,
            # so a grant between its check and its wait is never missed.
            if event is not None:
                event.set()

    def _accept_credit_locked(self, body: Dict[str, Any], claim_id: int) -> bool:
        identity = body.get("request_id")
        if identity is None:
            return self._supports_request_ids is not True
        if not isinstance(identity, str):
            return False
        pending = self._request_ids.get(identity)
        receipt = self._recent.get(identity)
        expected_claim = (pending.claim_id if pending is not None
                          else (receipt[0] if receipt else None))
        if expected_claim != claim_id or (receipt is not None and receipt[1]):
            return False
        self._recent[identity] = (claim_id, True)
        if len(self._recent) > 4096:
            oldest, _ = self._recent.popitem(last=False)
            self._expired_opens.discard(oldest)
        return True

    def _on_error(self, frame: Frame) -> None:
        self._complete_pending(frame.claim_id, frame.payload, Opcode.ERROR)

    def _reply_request_locked(self, claim_id: int, body: Dict[str, Any],
                              op: Opcode) -> Optional[_PendingRequest]:
        identity = body.get("request_id")
        if identity is not None:
            if not isinstance(identity, str):
                return None
            request = self._request_ids.get(identity)
            if request is not None:
                self._supports_request_ids = True
            return request
        if self._supports_request_ids is True:
            return None
        request = self._legacy_request_locked(claim_id, op)
        if request is not None:
            self._supports_request_ids = False
        return request

    def _legacy_request_locked(self, claim_id: int, op: Opcode) -> Optional[_PendingRequest]:
        request = self._pending.get(int(claim_id))
        if op == Opcode.OPENED:
            request = self._open_pending
        elif op == Opcode.LIST:
            request = self._list_pending
        elif op == Opcode.ERROR and claim_id == 0:
            candidates = [p for p in (self._open_pending, self._list_pending) if p is not None]
            request = candidates[0] if len(candidates) == 1 else None
        return request

    def _complete_pending(self, claim_id: int, payload: bytes,
                          expected_op: Opcode) -> None:
        with self._lock:
            if self._closed:
                return
            request = self._reply_request_locked(claim_id, _decode_json(payload), expected_op)
            if request is None:
                return
            if expected_op not in (request.expected_op, Opcode.ERROR):
                return
            if request.claim_id and request.claim_id != int(claim_id):
                return
            self._forget_request_locked(request)
            if expected_op == Opcode.ERROR:
                self._reasm.pop((request.claim_id, request.expected_op), None)
            request.reply_op = expected_op
            request.reply_payload = payload
            request.event.set()

    # --- Credit helpers ----------------------------------------------------

    def _consume_credit(self, claim_id: int) -> None:
        with self._lock:
            event = self._credit_events.get(int(claim_id))
        deadline_per_wait = max(0.05, self._credit_timeout)
        while True:
            with self._lock:
                if self._closed:
                    raise UsbClientClosed("client shut down while waiting for credit")
                available = self._credits.get(int(claim_id), 0)
                if available > 0:
                    self._credits[int(claim_id)] = available - 1
                    return
                if event is None:
                    # No tracked claim — proceed without credit accounting.
                    return
                event.clear()
            if not event.wait(timeout=deadline_per_wait):
                raise UsbClientTimeout(
                    f"timed out waiting for credit on claim {claim_id}",
                )

    def _forget_claim(self, claim_id: int) -> None:
        with self._lock:
            self._credits.pop(int(claim_id), None)
            self._credit_events.pop(int(claim_id), None)

    # --- Test introspection ------------------------------------------------

    def credits_remaining(self, claim_id: int) -> int:
        with self._lock:
            return self._credits.get(int(claim_id), 0)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._request_ids)

    # --- Internal ----------------------------------------------------------

    def _send(self, frame: Frame) -> None:
        try:
            self._send_frame(frame)
        except Exception as error:
            raise UsbClientError(f"transport send failed: {error}") from error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_frame(op: Opcode, claim_id: int, body: Dict[str, Any],
                   request: _PendingRequest) -> Frame:
    return Frame(op=op, claim_id=int(claim_id), payload=json.dumps(
        dict(body, request_id=request.request_id),
    ).encode("utf-8"))


def _endpoint_request(*, endpoint: int, direction: str, data: bytes,
                      length: int, timeout_ms: int) -> Dict[str, Any]:
    if direction not in ("in", "out"):
        raise ValueError(f"direction must be 'in' or 'out', got {direction!r}")
    body: Dict[str, Any] = {
        "endpoint": int(endpoint),
        "direction": direction,
        "timeout_ms": int(timeout_ms),
    }
    if data:
        body["data"] = base64.b64encode(bytes(data)).decode("ascii")
    if length:
        body["length"] = int(length)
    return body


def _decode_json(payload: bytes) -> Dict[str, Any]:
    if not payload:
        return {}
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except ValueError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded


__all__ = [
    "ClientHandle", "UsbClientClosed", "UsbClientError", "UsbClientTimeout",
    "UsbPassthroughClient",
]
