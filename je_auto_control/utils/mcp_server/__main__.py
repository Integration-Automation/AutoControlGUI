"""``python -m je_auto_control.utils.mcp_server`` entry point."""
from je_auto_control.utils.mcp_server.server import start_mcp_stdio_server


def main() -> None:
    """Launch the stdio MCP server; blocks until stdin closes."""
    start_mcp_stdio_server()


if __name__ == "__main__":
    main()
