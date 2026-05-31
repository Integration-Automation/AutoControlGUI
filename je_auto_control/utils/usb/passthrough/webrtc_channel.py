"""Bridge the USB passthrough protocol onto a WebRTC ``usb`` DataChannel.

The protocol, session, and client are transport-agnostic; this module
is the thin adapter that carries their binary frames over an aiortc
``RTCDataChannel`` (the same pattern ``webrtc_files`` uses for file
transfer). Two adapters:

* :class:`UsbChannelHost` — wraps a host-side channel + a
  :class:`UsbPassthroughSession`. Incoming frames are decoded, gated on
  the feature flag, fed to the session, and the replies are sent back.
* :class:`UsbChannelClient` — wraps a viewer-side channel + a
  :class:`UsbPassthroughClient`, exposing ``list_devices`` / ``open`` /
  ``resume``.

Sends are marshalled onto the aiortc event-loop thread via a bridge
with ``call_soon(fn, *args)`` (defaulting to the project's shared
WebRTC bridge). The bridge is injectable so the adapters can be tested
with a synchronous stand-in and a fake channel — no aiortc required to
exercise the bridging logic.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Callable, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.passthrough.flags import (
    is_usb_passthrough_enabled,
)
from je_auto_control.utils.usb.passthrough.protocol import (
    Frame, Opcode, ProtocolError, decode_frame, encode_frame,
)
from je_auto_control.utils.usb.passthrough.session import UsbPassthroughSession
from je_auto_control.utils.usb.passthrough.viewer_client import (
    ClientHandle, UsbPassthroughClient,
)

_USB_CHANNEL_LABEL = "usb"


class _ImmediateBridge:
    """Fallback bridge that runs the send inline (used by tests)."""

    @staticmethod
    def call_soon(fn: Callable[..., Any], *args: Any) -> None:
        fn(*args)


def _resolve_bridge(bridge: Optional[Any]) -> Any:
    if bridge is not None:
        return bridge
    from je_auto_control.utils.remote_desktop.webrtc_transport import (
        get_bridge,
    )
    return get_bridge()


def _as_bytes(raw: Any) -> bytes:
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return bytes(raw)
    raise TypeError(f"usb channel expects binary frames, got {type(raw).__name__}")


def _error_bytes(message: str) -> bytes:
    return encode_frame(Frame(
        op=Opcode.ERROR,
        payload=json.dumps({"error": message}).encode("utf-8"),
    ))


class UsbChannelHost:
    """Carry a :class:`UsbPassthroughSession` over a host DataChannel."""

    def __init__(self, channel: Any, *,
                 session: Optional[UsbPassthroughSession] = None,
                 session_factory: Optional[
                     Callable[[], UsbPassthroughSession]
                 ] = None,
                 bridge: Optional[Any] = None,
                 enabled_check: Optional[Callable[[], bool]] = None) -> None:
        self._channel = channel
        self._session = session
        self._factory = session_factory
        self._bridge = bridge
        self._enabled = enabled_check or is_usb_passthrough_enabled
        self._lock = threading.Lock()
        channel.on("message")(self._on_message)

    @property
    def session(self) -> Optional[UsbPassthroughSession]:
        return self._session

    def _ensure_session(self) -> Optional[UsbPassthroughSession]:
        with self._lock:
            if self._session is None and self._factory is not None:
                self._session = self._factory()
            return self._session

    def _on_message(self, raw: Any) -> None:
        if not self._enabled():
            self._reply(_error_bytes("usb passthrough disabled"))
            return
        try:
            frame = decode_frame(_as_bytes(raw))
        except (ProtocolError, TypeError) as error:
            self._reply(_error_bytes(f"bad frame: {error}"))
            return
        try:
            session = self._ensure_session()
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: backend construction can fail many ways; report, don't crash the channel
            self._reply(_error_bytes(f"usb backend unavailable: {error}"))
            return
        if session is None:
            self._reply(_error_bytes("no usb session on host"))
            return
        for reply in session.handle_frame(frame):
            self._reply(encode_frame(reply))

    def _reply(self, data: bytes) -> None:
        _resolve_bridge(self._bridge).call_soon(self._channel.send, data)


class UsbChannelClient:
    """Drive a :class:`UsbPassthroughClient` over a viewer DataChannel."""

    def __init__(self, channel: Any, *, bridge: Optional[Any] = None,
                 reply_timeout_s: float = 10.0) -> None:
        self._channel = channel
        self._bridge = bridge
        self.client = UsbPassthroughClient(
            send_frame=self._send_frame, reply_timeout_s=reply_timeout_s,
        )
        channel.on("message")(self._on_message)

    def _send_frame(self, frame: Frame) -> None:
        _resolve_bridge(self._bridge).call_soon(
            self._channel.send, encode_frame(frame),
        )

    def _on_message(self, raw: Any) -> None:
        try:
            self.client.feed_frame(decode_frame(_as_bytes(raw)))
        except (ProtocolError, TypeError) as error:
            autocontrol_logger.warning(
                "usb channel client: dropping bad frame: %r", error,
            )

    def list_devices(self) -> Any:
        return self.client.list_devices()

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> ClientHandle:
        return self.client.open(
            vendor_id=vendor_id, product_id=product_id, serial=serial,
        )

    def resume(self, resume_token: str) -> ClientHandle:
        return self.client.resume(resume_token)

    def shutdown(self) -> None:
        self.client.shutdown()


__all__ = [
    "UsbChannelClient", "UsbChannelHost", "_USB_CHANNEL_LABEL",
]
