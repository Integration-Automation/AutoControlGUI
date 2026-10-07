"""Session-local tool enable/disable/state handlers; availability never grants call privileges."""
from __future__ import annotations

from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.disclosure import (
    DisclosureMode, ToolDisclosureError, ToolView, preview_tool_disclosure,
)
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, ToolCategory, schema


def _view(ctx: ToolCallContext | None) -> ToolView:
    if ctx is None or ctx.tool_view is None:
        raise ToolDisclosureError('owned MCP session required')
    ctx.check_cancelled()
    return ctx.tool_view


def _enable(names: list[str], ctx: ToolCallContext | None = None) -> dict[str, object]:
    return _view(ctx).enable(names).to_dict()


def _disable(names: list[str], ctx: ToolCallContext | None = None) -> dict[str, object]:
    return _view(ctx).disable(names).to_dict()


def _state(ctx: ToolCallContext | None = None) -> dict[str, object]:
    return _view(ctx).state()


def _preview(mode: DisclosureMode = 'progressive', names: list[str] | None = None,
             profile: list[str] | None = None, ctx: ToolCallContext | None = None) -> dict[str, object]:
    index = ctx.tool_index() if ctx is not None and ctx.tool_index is not None else None
    return preview_tool_disclosure(mode, names if names is not None else (),
                                   profile if profile is not None else (), index=index)


def disclosure_tools() -> list[MCPTool]:
    """Expose per-session availability control and passive current state."""
    names_schema = schema({'names': {'type': 'array', 'maxItems': 100,
                                    'items': {'type': 'string', 'minLength': 1, 'maxLength': 256}}}, ['names'])
    category = ToolCategory('disclosure')
    return [
        MCPTool('ac_enable_tools', 'Enable authorized tools in this progressive session only; no execution.',
                names_schema, _enable, READ_ONLY, {'type': 'object'}, category),
        MCPTool('ac_disable_tools', 'Disable this session selection; core discovery tools stay available.',
                names_schema, _disable, READ_ONLY, {'type': 'object'}, category),
        MCPTool('ac_preview_tool_disclosure', 'Preview isolated tool availability; never change this session.',
                schema({'mode': {'type': 'string', 'enum': ['full', 'progressive', 'static']},
                        'names': names_schema['properties']['names'], 'profile': names_schema['properties']['names']}),
                _preview, READ_ONLY, {'type': 'object'}, category),
        MCPTool('ac_tool_state', 'Report this session tool mode, authorized visible names and registry version.',
                schema({}), _state, READ_ONLY, {'type': 'object'}, category),
    ]
