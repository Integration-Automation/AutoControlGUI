"""WebSocket-transport variant of :class:`RemoteDesktopViewer`.

Mirrors :class:`WebSocketDesktopHost`: the only difference from the TCP
viewer is that the connect-time channel factory performs an HTTP upgrade
handshake before falling back to the shared auth + receive loop.
"""
import socket

from je_auto_control.utils.remote_desktop.transport import (
    MessageChannel, WsMessageChannel,
)
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.remote_desktop.ws_protocol import client_handshake

_DEFAULT_PATH = "/"


class WebSocketDesktopViewer(RemoteDesktopViewer):
    """Speak the same protocol as :class:`RemoteDesktopViewer` over WebSockets."""

    def __init__(self, *args, path: str = _DEFAULT_PATH, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("path must be an absolute URL path starting with '/'")
        self._ws_path = path

    def _build_channel(self, sock: socket.socket) -> MessageChannel:
        client_handshake(sock, self._host, self._port, path=self._ws_path)
        return WsMessageChannel(sock, mask_outgoing=True)
