"""WebSocket-transport variant of :class:`RemoteDesktopHost`.

The only thing this subclass overrides is the per-connection channel
factory: each accepted (optionally TLS-wrapped) socket performs an HTTP
upgrade handshake before being handed to the shared client-handler
machinery. Auth, capture, frame broadcast, and input dispatch all
remain identical, so `wss://` is just `ws://` over the same
``ssl_context`` already supported by the parent.
"""
import socket

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.transport import (
    MessageChannel, WsMessageChannel,
)
from je_auto_control.utils.remote_desktop.ws_protocol import (
    WsProtocolError, server_handshake,
)

_HANDSHAKE_TIMEOUT_S = 5.0


class WebSocketDesktopHost(RemoteDesktopHost):
    """Speak the same protocol as :class:`RemoteDesktopHost` over WebSockets."""

    def _build_channel(self, sock: socket.socket,
                       address) -> MessageChannel:
        del address
        sock.settimeout(_HANDSHAKE_TIMEOUT_S)
        try:
            server_handshake(sock)
        except (WsProtocolError, OSError) as error:
            raise RuntimeError(
                f"websocket handshake failed: {error}"
            ) from error
        sock.settimeout(None)
        return WsMessageChannel(sock, mask_outgoing=False)
