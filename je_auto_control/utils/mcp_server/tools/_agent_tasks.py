"""Managed task tools with shared schemas and original caller/session authority."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime.commands import CATALOG
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.exception.cancellation import CancellationToken, cancellation_scope
from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.tools._base import MCPTool, NON_DESTRUCTIVE, READ_ONLY
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope, current_authorization


def _handler(command: str) -> Any:
    function, _properties, _required, _readonly, host_management = CATALOG[command]

    def handle(*, ctx: ToolCallContext | None = None, **arguments: Any) -> Any:
        if ctx is not None:
            ctx.check_cancelled()
            _paths(ctx, arguments)
        token = CancellationToken(0, event=ctx.cancelled_event) if ctx is not None else None
        identity = current_authorization()
        if identity is None and not host_management:
            if ctx is None or not ctx.session_id:
                raise AgentTaskError("managed MCP tasks require an authenticated caller or a live session")
            identity = AuthorizationContext("mcp:" + ctx.session_id, "operator")
        with authorization_scope(identity), cancellation_scope(token):
            return function(**arguments)
    return handle


def _paths(context: ToolCallContext, arguments: Any) -> None:
    policy = context.path_policy
    if policy is None or not policy.enabled:
        return
    if isinstance(arguments, dict):
        for name, value in arguments.items():
            if not _path_argument(policy, name, value):
                _paths(context, value)
    elif isinstance(arguments, (tuple, list)):
        for value in arguments:
            _paths(context, value)


def _path_argument(policy: Any, name: str, value: Any) -> bool:
    if name == "roots":
        if not isinstance(value, list):
            raise AgentTaskError("task roots must be an array")
        for path in value:
            policy.validate(path, operation="agent task roots")
        return True
    if name in {"path", "file_path", "directory", "source", "destination", "output_path"} and isinstance(value, str):
        policy.validate(value, operation="agent task path")
        return True
    return False


def agent_task_tools() -> list[MCPTool]:
    """Build task tools from exactly the same catalogue as executor and Builder."""
    tools = []
    for name, (function, properties, required, readonly, _management) in CATALOG.items():
        tools.append(MCPTool(name=name.lower(), description=function.__doc__ or name,
                             input_schema={"type": "object", "properties": properties,
                                           "required": list(required), "additionalProperties": False},
                             handler=_handler(name), annotations=READ_ONLY if readonly else NON_DESTRUCTIVE))
    return tools
