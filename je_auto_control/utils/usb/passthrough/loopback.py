"""In-process loopback transport for USB passthrough.

Wires a viewer-side :class:`UsbPassthroughClient` directly to a local
:class:`UsbPassthroughSession`, so the same machine can both *share* and
*use* a USB device with no WebRTC DataChannel in between. A daemon pump
thread routes client→host frames into the session and feeds the host's
replies back to the client.

This is the headless engine the AnyDesk-style USB panel drives, and it
is the clean seam where a real remote transport plugs in later: anything
that supplies a ``send_frame`` callable and calls ``client.feed_frame``
on inbound frames is a drop-in replacement for :class:`LoopbackTransport`.

Qt-free on purpose — importing it never drags in PySide6.
"""
from __future__ import annotations

import queue
import threading
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.passthrough.acl import UsbAcl
from je_auto_control.utils.usb.passthrough.backend import (
    UsbBackend, default_passthrough_backend,
)
from je_auto_control.utils.usb.passthrough.protocol import Frame
from je_auto_control.utils.usb.passthrough.session import UsbPassthroughSession
from je_auto_control.utils.usb.passthrough.viewer_client import (
    ClientHandle, UsbPassthroughClient,
)


_PUMP_POLL_S = 0.2
_JOIN_TIMEOUT_S = 2.0


class LoopbackTransport:
    """Routes frames between a client and a local session on a pump thread."""

    def __init__(self, session: UsbPassthroughSession) -> None:
        self._session = session
        self._queue: "queue.Queue[Optional[Frame]]" = queue.Queue()
        self._client: Optional[UsbPassthroughClient] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def bind(self, client: UsbPassthroughClient) -> None:
        """Attach the client whose replies this transport will feed."""
        self._client = client

    def send_frame(self, frame: Frame) -> None:
        """Client-side ``send_frame`` callable — enqueue for the pump."""
        self._queue.put(frame)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        thread = threading.Thread(
            target=self._pump, name="usb-loopback", daemon=True,
        )
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)  # unblock the pump immediately
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=_JOIN_TIMEOUT_S)

    def _pump(self) -> None:
        while not self._stop.is_set():
            try:
                frame = self._queue.get(timeout=_PUMP_POLL_S)
            except queue.Empty:
                continue
            if frame is None:
                return
            self._route(frame)

    def _route(self, frame: Frame) -> None:
        try:
            replies = self._session.handle_frame(frame)
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: a session error must not kill the pump thread
            autocontrol_logger.warning(
                "usb loopback: session.handle_frame raised %r", error,
            )
            return
        client = self._client
        if client is None:
            return
        for reply in replies:
            client.feed_frame(reply)


class UsbLoopback:
    """Bundled session + loopback transport + client for same-machine use.

    ``list_devices`` / ``open`` drive the full protocol stack (frames,
    ACL gating, credit flow control) exactly as a remote viewer would,
    just over an in-process transport. Use as a context manager or call
    :meth:`close` when done.
    """

    def __init__(self, *, backend: Optional[UsbBackend] = None,
                 acl: Optional[UsbAcl] = None,
                 prompt_callback: Optional[
                     Callable[[str, str, Optional[str]], bool]
                 ] = None,
                 viewer_id: str = "loopback",
                 max_claims: int = 4,
                 reply_timeout_s: float = 10.0) -> None:
        self.session = UsbPassthroughSession(
            backend if backend is not None else default_passthrough_backend(),
            acl=acl, prompt_callback=prompt_callback,
            viewer_id=viewer_id, max_claims=max_claims,
        )
        self.transport = LoopbackTransport(self.session)
        self.client = UsbPassthroughClient(
            send_frame=self.transport.send_frame,
            reply_timeout_s=reply_timeout_s,
        )
        self.transport.bind(self.client)
        self.transport.start()
        self._closed = False

    def list_devices(self) -> List[Dict[str, Any]]:
        """Enumerate ACL-visible devices over the loopback channel."""
        return self.client.list_devices()

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> ClientHandle:
        """Claim a device; returns a viewer-side handle for transfers."""
        return self.client.open(
            vendor_id=vendor_id, product_id=product_id, serial=serial,
        )

    def close(self) -> None:
        """Tear down client, transport, and host claims. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self.client.shutdown()
        self.transport.stop()
        self.session.close_all()

    def __enter__(self) -> "UsbLoopback":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


__all__ = ["LoopbackTransport", "UsbLoopback"]
