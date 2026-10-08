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
* ``UsbClientDesynchronized`` — an earlier request timed out against a
  host that does not echo request ids; see below.

Pairing replies with requests. Every request carries a ``request_id``
the host echoes (see ``protocol``), and a reply is handed to the request
with that id. A reply whose request has already timed out matches a
tombstone and is discarded -- that reply and no other.

A host older than the field echoes nothing, and its replies are paired by
kind (OPEN / LIST / claim) as they always were. That is only safe while
no request has timed out: afterwards a reply could be the late one or the
answer to the next request, and nothing on the wire says which. Dropping
"the next reply" would throw away a correct answer whenever the host
never sent the late one, so the client does not guess. It refuses further
requests of that kind with :class:`UsbClientDesynchronized` -- a claim
after a transfer timeout (close the handle and open the device again),
OPEN/RESUME or LIST after theirs (reconnect the channel). Until the first
echoed id arrives the peer's age is unknown and a timeout is treated the
cautious way; the first echoed id lifts it.
"""
from __future__ import annotations

import base64
import json
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.passthrough.protocol import (
    FLAG_EOF, REQUEST_ID_KEY, Frame, Opcode, ProtocolError, valid_request_id,
)

#: Largest reassembled message: a 1 MiB endpoint transfer (the host's
#: MAX_ENDPOINT_LENGTH) base64-encoded is ~1.4 MiB, plus JSON framing.
_MAX_REASSEMBLED_BYTES = 2 * 1024 * 1024


_DEFAULT_REPLY_TIMEOUT_S = 10.0
_DEFAULT_CREDIT_TIMEOUT_S = 30.0
_INITIAL_CREDIT_GUESS = 16
_CLIENT_SHUT_DOWN_MSG = "client is shut down"
#: Where a request waits: one OPEN/RESUME, one LIST, and one exchange per
#: claim id may be outstanding at a time.
_Slot = Union[str, int]
_OPEN_SLOT = "open"
_LIST_SLOT = "list"
#: Replies a host may split across frames, and those that are always one.
_FRAGMENTED_REPLIES = (Opcode.LIST, Opcode.CTRL, Opcode.BULK, Opcode.INT)
_SINGLE_FRAME_REPLIES = (Opcode.OPENED, Opcode.CLOSED, Opcode.ERROR)
#: Ids of timed-out requests kept so their late replies are recognised.
#: Forgetting one is harmless: a reply with an unknown id is dropped too.
_MAX_TOMBSTONES = 256


class UsbClientError(AutoControlException):
    """The host reported a transfer or open failure."""


class UsbClientTimeout(UsbClientError):
    """A reply did not arrive within the configured timeout."""


class UsbClientClosed(UsbClientError):
    """The client / handle was shut down before a reply arrived."""


class UsbClientDesynchronized(UsbClientError):
    """A timed-out request left replies impossible to pair; reconnect.

    Raised instead of sending when an earlier request of the same kind
    timed out and the host does not echo request ids: its late reply and
    the answer to a new request would be indistinguishable. A claim is
    recovered by closing its handle and opening the device again; OPEN /
    RESUME and LIST by reconnecting the channel with a new client.
    """


@dataclass
class _PendingRequest:
    """One outstanding viewer→host request awaiting a reply.

    The reply is kept as its decoded JSON body rather than a
    :class:`Frame` because a reassembled payload (open question 2) may
    exceed the per-frame cap that :class:`Frame` enforces.
    """

    send_op: Opcode
    expected_op: Opcode
    slot: _Slot
    event: threading.Event = field(default_factory=threading.Event)
    request_id: str = ""
    reply_op: Optional[Opcode] = None
    reply_body: Dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False

    @property
    def label(self) -> str:
        return self.send_op.name

    @property
    def claim_id(self) -> int:
        return self.slot if isinstance(self.slot, int) else 0

    def timeout_message(self) -> str:
        """What :class:`UsbClientTimeout` says when this request expires."""
        if isinstance(self.slot, int):
            return f"{self.label} timed out for claim {self.slot}"
        return f"{self.label} timed out"


def _desynchronized_message(slot: _Slot) -> str:
    reason = ("an earlier request timed out and the host does not echo request "
              "ids, so its late reply cannot be told from the next one")
    if isinstance(slot, int):
        return (f"claim {slot} cannot be reused: {reason}. "
                "Close this handle and open the device again.")
    return (f"no further {slot.upper()} on this client: {reason}. "
            "Reconnect the USB channel and use a new client.")


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
        with self._lock:
            return self._closed

    @property
    def reusable(self) -> bool:
        """False once the handle is closed or its claim is desynchronised.

        A transfer that timed out against a host that does not echo request
        ids leaves the claim unable to pair replies; further transfers raise
        :class:`UsbClientDesynchronized`. :meth:`close` still works.
        """
        return not self.closed and self._client.slot_reusable(self._claim_id)

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
        # One request per slot (pairing by kind, for hosts without ids)...
        self._pending: Dict[_Slot, _PendingRequest] = {}
        # ...and the same requests by the id a current host echoes.
        self._by_id: Dict[str, _PendingRequest] = {}
        self._tombstones: "OrderedDict[str, Opcode]" = OrderedDict()
        self._desynced: Set[_Slot] = set()
        self._peer_echoes_ids = False
        self._id_prefix = secrets.token_hex(4)
        self._id_counter = 0
        self._credits: Dict[int, int] = {}
        self._credit_events: Dict[int, threading.Event] = {}
        self._claim_locks: Dict[int, threading.Lock] = {}
        # Reassembly buffers for fragmented replies, keyed by claim_id
        # (open question 2). LIST uses claim_id 0.
        self._reasm: Dict[int, bytearray] = {}
        # Claims whose current message overflowed: drop through its EOF.
        self._reasm_skip: Set[int] = set()
        self._initial_credit_guess = max(1, int(initial_credit_guess))
        self._closed = False

    # --- Lifecycle ----------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel every outstanding request; subsequent calls raise."""
        with self._lock:
            self._closed = True
            pending: List[_PendingRequest] = list(self._pending.values())
            self._pending.clear()
            self._by_id.clear()
            self._tombstones.clear()
            self._reasm.clear()
            self._reasm_skip.clear()
            credit_events = list(self._credit_events.values())
            for request in pending:
                request.cancelled = True
        for request in pending:
            request.event.set()
        for event in credit_events:
            event.set()

    @property
    def peer_echoes_request_ids(self) -> bool:
        """True once the host has echoed a request id this client issued."""
        with self._lock:
            return self._peer_echoes_ids

    @property
    def reusable(self) -> bool:
        """False once the client is shut down or can no longer OPEN / RESUME.

        See :class:`UsbClientDesynchronized`; a claim's own state is on
        :attr:`ClientHandle.reusable`.
        """
        with self._lock:
            return not self._closed and _OPEN_SLOT not in self._desynced

    def slot_reusable(self, slot: _Slot) -> bool:
        """Whether requests may still go out on a claim id, ``"open"`` or ``"list"``."""
        with self._lock:
            return slot not in self._desynced

    # --- Inbound transport entry point --------------------------------------

    def feed_frame(self, frame: Frame) -> None:
        """Hand a frame received from the transport to the client."""
        if frame.op == Opcode.CREDIT:
            self._on_credit(frame)
            return
        if frame.op in _FRAGMENTED_REPLIES:
            payload = self._reassemble(frame)
            if payload is None:
                return
        elif frame.op in _SINGLE_FRAME_REPLIES:
            payload = bytes(frame.payload)
        else:
            autocontrol_logger.debug(
                "passthrough client: ignoring incoming opcode %s", frame.op,
            )
            return
        self._route_reply(frame.op, int(frame.claim_id), payload)

    def _reassemble(self, frame: Frame) -> Optional[bytes]:
        """Buffer a fragment; return the full payload once EOF arrives.

        A message may not grow past :data:`_MAX_REASSEMBLED_BYTES`: a host
        sending fragments without EOF grew the buffer without limit. The
        rest of a message dropped that way is skipped through its EOF --
        its tail used to be parsed as a message of its own. Nothing else
        resets a buffer: a request that times out leaves its half-received
        reply to finish and be discarded whole.
        """
        cid = int(frame.claim_id)
        is_last = bool(frame.flags & FLAG_EOF)
        with self._lock:
            if cid in self._reasm_skip:
                if is_last:
                    self._reasm_skip.discard(cid)
                return None
            buffer = self._reasm.setdefault(cid, bytearray())
            if len(buffer) + len(frame.payload) > _MAX_REASSEMBLED_BYTES:
                self._reasm.pop(cid, None)
                if not is_last:
                    self._reasm_skip.add(cid)
                autocontrol_logger.warning(
                    "passthrough client: message on claim %d exceeds %d bytes; dropped",
                    cid, _MAX_REASSEMBLED_BYTES)
                return None
            buffer.extend(frame.payload)
            if not is_last:
                return None
            self._reasm.pop(cid, None)
        return bytes(buffer)

    # --- Outbound: open / close ---------------------------------------------

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> ClientHandle:
        """Claim a device on the host; block until it answers."""
        body: Dict[str, Any] = {
            "vendor_id": vendor_id, "product_id": product_id,
        }
        if serial is not None:
            body["serial"] = serial
        request = _PendingRequest(Opcode.OPEN, Opcode.OPENED, _OPEN_SLOT)
        self._round_trip(request, body, busy="another open is in progress")
        return self._bind_claim(_accepted_body(request, "open failed"))

    def resume(self, resume_token: str) -> ClientHandle:
        """Re-bind a claim after a reconnect using a token from ``open``.

        The host session must still hold the claim (it outlived the
        viewer's transport drop). Returns a fresh :class:`ClientHandle`
        for the same ``claim_id``; raises :class:`UsbClientError` if the
        token is unknown or expired.
        """
        request = _PendingRequest(Opcode.RESUME, Opcode.OPENED, _OPEN_SLOT)
        self._round_trip(request, {"resume_token": resume_token},
                         busy="another open is in progress")
        return self._bind_claim(_accepted_body(request, "resume failed"))

    def _bind_claim(self, body: Dict[str, Any]) -> ClientHandle:
        claim_id = _claim_id_in(body)
        if claim_id is None:
            raise UsbClientError(f"host reply has no valid claim_id: {body!r}")
        with self._lock:
            self._credits[claim_id] = self._initial_credit_guess
            self._credit_events[claim_id] = threading.Event()
        return ClientHandle(self, claim_id, str(body.get("resume_token", "")))

    def list_devices(self) -> List[Dict[str, Any]]:
        """Ask the host for the ACL-visible device list (open question 3).

        Blocks until the host replies. Returns a list of dicts with
        ``vendor_id`` / ``product_id`` / ``serial`` / ``bus_location``.
        """
        request = _PendingRequest(Opcode.LIST, Opcode.LIST, _LIST_SLOT)
        self._round_trip(request, {}, busy="another list is in progress")
        if request.reply_op == Opcode.ERROR:
            raise UsbClientError(request.reply_body.get("error", "host ERROR"))
        devices = request.reply_body.get("devices")
        return list(devices) if isinstance(devices, list) else []

    def _exchange_close(self, claim_id: int) -> None:
        request = _PendingRequest(Opcode.CLOSE, Opcode.CLOSED, int(claim_id))
        with self._claim_lock(claim_id):
            self._round_trip(request, {})
        self._forget_claim(claim_id)

    def _claim_lock(self, claim_id: int) -> threading.Lock:
        """One exchange per claim at a time: an old host's replies carry only the claim id."""
        with self._lock:
            return self._claim_locks.setdefault(int(claim_id), threading.Lock())

    def _round_trip(self, request: "_PendingRequest", body: Dict[str, Any],
                    *, busy: Optional[str] = None) -> None:
        """Register ``request``, send it with its id, and wait for the reply.

        The entry is removed on every failure (a failed send or a missing
        credit left it behind). On return the request holds a reply.
        """
        self._register(request, busy)
        try:
            if isinstance(request.slot, int):
                self._consume_credit(request.slot)
            payload = dict(body)
            payload[REQUEST_ID_KEY] = request.request_id
            self._send(Frame(op=request.send_op, claim_id=request.claim_id,
                             payload=json.dumps(payload).encode("utf-8")))
        except BaseException:
            with self._lock:
                self._unregister_locked(request)
            raise
        if not request.event.wait(timeout=self._reply_timeout) and self._expire(request):
            raise UsbClientTimeout(request.timeout_message())
        if request.cancelled:
            raise UsbClientClosed(f"client shut down before {request.label} reply")
        if request.reply_op is None:
            raise UsbClientError("event signalled without a reply")

    def _register(self, request: "_PendingRequest", busy: Optional[str]) -> None:
        """Give ``request`` its id and its slot, or refuse to send it."""
        with self._lock:
            if self._closed:
                raise UsbClientClosed(_CLIENT_SHUT_DOWN_MSG)
            # CLOSE is exempt: its CLOSED reply is a kind no late transfer
            # reply can be mistaken for, and the device must be released.
            if request.send_op != Opcode.CLOSE and request.slot in self._desynced:
                raise UsbClientDesynchronized(_desynchronized_message(request.slot))
            if busy is not None and request.slot in self._pending:
                raise UsbClientError(busy)
            request.request_id = self._next_request_id_locked()
            self._pending[request.slot] = request
            self._by_id[request.request_id] = request

    def _next_request_id_locked(self) -> str:
        self._id_counter += 1
        return f"{self._id_prefix}-{self._id_counter}"

    def _unregister_locked(self, request: "_PendingRequest") -> None:
        if self._pending.get(request.slot) is request:
            self._pending.pop(request.slot, None)
        if self._by_id.get(request.request_id) is request:
            self._by_id.pop(request.request_id, None)

    def _expire(self, request: "_PendingRequest") -> bool:
        """Give up on ``request``; False if its reply arrived just in time.

        A host that echoes ids only needs the tombstone. One that does not
        (or has not shown that it does) could deliver the late reply to the
        slot's next request, so the slot stops taking requests instead.
        """
        with self._lock:
            if self._by_id.get(request.request_id) is not request:
                return False
            self._unregister_locked(request)
            self._bury_locked(request.request_id, request.send_op)
            if not self._peer_echoes_ids:
                self._desynced.add(request.slot)
        return True

    def _bury_locked(self, request_id: str, send_op: Opcode) -> None:
        self._tombstones[request_id] = send_op
        while len(self._tombstones) > _MAX_TOMBSTONES:
            self._tombstones.popitem(last=False)

    # --- Outbound: transfers ------------------------------------------------

    def _exchange_transfer(self, claim_id: int, op: Opcode,
                           body: Dict[str, Any]) -> bytes:
        request = _PendingRequest(op, op, int(claim_id))
        # Serialised per claim: a second transfer overwrote the first's
        # pending entry, and one caller received the other's data.
        with self._claim_lock(claim_id):
            self._round_trip(request, body)
        reply = _accepted_body(request, "transfer failed")
        try:
            return base64.b64decode(reply.get("data") or "", validate=True)
        except (TypeError, ValueError) as error:   # binascii.Error is a ValueError
            raise UsbClientError(f"host sent undecodable transfer data: {error}") from error

    # --- Inbound dispatch helpers ------------------------------------------

    def _route_reply(self, op: Opcode, claim_id: int, payload: bytes) -> None:
        """Hand a complete reply to the request it answers, or drop it."""
        body = _decode_json(payload)
        request_id = body.get(REQUEST_ID_KEY)
        orphan: Optional[int] = None
        with self._lock:
            if isinstance(request_id, str) and valid_request_id(request_id):
                request, orphan = self._take_by_id_locked(request_id, op, body)
            else:
                request = self._take_by_kind_locked(op, claim_id, payload)
            if request is not None:
                request.reply_op = op
                request.reply_body = body
        if request is not None:
            request.event.set()
        if orphan is not None:
            self._release_orphan(orphan)

    def _take_by_id_locked(self, request_id: str, op: Opcode, body: Dict[str, Any],
                           ) -> Tuple[Optional[_PendingRequest], Optional[int]]:
        """The request ``request_id`` names, plus a claim to release if any."""
        request = self._by_id.get(request_id)
        if request is None:
            return None, self._discard_late_locked(request_id, op, body)
        self._peer_echoes_ids_locked()
        if op not in (request.expected_op, Opcode.ERROR):
            autocontrol_logger.warning(
                "passthrough client: %s reply to a %s request dropped",
                op.name, request.label)
            return None, None
        self._unregister_locked(request)
        return request, None

    def _discard_late_locked(self, request_id: str, op: Opcode,
                             body: Dict[str, Any]) -> Optional[int]:
        """Drop a reply nobody is waiting for; return a claim it leaves open.

        A late OPENED that succeeded means the host holds a device for a
        caller that already got a timeout. A late RESUME is left alone: the
        claim it names may have been resumed again and be in use.
        """
        sent_as = self._tombstones.pop(request_id, None)
        if sent_as is None:
            autocontrol_logger.warning(
                "passthrough client: %s reply with unknown request id dropped", op.name)
            return None
        self._peer_echoes_ids_locked()
        autocontrol_logger.debug(
            "passthrough client: late reply to timed-out %s discarded", sent_as.name)
        if sent_as == Opcode.OPEN and op == Opcode.OPENED and body.get("ok"):
            return _claim_id_in(body)
        return None

    def _peer_echoes_ids_locked(self) -> None:
        """The host echoed an id of ours: every reply is identifiable."""
        self._peer_echoes_ids = True
        self._desynced.clear()

    def _take_by_kind_locked(self, op: Opcode, claim_id: int,
                             payload: bytes) -> Optional[_PendingRequest]:
        """Pair a reply that has no id the way hosts without ids require."""
        slot: _Slot = claim_id
        if op == Opcode.OPENED:
            slot = _OPEN_SLOT
        elif op == Opcode.LIST:
            slot = _LIST_SLOT
        request = self._pending.get(slot)
        if op == Opcode.ERROR:
            self._reasm.pop(claim_id, None)
            if request is None:
                autocontrol_logger.warning(
                    "passthrough client: unsolicited ERROR for claim %s: %s",
                    claim_id, payload[:200])
        elif request is not None and request.expected_op != op:
            return None
        if request is not None:
            self._unregister_locked(request)
        return request

    def _release_orphan(self, claim_id: int) -> None:
        """CLOSE a claim whose OPEN had already timed out; nobody holds it."""
        with self._lock:
            if self._closed:
                return
            request_id = self._next_request_id_locked()
            self._bury_locked(request_id, Opcode.CLOSE)   # its CLOSED is unwanted
        try:
            self._send(Frame(
                op=Opcode.CLOSE, claim_id=claim_id,
                payload=json.dumps({REQUEST_ID_KEY: request_id}).encode("utf-8")))
        except (UsbClientError, ProtocolError) as error:
            autocontrol_logger.warning(
                "passthrough client: could not release claim %s left by a late "
                "OPENED: %r", claim_id, error)

    def _on_credit(self, frame: Frame) -> None:
        try:
            grant = int(_decode_json(frame.payload).get("credits", 0))
        except (TypeError, ValueError, OverflowError):   # null, a list, 1e999
            return
        if grant <= 0:
            return
        with self._lock:
            self._credits[int(frame.claim_id)] = (
                self._credits.get(int(frame.claim_id), 0) + grant
            )
            event = self._credit_events.get(int(frame.claim_id))
            # Left set: a waiter clears it under the lock before it looks,
            # so a grant between its check and its wait is never missed.
            if event is not None:
                event.set()

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
            return sum(1 for slot in self._pending if slot != _LIST_SLOT)

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


def _accepted_body(request: _PendingRequest, default_error: str) -> Dict[str, Any]:
    """The reply's body, or :class:`UsbClientError` if the host refused."""
    body = request.reply_body
    if request.reply_op == Opcode.ERROR:
        raise UsbClientError(body.get("error", "host ERROR"))
    if not body.get("ok"):
        raise UsbClientError(body.get("error", default_error))
    return body


def _claim_id_in(body: Dict[str, Any]) -> Optional[int]:
    """The ``claim_id`` of an OPENED body if it is a usable one."""
    try:
        claim_id = int(body["claim_id"])
    except (KeyError, TypeError, ValueError):
        return None
    return claim_id if 0 <= claim_id <= 0xFFFF else None


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
    "ClientHandle", "UsbClientClosed", "UsbClientDesynchronized",
    "UsbClientError", "UsbClientTimeout", "UsbPassthroughClient",
]
