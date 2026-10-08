"""HTTP transport for the MCP server.

Implements a Streamable HTTP transport so MCP clients that prefer HTTP — or
that need to reach the server from another process / container — can talk to
the same :class:`MCPServer` dispatcher already used by the stdio transport.

Notifications are answered with ``202 Accepted`` per the MCP spec;
ordinary requests return their JSON-RPC response with
``Content-Type: application/json``. The default bind is
``127.0.0.1`` to honour the project's least-privilege policy.

**RBAC.** With a user store -- ``user_store=`` or ``JE_AUTOCONTROL_RBAC_USERS``
-- a bearer token must be one user's, the shared ``auth_token`` is not
accepted, and each request is dispatched as that user (:mod:`._authz`).

**Sessions.** ``initialize`` mints an ``Mcp-Session-Id`` and returns it as a
response header; a client that echoes it back keeps one dispatcher scope
across every connection it makes, and may open a standing server-to-client
SSE stream with ``GET``. That stream is what lets the server ask the client
something mid-call — the ``elicitation/create`` behind the destructive-action
confirmation gate. A client that ignores the header still works exactly as
before, scoped to its TCP connection, but cannot be prompted: there is no
channel to carry the question. See :mod:`.http_sessions`.

**2026-07-28.** A request that declares the stateless revision, in its
``MCP-Protocol-Version`` header or its ``_meta``, is checked against that
revision's header rules (:mod:`._http_stateless`) and served without a
session: its ``Mcp-Session-Id`` is ignored and none is minted. Its
``subscriptions/listen`` holds the response stream open for the change
notifications it asked for, until the client closes it or the server stops.
"""
import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple

from je_auto_control.utils.http_headers import bearer_challenge, log_safe
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._authz import check_bearer
from je_auto_control.utils.mcp_server._http_origin import (
    ALLOWED_ORIGINS_ENV, origin_allowed,
)
from je_auto_control.utils.mcp_server._http_responses import (
    SSE_MEDIA_TYPE, HttpResponseMixin,
)
from je_auto_control.utils.mcp_server._http_stateless import (
    PROTOCOL_VERSION_HEADER, is_stateless, read_message, stateless_refusal,
    status_for, unsupported_header_refusal,
)
from je_auto_control.utils.mcp_server._protocol import (
    SUPPORTED_PROTOCOL_VERSIONS,
    _error_response, _notification_message,
)
from je_auto_control.utils.mcp_server._stateless import (
    LISTEN_METHOD, STATELESS_PROTOCOL_VERSIONS,
)
from je_auto_control.utils.mcp_server.http_sessions import (
    HttpSession, SESSION_HEADER, SessionRegistry, session_id_from_headers,
)
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, authorization_scope, user_store_from_env,
)
from je_auto_control.utils.rbac.users import UserStore

DEFAULT_PATH = "/mcp"
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
    except (ValueError, RecursionError):
        return False
    return isinstance(message, dict) and message.get("method") == "initialize"


def _forget_if_dropped(bridge: "MCPServer", session: Optional[HttpSession]) -> None:
    """Release a session's dispatcher state if it was dropped mid-request.

    A session evicted, swept or deleted while its ``initialize`` ran had the
    capabilities stored under its dead id after the drop hook had already
    run, and nothing would ever release them.
    """
    if session is not None and session.closed.is_set():
        bridge.forget_connection(session.id)


def _notifier_for(writer: Optional[Callable[[str], None]]):
    """Wrap a raw writer as a (method, params) notifier, or ``None``."""
    if writer is None:
        return None
    return lambda method, params: writer(
        _notification_message(method, params),
    )


class _MCPHttpHandler(HttpResponseMixin, BaseHTTPRequestHandler):
    """Bridges HTTP requests onto :meth:`MCPServer.handle_line`."""

    server_version = "AutoControlMCP/1.0"
    # The RBAC user this request authenticated as; None under the shared token.
    _caller: Optional[AuthorizationContext] = None
    # socketserver applies this to the connection socket in setup(); it bounds
    # every read (headers *and* body) so a stalled request cannot pin a worker.
    timeout = _REQUEST_TIMEOUT

    # Suppress default stderr access logs — route through project logger.
    def log_message(self, format, *args) -> None:  # noqa: A002  # pylint: disable=redefined-builtin  # reason: stdlib override
        autocontrol_logger.info("mcp-http %s - %s",
                                self.address_string(), log_safe(format % args))

    def do_POST(self) -> None:  # noqa: N802  # reason: stdlib API
        if not self._caller_allowed():
            return
        if self.path != DEFAULT_PATH:
            self._send_json({"error": "unknown path"}, status=404)
            return
        line = self._read_body()
        if line is None:
            return
        bridge: MCPServer = self.server.mcp  # type: ignore[attr-defined]
        message = read_message(line)
        refused = unsupported_header_refusal(self.headers, message)
        if refused is not None:
            self._send_raw_json(refused.body, status=refused.status)
            return
        # One scope around every way the line is dispatched: each of them
        # runs it on this thread.
        with authorization_scope(self._caller):
            if is_stateless(self.headers, message):
                self._serve_stateless(bridge, line, message)
                return
            self._serve_in_session(bridge, line)

    def _serve_in_session(self, bridge: MCPServer, line: str) -> None:
        """Serve a handshake-era request under its session, or its connection."""
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
            _forget_if_dropped(bridge, session)
            return
        # A plain POST has no stream of its own, but a session may have a
        # standing GET stream; server-initiated traffic belongs on it. Absent
        # one there is no writer, rather than whichever other peer's socket
        # happens to be open.
        writer = session.stream_writer if session is not None else None
        # concurrent_tools=False: a plain POST answers in its own body; with
        # the server's concurrent mode a tools/call went to a worker and the
        # POST was acknowledged 202 with nothing in it.
        with bridge.connection_scope(connection_id=conn_id, writer=writer,
                                      notifier=_notifier_for(writer),
                                      concurrent_tools=False):
            response = bridge.handle_line(line)
        _forget_if_dropped(bridge, session)
        if response is None:
            # MCP notification — no body, ack with 202.
            self._send_blank(status=202)
            return
        self._send_raw_json(response, extra_headers=extra)

    def _serve_stateless(self, bridge: MCPServer, line: str,
                         message: Optional[Dict[str, Any]]) -> None:
        """Serve a 2026-07-28 request: header rules first, and no session."""
        refused = stateless_refusal(self.headers, message)
        if refused is not None:
            self._send_raw_json(refused.body, status=refused.status)
            return
        if message is not None and message.get("method") == LISTEN_METHOD:
            self._stream_listen(bridge, line, message)
            return
        if self._client_accepts_sse():
            self._dispatch_sse(bridge, line, id(self))
            return
        with bridge.connection_scope(connection_id=id(self), concurrent_tools=False):
            response = bridge.handle_line(line)
        if response is None:
            self._send_blank(status=202)
            return
        self._send_raw_json(response, status=status_for(response))

    def _stream_listen(self, bridge: MCPServer, line: str,
                       message: Dict[str, Any]) -> None:
        """Hold a ``subscriptions/listen`` response stream open until it ends."""
        if not self._client_accepts_sse():
            self._send_raw_json(_error_response(
                message.get("id"), -32600,
                f"Invalid Request: {LISTEN_METHOD} needs Accept: {SSE_MEDIA_TYPE}"), status=406)
            return
        send_lock = threading.Lock()
        emit = self._open_event_stream(send_lock)
        with bridge.connection_scope(writer=emit, notifier=_notifier_for(emit),
                                     concurrent_tools=False, connection_id=id(self)):
            response = bridge.handle_line(line)
        if response is not None:
            # Refused: the error is the whole answer.
            emit(response)
            return
        closed = bridge.subscription(id(self), message["id"])
        try:
            while closed is not None and not closed.wait(timeout=_STREAM_HEARTBEAT):
                with send_lock:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
        except OSError as error:
            autocontrol_logger.info("MCP subscription stream ended: %r", error)
        finally:
            # Closing the stream is how an HTTP client cancels; no answer then.
            bridge.end_subscription(id(self), message["id"])

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
        """Refuse cross-site callers and bad tokens, then unsupported protocol versions."""
        return self._caller_allowed() and self._protocol_version_supported()

    def _protocol_version_supported(self) -> bool:
        """For GET and DELETE: an unsupported ``MCP-Protocol-Version`` header is a 400.

        A request without the header is served as before (the spec assumes
        2025-03-26 then); one naming a version this server does not speak
        used to be served as if it matched. 2026-07-28 has no GET stream and
        no session to delete, so a request naming it is a 405.
        """
        version = self.headers.get(PROTOCOL_VERSION_HEADER)
        if version is None or version.strip() in SUPPORTED_PROTOCOL_VERSIONS:
            return True
        if version.strip() in STATELESS_PROTOCOL_VERSIONS:
            self._send_json({"error": f"{self.command} is not part of MCP {version.strip()}"},
                            status=405, extra_headers={"Allow": "POST"})
            return False
        self._send_json({"error": f"unsupported MCP-Protocol-Version {version!r}"},
                        status=400)
        return False

    def _caller_allowed(self) -> bool:
        """Refuse browser cross-site requests, then check the bearer token."""
        if not origin_allowed(self.headers, self.server.server_address):
            self._send_json({"error": "origin not allowed"}, status=403)
            return False
        self._caller, refusal = check_bearer(
            self.headers.get("Authorization"), self.server.auth_token,  # type: ignore[attr-defined]
            self.server.user_store)  # type: ignore[attr-defined]
        if refusal is None:
            return True
        status, text = refusal
        # 401 with a challenge for a missing *and* a wrong token: the MCP
        # authorization spec requires both, and RFC 9110 the header.
        challenge = {"WWW-Authenticate": bearer_challenge(
            "autocontrol-mcp", self.headers.get("Authorization"))} if status == 401 else None
        self._send_json({"error": text}, status=status, extra_headers=challenge)
        return False

    def _dispatch_sse(self, bridge: MCPServer, line: str,
                      conn_id: Any,
                      extra_headers: Optional[Dict[str, str]] = None) -> None:
        """Stream progress notifications + the final response as SSE events."""
        # Force connection close so the client gets EOF after the last event.
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type",
                          f"{SSE_MEDIA_TYPE}; charset=utf-8")
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
                {"error": f"GET requires Accept: {SSE_MEDIA_TYPE}"},
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
                                  f"{SSE_MEDIA_TYPE}; charset=utf-8")
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
        if self.path != DEFAULT_PATH:
            # GET and POST answer 404 here; DELETE /anything ended the session.
            self._send_json({"error": "unknown path"}, status=404)
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


class _MCPHttpServer(ThreadingHTTPServer):
    """ThreadingHTTPServer extension that owns an :class:`MCPServer`."""

    def __init__(self, server_address: Tuple[str, int],
                 mcp: MCPServer,
                 auth_token: Optional[str] = None,
                 user_store: Optional[UserStore] = None) -> None:
        super().__init__(server_address, _MCPHttpHandler)
        self.mcp = mcp
        self.auth_token = auth_token
        self.user_store = user_store
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
                 user_store: Optional[UserStore] = None,
                 ) -> None:
        """``user_store`` switches RBAC on; ``None`` reads ``JE_AUTOCONTROL_RBAC_USERS``."""
        self._mcp = mcp if mcp is not None else MCPServer()
        self._users = user_store if user_store is not None else user_store_from_env()
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
            user_store=self._users,
        )
        if self._ssl_context is not None:
            # Defer the handshake so it runs in get_request() under a timeout
            # rather than implicitly inside accept() with no bound.
            self._server.socket = self._ssl_context.wrap_socket(
                self._server.socket, server_side=True,
                do_handshake_on_connect=False,
            )
        # `server_address` is typed for every address family a socketserver
        # can bind; an AF_INET HTTP server always answers with (host, port).
        bound_host, bound_port = self._server.server_address[:2]
        self._address = (
            bound_host.decode() if isinstance(bound_host, (bytes, bytearray))
            else bound_host,
            int(bound_port),
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True,
            name="AutoControlMCPHttp",
        )
        self._thread.start()
        scheme = "https" if self._ssl_context is not None else "http"
        autocontrol_logger.info("MCP %s listening on %s:%d (rbac=%s)", scheme,
                                 *self._address, "on" if self._users is not None else "off")

    def stop(self, timeout: float = 2.0) -> None:
        if self._server is None:
            return
        # Close the sessions and subscriptions first: a standing GET stream or
        # a subscriptions/listen parks a worker on its heartbeat, and ending
        # them releases it without waiting one out.
        self._mcp.end_subscriptions(stdio=False)
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
                          user_store: Optional[UserStore] = None,
                          ) -> HttpMCPServer:
    """Start and return an :class:`HttpMCPServer`; convenience wrapper."""
    server = HttpMCPServer(
        mcp=mcp, host=host, port=port,
        auth_token=auth_token, ssl_context=ssl_context, user_store=user_store,
    )
    server.start()
    return server


__all__ = ["ALLOWED_ORIGINS_ENV", "HttpMCPServer", "start_mcp_http_server"]
