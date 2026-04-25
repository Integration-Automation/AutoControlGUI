"""Headless MCP (Model Context Protocol) server for AutoControl.

Exposes the headless automation API as MCP tools so MCP-compatible
clients (Claude Desktop, Claude Code, Claude API tool-use loops, etc.)
can drive the host machine through AutoControl. The transport is
JSON-RPC 2.0 over stdio, implemented with stdlib only — no extra
dependencies are required.
"""
from je_auto_control.utils.mcp_server.server import (
    MCPServer, start_mcp_stdio_server,
)
from je_auto_control.utils.mcp_server.tools import (
    MCPContent, MCPTool, MCPToolAnnotations, build_default_tool_registry,
)

__all__ = [
    "MCPContent", "MCPServer", "MCPTool", "MCPToolAnnotations",
    "build_default_tool_registry", "start_mcp_stdio_server",
]
