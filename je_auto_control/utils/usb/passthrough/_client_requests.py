"""Request bookkeeping for the viewer-side USB passthrough client.

What one outstanding request is, where it waits, how long it may wait,
and how a reply body is read. No locking and no transport here: the
client in ``viewer_client`` owns both.
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union

from je_auto_control.utils.usb.passthrough.client_errors import UsbClientError
from je_auto_control.utils.usb.passthrough.protocol import Opcode

#: Where a request waits: one OPEN/RESUME, one LIST, and one exchange per
#: claim id may be outstanding at a time.
Slot = Union[str, int]
OPEN_SLOT = "open"
LIST_SLOT = "list"

#: The longest device timeout a host honours (``session.MAX_TIMEOUT_MS``).
#: A request asking for more is refused by the host at once, so the client
#: never needs to wait longer than this for the device itself.
MAX_DEVICE_TIMEOUT_MS = 60_000


@dataclass
class PendingRequest:
    """One outstanding viewer→host request awaiting a reply.

    The reply is kept as its decoded JSON body rather than a
    :class:`Frame` because a reassembled payload (open question 2) may
    exceed the per-frame cap that :class:`Frame` enforces.
    """

    send_op: Opcode
    expected_op: Opcode
    slot: Slot
    event: threading.Event = field(default_factory=threading.Event)
    request_id: str = ""
    reply_op: Optional[Opcode] = None
    reply_body: Dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False

    @property
    def label(self) -> str:
        """The request's opcode name, for messages."""
        return self.send_op.name

    @property
    def claim_id(self) -> int:
        """The claim the request is sent on; 0 for OPEN / RESUME / LIST."""
        return self.slot if isinstance(self.slot, int) else 0

    def timeout_message(self) -> str:
        """What :class:`UsbClientTimeout` says when this request expires."""
        if isinstance(self.slot, int):
            return f"{self.label} timed out for claim {self.slot}"
        return f"{self.label} timed out"


def desynchronized_message(slot: Slot) -> str:
    """What :class:`UsbClientDesynchronized` says for ``slot``."""
    reason = ("an earlier request timed out and the host does not echo request "
              "ids, so its late reply cannot be told from the next one")
    if isinstance(slot, int):
        return (f"claim {slot} cannot be reused: {reason}. "
                "Close this handle and open the device again.")
    return (f"no further {slot.upper()} on this client: {reason}. "
            "Reconnect the USB channel and use a new client.")


def device_timeout_s(body: Dict[str, Any]) -> float:
    """Seconds the host may spend on the device for the request ``body``.

    A transfer carries ``timeout_ms``, which the host hands to the device
    and honours up to :data:`MAX_DEVICE_TIMEOUT_MS`; its reply cannot be
    expected sooner. Requests without one (OPEN, LIST, CLOSE) and values
    that are not a number count as zero.
    """
    value = body.get("timeout_ms")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    if math.isnan(value) or value <= 0:
        return 0.0
    return min(float(value), float(MAX_DEVICE_TIMEOUT_MS)) / 1000.0


def accepted_body(request: PendingRequest, default_error: str) -> Dict[str, Any]:
    """The reply's body, or :class:`UsbClientError` if the host refused."""
    body = request.reply_body
    if request.reply_op == Opcode.ERROR:
        raise UsbClientError(body.get("error", "host ERROR"))
    if not body.get("ok"):
        raise UsbClientError(body.get("error", default_error))
    return body


def claim_id_in(body: Dict[str, Any]) -> Optional[int]:
    """The ``claim_id`` of an OPENED body if it is a usable one."""
    try:
        claim_id = int(body["claim_id"])
    except (KeyError, TypeError, ValueError):
        return None
    return claim_id if 0 <= claim_id <= 0xFFFF else None


def decode_json(payload: bytes) -> Dict[str, Any]:
    """The JSON object in ``payload``, or ``{}`` if it is not one."""
    if not payload:
        return {}
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except ValueError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded
