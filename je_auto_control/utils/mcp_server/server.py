"""Minimal MCP server speaking JSON-RPC 2.0 over stdio.

Implements the subset of the Model Context Protocol that Claude clients
(Claude Desktop, Claude Code, Claude API) use to discover and invoke
tools: ``initialize``, ``tools/list``, ``tools/call``, ``ping``, and
``notifications/initialized``. Each transport line is one JSON-RPC
message — no Content-Length framing — matching the MCP stdio spec.
"""
import contextlib
import functools
import itertools
import json
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, TextIO

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.context import (
    OperationCancelledError, ToolCallContext,
)
from je_auto_control.utils.mcp_server.log_bridge import (
    MCPLogBridge, mcp_level_to_logging,
)
from je_auto_control.utils.mcp_server.rate_limit import RateLimiter
from je_auto_control.utils.mcp_server.prompts import (
    PromptProvider, default_prompt_provider,
)
from je_auto_control.utils.mcp_server.resources import (
    ResourceProvider, default_resource_provider,
)
from je_auto_control.utils.mcp_server.tools import (
    MCPTool, build_default_tool_registry,
)
from je_auto_control.utils.mcp_server.tools._validation import (
    validate_arguments,
)
from je_auto_control.utils.mcp_server._client_requests import (
    ClientRequestMixin,
)
from je_auto_control.utils.mcp_server._protocol import (
    PROTOCOL_VERSION, SERVER_NAME, SERVER_VERSION, _capture_error_screenshot,
    _coerce_params, _DISPATCH_ERRORS, _error_response, _is_hashable,
    _MCPError, _notification_message, _result_response, _to_content_blocks,
    _TOOL_INVOKE_ERRORS, _TOOLS_CALL_METHOD,
)

#: How long a transport waits for in-flight tool replies before it gives up
#: and shuts down anyway.
WORKER_DRAIN_TIMEOUT = 10.0


class MCPServer(ClientRequestMixin):
    """JSON-RPC 2.0 MCP server with a configurable tool registry."""

    def __init__(self, tools: Optional[List[MCPTool]] = None,
                 resource_provider: Optional[ResourceProvider] = None,
                 prompt_provider: Optional[PromptProvider] = None,
                 concurrent_tools: bool = False,
                 audit_logger: Optional[AuditLogger] = None,
                 rate_limiter: Optional[RateLimiter] = None,
                 log_bridge: Optional[MCPLogBridge] = None,
                 ) -> None:
        registry = tools if tools is not None else build_default_tool_registry()
        self._tools: Dict[str, MCPTool] = {tool.name: tool for tool in registry}
        self._resources = (resource_provider if resource_provider is not None
                            else default_resource_provider())
        self._prompts = (prompt_provider if prompt_provider is not None
                          else default_prompt_provider())
        self._tools_lock = threading.Lock()
        self._default_concurrent_tools = bool(concurrent_tools)
        self._audit = (audit_logger if audit_logger is not None
                        else AuditLogger())
        self._rate_limiter = rate_limiter
        self._log_bridge = log_bridge
        self._stop = threading.Event()
        self._initialized = False
        # tools/call runs on a worker thread under the stdio transport, so a
        # reply can still be in flight when the loop reaches EOF. Tracking the
        # workers is what lets the transport wait for them instead of pulling
        # the writer out from under them.
        self._workers: List[threading.Thread] = []
        self._workers_lock = threading.Lock()
        # Connection-scoped state. The stdio transport has exactly one peer, so
        # a server-wide default is right for it; an HTTP transport has many, and
        # each request runs on its own thread. Keeping the notifier/writer in
        # thread-local storage is what stops one client's progress
        # notifications from being emitted down another client's socket.
        # See :meth:`connection_scope`.
        self._default_notifier: Optional[
            Callable[[str, Dict[str, Any]], None]] = None
        self._default_writer: Optional[Callable[[str], None]] = None
        self._local = threading.local()
        # Keyed by ``(connection_id, msg_id)`` so two HTTP clients that both
        # use msg id 1 get distinct slots instead of clobbering / cross-
        # cancelling each other. connection_id is None for stdio (one peer).
        self._active_calls: Dict[Any, ToolCallContext] = {}
        self._calls_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._sampling_id_counter = itertools.count(1)
        self._outbound_id_counter = itertools.count(1)
        self._pending_outbound: Dict[Any, Dict[str, Any]] = {}
        self._outbound_lock = threading.Lock()
        # Client capabilities are per-connection: over HTTP each peer runs its
        # own initialize, so a server-global copy let one client's handshake
        # clobber another's and made the destructive-confirmation gate read the
        # wrong peer's capabilities. stdio (one peer) uses the default slot.
        self._default_client_capabilities: Dict[str, Any] = {}
        self._client_caps_by_conn: Dict[Any, Dict[str, Any]] = {}
        self._caps_lock = threading.Lock()
        self._resource_subscriptions: Dict[str, Any] = {}
        self._subscriptions_lock = threading.Lock()

    # --- connection-scoped state ------------------------------------------
    #
    # Each property prefers a value set for the current thread (one HTTP
    # request = one thread) and falls back to the server-wide default that
    # stdio and set_notifier() use. A plain POST therefore sees *no* notifier
    # rather than inheriting whichever SSE connection happens to be open —
    # correct, since a plain POST has no stream to deliver notifications on.

    @property
    def _notifier(self) -> Optional[Callable[[str, Dict[str, Any]], None]]:
        return getattr(self._local, "notifier", None) or self._default_notifier

    @_notifier.setter
    def _notifier(self, value) -> None:
        self._default_notifier = value

    @property
    def _writer(self) -> Optional[Callable[[str], None]]:
        return getattr(self._local, "writer", None) or self._default_writer

    @_writer.setter
    def _writer(self, value) -> None:
        self._default_writer = value

    @property
    def _concurrent_tools(self) -> bool:
        scoped = getattr(self._local, "concurrent_tools", None)
        if scoped is None:
            return self._default_concurrent_tools
        return scoped

    @_concurrent_tools.setter
    def _concurrent_tools(self, value) -> None:
        self._default_concurrent_tools = bool(value)

    @property
    def _connection_id(self) -> Any:
        """Identity of the peer served on this thread (None for stdio)."""
        return getattr(self._local, "connection_id", None)

    @property
    def _client_capabilities(self) -> Dict[str, Any]:
        """Capabilities advertised by the peer served on this thread."""
        conn = self._connection_id
        if conn is None:
            return self._default_client_capabilities
        with self._caps_lock:
            return self._client_caps_by_conn.get(conn, {})

    @_client_capabilities.setter
    def _client_capabilities(self, value: Dict[str, Any]) -> None:
        conn = self._connection_id
        if conn is None:
            self._default_client_capabilities = value
            return
        with self._caps_lock:
            self._client_caps_by_conn[conn] = value

    @contextlib.contextmanager
    def connection_scope(self, *, notifier=None, writer=None,
                         concurrent_tools=None, connection_id=None):
        """Bind notifier/writer/concurrency/identity to the calling thread only.

        Transports that serve more than one peer must wrap each request in
        this. Previously they swapped the attributes on the shared server, so
        any concurrent request bound to the wrong peer's socket. ``connection_id``
        scopes active-call slots and client capabilities per peer.
        """
        prior = (getattr(self._local, "notifier", None),
                 getattr(self._local, "writer", None),
                 getattr(self._local, "concurrent_tools", None),
                 getattr(self._local, "connection_id", None))
        self._local.notifier = notifier
        self._local.writer = writer
        self._local.concurrent_tools = concurrent_tools
        self._local.connection_id = connection_id
        try:
            yield self
        finally:
            (self._local.notifier, self._local.writer,
             self._local.concurrent_tools, self._local.connection_id) = prior

    def forget_connection(self, connection_id: Any) -> None:
        """Drop per-connection state when a transport connection closes.

        HTTP connections are transient; without this their capabilities and
        any stray active-call contexts would accumulate for the server's life.
        """
        if connection_id is None:
            return
        with self._caps_lock:
            self._client_caps_by_conn.pop(connection_id, None)
        with self._calls_lock:
            stale = [key for key in self._active_calls
                     if isinstance(key, tuple) and key[0] == connection_id]
            for key in stale:
                self._active_calls.pop(key, None)

    def register_tool(self, tool: MCPTool) -> None:
        """Add or replace a tool in the live registry.

        Emits ``notifications/tools/list_changed`` to the connected
        client so it knows to refresh its cached tool list.
        """
        with self._tools_lock:
            self._tools[tool.name] = tool
        self._notify_tools_list_changed()

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool by name. Returns True if it existed."""
        with self._tools_lock:
            if name not in self._tools:
                return False
            del self._tools[name]
        self._notify_tools_list_changed()
        return True

    def _notify_tools_list_changed(self) -> None:
        notifier = self._notifier
        if notifier is None:
            return
        try:
            notifier("notifications/tools/list_changed", {})
        except (OSError, RuntimeError, ValueError):
            autocontrol_logger.exception(
                "MCP failed to send tools/list_changed",
            )

    def stop(self) -> None:
        """Request the stdio loop to exit at its next iteration."""
        self._stop.set()

    def serve_stdio(self, stdin: Optional[TextIO] = None,
                    stdout: Optional[TextIO] = None) -> None:
        """Run the message loop until EOF on stdin or :meth:`stop`."""
        in_stream = stdin if stdin is not None else sys.stdin
        out_stream = stdout if stdout is not None else sys.stdout
        autocontrol_logger.info(
            "MCP server starting (stdio, %d tools)", len(self._tools),
        )
        prior_notifier = self._notifier
        prior_writer = self._writer
        prior_concurrent = self._concurrent_tools
        self._writer = lambda payload: self._write_message(out_stream, payload)
        self._notifier = lambda method, params: self._writer(  # type: ignore[misc]
            _notification_message(method, params),
        )
        # Stdio always opts into concurrent tool execution so sampling
        # requests issued by tool handlers don't block the reader.
        self._concurrent_tools = True
        self._attach_log_bridge_if_configured()
        try:
            while not self._stop.is_set():
                line = in_stream.readline()
                if line == "":
                    break
                line = line.strip()
                if not line:
                    continue
                response = self._handle_line_safely(line)
                if response is not None:
                    self._write_message(out_stream, response)
        finally:
            # Before anything is restored: a tools/call dispatched just before
            # EOF is still running, and its reply has nowhere to go once the
            # writer is swapped back.
            self._join_workers()
            self._detach_log_bridge_if_configured()
            self._notifier = prior_notifier
            self._writer = prior_writer
            self._concurrent_tools = prior_concurrent
            autocontrol_logger.info("MCP server stopped")

    def _write_message(self, out_stream: TextIO, payload: str) -> None:
        """Serialize an outbound JSON-RPC line under a writer lock."""
        with self._write_lock:
            out_stream.write(payload + "\n")
            out_stream.flush()

    def set_notifier(self,
                     notifier: Optional[Callable[[str, Dict[str, Any]], None]]
                     ) -> None:
        """Install a callback used to send outbound notifications.

        The HTTP transport sets this to push notifications onto an
        SSE stream; the stdio loop installs its own writer. Tests may
        register a list-collecting callback to inspect notifications.
        """
        self._notifier = notifier

    def _attach_log_bridge_if_configured(self) -> None:
        """Wire the log bridge into the project logger and notifier."""
        if self._log_bridge is None:
            self._log_bridge = MCPLogBridge()
        self._log_bridge.set_notifier(self._notifier)
        if self._log_bridge not in autocontrol_logger.handlers:
            autocontrol_logger.addHandler(self._log_bridge)

    def _detach_log_bridge_if_configured(self) -> None:
        if self._log_bridge is None:
            return
        self._log_bridge.set_notifier(None)
        try:
            autocontrol_logger.removeHandler(self._log_bridge)
        except ValueError:
            pass

    def set_writer(self, writer: Optional[Callable[[str], None]]) -> None:
        """Install a callback used to write any outbound JSON-RPC line.

        This is the lower-level companion to :meth:`set_notifier` —
        used to deliver server-initiated requests (e.g. sampling) and
        to emit asynchronously-produced tools/call responses when the
        server is running in concurrent mode.
        """
        self._writer = writer

    def handle_line(self, line: str) -> Optional[str]:
        """Process one JSON-RPC line; return the response line or ``None``."""
        try:
            message = json.loads(line)
        except ValueError as error:
            autocontrol_logger.warning("MCP parse error: %r", error)
            return _error_response(None, -32700, "Parse error")
        if not isinstance(message, dict):
            return _error_response(None, -32600, "Invalid Request")

        method = message.get("method")
        msg_id = message.get("id")

        if self._is_outbound_response(method, msg_id, message):
            # An inbound reply's id is used as a dict key; a non-hashable id
            # (e.g. a JSON array) would raise TypeError here and, with no guard
            # in the stdio read loop, take the whole server down.
            if _is_hashable(msg_id):
                self._dispatch_outbound_response(msg_id, message)
            else:
                autocontrol_logger.warning(
                    "MCP dropping outbound response with non-hashable id %r",
                    msg_id,
                )
            return None

        params, params_error = _coerce_params(message.get("params"), msg_id)
        if params_error is not None:
            return params_error
        if msg_id is None:
            self._handle_notification(method, params)
            return None
        if method == _TOOLS_CALL_METHOD and self._concurrent_tools:
            self._dispatch_tools_call_async(msg_id, params)
            return None
        return self._build_response(msg_id, method, params)

    def _handle_line_safely(self, line: str) -> Optional[str]:
        """Call :meth:`handle_line`, swallowing any leak so the loop survives.

        handle_line already validates its input, but this final net guarantees
        that one malformed line can never terminate the stdio read loop.
        """
        try:
            return self.handle_line(line)
        except _DISPATCH_ERRORS:
            autocontrol_logger.exception("MCP handle_line failed; line skipped")
            return None

    def _dispatch_tools_call_async(self, msg_id: Any,
                                   params: Dict[str, Any]) -> None:
        """Run a tools/call on a worker thread; the worker writes the reply."""
        # Captured here rather than read inside the worker. The worker may not
        # reach its write until after the transport's `finally` has restored
        # the previous writer, and then the reply would go down the previous
        # connection or be dropped as "no writer" — a reply belongs to the
        # transport that accepted the request.
        writer = self._writer

        def worker() -> None:
            payload = self._build_response(msg_id, _TOOLS_CALL_METHOD, params)
            if writer is None:
                autocontrol_logger.warning(
                    "MCP async tool reply with no writer; dropping %s", msg_id,
                )
                return
            writer(payload)
        thread = threading.Thread(
            target=worker, daemon=True, name=f"MCPCall-{msg_id}",
        )
        with self._workers_lock:
            self._workers = [live for live in self._workers if live.is_alive()]
            self._workers.append(thread)
        thread.start()

    def _join_workers(self, timeout: float = WORKER_DRAIN_TIMEOUT) -> None:
        """Wait for in-flight tool replies before the transport goes away.

        Bounded: a handler that never returns must not keep the process from
        shutting down, so this says which worker outstayed its welcome and
        gives up rather than hanging.
        """
        deadline = time.monotonic() + timeout
        with self._workers_lock:
            pending = [live for live in self._workers if live.is_alive()]
        for thread in pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                autocontrol_logger.warning(
                    "MCP shutdown: %s is still running; its reply is lost",
                    thread.name,
                )
                continue
            thread.join(remaining)

    def _build_response(self, msg_id: Any, method: Optional[str],
                        params: Dict[str, Any]) -> str:
        """Dispatch a request and serialise the result or error."""
        try:
            result = self._dispatch(msg_id, method, params)
        except _MCPError as error:
            return _error_response(msg_id, error.code, error.message)
        except OperationCancelledError as error:
            autocontrol_logger.info("MCP call %s cancelled by client", msg_id)
            return _error_response(msg_id, -32800, str(error))
        except _DISPATCH_ERRORS as error:
            autocontrol_logger.exception("MCP dispatch failed")
            return _error_response(msg_id, -32603, f"Internal error: {error}")
        return _result_response(msg_id, result)

    def _handle_notification(self, method: Optional[str],
                             params: Dict[str, Any]) -> None:
        """Notifications carry no id and never get a response."""
        if method == "notifications/initialized":
            self._initialized = True
            autocontrol_logger.info("MCP client initialized")
            self._maybe_request_roots_async()
            return
        if method == "notifications/cancelled":
            self._cancel_active_call(params)
            return
        if method == "notifications/roots/list_changed":
            self._maybe_request_roots_async()
            return
        autocontrol_logger.debug("MCP notification ignored: %s", method)

    def _cancel_active_call(self, params: Dict[str, Any]) -> None:
        """Mark the matching active tool call as cancelled, if any."""
        request_id = params.get("requestId")
        if request_id is None or not _is_hashable(request_id):
            return
        call_key = (self._connection_id, request_id)
        with self._calls_lock:
            ctx = self._active_calls.get(call_key)
        if ctx is not None:
            ctx.cancelled_event.set()
            autocontrol_logger.info(
                "MCP cancel signalled for call %r", request_id,
            )

    def _dispatch(self, msg_id: Any, method: Optional[str],
                  params: Dict[str, Any]) -> Any:
        if method == _TOOLS_CALL_METHOD:
            return self._handle_tools_call(msg_id, params)
        if method is None:
            raise _MCPError(-32601, f"Method not found: {method}")
        nullary = {
            "ping": self._handle_ping,
            "tools/list": self._handle_tools_list,
            "resources/list": self._handle_resources_list,
            "prompts/list": self._handle_prompts_list,
        }.get(method)
        if nullary is not None:
            return nullary()
        handler = {
            "initialize": self._handle_initialize,
            "resources/read": self._handle_resources_read,
            "resources/subscribe": self._handle_resources_subscribe,
            "resources/unsubscribe": self._handle_resources_unsubscribe,
            "prompts/get": self._handle_prompts_get,
            "logging/setLevel": self._handle_logging_set_level,
        }.get(method)
        if handler is None:
            raise _MCPError(-32601, f"Method not found: {method}")
        return handler(params)

    def _handle_ping(self) -> Dict[str, Any]:
        """Liveness probe; returns an empty result per the MCP spec."""
        return {}

    def _handle_tools_list(self) -> Dict[str, Any]:
        """List descriptors for every registered tool."""
        # Snapshot under the lock: PluginWatcher re-registers tools from its
        # own thread, and mutating the dict mid-iteration surfaced to the
        # client as "-32603 dictionary changed size during iteration".
        with self._tools_lock:
            tools = list(self._tools.values())
        return {"tools": [tool.to_descriptor() for tool in tools]}

    def _handle_resources_list(self) -> Dict[str, Any]:
        """List descriptors for every registered resource."""
        return {"resources": [resource.to_descriptor()
                              for resource in self._resources.list()]}

    def _handle_prompts_list(self) -> Dict[str, Any]:
        """List descriptors for every registered prompt."""
        return {"prompts": [prompt.to_descriptor()
                            for prompt in self._prompts.list()]}

    def _handle_logging_set_level(self,
                                  params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("level")
        if not isinstance(name, str):
            raise _MCPError(-32602, "logging/setLevel requires string 'level'")
        level = mcp_level_to_logging(name)
        if level is None:
            raise _MCPError(-32602, f"unknown log level: {name!r}")
        if self._log_bridge is None:
            self._log_bridge = MCPLogBridge()
        self._log_bridge.setLevel(level)
        autocontrol_logger.setLevel(min(autocontrol_logger.level or level,
                                         level) if autocontrol_logger.level
                                    else level)
        return {}

    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        client_version = params.get("protocolVersion", PROTOCOL_VERSION)
        client_caps = params.get("capabilities") or {}
        if isinstance(client_caps, dict):
            self._client_capabilities = client_caps
        capabilities: Dict[str, Any] = {
            "tools": {"listChanged": True},
            "resources": {"listChanged": False, "subscribe": True},
            "prompts": {"listChanged": False},
            "sampling": {},
            "logging": {},
        }
        if "roots" in self._client_capabilities:
            capabilities["roots"] = {"listChanged": True}
        return {
            "protocolVersion": client_version or PROTOCOL_VERSION,
            "capabilities": capabilities,
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    def _handle_resources_read(self,
                               params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise _MCPError(-32602, "resources/read requires string 'uri'")
        content = self._resources.read(uri)
        if content is None:
            raise _MCPError(-32602, f"Unknown resource: {uri}")
        return {"contents": [content]}

    def _handle_resources_subscribe(self,
                                    params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise _MCPError(-32602, "resources/subscribe requires 'uri'")
        # Hold the lock across the check *and* the subscribe so two concurrent
        # requests for the same uri cannot both create a provider handle and
        # leak the loser (a TOCTOU that left an orphaned subscription running).
        with self._subscriptions_lock:
            if uri in self._resource_subscriptions:
                return {}
            handle = self._resources.subscribe(
                uri,
                functools.partial(self._notify_resource_updated, uri),
            )
            if handle is None:
                raise _MCPError(-32602, f"Unsubscribable resource: {uri}")
            self._resource_subscriptions[uri] = handle
        return {}

    def _handle_resources_unsubscribe(self,
                                      params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise _MCPError(-32602, "resources/unsubscribe requires 'uri'")
        with self._subscriptions_lock:
            handle = self._resource_subscriptions.pop(uri, None)
        if handle is not None:
            self._resources.unsubscribe(uri, handle)
        return {}

    def _notify_resource_updated(self, uri: str) -> None:
        notifier = self._notifier
        if notifier is None:
            return
        try:
            notifier("notifications/resources/updated", {"uri": uri})
        except (OSError, RuntimeError, ValueError):
            autocontrol_logger.exception(
                "MCP failed to send resources/updated for %s", uri,
            )

    def _handle_prompts_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not name:
            raise _MCPError(-32602, "prompts/get requires string 'name'")
        if not isinstance(arguments, dict):
            raise _MCPError(-32602, "prompts/get 'arguments' must be an object")
        try:
            payload = self._prompts.get(name, arguments)
        except ValueError as error:
            raise _MCPError(-32602, str(error)) from error
        if payload is None:
            raise _MCPError(-32602, f"Unknown prompt: {name}")
        return payload

    def _prepare_tool_call(
        self, params: Dict[str, Any],
    ) -> tuple[str, Any, Dict[str, Any]]:
        """Validate a tools/call request; return ``(name, tool, arguments)``.

        Raises :class:`_MCPError` when the request is malformed, the tool is
        unknown, arguments fail schema validation, or the rate limit is hit.
        """
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            raise _MCPError(-32602, "tools/call requires string 'name'")
        if not isinstance(arguments, dict):
            raise _MCPError(-32602, "tools/call 'arguments' must be an object")
        tool = self._tools.get(name)
        if tool is None:
            raise _MCPError(-32602, f"Unknown tool: {name}")
        violation = validate_arguments(tool.input_schema, arguments)
        if violation is not None:
            raise _MCPError(-32602, f"Invalid arguments for {name}: {violation}")
        if self._rate_limiter is not None and not self._rate_limiter.try_acquire():
            raise _MCPError(-32000, f"Rate limit exceeded for tool {name!r}")
        self._maybe_confirm_destructive(name, tool, arguments)
        return name, tool, arguments

    def _handle_tools_call(self, msg_id: Any,
                           params: Dict[str, Any]) -> Dict[str, Any]:
        name, tool, arguments = self._prepare_tool_call(params)
        ctx = self._build_call_context(msg_id, params)
        call_key = (self._connection_id, msg_id)
        with self._calls_lock:
            self._active_calls[call_key] = ctx
        started_at = time.monotonic()
        try:
            result = tool.invoke(arguments, ctx=ctx)
        except OperationCancelledError:
            self._audit.record(
                tool=name, arguments=arguments, status="cancelled",
                duration_seconds=time.monotonic() - started_at,
            )
            raise
        except _TOOL_INVOKE_ERRORS as error:
            # NotImplementedError subclasses RuntimeError so it's already covered;
            # AutoControlException / subprocess timeouts / sqlite3 errors are
            # added via _FRAMEWORK_TOOL_ERRORS so a failing tool returns an
            # isError result instead of killing the worker / aborting the socket.
            autocontrol_logger.warning("MCP tool %s failed: %r", name, error)
            artifact = _capture_error_screenshot(name)
            self._audit.record(
                tool=name, arguments=arguments, status="error",
                duration_seconds=time.monotonic() - started_at,
                error_text=f"{type(error).__name__}: {error}",
                artifact_path=artifact,
            )
            error_text = f"{type(error).__name__}: {error}"
            if artifact is not None:
                error_text += f"\n(error screenshot saved to {artifact})"
            return {
                "content": [{"type": "text", "text": error_text}],
                "isError": True,
            }
        finally:
            with self._calls_lock:
                self._active_calls.pop(call_key, None)
        self._audit.record(
            tool=name, arguments=arguments, status="ok",
            duration_seconds=time.monotonic() - started_at,
        )
        response: Dict[str, Any] = {
            "content": _to_content_blocks(result),
            "isError": False,
        }
        # 2025-06-18 spec: tools with an outputSchema return their dict result
        # as structuredContent for typed, token-cheap client consumption.
        if tool.output_schema is not None and isinstance(result, dict):
            response["structuredContent"] = result
        return response

    def _build_call_context(self, msg_id: Any,
                            params: Dict[str, Any]) -> ToolCallContext:
        meta = params.get("_meta") if isinstance(params.get("_meta"),
                                                  dict) else {}
        progress_token = meta.get("progressToken") if isinstance(meta, dict) else None
        return ToolCallContext(
            request_id=msg_id, progress_token=progress_token,
            notifier=self._notifier,
        )


def start_mcp_stdio_server() -> MCPServer:
    """Start a stdio MCP server in the foreground; blocks until EOF."""
    server = MCPServer()
    server.serve_stdio()
    return server
