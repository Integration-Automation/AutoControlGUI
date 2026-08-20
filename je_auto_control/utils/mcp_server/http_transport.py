"""HTTP transport for the MCP server.

Implements a Streamable HTTP transport so MCP clients that prefer HTTP — or
that need to reach the server from another process / container — can talk to
the same :class:`MCPServer` dispatcher already used by the stdio transport.

Notifications are answered with ``202 Accepted`` per the MCP spec;
ordinary requests return their JSON-RPC response with
``Content-Type: application/json``. The default bind is
``127.0.0.1`` to honour the project's least-privilege policy.

**Sessions.** ``initialize`` mints an ``Mcp-Session-Id`` and returns it as a
response header; a client that echoes it back keeps one dispatcher scope
across every connection it makes, and may open a standing server-to-client
SSE stream with ``GET``. That stream is what lets the server ask the client
something mid-call — the ``elicitation/create`` behind the destructive-action
confirmation gate. A client that ignores the header still works exactly as
before, scoped to its TCP connection, but cannot be prompted: there is no
channel to carry the question. See :mod:`.http_sessions`.
"""
import hmac
import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple

from je_auto_control.utils.http_headers import parse_content_length
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._protocol import (
    _notification_message,
)
from je_auto_control.utils.mcp_server.http_sessions import (
    HttpSession, SESSION_HEADER, SessionRegistry, session_id_from_headers,
)
from je_auto_control.utils.mcp_server.server import MCPServer

DEFAULT_PATH = "/mcp"
_MAX_BODY = 1_000_000
_SSE_MEDIA_TYPE = "text/event-stream"
# Cap drain reads so a hostile Content-Length can't make us spin forever.
_DRAIN_CHUNK = 64 * 1024
_DRAIN_CAP_MULTIPLE = 4
# Bound per-request reads so a client that declares a Content-Length then
# stalls (body underrun) can't pin a worker thread forever.
_REQUEST_TIMEOUT = 30.0
# Bound the TLS handshake so one silent client can't wedge the single accept
# thread waiting for a ClientHello that never arrives.
_HANDSHAKE_TIMEOUT = 10.0
# How often a standing GET stream writes an SSE comment. It keeps the session
# off the idle sweep and turns a client that vanished without a FIN into a
# write error instead of a thread parked forever.
_STREAM_HEARTBEAT = 15.0


def _is_initialize(line: str) -> bool:
    """True when ``line`` is an ``initialize`` request; tolerant of junk."""
    try:
        message = json.loads(line)
    except ValueError:
        return False
    return isinstance(message, dict) and message.get("method") == "initialize"


def _notifier_for(writer: Optional[Callable[[str], None]]):
    """Wrap a raw writer as a (method, params) notifier, or ``None``."""
    if writer is None:
        return None
    return lambda method, params: writer(
        _notification_message(method, params),
    )


class _MCPHttpHandler(BaseHTTPRequestHandler):
    """Bridges HTTP requests onto :meth:`MCPServer.handle_line`."""

    server_version = "AutoControlMCP/1.0"
    # Set once this request's body has been read off the socket, so a later
    # error response knows there is nothing left to drain.
    _body_consumed = False
    # socketserver applies this to the connection socket in setup(); it bounds
    # every read (headers *and* body) so a stalled request cannot pin a worker.
    timeout = _REQUEST_TIMEOUT

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
        session, resolved = self._resolve_session(line)
        if not resolved:
            return
        # Prefer the session's identity over the socket's: a client that
        # echoes Mcp-Session-Id keeps one scope — and so keeps the
        # capabilities it advertised at initialize — across connections.
        conn_id = session.id if session is not None else id(self)
        extra = {SESSION_HEADER: session.id} if session is not None else None
        if self._client_accepts_sse():
            self._dispatch_sse(bridge, line, conn_id, extra)
            return
        # A plain POST has no stream of its own, but a session may have a
        # standing GET stream; server-initiated traffic belongs on it. Absent
        # one there is no writer, rather than whichever other peer's socket
        # happens to be open.
        writer = session.stream_writer if session is not None else None
        with bridge.connection_scope(connection_id=conn_id, writer=writer,
                                      notifier=_notifier_for(writer)):
            response = bridge.handle_line(line)
        if response is None:
            # MCP notification — no body, ack with 202.
            self._send_blank(status=202)
            return
        self._send_raw_json(response, extra_headers=extra)

    def _resolve_session(self, line: str) -> Tuple[Optional[HttpSession],
                                                    bool]:
        """Resolve this request's session; False means a reply was sent.

        A request carrying an unknown or expired id is refused with 404
        rather than silently served under a fresh scope — the client has
        state we do not, and it needs to know to re-initialize.
        """
        registry: SessionRegistry = self.server.sessions  # type: ignore[attr-defined]
        header_id = session_id_from_headers(self.headers)
        if header_id is not None:
            session = registry.get(header_id)
            if session is None:
                self._send_json(
                    {"error": "unknown or expired session"}, status=404,
                )
                return None, False
            return session, True
        if _is_initialize(line):
            return registry.create(), True
        return None, True

    def finish(self) -> None:
        """Release this connection's per-peer server state, then close.

        Only the anonymous, connection-keyed scope is dropped here. State
        held under a session id outlives the socket by design and is
        released when the session is terminated, swept or evicted.
        """
        try:
            super().finish()
        finally:
            bridge = getattr(self.server, "mcp", None)
            if bridge is not None:
                bridge.forget_connection(id(self))

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

    def _dispatch_sse(self, bridge: MCPServer, line: str,
                      conn_id: Any,
                      extra_headers: Optional[Dict[str, str]] = None) -> None:
        """Stream progress notifications + the final response as SSE events."""
        # Force connection close so the client gets EOF after the last event.
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type",
                          f"{_SSE_MEDIA_TYPE}; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        send_lock = threading.Lock()

        def emit(payload: str) -> None:
            with send_lock:
                self.wfile.write(b"data: ")
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.write(b"\n\n")
                self.wfile.flush()

        # Bind this connection's emit to *this thread only*. Swapping the
        # attributes on the shared bridge (even under sse_lock) leaked across
        # peers: a plain POST deliberately skips that lock, reads the
        # server-global notifier, and so emitted its progress down whichever
        # SSE socket happened to be open — delivering one client's payload to
        # another. connection_scope keeps it thread-local instead.
        with bridge.connection_scope(
            notifier=lambda method, params: emit(
                _notification_message(method, params),
            ),
            writer=emit,
            concurrent_tools=False,
            connection_id=conn_id,
        ):
            response = bridge.handle_line(line)
            if response is not None:
                emit(response)

    def do_GET(self) -> None:  # noqa: N802  # reason: stdlib API
        """Open the session's standing server→client SSE stream."""
        if not self._authorize():
            return
        if self.path != DEFAULT_PATH:
            self._send_json({"error": "unknown path"}, status=404)
            return
        if not self._client_accepts_sse():
            self._send_json(
                {"error": f"GET requires Accept: {_SSE_MEDIA_TYPE}"},
                status=405,
            )
            return
        registry: SessionRegistry = self.server.sessions  # type: ignore[attr-defined]
        session = registry.get(session_id_from_headers(self.headers))
        if session is None:
            self._send_json(
                {"error": "unknown or expired session"}, status=404,
            )
            return
        self._stream_session(registry, session)

    def _stream_session(self, registry: SessionRegistry,
                        session: HttpSession) -> None:
        """Hold this socket open as the session's outbound channel."""
        self.close_connection = True
        send_lock = threading.Lock()

        def emit(payload: str) -> None:
            with send_lock:
                self.wfile.write(b"data: ")
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.write(b"\n\n")
                self.wfile.flush()

        # Claim the slot before writing headers, and write them under the
        # same lock, so an elicitation racing the handshake cannot land in
        # front of the status line.
        if not session.attach_stream(emit):
            self._send_json(
                {"error": "session already has an open stream"}, status=409,
            )
            return
        try:
            with send_lock:
                self.send_response(200)
                self.send_header("Content-Type",
                                  f"{_SSE_MEDIA_TYPE}; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.send_header(SESSION_HEADER, session.id)
                self.end_headers()
                self.wfile.flush()
            self._heartbeat_until_closed(registry, session, send_lock)
        except OSError as error:
            # The client went away, or stopped reading long enough for the
            # send to time out. Either way this stream is over.
            autocontrol_logger.info(
                "MCP session stream %s ended: %r", session.id, error,
            )
        finally:
            session.detach_stream(emit)

    def _heartbeat_until_closed(self, registry: SessionRegistry,
                                session: HttpSession,
                                send_lock: threading.Lock) -> None:
        """Write an SSE comment periodically until the session ends."""
        while not session.closed.wait(timeout=_STREAM_HEARTBEAT):
            # Touching through the registry both keeps this session off the
            # idle sweep and tells us when it has already been dropped.
            if registry.get(session.id) is None:
                return
            with send_lock:
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()

    def do_DELETE(self) -> None:  # noqa: N802  # reason: stdlib API
        """Terminate the session named by the header, if there is one."""
        if not self._authorize():
            return
        registry: SessionRegistry = self.server.sessions  # type: ignore[attr-defined]
        header_id = session_id_from_headers(self.headers)
        if header_id is None:
            # No session to drop — accept it so sessionless clients can
            # still run their cleanup unchanged.
            self._send_json({"status": "session terminated"})
            return
        if registry.terminate(header_id) is None:
            self._send_json(
                {"error": "unknown or expired session"}, status=404,
            )
            return
        self._send_json({"status": "session terminated"})

    # --- helpers -------------------------------------------------------------

    def _read_body(self) -> Optional[str]:
        length = parse_content_length(self.headers)
        if length <= 0 or length > _MAX_BODY:
            self._send_json({"error": "invalid Content-Length"}, status=400)
            return None
        raw = self.rfile.read(length)
        # From here the body is gone from the socket. Any 4xx we send later
        # must not try to drain it again: there is nothing left to read, so
        # the drain would block on the next request's bytes until the socket
        # timeout and pin this worker for thirty seconds.
        self._body_consumed = True
        try:
            return raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            self._send_json({"error": "body must be UTF-8"}, status=400)
            return None

    def _send_json(self, payload: Any, status: int = 200,
                   extra_headers: Optional[Dict[str, str]] = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._write_headers(status, body, extra_headers)
        self.wfile.write(body)
        if status >= 400:
            # Drain any unread request body before the socket closes.
            # Without this, Windows TCP turns "close with unread bytes"
            # into RST and the client surfaces WinError 10053 before it
            # can read the 4xx response.
            self._drain_body()

    def _drain_body(self) -> None:
        if self._body_consumed:
            return
        declared = parse_content_length(self.headers)
        if declared <= 0:
            return
        cap = min(declared, _MAX_BODY * _DRAIN_CAP_MULTIPLE)
        remaining = cap
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, _DRAIN_CHUNK))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError as error:
            # Draining is a courtesy to the client's read of our 4xx. If the
            # peer has already gone, there is nothing left to be courteous
            # about — and letting this escape logs a whole traceback for it.
            autocontrol_logger.debug("MCP drain aborted: %r", error)

    def _send_raw_json(self, raw_json: str,
                       extra_headers: Optional[Dict[str, str]] = None) -> None:
        body = raw_json.encode("utf-8")
        self._write_headers(200, body, extra_headers)
        self.wfile.write(body)

    def _send_blank(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _write_headers(self, status: int, body: bytes,
                       extra_headers: Optional[Dict[str, str]] = None,
                       ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()


class _MCPHttpServer(ThreadingHTTPServer):
    """ThreadingHTTPServer extension that owns an :class:`MCPServer`."""

    def __init__(self, server_address: Tuple[str, int],
                 mcp: MCPServer,
                 auth_token: Optional[str] = None) -> None:
        super().__init__(server_address, _MCPHttpHandler)
        self.mcp = mcp
        self.auth_token = auth_token
        # Dropping a session releases the dispatcher state scoped to its id —
        # the same release a closing socket used to perform, moved to the
        # identity that actually owns that state.
        self.sessions = SessionRegistry(
            on_drop=lambda session: mcp.forget_connection(session.id),
        )
        # No sse_lock: SSE requests used to swap server-wide notifier/writer
        # state and needed serialising. They now bind that state to their own
        # thread via MCPServer.connection_scope, so concurrent SSE streams no
        # longer race — and, unlike the lock, plain POSTs can no longer read
        # another connection's notifier either.

    def get_request(self) -> Tuple[Any, Any]:
        """Accept a connection, time-boxing any TLS handshake.

        For a TLS listener wrapped with ``do_handshake_on_connect=False`` the
        handshake is performed here (on the accept thread) under a timeout, so
        a client that connects but never sends a ClientHello is dropped
        instead of wedging the accept thread for every other peer. On timeout
        ``do_handshake`` raises ``OSError``, which ``serve_forever`` treats as
        a failed accept and discards cleanly.
        """
        conn, addr = super().get_request()
        if isinstance(conn, ssl.SSLSocket):
            conn.settimeout(_HANDSHAKE_TIMEOUT)
            try:
                conn.do_handshake()
            except OSError:
                conn.close()
                raise
        return conn, addr


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

    @property
    def sessions(self) -> Optional[SessionRegistry]:
        """The live session registry, or ``None`` before :meth:`start`."""
        return self._server.sessions if self._server is not None else None

    def start(self) -> None:
        """Bind the socket and begin serving on a background thread."""
        if self._server is not None:
            return
        self._server = _MCPHttpServer(
            self._address, self._mcp, auth_token=self._auth_token,
        )
        if self._ssl_context is not None:
            # Defer the handshake so it runs in get_request() under a timeout
            # rather than implicitly inside accept() with no bound.
            self._server.socket = self._ssl_context.wrap_socket(
                self._server.socket, server_side=True,
                do_handshake_on_connect=False,
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
        # Close the sessions first: a standing GET stream parks a worker on
        # its heartbeat, and terminating releases it without waiting one out.
        self._server.sessions.terminate_all()
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
