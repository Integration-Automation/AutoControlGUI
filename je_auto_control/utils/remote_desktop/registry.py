"""Session-owned remote transports with compatible per-transport script defaults."""

import ssl
import threading
from typing import Any, Callable, Dict, Optional, Sequence

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.registry_sessions import RegistrySessions
from je_auto_control.utils.remote_desktop.sessions import SessionDirectory
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.remote_desktop.ws_host import WebSocketDesktopHost
from je_auto_control.utils.remote_desktop.ws_viewer import WebSocketDesktopViewer

FrameCallback = Callable[[bytes], None]
ErrorCallback = Callable[[Exception], None]


def _load_webrtc_classes():
    """Lazy import — aiortc/av are optional extras; absent ⇒ (None, None, None)."""
    try:
        # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
        from je_auto_control.utils.remote_desktop.webrtc_host import WebRTCDesktopHost

        # pylint: enable=import-outside-toplevel
        # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
        from je_auto_control.utils.remote_desktop.webrtc_transport import WebRTCConfig

        # pylint: enable=import-outside-toplevel
        # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
        from je_auto_control.utils.remote_desktop.webrtc_viewer import WebRTCDesktopViewer
        # pylint: enable=import-outside-toplevel
    except ImportError:
        return (None, None, None)
    return (WebRTCDesktopHost, WebRTCDesktopViewer, WebRTCConfig)


class _RemoteDesktopRegistry(RegistrySessions):  # pylint: disable=too-many-public-methods  # reason: compatible transport facade
    """Own independent GUI connections and legacy script aliases."""

    def __init__(self) -> None:
        self._sessions = SessionDirectory()
        self._operation_lock = threading.RLock()

    @property
    def host(self) -> Optional[RemoteDesktopHost]:
        """Read the TCP script-default host."""
        return self._host

    @property
    def viewer(self) -> Optional[RemoteDesktopViewer]:
        """Read the TCP script-default viewer."""
        return self._viewer

    # pylint: disable=too-many-arguments,too-many-positional-arguments  # reason: preserve existing positional API
    def start_host(
        self,
        token: str,
        bind: str = "127.0.0.1",
        port: int = 0,
        fps: float = 10.0,
        quality: int = 70,
        region: Optional[Sequence[int]] = None,
        max_clients: int = 4,
        host_id: Optional[str] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Allocate one owned tcp host; omitted identity replaces only its script default."""
        identifier = self._allocate_resource(
            "tcp",
            "host",
            session_id,
            lambda identifier: RemoteDesktopHost(
                token=token,
                bind=bind,
                port=int(port),
                fps=float(fps),
                quality=int(quality),
                region=region,
                max_clients=int(max_clients),
                host_id=host_id,
                ssl_context=ssl_context,
            ),
            lambda resource: resource.start(),
        )
        return self.host_status(session_id=identifier)

    # pylint: enable=too-many-arguments,too-many-positional-arguments

    def stop_host(self, timeout: float = 2.0, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Stop only a named connection or the script transport default."""
        self._disconnect_alias("tcp", "host", session_id, timeout)
        return self.host_status(session_id=session_id)

    def host_status(self, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        host = self._resource(session_id, "tcp", "host")
        if host is None:
            return self._status_identity(
                {"running": False, "port": 0, "connected_clients": 0, "host_id": None}, "tcp", "host", session_id
            )
        return self._status_identity(
            {
                "running": host.is_running,
                "port": host.port,
                "connected_clients": host.connected_clients,
                "host_id": host.host_id,
            },
            "tcp",
            "host",
            session_id,
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments  # reason: preserve existing positional API
    def connect_viewer(
        self,
        host: str,
        port: int,
        token: str,
        timeout: float = 5.0,
        on_frame: Optional[FrameCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        expected_host_id: Optional[str] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        server_hostname: Optional[str] = None,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Allocate one owned tcp viewer; omitted identity replaces only its script default."""
        identifier = self._allocate_resource(
            "tcp",
            "viewer",
            session_id,
            lambda identifier: RemoteDesktopViewer(
                host=host,
                port=int(port),
                token=token,
                on_frame=None if on_frame is None else self.bind_callback(identifier, on_frame),
                on_error=None if on_error is None else self.bind_callback(identifier, on_error),
                expected_host_id=expected_host_id,
                ssl_context=ssl_context,
                server_hostname=server_hostname,
            ),
            lambda resource: resource.connect(timeout=float(timeout)),
        )
        return self.viewer_status(session_id=identifier)

    # pylint: enable=too-many-arguments,too-many-positional-arguments

    def disconnect_viewer(self, timeout: float = 2.0, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Stop only a named connection or the script transport default."""
        self._disconnect_alias("tcp", "viewer", session_id, timeout)
        return self.viewer_status(session_id=session_id)

    def viewer_status(self, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        viewer = self._resource(session_id, "tcp", "viewer")
        if viewer is None:
            return self._status_identity({"connected": False, "host_id": None}, "tcp", "viewer", session_id)
        return self._status_identity(
            {"connected": viewer.connected, "host_id": viewer.remote_host_id}, "tcp", "viewer", session_id
        )

    def send_input(self, action: Dict[str, Any], *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Forward ``action`` through the connected viewer, raise if offline."""
        viewer = self._resource(session_id, "tcp", "viewer")
        if viewer is None or not viewer.connected:
            raise ConnectionError("no remote viewer is connected")
        viewer.send_input(action)
        return {"sent": True}

    # pylint: disable=too-many-arguments,too-many-positional-arguments  # reason: preserve existing positional API
    def start_ws_host(
        self,
        token: str,
        bind: str = "127.0.0.1",
        port: int = 0,
        fps: float = 10.0,
        quality: int = 70,
        region: Optional[Sequence[int]] = None,
        max_clients: int = 4,
        host_id: Optional[str] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Allocate one owned ws host; omitted identity replaces only its script default."""
        identifier = self._allocate_resource(
            "ws",
            "host",
            session_id,
            lambda identifier: WebSocketDesktopHost(
                token=token,
                bind=bind,
                port=int(port),
                fps=float(fps),
                quality=int(quality),
                region=region,
                max_clients=int(max_clients),
                host_id=host_id,
                ssl_context=ssl_context,
            ),
            lambda resource: resource.start(),
        )
        return self.ws_host_status(session_id=identifier)

    # pylint: enable=too-many-arguments,too-many-positional-arguments

    def stop_ws_host(self, timeout: float = 2.0, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Stop only a named connection or the script transport default."""
        self._disconnect_alias("ws", "host", session_id, timeout)
        return self.ws_host_status(session_id=session_id)

    def ws_host_status(self, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        host = self._resource(session_id, "ws", "host")
        if host is None:
            return self._status_identity(
                {"running": False, "port": 0, "connected_clients": 0, "host_id": None}, "ws", "host", session_id
            )
        return self._status_identity(
            {
                "running": host.is_running,
                "port": host.port,
                "connected_clients": host.connected_clients,
                "host_id": host.host_id,
            },
            "ws",
            "host",
            session_id,
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments  # reason: preserve existing positional API
    def connect_ws_viewer(
        self,
        host: str,
        port: int,
        token: str,
        path: str = "/",
        timeout: float = 5.0,
        on_frame: Optional[FrameCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        expected_host_id: Optional[str] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        server_hostname: Optional[str] = None,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Allocate one owned ws viewer; omitted identity replaces only its script default."""
        identifier = self._allocate_resource(
            "ws",
            "viewer",
            session_id,
            lambda identifier: WebSocketDesktopViewer(
                host=host,
                port=int(port),
                token=token,
                on_frame=None if on_frame is None else self.bind_callback(identifier, on_frame),
                on_error=None if on_error is None else self.bind_callback(identifier, on_error),
                expected_host_id=expected_host_id,
                ssl_context=ssl_context,
                server_hostname=server_hostname,
                path=path,
            ),
            lambda resource: resource.connect(timeout=float(timeout)),
        )
        return self.ws_viewer_status(session_id=identifier)

    # pylint: enable=too-many-arguments,too-many-positional-arguments

    def disconnect_ws_viewer(self, timeout: float = 2.0, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Stop only a named connection or the script transport default."""
        self._disconnect_alias("ws", "viewer", session_id, timeout)
        return self.ws_viewer_status(session_id=session_id)

    def ws_viewer_status(self, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        viewer = self._resource(session_id, "ws", "viewer")
        if viewer is None:
            return self._status_identity({"connected": False, "host_id": None}, "ws", "viewer", session_id)
        return self._status_identity(
            {"connected": viewer.connected, "host_id": viewer.remote_host_id}, "ws", "viewer", session_id
        )

    def ws_send_input(self, action: Dict[str, Any], *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        viewer = self._resource(session_id, "ws", "viewer")
        if viewer is None or not viewer.connected:
            raise ConnectionError("no websocket viewer is connected")
        viewer.send_input(action)
        return {"sent": True}

    @staticmethod
    def _require_webrtc():
        host_cls, viewer_cls, config_cls = _load_webrtc_classes()
        if host_cls is None:
            raise RuntimeError("WebRTC support is unavailable: install the 'webrtc' extra")
        return (host_cls, viewer_cls, config_cls)

    def start_webrtc_host(
        self, token: str, config: Optional[Any] = None, read_only: bool = False, *, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Allocate one owned webrtc host; omitted identity replaces only its script default."""
        host_cls, _viewer_cls, _config_cls = self._require_webrtc()
        identifier = self._allocate_resource(
            "webrtc",
            "host",
            session_id,
            lambda identifier: host_cls(token=token, config=config, read_only=bool(read_only)),
            lambda resource: None,
        )
        return self.webrtc_host_status(session_id=identifier)

    def webrtc_create_offer(
        self, peer_label: str = "remote viewer", *, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        host = self._resource(session_id, "webrtc", "host")
        if host is None:
            raise RuntimeError("no WebRTC host is running")
        offer_sdp = host.create_offer(peer_label=peer_label)
        return {"offer_sdp": offer_sdp}

    def webrtc_accept_answer(self, answer_sdp: str, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        host = self._resource(session_id, "webrtc", "host")
        if host is None:
            raise RuntimeError("no WebRTC host is running")
        host.accept_answer(answer_sdp)
        return self.webrtc_host_status(session_id=session_id)

    def stop_webrtc_host(self, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Stop only a named connection or the script transport default."""
        self._disconnect_alias("webrtc", "host", session_id, 2.0)
        return self.webrtc_host_status(session_id=session_id)

    def webrtc_host_status(self, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        host = self._resource(session_id, "webrtc", "host")
        if host is None:
            return self._status_identity(
                {"running": False, "authenticated": False, "state": "closed"}, "webrtc", "host", session_id
            )
        list_sessions = getattr(host, "list_sessions", None)
        if callable(list_sessions):
            peers = list_sessions()  # pylint: disable=not-callable  # reason: runtime callable guard
            status = {
                "running": True,
                "authenticated": any(peer["authenticated"] for peer in peers),
                "state": "multi",
                "connected_clients": len(peers),
                "peers": peers,
            }
        else:
            status = {"running": True, "authenticated": host.authenticated, "state": host.connection_state}
        return self._status_identity(
            status,
            "webrtc",
            "host",
            session_id,
        )

    def start_webrtc_viewer(
        self,
        token: str,
        config: Optional[Any] = None,
        viewer_id: Optional[str] = None,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Allocate one owned webrtc viewer; omitted identity replaces only its script default."""
        _host_cls, viewer_cls, _config_cls = self._require_webrtc()
        identifier = self._allocate_resource(
            "webrtc",
            "viewer",
            session_id,
            lambda identifier: viewer_cls(token=token, config=config, viewer_id=viewer_id),
            lambda resource: None,
        )
        return self.webrtc_viewer_status(session_id=identifier)

    def webrtc_process_offer(
        self, offer_sdp: str, expected_dtls_fingerprint: Optional[str] = None, *, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        viewer = self._resource(session_id, "webrtc", "viewer")
        if viewer is None:
            raise RuntimeError("no WebRTC viewer is active")
        answer_sdp = viewer.process_offer(offer_sdp, expected_dtls_fingerprint=expected_dtls_fingerprint)
        return {"answer_sdp": answer_sdp}

    def webrtc_send_input(self, action: Dict[str, Any], *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        viewer = self._resource(session_id, "webrtc", "viewer")
        if viewer is None:
            raise RuntimeError("no WebRTC viewer is active")
        viewer.send_input(action)
        return {"sent": True}

    def stop_webrtc_viewer(self, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Stop only a named connection or the script transport default."""
        self._disconnect_alias("webrtc", "viewer", session_id, 2.0)
        return self.webrtc_viewer_status(session_id=session_id)

    def webrtc_viewer_status(self, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Operate on the named connection or the transport script default."""
        viewer = self._resource(session_id, "webrtc", "viewer")
        if viewer is None:
            return self._status_identity({"active": False, "authenticated": False}, "webrtc", "viewer", session_id)
        return self._status_identity(
            {"active": True, "authenticated": getattr(viewer, "authenticated", False)}, "webrtc", "viewer", session_id
        )

    def webrtc_usb_client(self, *, session_id: Optional[str] = None):
        """Return the live WebRTC viewer's USB passthrough client, or None.

        The viewer exposes ``usb_client()`` once the host has opened the
        ``usb`` DataChannel. Returns None when no WebRTC viewer is active
        or the channel hasn't been negotiated yet.
        """
        viewer = self._resource(session_id, "webrtc", "viewer")
        if viewer is None:
            return None
        getter = getattr(viewer, "usb_client", None)
        return getter() if callable(getter) else None  # pylint: disable=not-callable  # reason: guarded adapter


registry = _RemoteDesktopRegistry()
