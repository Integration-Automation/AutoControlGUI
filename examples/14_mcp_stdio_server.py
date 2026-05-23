"""Start AutoControl as an MCP stdio server.

This is exactly what Claude Desktop calls when you wire it into
``claude_desktop_config.json``::

    {
      "mcpServers": {
        "autocontrol": {
          "command": "python",
          "args": ["-m", "je_auto_control.utils.mcp_server"]
        }
      }
    }

Calling :func:`start_mcp_stdio_server` blocks the foreground process,
reading newline-delimited JSON-RPC from stdin and writing responses
to stdout. Use the HTTP transport (:func:`start_mcp_http_server`)
when you need a long-running daemon instead.
"""
import je_auto_control as ac


def main() -> None:
    # Returns once stdin closes; logs go to autocontrol's logger.
    ac.start_mcp_stdio_server()


if __name__ == "__main__":
    main()
