"""The five tools a progressive MCP session starts with.

Search, schema, enable, disable and state: everything a client needs to find
a tool and add it to its own list, and nothing that runs one. They are
ordinary registry entries, so a call to any of them passes the same gates as
every other call, and each answers from the caller's own catalog
(:meth:`ToolDisclosure.catalog`) -- a tool the caller's role or the server's
read-only mode rules out is not found, described or enabled here.

All five are annotated read-only. They change one session's tool list, not
the machine, and a read-only server or a viewer role has to be able to use
them to reach the read-only tools it is allowed.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.mcp_server.disclosure import (
    CATEGORY_PREFIX, CORE_TOOL_NAMES, DISABLE_TOOL, ENABLE_TOOL, SCHEMA_TOOL,
    SEARCH_TOOL, STATE_TOOL, ToolDisclosure,
)
from je_auto_control.utils.mcp_server.discovery import (
    DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT, checked_limit,
)
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, schema
from je_auto_control.utils.rbac.authorization import current_authorization
from je_auto_control.utils.rbac.users import Capability

CORE_CATEGORY = "tool_discovery"
_Spec = Tuple[str, str, Dict[str, Any], Callable[..., Any]]


class _CoreHandlers:
    """The handlers, bound to one server's :class:`ToolDisclosure`."""

    def __init__(self, disclosure: ToolDisclosure) -> None:
        self._disclosure = disclosure

    def search(self, query: str = "", limit: int = DEFAULT_SEARCH_LIMIT,
               category: Optional[str] = None,
               capability: Optional[str] = None) -> Dict[str, Any]:
        """Summaries of the best matches, each marked with whether it is enabled."""
        bounded = checked_limit(limit)
        found = self._disclosure.index().matches(query, category=category, capability=capability)
        visible = set(self._disclosure.current_view().visible_names)
        return {
            "tools": [{**item.to_dict(), "enabled": item.name in visible}
                      for item in found[:bounded]],
            "total": len(found), "truncated": len(found) > bounded,
        }

    def schema(self, name: str) -> Dict[str, Any]:
        """The full descriptor of one tool."""
        return self._disclosure.index().get_schema(name).to_dict()

    def enable(self, names: Sequence[str]) -> Dict[str, Any]:
        """Add tools to the calling session's list."""
        return self._disclosure.current_view().enable(names).to_dict()

    def disable(self, names: Sequence[str]) -> Dict[str, Any]:
        """Remove tools the calling session enabled."""
        return self._disclosure.current_view().disable(names).to_dict()

    def state(self) -> Dict[str, Any]:
        """The mode, the session's enabled tools and the limits calls are held to."""
        disclosure = self._disclosure
        caller = current_authorization()
        index = disclosure.index()
        return {
            "mode": disclosure.mode.value, "read_only": disclosure.read_only,
            "role": caller.role if caller is not None else None,
            "path_roots": disclosure.argument_policy.path_policy.enabled,
            "env_allowlist": disclosure.argument_policy.env_allowlist is not None,
            "available": len(index),
            "enabled": [name for name in disclosure.current_view().visible_names
                        if name not in CORE_TOOL_NAMES],
            "categories": index.categories(),
        }


def build_core_tools(disclosure: ToolDisclosure) -> List[MCPTool]:
    """The core tools of ``disclosure``'s server, in :data:`CORE_TOOL_NAMES` order."""
    handlers = _CoreHandlers(disclosure)
    names = {"type": "array", "items": {"type": "string"},
             "description": f"Tool names, or {CATEGORY_PREFIX}<name> for a whole category."}
    specs: List[_Spec] = [
        (SEARCH_TOOL,
         "Search the tools this server has. Returns names, one-line summaries, category "
         f"and required capability, never schemas. Enable a result with {ENABLE_TOOL}.",
         schema({
             "query": {"type": "string", "description": "Words to look for; empty lists all."},
             "limit": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_LIMIT,
                       "default": DEFAULT_SEARCH_LIMIT},
             "category": {"type": "string", "description": f"From {STATE_TOOL}."},
             "capability": {"type": "string", "enum": Capability.all()},
         }), handlers.search),
        (SCHEMA_TOOL, "Return the full schema of one tool by name.",
         schema({"name": {"type": "string"}}, required=["name"]), handlers.schema),
        (ENABLE_TOOL,
         "Add tools to this session's tool list so they can be called. The list changes; "
         "request tools/list again if no list_changed notification arrives.",
         schema({"names": names}, required=["names"]), handlers.enable),
        (DISABLE_TOOL, "Remove tools this session enabled from its tool list.",
         schema({"names": names}, required=["names"]), handlers.disable),
        (STATE_TOOL,
         "Report the tool mode, what this session has enabled, the categories that can be "
         "searched and the limits (read-only, path roots, role) calls are held to.",
         schema({}), handlers.state),
    ]
    return [MCPTool(name=name, description=description, input_schema=input_schema,
                    handler=handler, annotations=READ_ONLY, category=CORE_CATEGORY)
            for name, description, input_schema, handler in specs]


__all__ = ["CORE_CATEGORY", "build_core_tools"]
