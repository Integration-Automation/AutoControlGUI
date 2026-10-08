"""Process-global singletons used by AC_remote_* executor commands.

JSON action scripts and the GUI both want to talk to one running host
and at most one active viewer per transport without juggling handles.
Holding those references here keeps :mod:`action_executor` thin and
avoids circular imports between the executor and the host/viewer
classes. Three transports are supported in parallel: plain TCP, WS
(``WebSocketDesktop*``) and WebRTC (``WebRTCDesktop*``); each has its
own host + viewer slot so JSON scripts can stand up, e.g., a TCP host
and a WebRTC viewer in the same process if they want to.

Ownership. The TCP and WebSocket slots are shared with the GUI panels, so
each occupant is recorded with the *owner* that put it there:

* ``AC_remote_*`` / ``AC_ws_*`` commands, the MCP ``ac_remote_*`` tools and
  any caller of the plain ``start_*`` / ``connect_*`` / ``stop_*`` /
  ``disconnect_*`` methods are the :data:`SCRIPT_OWNER`. They keep their
  documented meaning: they act on *the* active host or viewer of that
  transport whoever opened it, and the ``*_status`` dictionaries say who
  that is under ``"owner"``.
* A GUI panel takes a token from :func:`new_owner`, hands its host or
  viewer over with :meth:`_RemoteDesktopRegistry.adopt`, reads it back with
  :meth:`_RemoteDesktopRegistry.owned` and closes it with
  :meth:`_RemoteDesktopRegistry.release` - all three ignore a slot some
  other owner holds.

A slot still holds one occupant. When another owner replaces or closes it
(:meth:`_RemoteDesktopRegistry.adopt`, :meth:`_RemoteDesktopRegistry.evict`,
or the script-side methods above), the previous owner's ``on_displaced``
callback is called with ``(slot, by)`` so it can drop its window and state.
The callback runs on the thread that did the replacing.
"""
import itertools
import ssl
import threading
from typing import Any, Callable, Dict, NamedTuple, Optional, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.remote_desktop.ws_host import WebSocketDesktopHost
from je_auto_control.utils.remote_desktop.ws_viewer import (
    WebSocketDesktopViewer,
)

FrameCallback = Callable[[bytes], None]
ErrorCallback = Callable[[Exception], None]
#: ``on_displaced(slot, by)``: ``slot`` is the slot that was taken away and
#: ``by`` the owner that took it.
DisplacedCallback = Callable[[str, str], None]

#: Owner recorded for everything the executor commands and MCP tools open.
SCRIPT_OWNER = "script"

SLOT_HOST = "host"
SLOT_VIEWER = "viewer"
SLOT_WS_HOST = "ws_host"
SLOT_WS_VIEWER = "ws_viewer"
_SLOT_ATTRS = {
    SLOT_HOST: "_host", SLOT_VIEWER: "_viewer",
    SLOT_WS_HOST: "_ws_host", SLOT_WS_VIEWER: "_ws_viewer",
}
_HOST_SLOTS = (SLOT_HOST, SLOT_WS_HOST)
_owner_ids = itertools.count(1)


def new_owner(label: str) -> str:
    """Return an owner token unique in this process, e.g. ``"viewer-tab#3"``."""
    return f"{label}#{next(_owner_ids)}"


class _Claim(NamedTuple):
    """Who put ``resource`` in a slot and how to tell them it is gone."""

    resource: Any
    owner: str
    on_displaced: Optional[DisplacedCallback]


def _load_webrtc_classes():
    """Lazy import — aiortc/av are optional extras; absent ⇒ (None, None, None)."""
    try:
        from je_auto_control.utils.remote_desktop.webrtc_host import (
            WebRTCDesktopHost,
        )
        from je_auto_control.utils.remote_desktop.webrtc_viewer import (
            WebRTCDesktopViewer,
        )
        from je_auto_control.utils.remote_desktop.webrtc_transport import (
            WebRTCConfig,
        )
    except ImportError:
        return None, None, None
    return WebRTCDesktopHost, WebRTCDesktopViewer, WebRTCConfig


class _RemoteDesktopRegistry:
    """Hold one host + one viewer per transport for the executor surface."""

    def __init__(self) -> None:
        self._host: Optional[RemoteDesktopHost] = None
        self._viewer: Optional[RemoteDesktopViewer] = None
        self._ws_host: Optional[WebSocketDesktopHost] = None
        self._ws_viewer: Optional[WebSocketDesktopViewer] = None
        self._webrtc_host: Optional[Any] = None  # WebRTCDesktopHost
        self._webrtc_viewer: Optional[Any] = None  # WebRTCDesktopViewer
        self._claims: Dict[str, _Claim] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Ownership of the TCP / WebSocket slots
    # ------------------------------------------------------------------

    @staticmethod
    def _attr(slot: str) -> str:
        try:
            return _SLOT_ATTRS[slot]
        except KeyError:
            raise AutoControlException(
                f"unknown remote desktop slot {slot!r}; "
                f"expected one of {sorted(_SLOT_ATTRS)}"
            ) from None

    def _claim_of(self, slot: str) -> Optional[_Claim]:
        """Return the slot's occupant with its owner; call with the lock held.

        An occupant nobody adopted (a test that set the attribute directly)
        belongs to :data:`SCRIPT_OWNER`.
        """
        resource = getattr(self, self._attr(slot))
        if resource is None:
            return None
        claim = self._claims.get(slot)
        if claim is not None and claim.resource is resource:
            return claim
        return _Claim(resource, SCRIPT_OWNER, None)

    def _take(self, slot: str,
              only_owner: Optional[str] = None) -> Optional[_Claim]:
        """Empty ``slot`` and return what it held, or None if left alone."""
        with self._lock:
            claim = self._claim_of(slot)
            if claim is None:
                return None
            if only_owner is not None and claim.owner != only_owner:
                return None
            setattr(self, self._attr(slot), None)
            self._claims.pop(slot, None)
        return claim

    def _shut(self, slot: str, claim: _Claim, timeout: float, by: str) -> None:
        """Stop a displaced occupant, then tell its owner unless it asked."""
        try:
            if slot in _HOST_SLOTS:
                claim.resource.stop(timeout=timeout)
            else:
                claim.resource.disconnect(timeout=timeout)
        finally:
            if claim.owner != by:
                self._notify(slot, claim, by)

    @staticmethod
    def _notify(slot: str, claim: _Claim, by: str) -> None:
        callback = claim.on_displaced
        if callback is None:
            return
        try:
            callback(slot, by)
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: a displaced owner's callback must not undo the new owner's connect
            autocontrol_logger.warning(
                "remote desktop: %s owner %s failed handling displacement by %s: %r",
                slot, claim.owner, by, error,
            )

    def adopt(self, slot: str, resource: Any, owner: str,
              on_displaced: Optional[DisplacedCallback] = None,
              timeout: float = 2.0) -> None:
        """Put an already started host / connected viewer in ``slot`` for ``owner``.

        Whatever the slot held is stopped; its owner, when it is someone
        else, has ``on_displaced(slot, owner)`` called.
        """
        attr = self._attr(slot)
        with self._lock:
            previous = self._claim_of(slot)
            setattr(self, attr, resource)
            self._claims[slot] = _Claim(resource, owner, on_displaced)
        if previous is not None and previous.resource is not resource:
            self._shut(slot, previous, timeout, by=owner)

    def evict(self, slot: str, by: str, timeout: float = 2.0) -> bool:
        """Close whatever ``slot`` holds, whoever owns it; True if it held anything.

        The owner is told through ``on_displaced(slot, by)`` unless it is
        ``by`` itself. Panels call this before starting their own host or
        viewer, so the old one has let go of its port or its seat first.
        """
        claim = self._take(slot)
        if claim is None:
            return False
        self._shut(slot, claim, timeout, by=by)
        return True

    def release(self, slot: str, owner: str, timeout: float = 2.0) -> bool:
        """Close ``slot`` only if ``owner`` holds it; True if it was closed."""
        claim = self._take(slot, only_owner=owner)
        if claim is None:
            return False
        self._shut(slot, claim, timeout, by=owner)
        return True

    def owner_of(self, slot: str) -> Optional[str]:
        """Return the owner of ``slot``'s occupant, or None when it is empty."""
        with self._lock:
            claim = self._claim_of(slot)
        return None if claim is None else claim.owner

    def owned(self, slot: str, owner: str) -> Optional[Any]:
        """Return ``slot``'s host / viewer if ``owner`` holds it, else None."""
        with self._lock:
            claim = self._claim_of(slot)
        if claim is None or claim.owner != owner:
            return None
        return claim.resource

    def _close(self, slot: str, owner: Optional[str], timeout: float) -> None:
        if owner is None:
            self.evict(slot, by=SCRIPT_OWNER, timeout=timeout)
        else:
            self.release(slot, owner, timeout=timeout)

    def _host_status(self, slot: str) -> Dict[str, Any]:
        with self._lock:
            claim = self._claim_of(slot)
        if claim is None:
            return {
                "running": False, "port": 0, "connected_clients": 0,
                "host_id": None, "owner": None,
            }
        host = claim.resource
        return {
            "running": host.is_running,
            "port": host.port,
            "connected_clients": host.connected_clients,
            "host_id": host.host_id,
            "owner": claim.owner,
        }

    def _viewer_status(self, slot: str) -> Dict[str, Any]:
        with self._lock:
            claim = self._claim_of(slot)
        if claim is None:
            return {"connected": False, "host_id": None, "owner": None}
        return {
            "connected": claim.resource.connected,
            "host_id": claim.resource.remote_host_id,
            "owner": claim.owner,
        }

    # ------------------------------------------------------------------
    # TCP transport
    # ------------------------------------------------------------------

    @property
    def host(self) -> Optional[RemoteDesktopHost]:
        return self._host

    @property
    def viewer(self) -> Optional[RemoteDesktopViewer]:
        return self._viewer

    def start_host(self, token: str,
                   bind: str = "127.0.0.1",
                   port: int = 0,
                   fps: float = 10.0,
                   quality: int = 70,
                   region: Optional[Sequence[int]] = None,
                   max_clients: int = 4,
                   host_id: Optional[str] = None,
                   ssl_context: Optional[ssl.SSLContext] = None,
                   ) -> Dict[str, Any]:
        """Stop any existing host, then start a fresh one with the given config."""
        self.stop_host()
        host = RemoteDesktopHost(
            token=token, bind=bind, port=int(port),
            fps=float(fps), quality=int(quality),
            region=region, max_clients=int(max_clients),
            host_id=host_id, ssl_context=ssl_context,
        )
        host.start()
        self.adopt(SLOT_HOST, host, SCRIPT_OWNER)
        return self.host_status()

    def stop_host(self, timeout: float = 2.0,
                  owner: Optional[str] = None) -> Dict[str, Any]:
        """Stop the active host (if any) and clear the slot.

        With ``owner`` the host is stopped only if that owner started it.
        Without, it is stopped whoever started it and that owner is told.
        """
        self._close(SLOT_HOST, owner, timeout)
        return self.host_status()

    def host_status(self) -> Dict[str, Any]:
        """Describe the active host; ``"owner"`` names who started it."""
        return self._host_status(SLOT_HOST)

    def connect_viewer(self, host: str, port: int, token: str,
                       timeout: float = 5.0,
                       on_frame: Optional[FrameCallback] = None,
                       on_error: Optional[ErrorCallback] = None,
                       expected_host_id: Optional[str] = None,
                       ssl_context: Optional[ssl.SSLContext] = None,
                       server_hostname: Optional[str] = None,
                       ) -> Dict[str, Any]:
        """Disconnect any existing viewer, then connect a fresh one.

        ``on_frame`` and ``on_error`` are wired before the receiver
        thread starts, so no frame can arrive while the GUI is still
        attaching its callbacks. When ``expected_host_id`` is provided
        the handshake is rejected if the server reports a different ID.
        Pass an ``ssl_context`` to upgrade the connection to TLS.
        """
        self.disconnect_viewer()
        viewer = RemoteDesktopViewer(
            host=host, port=int(port), token=token,
            on_frame=on_frame, on_error=on_error,
            expected_host_id=expected_host_id,
            ssl_context=ssl_context,
            server_hostname=server_hostname,
        )
        viewer.connect(timeout=float(timeout))
        self.adopt(SLOT_VIEWER, viewer, SCRIPT_OWNER)
        return self.viewer_status()

    def disconnect_viewer(self, timeout: float = 2.0,
                          owner: Optional[str] = None) -> Dict[str, Any]:
        """Disconnect the active viewer (if any) and clear the slot.

        With ``owner`` the viewer is disconnected only if that owner opened
        it. Without, it is disconnected whoever opened it and that owner is
        told.
        """
        self._close(SLOT_VIEWER, owner, timeout)
        return self.viewer_status()

    def viewer_status(self) -> Dict[str, Any]:
        """Describe the active viewer; ``"owner"`` names who opened it."""
        return self._viewer_status(SLOT_VIEWER)

    def send_input(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Forward ``action`` through the connected viewer, raise if offline.

        The viewer is the active one, whoever opened it.
        """
        viewer = self._viewer
        if viewer is None or not viewer.connected:
            raise ConnectionError("no remote viewer is connected")
        viewer.send_input(action)
        return {"sent": True}

    # ------------------------------------------------------------------
    # WebSocket transport
    # ------------------------------------------------------------------

    def start_ws_host(self, token: str,
                      bind: str = "127.0.0.1",
                      port: int = 0,
                      fps: float = 10.0,
                      quality: int = 70,
                      region: Optional[Sequence[int]] = None,
                      max_clients: int = 4,
                      host_id: Optional[str] = None,
                      ssl_context: Optional[ssl.SSLContext] = None,
                      ) -> Dict[str, Any]:
        """Stop any existing WS host, then start a fresh one (wss:// when ssl)."""
        self.stop_ws_host()
        host = WebSocketDesktopHost(
            token=token, bind=bind, port=int(port),
            fps=float(fps), quality=int(quality),
            region=region, max_clients=int(max_clients),
            host_id=host_id, ssl_context=ssl_context,
        )
        host.start()
        self.adopt(SLOT_WS_HOST, host, SCRIPT_OWNER)
        return self.ws_host_status()

    def stop_ws_host(self, timeout: float = 2.0,
                     owner: Optional[str] = None) -> Dict[str, Any]:
        """Stop the WS host; with ``owner``, only if that owner started it."""
        self._close(SLOT_WS_HOST, owner, timeout)
        return self.ws_host_status()

    def ws_host_status(self) -> Dict[str, Any]:
        """Describe the active WS host; ``"owner"`` names who started it."""
        return self._host_status(SLOT_WS_HOST)

    def connect_ws_viewer(self, host: str, port: int, token: str,
                          path: str = "/",
                          timeout: float = 5.0,
                          on_frame: Optional[FrameCallback] = None,
                          on_error: Optional[ErrorCallback] = None,
                          expected_host_id: Optional[str] = None,
                          ssl_context: Optional[ssl.SSLContext] = None,
                          server_hostname: Optional[str] = None,
                          ) -> Dict[str, Any]:
        """Disconnect any existing WS viewer, then connect a fresh one."""
        self.disconnect_ws_viewer()
        viewer = WebSocketDesktopViewer(
            host=host, port=int(port), token=token,
            on_frame=on_frame, on_error=on_error,
            expected_host_id=expected_host_id,
            ssl_context=ssl_context,
            server_hostname=server_hostname,
            path=path,
        )
        viewer.connect(timeout=float(timeout))
        self.adopt(SLOT_WS_VIEWER, viewer, SCRIPT_OWNER)
        return self.ws_viewer_status()

    def disconnect_ws_viewer(self, timeout: float = 2.0,
                             owner: Optional[str] = None) -> Dict[str, Any]:
        """Disconnect the WS viewer; with ``owner``, only if that owner opened it."""
        self._close(SLOT_WS_VIEWER, owner, timeout)
        return self.ws_viewer_status()

    def ws_viewer_status(self) -> Dict[str, Any]:
        """Describe the active WS viewer; ``"owner"`` names who opened it."""
        return self._viewer_status(SLOT_WS_VIEWER)

    def ws_send_input(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Forward ``action`` through the active WS viewer, whoever opened it."""
        viewer = self._ws_viewer
        if viewer is None or not viewer.connected:
            raise ConnectionError("no websocket viewer is connected")
        viewer.send_input(action)
        return {"sent": True}

    # ------------------------------------------------------------------
    # WebRTC transport (optional — requires aiortc + av)
    # ------------------------------------------------------------------

    @staticmethod
    def _require_webrtc():
        host_cls, viewer_cls, config_cls = _load_webrtc_classes()
        if host_cls is None:
            raise RuntimeError(
                "WebRTC support is unavailable: install the 'webrtc' extra"
            )
        return host_cls, viewer_cls, config_cls

    def start_webrtc_host(self, token: str,
                          config: Optional[Any] = None,
                          read_only: bool = False,
                          ) -> Dict[str, Any]:
        """Build a WebRTC host with manual SDP signaling.

        The caller must follow up with :meth:`webrtc_create_offer` and
        :meth:`webrtc_accept_answer` to complete the handshake; this
        method only allocates the host singleton.
        """
        host_cls, _viewer_cls, _config_cls = self._require_webrtc()
        self.stop_webrtc_host()
        host = host_cls(
            token=token, config=config, read_only=bool(read_only),
        )
        self._webrtc_host = host
        return self.webrtc_host_status()

    def webrtc_create_offer(self,
                            peer_label: str = "remote viewer") -> Dict[str, Any]:
        if self._webrtc_host is None:
            raise RuntimeError("no WebRTC host is running")
        offer_sdp = self._webrtc_host.create_offer(peer_label=peer_label)
        return {"offer_sdp": offer_sdp}

    def webrtc_accept_answer(self, answer_sdp: str) -> Dict[str, Any]:
        if self._webrtc_host is None:
            raise RuntimeError("no WebRTC host is running")
        self._webrtc_host.accept_answer(answer_sdp)
        return self.webrtc_host_status()

    def stop_webrtc_host(self) -> Dict[str, Any]:
        if self._webrtc_host is not None:
            try:
                self._webrtc_host.stop()
            finally:
                self._webrtc_host = None
        return self.webrtc_host_status()

    def webrtc_host_status(self) -> Dict[str, Any]:
        host = self._webrtc_host
        if host is None:
            return {"running": False, "authenticated": False, "state": "closed"}
        return {
            "running": True,
            "authenticated": host.authenticated,
            "state": host.connection_state,
        }

    def start_webrtc_viewer(self, token: str,
                            config: Optional[Any] = None,
                            viewer_id: Optional[str] = None,
                            ) -> Dict[str, Any]:
        """Build a WebRTC viewer; call :meth:`webrtc_process_offer` next."""
        _host_cls, viewer_cls, _config_cls = self._require_webrtc()
        self.stop_webrtc_viewer()
        viewer = viewer_cls(
            token=token, config=config, viewer_id=viewer_id,
        )
        self._webrtc_viewer = viewer
        return self.webrtc_viewer_status()

    def webrtc_process_offer(self, offer_sdp: str,
                             expected_dtls_fingerprint: Optional[str] = None,
                             ) -> Dict[str, Any]:
        if self._webrtc_viewer is None:
            raise RuntimeError("no WebRTC viewer is active")
        answer_sdp = self._webrtc_viewer.process_offer(
            offer_sdp,
            expected_dtls_fingerprint=expected_dtls_fingerprint,
        )
        return {"answer_sdp": answer_sdp}

    def webrtc_send_input(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self._webrtc_viewer is None:
            raise RuntimeError("no WebRTC viewer is active")
        self._webrtc_viewer.send_input(action)
        return {"sent": True}

    def stop_webrtc_viewer(self) -> Dict[str, Any]:
        if self._webrtc_viewer is not None:
            try:
                self._webrtc_viewer.stop()
            finally:
                self._webrtc_viewer = None
        return self.webrtc_viewer_status()

    def webrtc_viewer_status(self) -> Dict[str, Any]:
        viewer = self._webrtc_viewer
        if viewer is None:
            return {"active": False, "authenticated": False}
        return {
            "active": True,
            "authenticated": getattr(viewer, "authenticated", False),
        }

    def webrtc_usb_client(self):
        """Return the live WebRTC viewer's USB passthrough client, or None.

        The viewer exposes ``usb_client()`` once the host has opened the
        ``usb`` DataChannel. Returns None when no WebRTC viewer is active
        or the channel hasn't been negotiated yet.
        """
        viewer = self._webrtc_viewer
        if viewer is None:
            return None
        getter = getattr(viewer, "usb_client", None)
        # pylint: disable=not-callable  # reason: guarded by callable(getter)
        return getter() if callable(getter) else None


registry = _RemoteDesktopRegistry()
