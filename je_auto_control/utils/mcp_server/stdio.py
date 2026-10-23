"""Lazy stdio entry point with optional host-configured tool availability."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from je_auto_control.utils.mcp_server.server import MCPServer


def start_mcp_stdio_server(read_only: bool | None = None, *, disclosure: str | None = None,
                           tool_profile: list[str] | None = None, page_size: int = 50) -> MCPServer:
    """Start the shared dispatcher in the foreground, respecting the read-only environment by default."""
    # pylint: disable-next=import-outside-toplevel  # reason: retain the legacy server-module re-export without a cycle
    from je_auto_control.utils.mcp_server.server import MCPServer
    # pylint: disable-next=import-outside-toplevel  # reason: registry construction is only needed when serving
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    server = MCPServer(tools=build_default_tool_registry(read_only=read_only))
    settings = server.tool_disclosure_configuration()
    server.configure_tool_disclosure(disclosure or settings["mode"],
                                    names=tool_profile if tool_profile is not None else settings["names"],
                                    page_size=page_size, read_only=read_only)
    server.serve_stdio()
    return server
