"""Small discovery tools query the active server registry instead of constructing another catalogue."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, schema


def _search(query: str, limit: int = 10, ctx: ToolCallContext | None = None) -> list:
    if ctx is not None and ctx.tool_catalog is not None:
        ctx.check_cancelled()
        return ctx.tool_catalog().search(query, limit=limit)
    # pylint: disable-next=import-outside-toplevel  # reason: avoid a registry/type import cycle
    from je_auto_control.utils.mcp_server.discovery import search_mcp_tools
    return search_mcp_tools(query, limit=limit)


def _schema(name: str, ctx: ToolCallContext | None = None) -> dict[str, Any]:
    if ctx is not None and ctx.tool_catalog is not None:
        ctx.check_cancelled()
        return ctx.tool_catalog().get_schema(name)
    # pylint: disable-next=import-outside-toplevel  # reason: avoid a registry/type import cycle
    from je_auto_control.utils.mcp_server.discovery import get_mcp_tool_schema
    return get_mcp_tool_schema(name)


def discovery_tools() -> list[MCPTool]:
    """Declare discovery from the same registry source and existing invocation boundary."""
    return [
        MCPTool("ac_mcp_tool_search", "Search permitted tools; returns summaries without full schemas.",
                schema({"query": {"type": "string", "maxLength": 256},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, required=["query"]),
                _search, READ_ONLY),
        MCPTool("ac_mcp_tool_schema", "Inspect one permitted tool's complete schema without executing it.",
                schema({"name": {"type": "string", "minLength": 1, "maxLength": 256}}, required=["name"]),
                _schema, READ_ONLY),
    ]
