"""Per-peer USB passthrough session — Phase 2a.1.

A session owns the claim table for one WebRTC peer. Frames received on
the ``usb`` DataChannel are passed to ``handle_frame()``; replies are
returned as a list of frames the caller is expected to send back over
the same channel.

Phase 2a.1 implements OPEN/OPENED, CLOSE/CLOSED, and the three transfer
opcodes (CTRL/BULK/INT) plus a CREDIT-based inbound flow control.
``LIST`` responses, viewer-side flow control, and the actual viewer
client stay TODO for later phases.

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
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.passthrough.acl import UsbAcl
from je_auto_control.utils.usb.passthrough.backend import UsbBackend, UsbHandle
from je_auto_control.utils.usb.passthrough.protocol import (
    Frame, Opcode,
)


_DEFAULT_MAX_CLAIMS = 4
_DEFAULT_INITIAL_CREDITS = 16
_TOPUP_PER_REPLY = 1


class SessionError(Exception):
    """Raised on session-level invariant violations (not protocol parse errors)."""


@dataclass
class _ClaimState:
    """Per-claim handle + credit accounting."""

    handle: UsbHandle
    inbound_credits: int = _DEFAULT_INITIAL_CREDITS
    outbound_credits: int = _DEFAULT_INITIAL_CREDITS


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
        self._next_claim_id = 1

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
        for handle in handles:
            try:
                handle.close()
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: best-effort cleanup; surface via logger
                autocontrol_logger.warning(
                    "passthrough close_all: handle.close() raised %r", error,
                )

    def handle_frame(self, frame: Frame) -> List[Frame]:
        """Process one incoming frame; return zero or more reply frames."""
        if frame.op == Opcode.OPEN:
            return [self._handle_open(frame)]
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
        if frame.op in (Opcode.OPENED, Opcode.CLOSED, Opcode.ERROR,
                        Opcode.LIST):
            # Responses we don't expect to receive on the host side here.
            return []
        return [_error_frame(frame.claim_id, f"unsupported opcode {frame.op}")]

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
        with self._lock:
            claim_id = self._next_claim_id
            self._next_claim_id = (self._next_claim_id % 0xFFFE) + 1
            self._claims[claim_id] = _ClaimState(
                handle=handle,
                inbound_credits=self._initial_credits,
                outbound_credits=self._initial_credits,
            )
        self._audit("usb_open_allowed", vendor_id, product_id, serial,
                    detail=f"claim_id={claim_id}")
        return Frame(
            op=Opcode.OPENED, claim_id=claim_id,
            payload=_encode_json_payload({"ok": True, "claim_id": claim_id}),
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
            return [
                Frame(op=_reply_opcode(frame.op), claim_id=frame.claim_id,
                      payload=reply_payload),
                self._make_credit_frame(frame.claim_id, _TOPUP_PER_REPLY),
            ]
        reply_payload = _encode_json_payload({
            "ok": True,
            "data": base64.b64encode(result_bytes).decode("ascii"),
        })
        return [
            Frame(op=_reply_opcode(frame.op), claim_id=frame.claim_id,
                  payload=reply_payload),
            self._make_credit_frame(frame.claim_id, _TOPUP_PER_REPLY),
        ]

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
