"""Per-peer USB passthrough session — Phase 2a.1.

A session owns the claim table for one WebRTC peer. Frames received on
the ``usb`` DataChannel are passed to ``handle_frame()``; replies are
returned as a list of frames the caller is expected to send back over
the same channel.

Handles OPEN/OPENED, CLOSE/CLOSED, the three transfer opcodes
(CTRL/BULK/INT) with CREDIT-based inbound flow control, and
LIST-over-channel (ACL-filtered). Oversize replies are fragmented with
``FLAG_EOF``. The symmetric viewer side lives in ``viewer_client``.

OPEN payload (UTF-8 JSON)::

    {"vendor_id": "1050", "product_id": "0407", "serial": "..."}

OPENED payload::

    {"ok": true,  "claim_id": 7}             on success
    {"ok": false, "error": "<message>"}      on failure (claim_id=0)

CTRL request payload::

    {"bm_request_type": <int 0..255>,
     "b_request": <int>,
     "w_value": <int>, "w_index": <int>,
     "data": "<base64 OUT bytes>",   # omit for IN transfers
     "length": <int IN length>,      # omit for OUT transfers
     "timeout_ms": <int>}            # optional, default 1000

BULK / INT request payload::

    {"endpoint": <int>,
     "direction": "in" | "out",
     "data": "<base64>" | "length": <int>,
     "timeout_ms": <int>}

Transfer response payload::

    {"ok": true,  "data": "<base64>"}        # data is "" for OUT transfers
    {"ok": false, "error": "<message>"}

CREDIT payload::

    {"credits": <int positive>}              # how many additional frames
                                             # the sender may issue

ERROR payload::

    {"error": "<message>"}

Per-claim inbound credit budget defaults to 16. Each transfer frame
received decrements the budget; the host returns a CREDIT(1) frame
alongside every transfer reply so a well-behaved peer never stalls.
A peer that exhausts its budget gets ERROR("credit exhausted") and is
expected to wait for CREDIT before retrying.
"""
from __future__ import annotations

import base64
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.passthrough.acl import UsbAcl
from je_auto_control.utils.usb.passthrough.backend import UsbBackend, UsbHandle
from je_auto_control.utils.usb.passthrough.protocol import (
    Frame, Opcode, fragment_payload,
)


_DEFAULT_MAX_CLAIMS = 4
_DEFAULT_INITIAL_CREDITS = 16
_TOPUP_PER_REPLY = 1
# Abuse tracking: a viewer that provokes this many protocol failures
# faster than they decay gets locked out for a cool-down. Tuned so
# normal operation (the odd bad frame) never trips it.
_ABUSE_MAX_STRIKES = 20.0
_ABUSE_DECAY_PER_S = 5.0
_ABUSE_LOCKOUT_S = 5.0


class SessionError(Exception):
    """Raised on session-level invariant violations (not protocol parse errors)."""


class _AbuseTracker:
    """Leaky-bucket strike counter that locks out a misbehaving peer."""

    def __init__(self, *, max_strikes: float = _ABUSE_MAX_STRIKES,
                 decay_per_s: float = _ABUSE_DECAY_PER_S,
                 lockout_s: float = _ABUSE_LOCKOUT_S) -> None:
        self._max = float(max_strikes)
        self._decay = float(decay_per_s)
        self._lockout_s = float(lockout_s)
        self._strikes = 0.0
        self._last = time.monotonic()
        self._locked_until = 0.0
        self._lock = threading.Lock()

    def record_strike(self) -> bool:
        """Count one protocol failure; return True if it triggers lockout."""
        with self._lock:
            now = time.monotonic()
            self._strikes = max(0.0, self._strikes - (now - self._last) * self._decay)
            self._last = now
            self._strikes += 1.0
            if self._strikes >= self._max:
                self._locked_until = now + self._lockout_s
                self._strikes = 0.0
                return True
            return False

    def is_locked(self) -> bool:
        with self._lock:
            return time.monotonic() < self._locked_until


@dataclass
class _ClaimState:
    """Per-claim handle + credit accounting + resume token."""

    handle: UsbHandle
    inbound_credits: int = _DEFAULT_INITIAL_CREDITS
    outbound_credits: int = _DEFAULT_INITIAL_CREDITS
    resume_token: str = ""


class UsbPassthroughSession:
    """Owns the active USB claims for one WebRTC peer."""

    def __init__(self, backend: UsbBackend,
                 *, max_claims: int = _DEFAULT_MAX_CLAIMS,
                 initial_credits: int = _DEFAULT_INITIAL_CREDITS,
                 acl: Optional[UsbAcl] = None,
                 prompt_callback: Optional[
                     Callable[[str, str, Optional[str]], bool]
                 ] = None,
                 viewer_id: Optional[str] = None,
                 audit_log: Any = None) -> None:
        self._backend = backend
        self._max_claims = max(1, int(max_claims))
        self._initial_credits = max(1, int(initial_credits))
        self._acl = acl
        self._prompt_callback = prompt_callback
        self._viewer_id = viewer_id
        self._audit_log = audit_log  # Late-bound; resolved on first use.
        self._lock = threading.Lock()
        self._claims: Dict[int, _ClaimState] = {}
        self._resume_index: Dict[str, int] = {}
        self._next_claim_id = 1
        self._abuse = _AbuseTracker()

    @property
    def active_claim_count(self) -> int:
        with self._lock:
            return len(self._claims)

    def credits_for(self, claim_id: int) -> Optional[Dict[str, int]]:
        """Inspect (inbound, outbound) credits for a claim — for tests."""
        with self._lock:
            claim = self._claims.get(int(claim_id))
            if claim is None:
                return None
            return {
                "inbound": claim.inbound_credits,
                "outbound": claim.outbound_credits,
            }

    def close_all(self) -> None:
        """Release every outstanding claim — call on peer disconnect."""
        with self._lock:
            handles = [c.handle for c in self._claims.values()]
            self._claims.clear()
            self._resume_index.clear()
        for handle in handles:
            try:
                handle.close()
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: best-effort cleanup; surface via logger
                autocontrol_logger.warning(
                    "passthrough close_all: handle.close() raised %r", error,
                )

    def is_locked_out(self) -> bool:
        """True while the peer is in a rate-limit cool-down."""
        return self._abuse.is_locked()

    def handle_frame(self, frame: Frame) -> List[Frame]:
        """Process one frame, with abuse tracking, and return replies."""
        if self._abuse.is_locked():
            return [_error_frame(frame.claim_id, "rate limited; locked out")]
        replies = self._dispatch(frame)
        if _is_misbehaviour(replies) and self._abuse.record_strike():
            self._audit("usb_rate_limited", "?", "?", None,
                        detail="viewer locked out for repeated failures")
        return replies

    def _dispatch(self, frame: Frame) -> List[Frame]:
        """Route one incoming frame; return zero or more reply frames."""
        if frame.op == Opcode.OPEN:
            return [self._handle_open(frame)]
        if frame.op == Opcode.RESUME:
            return [self._handle_resume(frame)]
        if frame.op == Opcode.CLOSE:
            return [self._handle_close(frame)]
        if frame.op == Opcode.CTRL:
            return self._handle_transfer(frame, _control_handler)
        if frame.op == Opcode.BULK:
            return self._handle_transfer(frame, _bulk_handler)
        if frame.op == Opcode.INT:
            return self._handle_transfer(frame, _interrupt_handler)
        if frame.op == Opcode.CREDIT:
            self._handle_credit(frame)
            return []
        if frame.op == Opcode.LIST:
            return self._handle_list(frame)
        if frame.op in (Opcode.OPENED, Opcode.CLOSED, Opcode.ERROR):
            # Responses we don't expect to receive on the host side here.
            return []
        return [_error_frame(frame.claim_id, f"unsupported opcode {frame.op}")]

    # --- LIST ---------------------------------------------------------------

    def _handle_list(self, frame: Frame) -> List[Frame]:
        """Enumerate backend devices the ACL would not outright deny.

        Resolves open question 3: the device list rides the same ``usb``
        DataChannel as transfers instead of forcing a second REST round
        trip. Devices the ACL denies are filtered out so the viewer never
        learns they exist.
        """
        try:
            devices = self._backend.list()
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: backends raise their own error types
            return [_error_frame(frame.claim_id, f"list failed: {error}")]
        visible = [
            {
                "vendor_id": dev.vendor_id,
                "product_id": dev.product_id,
                "serial": dev.serial,
                "bus_location": dev.bus_location,
            }
            for dev in devices
            if self._list_visible(dev.vendor_id, dev.product_id, dev.serial)
        ]
        payload = _encode_json_payload({"devices": visible})
        return fragment_payload(Opcode.LIST, frame.claim_id, payload)

    def _list_visible(self, vendor_id: str, product_id: str,
                      serial: Optional[str]) -> bool:
        if self._acl is None:
            return True
        return self._acl.decide(
            vendor_id=vendor_id, product_id=product_id, serial=serial,
        ) != "deny"

    # --- OPEN / CLOSE -------------------------------------------------------

    def _handle_open(self, frame: Frame) -> Frame:
        try:
            request = _decode_json_payload(frame.payload)
            vendor_id = str(request["vendor_id"])
            product_id = str(request["product_id"])
            serial = request.get("serial")
            if serial is not None:
                serial = str(serial)
        except (KeyError, ValueError, TypeError) as error:
            return _opened_failure(frame.claim_id, f"bad OPEN payload: {error}")
        decision = self._acl_decision(vendor_id, product_id, serial)
        if decision == "deny":
            self._audit("usb_open_denied", vendor_id, product_id, serial)
            return _opened_failure(
                frame.claim_id, "denied by ACL policy",
            )
        with self._lock:
            if len(self._claims) >= self._max_claims:
                self._audit("usb_open_rejected_max_claims",
                            vendor_id, product_id, serial)
                return _opened_failure(
                    frame.claim_id,
                    f"max concurrent claims reached ({self._max_claims})",
                )
        try:
            handle = self._backend.open(
                vendor_id=vendor_id, product_id=product_id, serial=serial,
            )
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: backends raise their own error types
            self._audit("usb_open_backend_error", vendor_id, product_id,
                        serial, detail=str(error))
            return _opened_failure(frame.claim_id, str(error))
        resume_token = secrets.token_hex(16)
        with self._lock:
            claim_id = self._next_claim_id
            self._next_claim_id = (self._next_claim_id % 0xFFFE) + 1
            self._claims[claim_id] = _ClaimState(
                handle=handle,
                inbound_credits=self._initial_credits,
                outbound_credits=self._initial_credits,
                resume_token=resume_token,
            )
            self._resume_index[resume_token] = claim_id
        self._audit("usb_open_allowed", vendor_id, product_id, serial,
                    detail=f"claim_id={claim_id}")
        return Frame(
            op=Opcode.OPENED, claim_id=claim_id,
            payload=_encode_json_payload({
                "ok": True, "claim_id": claim_id,
                "resume_token": resume_token,
            }),
        )

    def _handle_resume(self, frame: Frame) -> Frame:
        """Re-bind a still-open claim to a reconnecting viewer.

        Resolves claim continuity (open question / Phase 2 resilience):
        if the host session outlived a viewer transport drop, the viewer
        replays its ``resume_token`` instead of re-OPENing, keeping the
        device state and claim_id intact.
        """
        try:
            token = str(_decode_json_payload(frame.payload)["resume_token"])
        except (KeyError, ValueError, TypeError) as error:
            return _opened_failure(frame.claim_id, f"bad RESUME payload: {error}")
        with self._lock:
            claim_id = self._resume_index.get(token)
            claim = self._claims.get(claim_id) if claim_id is not None else None
        if claim is None:
            return _opened_failure(frame.claim_id, "unknown or expired resume token")
        self._audit("usb_resume", "?", "?", None, detail=f"claim_id={claim_id}")
        return Frame(
            op=Opcode.OPENED, claim_id=claim_id,
            payload=_encode_json_payload({
                "ok": True, "claim_id": claim_id, "resume_token": token,
            }),
        )

    def _acl_decision(self, vendor_id: str, product_id: str,
                      serial: Optional[str]) -> str:
        """Resolve ALLOW/DENY/PROMPT into a final allow/deny."""
        if self._acl is None:
            return "allow"
        verdict = self._acl.decide(
            vendor_id=vendor_id, product_id=product_id, serial=serial,
        )
        if verdict in ("allow", "deny"):
            return verdict
        # PROMPT path — if no callback wired, default to deny so the
        # operator can't be silently bypassed.
        if self._prompt_callback is None:
            return "deny"
        try:
            decision = bool(self._prompt_callback(
                vendor_id, product_id, serial,
            ))
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: defensively treat any prompt failure as deny
            autocontrol_logger.warning(
                "usb prompt callback raised: %r", error,
            )
            return "deny"
        return "allow" if decision else "deny"

    def _audit(self, event_type: str, vendor_id: str, product_id: str,
               serial: Optional[str], *, detail: str = "") -> None:
        """Best-effort audit-log row. Resolves the log lazily."""
        log = self._audit_log
        if log is None:
            try:
                from je_auto_control.utils.remote_desktop.audit_log import (
                    default_audit_log,
                )
                log = default_audit_log()
                self._audit_log = log
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: audit is best-effort
                autocontrol_logger.debug(
                    "usb passthrough audit unavailable: %r", error,
                )
                return
        descriptor = f"{vendor_id}:{product_id}"
        if serial is not None:
            descriptor += f"/{serial}"
        if detail:
            descriptor += f" {detail}"
        try:
            log.log(
                event_type, host_id=descriptor,
                viewer_id=self._viewer_id, detail=detail or None,
            )
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: never let audit-write failure poison the session
            autocontrol_logger.debug(
                "usb passthrough audit write failed: %r", error,
            )

    def _handle_close(self, frame: Frame) -> Frame:
        with self._lock:
            claim = self._claims.pop(int(frame.claim_id), None)
            if claim is not None and claim.resume_token:
                self._resume_index.pop(claim.resume_token, None)
        if claim is None:
            return _error_frame(
                frame.claim_id, f"unknown claim_id {frame.claim_id}",
            )
        try:
            claim.handle.close()
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: log-and-acknowledge; the claim is already gone from our table
            return _error_frame(frame.claim_id, f"close failed: {error}")
        self._audit("usb_close", "?", "?", None,
                    detail=f"claim_id={frame.claim_id}")
        return Frame(
            op=Opcode.CLOSED, claim_id=frame.claim_id,
            payload=_encode_json_payload({"ok": True}),
        )

    # --- Transfers ----------------------------------------------------------

    def _handle_transfer(self, frame: Frame,
                         dispatcher: Callable[[UsbHandle, Dict[str, Any]], bytes],
                         ) -> List[Frame]:
        with self._lock:
            claim = self._claims.get(int(frame.claim_id))
            if claim is None:
                return [_error_frame(
                    frame.claim_id, f"unknown claim_id {frame.claim_id}",
                )]
            if claim.inbound_credits <= 0:
                return [_error_frame(frame.claim_id, "credit exhausted")]
            claim.inbound_credits -= 1
            handle = claim.handle
        try:
            request = _decode_json_payload(frame.payload)
        except ValueError as error:
            return [_error_frame(frame.claim_id, f"bad payload: {error}")]
        try:
            result_bytes = dispatcher(handle, request)
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: backends raise their own error types
            reply_payload = _encode_json_payload(
                {"ok": False, "error": str(error)},
            )
        else:
            reply_payload = _encode_json_payload({
                "ok": True,
                "data": base64.b64encode(result_bytes).decode("ascii"),
            })
        # Fragment so an oversize IN transfer (open question 2) spans
        # multiple EOF-terminated frames instead of breaching the cap.
        frames = fragment_payload(
            _reply_opcode(frame.op), frame.claim_id, reply_payload,
        )
        frames.append(self._make_credit_frame(frame.claim_id, _TOPUP_PER_REPLY))
        return frames

    def _handle_credit(self, frame: Frame) -> None:
        try:
            request = _decode_json_payload(frame.payload)
            grant = int(request["credits"])
        except (KeyError, ValueError, TypeError) as error:
            autocontrol_logger.warning(
                "passthrough CREDIT: bad payload: %r", error,
            )
            return
        if grant <= 0:
            return
        with self._lock:
            claim = self._claims.get(int(frame.claim_id))
            if claim is not None:
                claim.outbound_credits += grant

    def _make_credit_frame(self, claim_id: int, grant: int) -> Frame:
        # Replenishing a peer's send budget isn't strictly tied to our
        # outbound_credits accounting (that tracks how many *we* may send
        # before the peer must replenish *us*). Keep the two streams
        # separate; this method just emits one credit grant.
        return Frame(
            op=Opcode.CREDIT, claim_id=claim_id,
            payload=_encode_json_payload({"credits": int(grant)}),
        )


# ---------------------------------------------------------------------------
# Transfer dispatchers — pure functions that pull args out of the JSON
# payload and call the right backend method.
# ---------------------------------------------------------------------------


def _control_handler(handle: UsbHandle, request: Dict[str, Any]) -> bytes:
    payload = _decode_b64(request.get("data"))
    return handle.control_transfer(
        bm_request_type=int(request["bm_request_type"]),
        b_request=int(request["b_request"]),
        w_value=int(request.get("w_value", 0)),
        w_index=int(request.get("w_index", 0)),
        data=payload,
        length=int(request.get("length", 0)),
        timeout_ms=int(request.get("timeout_ms", 1000)),
    )


def _bulk_handler(handle: UsbHandle, request: Dict[str, Any]) -> bytes:
    return _endpoint_call(handle.bulk_transfer, request)


def _interrupt_handler(handle: UsbHandle, request: Dict[str, Any]) -> bytes:
    return _endpoint_call(handle.interrupt_transfer, request)


def _endpoint_call(method: Callable[..., bytes],
                   request: Dict[str, Any]) -> bytes:
    direction = str(request.get("direction", ""))
    if direction not in ("in", "out"):
        raise RuntimeError(f"direction must be 'in' or 'out', got {direction!r}")
    return method(
        endpoint=int(request["endpoint"]),
        direction=direction,
        data=_decode_b64(request.get("data")),
        length=int(request.get("length", 0)),
        timeout_ms=int(request.get("timeout_ms", 1000)),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_REPLY_OPCODES: Dict[Opcode, Opcode] = {
    Opcode.CTRL: Opcode.CTRL,
    Opcode.BULK: Opcode.BULK,
    Opcode.INT: Opcode.INT,
}


def _reply_opcode(request_op: Opcode) -> Opcode:
    return _REPLY_OPCODES.get(request_op, Opcode.ERROR)


def _is_misbehaviour(replies: List[Frame]) -> bool:
    """True if the replies indicate a viewer-caused protocol failure.

    Counts ERROR frames and failed OPENED replies as strikes; a device
    transfer that fails at the backend (CTRL/BULK/INT with ok=false) is
    the device's fault, not the viewer's, so it is not counted.
    """
    for reply in replies:
        if reply.op == Opcode.ERROR:
            return True
        if reply.op == Opcode.OPENED:
            try:
                body = json.loads(reply.payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return True
            if not body.get("ok"):
                return True
    return False


def _decode_b64(value: Any) -> bytes:
    if value is None or value == "":
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return base64.b64decode(str(value))


def _opened_failure(claim_id: int, message: str) -> Frame:
    return Frame(
        op=Opcode.OPENED, claim_id=claim_id,
        payload=_encode_json_payload({"ok": False, "error": message}),
    )


def _error_frame(claim_id: int, message: str) -> Frame:
    return Frame(
        op=Opcode.ERROR, claim_id=claim_id,
        payload=_encode_json_payload({"error": message}),
    )


def _encode_json_payload(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _decode_json_payload(payload: bytes) -> dict:
    if not payload:
        raise ValueError("empty payload")
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("payload must be a JSON object")
    return decoded


__all__ = ["SessionError", "UsbPassthroughSession"]
