"""Bearer authentication and per-role tool authorisation for the MCP server.

Two halves, one per layer. :func:`check_bearer` is the HTTP transport's: it
turns the ``Authorization`` header value into either a refusal or -- when a user
store is configured -- the caller's identity. :func:`visible_tools` and
:func:`authorize_tool_call` are the dispatcher's: ``tools/list`` shows only
what the caller may call, and ``tools/call`` refuses the rest, so the two
answers cannot disagree.

Without a user store nothing here identifies anyone: the transport keeps
its optional shared token and the dispatcher offers every tool, as before.
"""
import hmac
from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.mcp_server._protocol import _MCPError
from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, current_authorization, resolve_token,
)
from je_auto_control.utils.rbac.policy import capability_for_tool, denied_command_in
from je_auto_control.utils.rbac.users import Capability, UserStore

#: JSON-RPC error code of a call refused for the caller's role.
FORBIDDEN_CODE = -32003

#: ``(HTTP status, error text)`` of a refused request.
Refusal = Tuple[int, str]


def check_bearer(authorization: Optional[str], expected: Optional[str],
                 users: Optional[UserStore],
                 ) -> Tuple[Optional[AuthorizationContext], Optional[Refusal]]:
    """``(caller, refusal)`` for a request's ``Authorization`` header.

    With ``users`` the token must be one user's and the caller is returned;
    the shared ``expected`` token is not consulted, because a token that
    passed for everyone could not be given a role. Without ``users`` the
    caller is always ``None`` and ``expected`` is compared as before -- no
    token configured means no check.
    """
    if users is None and expected is None:
        return None, None
    # The scheme is case-insensitive (RFC 7235 2.1): "bearer tok" was
    # refused here while the REST gate accepted it.
    scheme, _, provided = (authorization or "").strip().partition(" ")
    if scheme.lower() != "bearer":
        return None, (401, "missing bearer token")
    provided = provided.strip()
    if users is None:
        # Bytes: compare_digest raises TypeError on a non-ASCII str, and
        # http.server decodes headers as latin-1, so a crafted token used to
        # kill the request thread instead of being refused.
        if hmac.compare_digest(provided.encode("utf-8"), str(expected).encode("utf-8")):
            return None, None
        return None, (401, "invalid bearer token")
    caller = resolve_token(users, provided) if provided else None
    if caller is None:
        return None, (401, "invalid bearer token")
    if not caller.allows(Capability.READ_SCREEN):
        # A role the store does not define grants nothing; without this the
        # ungated methods (resources, prompts) would still answer it.
        return None, (403, f"role {caller.role!r} grants no access")
    return caller, None


def _tool_capability(tool: MCPTool) -> str:
    return capability_for_tool(tool.name, tool.annotations.read_only)


def visible_tools(tools: List[MCPTool]) -> List[MCPTool]:
    """The tools the current caller may call; all of them outside an RBAC scope."""
    caller = current_authorization()
    if caller is None:
        return tools
    return [tool for tool in tools if caller.allows(_tool_capability(tool))]


def authorize_tool_call(tool: MCPTool, arguments: Dict[str, Any],
                        audit: AuditLogger) -> None:
    """Refuse, and record, a call the current caller's role does not grant.

    Two things can be missing: the capability of the tool itself, or that of
    a privileged ``AC_*`` command inside an action list among its arguments
    -- ``ac_execute_actions`` is open to an operator, signing a file through
    it is not.
    """
    caller = current_authorization()
    if caller is None:
        return
    needed: Optional[str] = _tool_capability(tool)
    reason = f"tool {tool.name!r}"
    if caller.allows(str(needed)):
        denied = denied_command_in(arguments, caller)
        if denied is None:
            return
        reason, needed = f"command {denied[0]!r}", denied[1]
    message = (f"Forbidden: {reason} needs the {needed!r} capability; "
               f"role {caller.role!r} does not grant it")
    audit.record(tool=tool.name, arguments=arguments, status="denied",
                 duration_seconds=0.0, error_text=message)
    raise _MCPError(FORBIDDEN_CODE, message, {"required_capability": needed})


__all__ = [
    "FORBIDDEN_CODE", "authorize_tool_call", "check_bearer", "visible_tools",
]
