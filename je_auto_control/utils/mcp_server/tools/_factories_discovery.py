"""Compact discovery/schema MCP tools bound to the actual serving registry."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.discovery import ToolIndex, default_tool_index
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, ToolCategory, schema


def _index(ctx: ToolCallContext | None) -> ToolIndex:
    return ctx.tool_index() if ctx is not None and ctx.tool_index is not None else default_tool_index()


def _discover(query: str = '', limit: int = 10, ctx: ToolCallContext | None = None) -> dict[str, object]:
    index = _index(ctx)
    return {'version': index.version, 'tools': [row.to_dict() for row in index.search(query, limit=limit)]}


def _get_schema(name: str, ctx: ToolCallContext | None = None) -> dict[str, Any]:
    return _index(ctx).get_schema(name).to_dict()


def discovery_tools() -> list[MCPTool]:
    """Expose bounded summary search and one authorized descriptor at a time."""
    return [
        MCPTool('ac_discover_tools', 'Search available tools; returns compact summaries without schemas.',
                schema({'query': {'type': 'string', 'maxLength': 512},
                        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}), _discover, READ_ONLY,
                {'type': 'object', 'properties': {'version': {'type': 'integer'}, 'tools': {'type': 'array'}}},
                ToolCategory('discovery')),
        MCPTool('ac_get_tool_schema', 'Read one available tool schema without calling or enabling it.',
                schema({'name': {'type': 'string', 'minLength': 1, 'maxLength': 256}}, ['name']),
                _get_schema, READ_ONLY, {'type': 'object'}, ToolCategory('discovery')),
    ]
