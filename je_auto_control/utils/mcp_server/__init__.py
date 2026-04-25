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
from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.context import (
    OperationCancelledError, ToolCallContext,
)
from je_auto_control.utils.mcp_server.fake_backend import (
    FakeState, fake_state, install_fake_backend, reset_fake_state,
    uninstall_fake_backend,
)
from je_auto_control.utils.mcp_server.log_bridge import MCPLogBridge
from je_auto_control.utils.mcp_server.rate_limit import RateLimiter
from je_auto_control.utils.mcp_server.http_transport import (
    HttpMCPServer, start_mcp_http_server,
)
from je_auto_control.utils.mcp_server.prompts import (
    MCPPrompt, MCPPromptArgument, PromptProvider, default_prompt_provider,
)
from je_auto_control.utils.mcp_server.resources import (
    MCPResource, ResourceProvider, default_resource_provider,
)
from je_auto_control.utils.mcp_server.tools import (
    MCPContent, MCPTool, MCPToolAnnotations, build_default_tool_registry,
    make_plugin_tool, register_plugin_tools,
)

__all__ = [
    "AuditLogger", "FakeState", "HttpMCPServer", "MCPContent",
    "MCPLogBridge", "MCPPrompt", "MCPPromptArgument", "MCPResource",
    "MCPServer", "MCPTool", "MCPToolAnnotations",
    "OperationCancelledError", "PromptProvider", "RateLimiter",
    "ResourceProvider", "ToolCallContext",
    "build_default_tool_registry",
    "default_prompt_provider", "default_resource_provider",
    "fake_state", "install_fake_backend", "make_plugin_tool",
    "register_plugin_tools", "reset_fake_state",
    "start_mcp_http_server", "start_mcp_stdio_server",
    "uninstall_fake_backend",
]
