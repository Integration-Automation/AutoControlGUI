"""MCP tool registry for AutoControl.

The package is split into ``_base`` (value types and helpers),
``_handlers`` (adapter functions that bridge to the headless API), and
``_factories`` (per-domain ``MCPTool`` builders). Public consumers
should import only the names re-exported here.
"""
from typing import List, Optional

from je_auto_control.utils.mcp_server.tools._base import (
    MCPContent, MCPTool, MCPToolAnnotations, read_only_env_flag,
)
from je_auto_control.utils.mcp_server.tools._factories import ALL_FACTORIES


def build_default_tool_registry(read_only: Optional[bool] = None
                                ) -> List[MCPTool]:
    """Return the full set of tools the MCP server exposes by default.

    :param read_only: when True, drop every tool whose annotations
        indicate it can mutate state. When None (default), the value
        of ``JE_AUTOCONTROL_MCP_READONLY`` is consulted, so deployments
        can pin the server in safe mode without code changes.
    """
    enforce_read_only = (
        read_only_env_flag() if read_only is None else bool(read_only)
    )
    tools: List[MCPTool] = []
    for factory in ALL_FACTORIES:
        tools.extend(factory())
    if enforce_read_only:
        tools = [tool for tool in tools if tool.annotations.read_only]
    return tools


__all__ = [
    "MCPContent", "MCPTool", "MCPToolAnnotations",
    "build_default_tool_registry",
]
