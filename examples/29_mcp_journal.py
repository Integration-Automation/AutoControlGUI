"""Capture and inspect variable-only actions through an in-process MCP client.

Run: python examples/29_mcp_journal.py run.jsonl
No desktop input, external transport or paid API is used.
"""
import argparse
import json
from pathlib import Path

from je_auto_control import MCPServer


def main() -> None:
    """Send two JSON-RPC calls and print the sanitized journal snapshots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    args = parser.parse_args()
    server = MCPServer()
    requests = [
        ("ac_journal_capture", {"path": str(args.journal), "metadata": {"run_id": "mcp-example"},
                                "actions": [["AC_set_var", {"name": "message", "value": "hello"}]]}),
        ("ac_journal_read", {"path": str(args.journal), "run_id": "mcp-example"}),
    ]
    for request_id, (name, arguments) in enumerate(requests, 1):
        line = server.handle_line(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                                              "params": {"name": name, "arguments": arguments}}))
        reply = json.loads(line)
        if "error" in reply or reply["result"]["isError"]:
            raise SystemExit(json.dumps(reply))
    print(json.dumps(reply["result"]["structuredContent"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
