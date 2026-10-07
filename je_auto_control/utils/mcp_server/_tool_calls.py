"""MCP tool invocation and authenticated audit records, isolated from dispatch."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.context import OperationCancelledError
from je_auto_control.utils.mcp_server._input_required import AnsweredByGate
from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.mcp_server.tools._base import read_only_env_flag
from je_auto_control.utils.mcp_server.tools._validation import undeclared_arguments, validate_arguments
from je_auto_control.utils.mcp_server.tools._path_metadata import validate_path_arguments
from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
from je_auto_control.utils.rbac.authorization import require_command

from je_auto_control.utils.mcp_server._protocol import (
    _InvalidToolArguments, _MCPError, _capture_error_screenshot, _to_content_blocks,
)
from je_auto_control.utils.path_guard.policy import path_policy_scope
from je_auto_control.utils.script_vars.scope import execution_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError, current_authorization

if TYPE_CHECKING:
    from je_auto_control.utils.mcp_server.server import MCPServer


def handle_tool_call(server: MCPServer, msg_id: Any,
                     params: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke one authorized tool and preserve its authenticated audit identity."""
    identity = current_authorization()
    user_id = identity.user_id if identity is not None else None
    try:
        name, tool, arguments = server._prepare_tool_call(params)
    except AuthorizationError as error:
        server._audit.record(
            tool=str(params.get('name', '')), arguments=params.get('arguments') or {},
            status='denied', duration_seconds=0,
            user_id=user_id)
        return {'content': [{'type': 'text', 'text': str(error)}], 'isError': True}
    except _InvalidToolArguments as error:
        return {"content": [{"type": "text", "text": str(error)}], "isError": True}
    except AnsweredByGate as answered:
        return answered.result
    return _invoke_tool(server, msg_id, name, tool, arguments, user_id, params)


def _invoke_tool(server: MCPServer, msg_id: Any, name: str, tool: Any,
                 arguments: Dict[str, Any], user_id: Optional[str],
                 params: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke validated tools and audit outcomes within their request scope."""
    ctx = server._build_call_context(msg_id, params)
    call_key = (server._connection_id, msg_id)
    with server._calls_lock:
        server._active_calls[call_key] = ctx
    started_at = time.monotonic()
    try:
        with path_policy_scope(server._current_path_policy()), execution_scope(isolated=True):
            result = tool.invoke(arguments, ctx=ctx)
    except OperationCancelledError:
        server._audit.record(
            tool=name, arguments=arguments, status="cancelled",
            user_id=user_id,
            duration_seconds=time.monotonic() - started_at,
        )
        raise
    except _MCPError:
        raise
    # Any exception, not a list: re.PatternError, ET.ParseError, cv2.error or
    # a plugin's own error escaped the list, killed the worker thread and
    # left the call unanswered (stdio) or dropped the connection (HTTP).
    except Exception as error:  # noqa: BLE001  # reason: a tool's failure of any type must answer the call with isError
        autocontrol_logger.warning("MCP tool %s failed: %r", name, error)
        artifact = _capture_error_screenshot(name)
        server._audit.record(
            tool=name, arguments=arguments, status="error",
            user_id=user_id,
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
        with server._calls_lock:
            server._active_calls.pop(call_key, None)
    server._audit.record(
        tool=name, arguments=arguments, status="ok",
        user_id=user_id,
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


def prepare_tool_call(server: MCPServer, params: Dict[str, Any]) -> tuple[str, MCPTool, Dict[str, Any]]:
    """Apply the existing call authorization/schema/path/rate/confirmation pipeline."""
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str):
        raise _MCPError(-32602, "tools/call requires string 'name'")
    if not isinstance(arguments, dict):
        raise _MCPError(-32602, "tools/call 'arguments' must be an object")
    tool = server._tools.get(name)
    if tool is None:
        raise _MCPError(-32602, f"Unknown tool: {name}")
    _authorize_call(name, tool, arguments)
    violation = (validate_arguments(tool.input_schema, arguments)
                 or undeclared_arguments(tool.input_schema, arguments))
    if violation is not None:
        raise _InvalidToolArguments(f"Invalid arguments for {name}: {violation}")
    try:
        arguments = validate_path_arguments(arguments, tool.input_schema,
                                             server._current_path_policy())
    except PathNotAllowedError as error:
        raise _InvalidToolArguments(str(error)) from error
    if server._rate_limiter is not None and not server._rate_limiter.try_acquire():
        raise _MCPError(-32000, f"Rate limit exceeded for tool {name!r}")
    server._maybe_confirm_destructive(name, tool, arguments)
    return name, tool, arguments


def _authorize_call(name: str, tool: MCPTool, arguments: Dict[str, Any]) -> None:
    """Refuse readonly mutations before the existing argument-sensitive capability guard."""
    if read_only_env_flag() and not tool.annotations.read_only:
        raise AuthorizationError("tool unavailable in readonly mode")
    require_command(name, read_only=tool.annotations.read_only, arguments=arguments)
