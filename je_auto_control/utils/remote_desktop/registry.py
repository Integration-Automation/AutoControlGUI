"""Process-global singletons used by AC_remote_* executor commands.

JSON action scripts and the GUI both want to talk to one running host
and at most one active viewer without juggling handles. Holding those
references here keeps :mod:`action_executor` thin and avoids circular
imports between the executor and the host/viewer classes.
"""
from typing import Any, Callable, Dict, Optional, Sequence

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer

FrameCallback = Callable[[bytes], None]
ErrorCallback = Callable[[Exception], None]


class _RemoteDesktopRegistry:
    """Hold one host + one viewer for the executor command surface."""

    def __init__(self) -> None:
        self._host: Optional[RemoteDesktopHost] = None
        self._viewer: Optional[RemoteDesktopViewer] = None

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
                   max_clients: int = 4) -> Dict[str, Any]:
        """Stop any existing host, then start a fresh one with the given config."""
        self.stop_host()
        host = RemoteDesktopHost(
            token=token, bind=bind, port=int(port),
            fps=float(fps), quality=int(quality),
            region=region, max_clients=int(max_clients),
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
            return {"running": False, "port": 0, "connected_clients": 0}
        return {
            "running": host.is_running,
            "port": host.port,
            "connected_clients": host.connected_clients,
        }

    def connect_viewer(self, host: str, port: int, token: str,
                       timeout: float = 5.0,
                       on_frame: Optional[FrameCallback] = None,
                       on_error: Optional[ErrorCallback] = None,
                       ) -> Dict[str, Any]:
        """Disconnect any existing viewer, then connect a fresh one.

        ``on_frame`` and ``on_error`` are wired before the receiver
        thread starts, so no frame can arrive while the GUI is still
        attaching its callbacks.
        """
        self.disconnect_viewer()
        viewer = RemoteDesktopViewer(
            host=host, port=int(port), token=token,
            on_frame=on_frame, on_error=on_error,
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
            return {"connected": False}
        return {"connected": viewer.connected}

    def send_input(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Forward ``action`` through the connected viewer, raise if offline."""
        if self._viewer is None or not self._viewer.connected:
            raise ConnectionError("no remote viewer is connected")
        self._viewer.send_input(action)
        return {"sent": True}


registry = _RemoteDesktopRegistry()
