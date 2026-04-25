"""Minimal MCP server speaking JSON-RPC 2.0 over stdio.

Implements the subset of the Model Context Protocol that Claude clients
(Claude Desktop, Claude Code, Claude API) use to discover and invoke
tools: ``initialize``, ``tools/list``, ``tools/call``, ``ping``, and
``notifications/initialized``. Each transport line is one JSON-RPC
message — no Content-Length framing — matching the MCP stdio spec.
"""
import itertools
import json
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, TextIO

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.context import (
    OperationCancelledError, ToolCallContext,
)
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
                 concurrent_tools: bool = False
                 ) -> None:
        registry = tools if tools is not None else build_default_tool_registry()
        self._tools: Dict[str, MCPTool] = {tool.name: tool for tool in registry}
        self._resources = (resource_provider if resource_provider is not None
                            else default_resource_provider())
        self._prompts = (prompt_provider if prompt_provider is not None
                          else default_prompt_provider())
        self._concurrent_tools = bool(concurrent_tools)
        self._stop = threading.Event()
        self._initialized = False
        self._notifier: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._writer: Optional[Callable[[str], None]] = None
        self._active_calls: Dict[Any, ToolCallContext] = {}
        self._calls_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._sampling_id_counter = itertools.count(1)
        self._pending_outbound: Dict[Any, Dict[str, Any]] = {}
        self._outbound_lock = threading.Lock()

    def register_tool(self, tool: MCPTool) -> None:
        """Add or replace a tool in the live registry."""
        self._tools[tool.name] = tool

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
        if method == "tools/call" and self._concurrent_tools:
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
            payload = self._build_response(msg_id, "tools/call", params)
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
            return
        if method == "notifications/cancelled":
            self._cancel_active_call(params)
            return
        autocontrol_logger.debug("MCP notification ignored: %s", method)

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
        if method == "tools/call":
            return self._handle_tools_call(msg_id, params)
        if method == "resources/list":
            return {"resources": [resource.to_descriptor()
                                   for resource in self._resources.list()]}
        if method == "resources/read":
            return self._handle_resources_read(params)
        if method == "prompts/list":
            return {"prompts": [prompt.to_descriptor()
                                 for prompt in self._prompts.list()]}
        if method == "prompts/get":
            return self._handle_prompts_get(params)
        raise _MCPError(-32601, f"Method not found: {method}")

    @staticmethod
    def _handle_initialize(params: Dict[str, Any]) -> Dict[str, Any]:
        client_version = params.get("protocolVersion", PROTOCOL_VERSION)
        return {
            "protocolVersion": client_version or PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
                "prompts": {"listChanged": False},
                "sampling": {},
            },
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
        ctx = self._build_call_context(msg_id, params)
        with self._calls_lock:
            self._active_calls[msg_id] = ctx
        try:
            result = tool.invoke(arguments, ctx=ctx)
        except OperationCancelledError:
            raise
        except (OSError, RuntimeError, ValueError, TypeError,
                AttributeError, KeyError, NotImplementedError) as error:
            autocontrol_logger.warning("MCP tool %s failed: %r", name, error)
            return {
                "content": [{"type": "text",
                             "text": f"{type(error).__name__}: {error}"}],
                "isError": True,
            }
        finally:
            with self._calls_lock:
                self._active_calls.pop(msg_id, None)
        return {
            "content": _to_content_blocks(result),
            "isError": False,
        }

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
