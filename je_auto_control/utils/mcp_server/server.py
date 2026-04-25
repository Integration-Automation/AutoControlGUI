"""Minimal MCP server speaking JSON-RPC 2.0 over stdio.

Implements the subset of the Model Context Protocol that Claude clients
(Claude Desktop, Claude Code, Claude API) use to discover and invoke
tools: ``initialize``, ``tools/list``, ``tools/call``, ``ping``, and
``notifications/initialized``. Each transport line is one JSON-RPC
message — no Content-Length framing — matching the MCP stdio spec.
"""
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
                 prompt_provider: Optional[PromptProvider] = None
                 ) -> None:
        registry = tools if tools is not None else build_default_tool_registry()
        self._tools: Dict[str, MCPTool] = {tool.name: tool for tool in registry}
        self._resources = (resource_provider if resource_provider is not None
                            else default_resource_provider())
        self._prompts = (prompt_provider if prompt_provider is not None
                          else default_prompt_provider())
        self._stop = threading.Event()
        self._initialized = False
        self._notifier: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._active_calls: Dict[Any, ToolCallContext] = {}
        self._calls_lock = threading.Lock()
        self._write_lock = threading.Lock()

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
        self._notifier = lambda method, params: self._write_message(
            out_stream, _notification_message(method, params),
        )
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

        if msg_id is None:
            self._handle_notification(method, params)
            return None
        return self._build_response(msg_id, method, params)

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
