"""Minimal MCP server speaking JSON-RPC 2.0 over stdio.

Implements the subset of the Model Context Protocol that Claude clients
(Claude Desktop, Claude Code, Claude API) use to discover and invoke
tools: ``initialize``, ``tools/list``, ``tools/call``, ``ping``, and
``notifications/initialized``. Each transport line is one JSON-RPC
message — no Content-Length framing — matching the MCP stdio spec.
"""
import itertools
import json
import os
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
    MCPContent, MCPTool, build_default_tool_registry,
)
from je_auto_control.utils.mcp_server.tools._validation import (
    validate_arguments,
)

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "je_auto_control"
SERVER_VERSION = "0.1.0"
_TOOLS_CALL_METHOD = "tools/call"


class _MCPError(Exception):
    """Raised inside the dispatcher to surface a JSON-RPC error response."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MCPServer:
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
        self._concurrent_tools = bool(concurrent_tools)
        self._audit = (audit_logger if audit_logger is not None
                        else AuditLogger())
        self._rate_limiter = rate_limiter
        self._log_bridge = log_bridge
        self._stop = threading.Event()
        self._initialized = False
        self._notifier: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._writer: Optional[Callable[[str], None]] = None
        self._active_calls: Dict[Any, ToolCallContext] = {}
        self._calls_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._sampling_id_counter = itertools.count(1)
        self._outbound_id_counter = itertools.count(1)
        self._pending_outbound: Dict[Any, Dict[str, Any]] = {}
        self._outbound_lock = threading.Lock()
        self._client_capabilities: Dict[str, Any] = {}
        self._resource_subscriptions: Dict[str, Any] = {}
        self._subscriptions_lock = threading.Lock()

    def register_tool(self, tool: MCPTool) -> None:
        """Add or replace a tool in the live registry.

        Emits ``notifications/tools/list_changed`` to the connected
        client so it knows to refresh its cached tool list.
        """
        self._tools[tool.name] = tool
        self._notify_tools_list_changed()

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool by name. Returns True if it existed."""
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
                response = self.handle_line(line)
                if response is not None:
                    self._write_message(out_stream, response)
        finally:
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
        params = message.get("params") or {}

        if method is None and msg_id is not None and (
            "result" in message or "error" in message
        ):
            self._dispatch_outbound_response(msg_id, message)
            return None
        if msg_id is None:
            self._handle_notification(method, params)
            return None
        if method == _TOOLS_CALL_METHOD and self._concurrent_tools:
            self._dispatch_tools_call_async(msg_id, params)
            return None
        return self._build_response(msg_id, method, params)

    def _dispatch_outbound_response(self, msg_id: Any,
                                    message: Dict[str, Any]) -> None:
        """Route a JSON-RPC response to the matching pending request."""
        with self._outbound_lock:
            slot = self._pending_outbound.get(msg_id)
        if slot is None:
            autocontrol_logger.debug(
                "MCP outbound response for unknown id %r", msg_id,
            )
            return
        if "error" in message:
            slot["error"] = message["error"]
        else:
            slot["result"] = message.get("result")
        slot["event"].set()

    def _dispatch_tools_call_async(self, msg_id: Any,
                                   params: Dict[str, Any]) -> None:
        """Run a tools/call on a worker thread; the worker writes the reply."""
        def worker() -> None:
            payload = self._build_response(msg_id, _TOOLS_CALL_METHOD, params)
            writer = self._writer
            if writer is None:
                autocontrol_logger.warning(
                    "MCP async tool reply with no writer; dropping %s", msg_id,
                )
                return
            writer(payload)
        threading.Thread(
            target=worker, daemon=True, name=f"MCPCall-{msg_id}",
        ).start()

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
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as error:
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

    def _maybe_request_roots_async(self) -> None:
        """Fire a roots/list request when the client supports it."""
        if "roots" not in self._client_capabilities:
            return
        if self._writer is None:
            return
        threading.Thread(
            target=self._refresh_roots_safely, daemon=True,
            name="MCPRootsRefresh",
        ).start()

    def _refresh_roots_safely(self) -> None:
        try:
            self.refresh_roots(timeout=5.0)
        except (RuntimeError, TimeoutError) as error:
            autocontrol_logger.info("MCP roots refresh skipped: %r", error)

    def refresh_roots(self, timeout: float = 10.0) -> List[Dict[str, Any]]:
        """Send ``roots/list`` to the client and apply the first root."""
        result = self._send_outbound_request(
            "roots/list", params={}, timeout=timeout,
        )
        roots_list = (result or {}).get("roots") or []
        if not isinstance(roots_list, list) or not roots_list:
            return []
        first_uri = roots_list[0].get("uri") if isinstance(roots_list[0],
                                                            dict) else None
        if isinstance(first_uri, str):
            local_path = _file_uri_to_path(first_uri)
            if local_path:
                self._resources.set_workspace_root(local_path)
                autocontrol_logger.info("MCP workspace root → %s", local_path)
        return roots_list

    def _send_outbound_request(self, method: str,
                               params: Dict[str, Any],
                               timeout: float = 10.0) -> Dict[str, Any]:
        """Send a server-initiated request and wait for the response."""
        writer = self._writer
        if writer is None:
            raise RuntimeError(f"{method} requires an outbound writer")
        request_id = f"srv-{next(self._outbound_id_counter)}"
        slot = {"event": threading.Event()}
        with self._outbound_lock:
            self._pending_outbound[request_id] = slot
        envelope = json.dumps({
            "jsonrpc": "2.0", "id": request_id,
            "method": method, "params": params,
        }, ensure_ascii=False, default=str)
        try:
            writer(envelope)
            if not slot["event"].wait(timeout=timeout):
                raise TimeoutError(f"{method} timed out after {timeout}s")
        finally:
            with self._outbound_lock:
                self._pending_outbound.pop(request_id, None)
        if "error" in slot:
            raise RuntimeError(f"{method} failed: {slot['error']}")
        return slot.get("result") or {}

    def _cancel_active_call(self, params: Dict[str, Any]) -> None:
        """Mark the matching active tool call as cancelled, if any."""
        request_id = params.get("requestId")
        if request_id is None:
            return
        with self._calls_lock:
            ctx = self._active_calls.get(request_id)
        if ctx is not None:
            ctx.cancelled_event.set()
            autocontrol_logger.info(
                "MCP cancel signalled for call %r", request_id,
            )

    def _dispatch(self, msg_id: Any, method: Optional[str],
                  params: Dict[str, Any]) -> Any:
        if method == "initialize":
            return self._handle_initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [tool.to_descriptor()
                              for tool in self._tools.values()]}
        if method == _TOOLS_CALL_METHOD:
            return self._handle_tools_call(msg_id, params)
        if method == "resources/list":
            return {"resources": [resource.to_descriptor()
                                   for resource in self._resources.list()]}
        if method == "resources/read":
            return self._handle_resources_read(params)
        if method == "resources/subscribe":
            return self._handle_resources_subscribe(params)
        if method == "resources/unsubscribe":
            return self._handle_resources_unsubscribe(params)
        if method == "prompts/list":
            return {"prompts": [prompt.to_descriptor()
                                 for prompt in self._prompts.list()]}
        if method == "prompts/get":
            return self._handle_prompts_get(params)
        if method == "logging/setLevel":
            return self._handle_logging_set_level(params)
        raise _MCPError(-32601, f"Method not found: {method}")

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
        with self._subscriptions_lock:
            if uri in self._resource_subscriptions:
                return {}
        handle = self._resources.subscribe(
            uri, lambda u=uri: self._notify_resource_updated(u),
        )
        if handle is None:
            raise _MCPError(-32602, f"Unsubscribable resource: {uri}")
        with self._subscriptions_lock:
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

    def _handle_tools_call(self, msg_id: Any,
                           params: Dict[str, Any]) -> Dict[str, Any]:
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
        ctx = self._build_call_context(msg_id, params)
        with self._calls_lock:
            self._active_calls[msg_id] = ctx
        started_at = time.monotonic()
        try:
            result = tool.invoke(arguments, ctx=ctx)
        except OperationCancelledError:
            self._audit.record(
                tool=name, arguments=arguments, status="cancelled",
                duration_seconds=time.monotonic() - started_at,
            )
            raise
        except (OSError, RuntimeError, ValueError, TypeError,
                AttributeError, KeyError) as error:
            # NotImplementedError subclasses RuntimeError so it's already covered.
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
                self._active_calls.pop(msg_id, None)
        self._audit.record(
            tool=name, arguments=arguments, status="ok",
            duration_seconds=time.monotonic() - started_at,
        )
        return {
            "content": _to_content_blocks(result),
            "isError": False,
        }

    def request_elicitation(self, message: str,
                            requested_schema: Optional[Dict[str, Any]] = None,
                            timeout: float = 60.0) -> Dict[str, Any]:
        """Ask the connected client to elicit a response from the user.

        Returns the raw payload (typically ``{"action": "accept" | "decline" | "cancel", ...}``).
        Requires the client to advertise the ``elicitation`` capability.
        """
        params: Dict[str, Any] = {"message": str(message)}
        if requested_schema is not None:
            params["requestedSchema"] = requested_schema
        return self._send_outbound_request(
            "elicitation/create", params=params, timeout=timeout,
        )

    def request_sampling(self, messages: List[Dict[str, Any]],
                         system_prompt: Optional[str] = None,
                         max_tokens: int = 1024,
                         model_preferences: Optional[Dict[str, Any]] = None,
                         timeout: float = 120.0) -> Dict[str, Any]:
        """Ask the connected client to run an LLM sampling request.

        Tools that need the model's help (e.g. an OCR fallback that
        wants the model to identify a UI element from a screenshot)
        can call this and receive the assistant's reply. Requires the
        server to be running in concurrent mode with an outbound
        writer set — typically meaning ``serve_stdio`` or the HTTP
        SSE transport.
        """
        writer = self._writer
        if writer is None:
            raise RuntimeError(
                "request_sampling requires an outbound writer; "
                "start serve_stdio or call set_writer() first",
            )
        request_id = f"sampling-{next(self._sampling_id_counter)}"
        params: Dict[str, Any] = {
            "messages": list(messages),
            "maxTokens": int(max_tokens),
        }
        if system_prompt is not None:
            params["systemPrompt"] = str(system_prompt)
        if model_preferences is not None:
            params["modelPreferences"] = dict(model_preferences)
        slot = {"event": threading.Event()}
        with self._outbound_lock:
            self._pending_outbound[request_id] = slot
        envelope = json.dumps({
            "jsonrpc": "2.0", "id": request_id,
            "method": "sampling/createMessage", "params": params,
        }, ensure_ascii=False, default=str)
        try:
            writer(envelope)
            if not slot["event"].wait(timeout=timeout):
                raise TimeoutError(
                    f"sampling request {request_id} timed out after {timeout}s"
                )
        finally:
            with self._outbound_lock:
                self._pending_outbound.pop(request_id, None)
        if "error" in slot:
            raise RuntimeError(f"sampling failed: {slot['error']}")
        return slot.get("result") or {}

    def _maybe_confirm_destructive(self, name: str, tool: MCPTool,
                                    arguments: Dict[str, Any]) -> None:
        """Ask the client to confirm before running a destructive tool."""
        if not _confirm_destructive_enabled():
            return
        annotations = tool.annotations
        if annotations.read_only or not annotations.destructive:
            return
        if "elicitation" not in self._client_capabilities:
            autocontrol_logger.info(
                "MCP confirmation requested for %s but client lacks "
                "elicitation capability — proceeding without prompt", name,
            )
            return
        if self._writer is None:
            return
        prompt = (f"AutoControl is about to run a destructive tool "
                  f"'{name}'. Continue?")
        try:
            response = self.request_elicitation(
                message=prompt, requested_schema={"type": "object",
                                                    "properties": {}},
                timeout=60.0,
            )
        except (RuntimeError, TimeoutError) as error:
            autocontrol_logger.info(
                "MCP elicitation for %s failed (%r) — refusing call",
                name, error,
            )
            raise _MCPError(-32000,
                             f"User confirmation unavailable for {name}")
        action = response.get("action") if isinstance(response, dict) else None
        if action != "accept":
            raise _MCPError(-32000, f"User declined to run {name}: action={action!r}")
        del arguments  # available for future per-arg confirmation policies

    def _build_call_context(self, msg_id: Any,
                            params: Dict[str, Any]) -> ToolCallContext:
        meta = params.get("_meta") if isinstance(params.get("_meta"),
                                                  dict) else {}
        progress_token = meta.get("progressToken") if isinstance(meta, dict) else None
        return ToolCallContext(
            request_id=msg_id, progress_token=progress_token,
            notifier=self._notifier,
        )


def _to_content_blocks(result: Any) -> List[Dict[str, Any]]:
    """Normalise a tool's return value into MCP ``content`` blocks."""
    if isinstance(result, MCPContent):
        return [result.to_dict()]
    if isinstance(result, list) and result and \
            all(isinstance(item, MCPContent) for item in result):
        return [item.to_dict() for item in result]
    return [{"type": "text", "text": _stringify_result(result)}]


def _stringify_result(value: Any) -> str:
    """Convert a tool return value into a model-readable string."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


def _confirm_destructive_enabled() -> bool:
    """Return True when the operator wants destructive tools gated on user OK."""
    raw = os.environ.get("JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _capture_error_screenshot(tool_name: str) -> Optional[str]:
    """Save a debug screenshot when JE_AUTOCONTROL_MCP_ERROR_SHOTS is set."""
    debug_dir = os.environ.get("JE_AUTOCONTROL_MCP_ERROR_SHOTS")
    if not debug_dir:
        return None
    target_dir = os.path.realpath(os.fspath(debug_dir))
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as error:
        autocontrol_logger.info(
            "MCP error-screenshot dir unavailable: %r", error,
        )
        return None
    filename = f"{tool_name}_{int(time.time() * 1000)}.png"
    path = os.path.join(target_dir, filename)
    try:
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        pil_screenshot(file_path=path)
    except (OSError, RuntimeError, ValueError, AttributeError,
            ImportError) as error:
        autocontrol_logger.info(
            "MCP failed to capture error screenshot: %r", error,
        )
        return None
    return path


def _file_uri_to_path(uri: str) -> Optional[str]:
    """Convert a ``file://`` URI to a local filesystem path; ``None`` otherwise."""
    if not isinstance(uri, str) or not uri.startswith("file://"):
        return None
    from urllib.parse import unquote, urlparse
    parsed = urlparse(uri)
    raw_path = unquote(parsed.path)
    # Windows: file:///C:/foo strips the leading slash before the drive letter.
    if sys.platform.startswith("win") and raw_path.startswith("/") and \
            len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return raw_path or None


def _notification_message(method: str, params: Dict[str, Any]) -> str:
    return json.dumps({"jsonrpc": "2.0", "method": method, "params": params},
                      ensure_ascii=False, default=str)


def _result_response(msg_id: Any, result: Any) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": msg_id, "result": result},
        ensure_ascii=False, default=str,
    )


def _error_response(msg_id: Any, code: int, message: str) -> str:
    return json.dumps({
        "jsonrpc": "2.0", "id": msg_id,
        "error": {"code": code, "message": message},
    }, ensure_ascii=False)


def start_mcp_stdio_server() -> MCPServer:
    """Start a stdio MCP server in the foreground; blocks until EOF."""
    server = MCPServer()
    server.serve_stdio()
    return server
