"""Viewer-side client of the USB passthrough protocol.

The host side (:class:`UsbPassthroughSession`) accepts frames over a
WebRTC DataChannel; this module is the symmetric viewer side that
*issues* frames and blocks on the matching reply.

Transport-agnostic on purpose: pass any ``send_frame: Callable[[Frame],
None]`` (typically the DataChannel's ``send`` wrapped to call
``encode_frame``) and call ``feed_frame(frame)`` from your transport's
on-message handler. The client takes care of the synchronous request /
reply correlation and credit-based outbound flow control.

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
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.passthrough.protocol import (
    Frame, Opcode,
)


_DEFAULT_REPLY_TIMEOUT_S = 10.0
_DEFAULT_CREDIT_TIMEOUT_S = 30.0
_INITIAL_CREDIT_GUESS = 16


class UsbClientError(Exception):
    """The host reported a transfer or open failure."""


class UsbClientTimeout(UsbClientError):
    """A reply did not arrive within the configured timeout."""


class UsbClientClosed(UsbClientError):
    """The client / handle was shut down before a reply arrived."""


@dataclass
class _PendingRequest:
    """One outstanding viewer→host request awaiting a reply frame."""

    expected_op: Opcode
    event: threading.Event
    reply: Optional[Frame] = None
    cancelled: bool = False


# ---------------------------------------------------------------------------
# ClientHandle — what the user actually drives once they hold a claim
# ---------------------------------------------------------------------------


class ClientHandle:
    """One open USB device claim from the viewer's perspective.

    All transfer methods are blocking — they enqueue the right request
    frame, wait for the host to send the matching reply (or ERROR),
    and return ``bytes``. Backend errors raise :class:`UsbClientError`.
    """

    def __init__(self, client: "UsbPassthroughClient", claim_id: int) -> None:
        self._client = client
        self._claim_id = claim_id
        self._closed = False
        self._lock = threading.Lock()

    @property
    def claim_id(self) -> int:
        return self._claim_id

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def control_transfer(self, *, bm_request_type: int, b_request: int,
                         w_value: int = 0, w_index: int = 0,
                         data: bytes = b"", length: int = 0,
                         timeout_ms: int = 1000) -> bytes:
        request = {
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
        self._credits: Dict[int, int] = {}
        self._credit_events: Dict[int, threading.Event] = {}
        self._open_pending: Optional[_PendingRequest] = None
        self._initial_credit_guess = max(1, int(initial_credit_guess))
        self._closed = False

    # --- Lifecycle ----------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel every outstanding request; subsequent calls raise."""
        with self._lock:
            self._closed = True
            pending: List[_PendingRequest] = list(self._pending.values())
            if self._open_pending is not None:
                pending.append(self._open_pending)
            self._pending.clear()
            self._open_pending = None
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
            self._complete_pending(frame.claim_id, frame, Opcode.CLOSED)
            return
        if frame.op == Opcode.CREDIT:
            self._on_credit(frame)
            return
        if frame.op in (Opcode.CTRL, Opcode.BULK, Opcode.INT):
            self._complete_pending(frame.claim_id, frame, frame.op)
            return
        if frame.op == Opcode.ERROR:
            self._on_error(frame)
            return
        autocontrol_logger.debug(
            "passthrough client: ignoring incoming opcode %s", frame.op,
        )

    # --- Outbound: open / close ---------------------------------------------

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> ClientHandle:
        request = _PendingRequest(
            expected_op=Opcode.OPENED, event=threading.Event(),
        )
        with self._lock:
            if self._closed:
                raise UsbClientClosed("client is shut down")
            if self._open_pending is not None:
                raise UsbClientError("another open is in progress")
            self._open_pending = request
        body: Dict[str, Any] = {
            "vendor_id": vendor_id, "product_id": product_id,
        }
        if serial is not None:
            body["serial"] = serial
        self._send(Frame(op=Opcode.OPEN,
                         payload=json.dumps(body).encode("utf-8")))
        if not request.event.wait(timeout=self._reply_timeout):
            with self._lock:
                if self._open_pending is request:
                    self._open_pending = None
            raise UsbClientTimeout("OPEN timed out")
        if request.cancelled:
            raise UsbClientClosed("client shut down before OPEN reply")
        reply = request.reply
        if reply is None:
            raise UsbClientError("event signalled without a reply")
        body = _decode_json(reply.payload)
        if not body.get("ok"):
            raise UsbClientError(body.get("error", "open failed"))
        claim_id = int(body["claim_id"])
        with self._lock:
            self._credits[claim_id] = self._initial_credit_guess
            self._credit_events[claim_id] = threading.Event()
        return ClientHandle(self, claim_id)

    def _exchange_close(self, claim_id: int) -> None:
        request = _PendingRequest(
            expected_op=Opcode.CLOSED, event=threading.Event(),
        )
        with self._lock:
            if self._closed:
                raise UsbClientClosed("client is shut down")
            self._pending[int(claim_id)] = request
        self._consume_credit(claim_id)
        self._send(Frame(op=Opcode.CLOSE, claim_id=int(claim_id)))
        if not request.event.wait(timeout=self._reply_timeout):
            with self._lock:
                self._pending.pop(int(claim_id), None)
            raise UsbClientTimeout(f"CLOSE timed out for claim {claim_id}")
        if request.cancelled:
            raise UsbClientClosed("client shut down before CLOSE reply")
        self._forget_claim(claim_id)

    # --- Outbound: transfers ------------------------------------------------

    def _exchange_transfer(self, claim_id: int, op: Opcode,
                           body: Dict[str, Any]) -> bytes:
        request = _PendingRequest(expected_op=op, event=threading.Event())
        with self._lock:
            if self._closed:
                raise UsbClientClosed("client is shut down")
            self._pending[int(claim_id)] = request
        self._consume_credit(claim_id)
        self._send(Frame(
            op=op, claim_id=int(claim_id),
            payload=json.dumps(body).encode("utf-8"),
        ))
        if not request.event.wait(timeout=self._reply_timeout):
            with self._lock:
                self._pending.pop(int(claim_id), None)
            raise UsbClientTimeout(f"{op.name} timed out for claim {claim_id}")
        if request.cancelled:
            raise UsbClientClosed("client shut down before reply")
        reply = request.reply
        if reply is None:
            raise UsbClientError("event signalled without a reply")
        if reply.op == Opcode.ERROR:
            err = _decode_json(reply.payload).get("error", "host ERROR")
            raise UsbClientError(err)
        body = _decode_json(reply.payload)
        if not body.get("ok"):
            raise UsbClientError(body.get("error", "transfer failed"))
        return base64.b64decode(body.get("data") or "")

    # --- Inbound dispatch helpers ------------------------------------------

    def _on_opened(self, frame: Frame) -> None:
        with self._lock:
            request = self._open_pending
            self._open_pending = None
        if request is not None:
            request.reply = frame
            request.event.set()

    def _on_credit(self, frame: Frame) -> None:
        try:
            grant = int(_decode_json(frame.payload).get("credits", 0))
        except (ValueError, KeyError):
            return
        if grant <= 0:
            return
        with self._lock:
            self._credits[int(frame.claim_id)] = (
                self._credits.get(int(frame.claim_id), 0) + grant
            )
            event = self._credit_events.get(int(frame.claim_id))
        if event is not None:
            event.set()
            event.clear()

    def _on_error(self, frame: Frame) -> None:
        # An unsolicited ERROR — route to whichever pending request matches
        # the claim_id; if none, log and drop.
        with self._lock:
            request = self._pending.pop(int(frame.claim_id), None)
        if request is None:
            autocontrol_logger.warning(
                "passthrough client: unsolicited ERROR for claim %s: %s",
                frame.claim_id, frame.payload[:200],
            )
            return
        request.reply = frame
        request.event.set()

    def _complete_pending(self, claim_id: int, frame: Frame,
                          expected_op: Opcode) -> None:
        with self._lock:
            request = self._pending.get(int(claim_id))
            if request is None:
                return
            if request.expected_op != expected_op:
                return
            self._pending.pop(int(claim_id), None)
        request.reply = frame
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
            return len(self._pending) + (1 if self._open_pending else 0)

    # --- Internal ----------------------------------------------------------

    def _send(self, frame: Frame) -> None:
        try:
            self._send_frame(frame)
        except Exception as error:
            raise UsbClientError(f"transport send failed: {error}") from error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
