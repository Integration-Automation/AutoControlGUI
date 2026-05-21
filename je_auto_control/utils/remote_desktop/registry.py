"""Process-global singletons used by AC_remote_* executor commands.

JSON action scripts and the GUI both want to talk to one running host
and at most one active viewer per transport without juggling handles.
Holding those references here keeps :mod:`action_executor` thin and
avoids circular imports between the executor and the host/viewer
classes. Three transports are supported in parallel: plain TCP, WS
(``WebSocketDesktop*``) and WebRTC (``WebRTCDesktop*``); each has its
own host + viewer slot so JSON scripts can stand up, e.g., a TCP host
and a WebRTC viewer in the same process if they want to.
"""
import ssl
from typing import Any, Callable, Dict, Optional, Sequence

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.remote_desktop.ws_host import WebSocketDesktopHost
from je_auto_control.utils.remote_desktop.ws_viewer import (
    WebSocketDesktopViewer,
)

FrameCallback = Callable[[bytes], None]
ErrorCallback = Callable[[Exception], None]


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
        self._host = host
        return self.host_status()

    def stop_host(self, timeout: float = 2.0) -> Dict[str, Any]:
        """Stop the active host (if any) and clear the slot."""
        if self._host is not None:
            self._host.stop(timeout=timeout)
            self._host = None
        return self.host_status()

    def host_status(self) -> Dict[str, Any]:
        host = self._host
        if host is None:
            return {
                "running": False, "port": 0, "connected_clients": 0,
                "host_id": None,
            }
        return {
            "running": host.is_running,
            "port": host.port,
            "connected_clients": host.connected_clients,
            "host_id": host.host_id,
        }

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
        self._viewer = viewer
        return self.viewer_status()

    def disconnect_viewer(self, timeout: float = 2.0) -> Dict[str, Any]:
        """Disconnect the active viewer (if any) and clear the slot."""
        if self._viewer is not None:
            self._viewer.disconnect(timeout=timeout)
            self._viewer = None
        return self.viewer_status()

    def viewer_status(self) -> Dict[str, Any]:
        viewer = self._viewer
        if viewer is None:
            return {"connected": False, "host_id": None}
        return {
            "connected": viewer.connected,
            "host_id": viewer.remote_host_id,
        }

    def send_input(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Forward ``action`` through the connected viewer, raise if offline."""
        if self._viewer is None or not self._viewer.connected:
            raise ConnectionError("no remote viewer is connected")
        self._viewer.send_input(action)
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
        self._ws_host = host
        return self.ws_host_status()

    def stop_ws_host(self, timeout: float = 2.0) -> Dict[str, Any]:
        if self._ws_host is not None:
            self._ws_host.stop(timeout=timeout)
            self._ws_host = None
        return self.ws_host_status()

    def ws_host_status(self) -> Dict[str, Any]:
        host = self._ws_host
        if host is None:
            return {
                "running": False, "port": 0, "connected_clients": 0,
                "host_id": None,
            }
        return {
            "running": host.is_running,
            "port": host.port,
            "connected_clients": host.connected_clients,
            "host_id": host.host_id,
        }

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
        self._ws_viewer = viewer
        return self.ws_viewer_status()

    def disconnect_ws_viewer(self, timeout: float = 2.0) -> Dict[str, Any]:
        if self._ws_viewer is not None:
            self._ws_viewer.disconnect(timeout=timeout)
            self._ws_viewer = None
        return self.ws_viewer_status()

    def ws_viewer_status(self) -> Dict[str, Any]:
        viewer = self._ws_viewer
        if viewer is None:
            return {"connected": False, "host_id": None}
        return {
            "connected": viewer.connected,
            "host_id": viewer.remote_host_id,
        }

    def ws_send_input(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self._ws_viewer is None or not self._ws_viewer.connected:
            raise ConnectionError("no websocket viewer is connected")
        self._ws_viewer.send_input(action)
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


registry = _RemoteDesktopRegistry()
