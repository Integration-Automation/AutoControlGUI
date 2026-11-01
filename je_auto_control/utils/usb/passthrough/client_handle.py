"""The viewer's handle on one claimed USB device.

:class:`ClientHandle` is what a caller drives once
:meth:`UsbPassthroughClient.open` (or ``resume``) has returned: it turns
transfer calls into request bodies and leaves the wire, the pairing of
replies and the waiting to the client. Re-exported from ``viewer_client``.
"""
from __future__ import annotations

import base64
import threading
from typing import TYPE_CHECKING, Any, Dict

from je_auto_control.utils.usb.passthrough.client_errors import UsbClientClosed
from je_auto_control.utils.usb.passthrough.protocol import Opcode

if TYPE_CHECKING:
    from je_auto_control.utils.usb.passthrough.viewer_client import (
        UsbPassthroughClient,
    )


class ClientHandle:
    """One open USB device claim from the viewer's perspective.

    All transfer methods are blocking — they enqueue the right request
    frame, wait for the host to send the matching reply (or ERROR),
    and return ``bytes``. Backend errors raise :class:`UsbClientError`.

    ``timeout_ms`` is the device timeout the host applies (at most 60 000).
    The call itself waits that long plus the client's ``reply_timeout_s``
    before raising :class:`UsbClientTimeout`.
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


__all__ = ["ClientHandle"]
