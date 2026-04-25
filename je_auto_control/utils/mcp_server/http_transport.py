"""HTTP transport for the MCP server.

Implements a minimal Streamable HTTP transport (JSON-only, no SSE
streaming) so MCP clients that prefer HTTP — or that need to reach
the server from another process / container — can talk to the same
:class:`MCPServer` dispatcher already used by the stdio transport.

Notifications are answered with ``202 Accepted`` per the MCP spec;
ordinary requests return their JSON-RPC response with
``Content-Type: application/json``. The default bind is
``127.0.0.1`` to honour the project's least-privilege policy.
"""
import hmac
import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.server import (
    MCPServer, _notification_message,
)

DEFAULT_PATH = "/mcp"
_MAX_BODY = 1_000_000
_SSE_MEDIA_TYPE = "text/event-stream"


class _MCPHttpHandler(BaseHTTPRequestHandler):
    """Bridges HTTP requests onto :meth:`MCPServer.handle_line`."""

    server_version = "AutoControlMCP/1.0"

    # Suppress default stderr access logs — route through project logger.
    def log_message(self, format, *args) -> None:  # noqa: A002  # pylint: disable=redefined-builtin  # reason: stdlib override
        autocontrol_logger.info("mcp-http %s - %s",
                                self.address_string(), format % args)

    def do_POST(self) -> None:  # noqa: N802  # reason: stdlib API
        if not self._authorize():
            return
        if self.path != DEFAULT_PATH:
            self._send_json({"error": "unknown path"}, status=404)
            return
        line = self._read_body()
        if line is None:
            return
        bridge: MCPServer = self.server.mcp  # type: ignore[attr-defined]
        if self._client_accepts_sse():
            self._dispatch_sse(bridge, line)
            return
        response = bridge.handle_line(line)
        if response is None:
            # MCP notification — no body, ack with 202.
            self._send_blank(status=202)
            return
        self._send_raw_json(response)

    def _authorize(self) -> bool:
        """Validate Bearer token if the server has one configured."""
        expected: Optional[str] = self.server.auth_token  # type: ignore[attr-defined]
        if expected is None:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            self._send_json({"error": "missing bearer token"}, status=401)
            return False
        provided = header[len("Bearer "):].strip()
        if not hmac.compare_digest(provided, expected):
            self._send_json({"error": "invalid bearer token"}, status=403)
            return False
        return True

    def _client_accepts_sse(self) -> bool:
        accept = self.headers.get("Accept", "")
        return _SSE_MEDIA_TYPE in accept

    def _dispatch_sse(self, bridge: MCPServer, line: str) -> None:
        """Stream progress notifications + the final response as SSE events."""
        # Force connection close so the client gets EOF after the last event.
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type",
                          f"{_SSE_MEDIA_TYPE}; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        send_lock = threading.Lock()

        def emit(payload: str) -> None:
            with send_lock:
                self.wfile.write(b"data: ")
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.write(b"\n\n")
                self.wfile.flush()

        sse_lock = self.server.sse_lock  # type: ignore[attr-defined]
        with sse_lock:
            saved = (bridge._notifier, bridge._writer,
                      bridge._concurrent_tools)
            bridge._notifier = lambda method, params: emit(
                _notification_message(method, params),
            )
            bridge._writer = emit
            bridge._concurrent_tools = False
            try:
                response = bridge.handle_line(line)
                if response is not None:
                    emit(response)
            finally:
                bridge._notifier, bridge._writer, bridge._concurrent_tools = saved

    def do_GET(self) -> None:  # noqa: N802  # reason: stdlib API
        if not self._authorize():
            return
        # MCP optionally allows server→client SSE on GET; not used here.
        self._send_json({"error": "GET stream not supported"}, status=405)

    def do_DELETE(self) -> None:  # noqa: N802  # reason: stdlib API
        if not self._authorize():
            return
        # Sessionless server — accept the terminate so clients can cleanup.
        self._send_json({"status": "session terminated"})

    # --- helpers -------------------------------------------------------------

    def _read_body(self) -> Optional[str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > _MAX_BODY:
            self._send_json({"error": "invalid Content-Length"}, status=400)
            return None
        raw = self.rfile.read(length)
        try:
            return raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            self._send_json({"error": "body must be UTF-8"}, status=400)
            return None

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._write_headers(status, body)
        self.wfile.write(body)

    def _send_raw_json(self, raw_json: str) -> None:
        body = raw_json.encode("utf-8")
        self._write_headers(200, body)
        self.wfile.write(body)

    def _send_blank(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _write_headers(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()


class _MCPHttpServer(ThreadingHTTPServer):
    """ThreadingHTTPServer extension that owns an :class:`MCPServer`."""

    def __init__(self, server_address: Tuple[str, int],
                 mcp: MCPServer,
                 auth_token: Optional[str] = None) -> None:
        super().__init__(server_address, _MCPHttpHandler)
        self.mcp = mcp
        self.auth_token = auth_token
        # Serialise SSE requests — they swap server-wide notifier/writer
        # state, so concurrent SSE streams would race. POST-without-SSE
        # requests don't take this lock and remain fully concurrent.
        self.sse_lock = threading.Lock()


class HttpMCPServer:
    """Threaded HTTP transport for the MCP dispatcher."""

    def __init__(self, mcp: Optional[MCPServer] = None,
                 host: str = "127.0.0.1", port: int = 9940,
                 auth_token: Optional[str] = None,
                 ssl_context: Optional[ssl.SSLContext] = None,
                 ) -> None:
        self._mcp = mcp if mcp is not None else MCPServer()
        self._address: Tuple[str, int] = (host, port)
        self._auth_token = auth_token if auth_token is not None else (
            os.environ.get("JE_AUTOCONTROL_MCP_TOKEN") or None
        )
        self._ssl_context = ssl_context
        self._server: Optional[_MCPHttpServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def address(self) -> Tuple[str, int]:
        """Return the resolved (host, port) tuple after :meth:`start`."""
        return self._address

    @property
    def mcp(self) -> MCPServer:
        return self._mcp

    def start(self) -> None:
        """Bind the socket and begin serving on a background thread."""
        if self._server is not None:
            return
        self._server = _MCPHttpServer(
            self._address, self._mcp, auth_token=self._auth_token,
        )
        if self._ssl_context is not None:
            self._server.socket = self._ssl_context.wrap_socket(
                self._server.socket, server_side=True,
            )
        self._address = self._server.server_address[:2]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True,
            name="AutoControlMCPHttp",
        )
        self._thread.start()
        scheme = "https" if self._ssl_context is not None else "http"
        autocontrol_logger.info("MCP %s listening on %s:%d", scheme,
                                 *self._address)

    def stop(self, timeout: float = 2.0) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._server = None
        self._thread = None


def start_mcp_http_server(host: str = "127.0.0.1", port: int = 9940,
                          mcp: Optional[MCPServer] = None,
                          auth_token: Optional[str] = None,
                          ssl_context: Optional[ssl.SSLContext] = None,
                          ) -> HttpMCPServer:
    """Start and return an :class:`HttpMCPServer`; convenience wrapper."""
    server = HttpMCPServer(
        mcp=mcp, host=host, port=port,
        auth_token=auth_token, ssl_context=ssl_context,
    )
    server.start()
    return server


__all__ = ["HttpMCPServer", "start_mcp_http_server"]
