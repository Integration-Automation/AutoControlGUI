"""Give an MCP client a handful of tools instead of several hundred schemas.

The default (``full``) tool mode answers ``tools/list`` with every registered
tool. Two other modes exist for clients that should not carry all of that:

* ``progressive`` -- a session starts with five core tools and grows::

      ac_tools_search   find tools by words; returns name, summary, category
      ac_tools_schema   the full input schema of one tool
      ac_tools_enable   add tools (or ``category:<name>``) to this session
      ac_tools_disable  take them out again
      ac_tools_state    what this session currently has enabled

  Enabling sends the session ``notifications/tools/list_changed``.
* ``static`` -- ``tools/list`` is a fixed profile and nothing can be enabled,
  for a client that reads the list once.

Choose the mode when starting the server::

    python -m je_auto_control.utils.mcp_server --tool-mode progressive
    JE_AUTOCONTROL_MCP_TOOL_MODE=progressive python -m je_auto_control.utils.mcp_server
    ac.start_mcp_stdio_server(tool_mode="progressive")

``JE_AUTOCONTROL_MCP_TOOL_PROFILE`` (comma-separated tool names and
``category:<name>`` entries) sets the static profile.

Disclosure changes what is *offered*, never what is *allowed*: a tool the
caller's role, read-only mode or the path roots rule out cannot be searched
for or enabled, and an enabled tool still passes every existing check when it
is called.

``--validate`` drives an in-process server through the same ``handle_line``
entry point both transports use. It lists, searches, reads a schema and
enables a tool; it never *calls* one that touches the desktop. Without the
flag the script serves MCP over stdio in progressive mode (and blocks, like
``14_mcp_stdio_server.py``).
"""
import argparse
import json
import sys
from typing import Any, Dict, List, Optional

import je_auto_control as ac

_QUERY = "screenshot"
_PROTOCOL = "2025-11-25"


class _Session:
    """A JSON-RPC client talking to one in-process server, no transport."""

    def __init__(self, server: ac.MCPServer) -> None:
        self._server = server
        self._next_id = 0
        self.notifications: List[str] = []
        # What a stdio transport does with a server-initiated message.
        server.set_notifier(lambda method, _params: self.notifications.append(method))

    def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send one request and return its ``result``; raise on a JSON-RPC error."""
        self._next_id += 1
        line = json.dumps({"jsonrpc": "2.0", "id": self._next_id, "method": method,
                           "params": params or {}})
        reply = json.loads(self._server.handle_line(line))
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error']}")
        return reply["result"]

    def notify(self, method: str) -> None:
        """Send a notification (no id, no reply)."""
        self._server.handle_line(json.dumps({"jsonrpc": "2.0", "method": method, "params": {}}))

    def tool_names(self) -> List[str]:
        """Every tool name ``tools/list`` offers this session, all pages."""
        names: List[str] = []
        cursor = None
        while True:
            page = self.request("tools/list", {"cursor": cursor} if cursor else {})
            names += [tool["name"] for tool in page["tools"]]
            cursor = page.get("nextCursor")
            if cursor is None:
                return names

    def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool and decode its JSON text result."""
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        text = result["content"][0]["text"]
        if result.get("isError"):
            raise RuntimeError(f"{name}: {text}")
        return json.loads(text)


def _open(mode: str) -> _Session:
    session = _Session(ac.MCPServer(tools=ac.build_default_tool_registry(), tool_mode=mode))
    session.request("initialize", {"protocolVersion": _PROTOCOL, "capabilities": {}})
    session.notify("notifications/initialized")
    return session


def validate() -> int:
    """Compare a full and a progressive session, then grow the progressive one."""
    full = _open("full").tool_names()
    session = _open("progressive")
    core = session.tool_names()
    print(f"full mode offers {len(full)} tools; a progressive session starts with {len(core)}:")
    print("  " + ", ".join(core))

    found = session.call("ac_tools_search", {"query": _QUERY, "limit": 5})
    print(f"search {_QUERY!r} -> {json.dumps(found)[:200]}...")
    target = found["tools"][0]["name"]
    schema = session.call("ac_tools_schema", {"name": target})
    enabled = session.call("ac_tools_enable", {"names": [target]})
    after = session.tool_names()
    state = session.call("ac_tools_state", {})
    print(f"schema of {target}: {sorted(schema)}")
    print(f"enabled {target}: {json.dumps(enabled)[:160]}")
    print(f"the session now lists {len(after)} tools; notifications: {session.notifications}")
    print(f"state: {json.dumps(state)[:200]}")

    problems = []
    if not len(core) < len(full):
        problems.append("progressive mode did not start smaller than full mode")
    if target in core or target not in after:
        problems.append(f"{target} was not added by ac_tools_enable")
    if "notifications/tools/list_changed" not in session.notifications:
        problems.append("enabling did not notify the session that its list changed")
    for problem in problems:
        print(f"FAILED: {problem}")
    print("validate:", "failed" if problems else "ok")
    return 1 if problems else 0


def main(argv: Optional[List[str]] = None) -> int:
    """Parse the command line; see the module docstring."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validate", action="store_true",
                        help="exercise the progressive tools in-process; call no desktop tool")
    args = parser.parse_args(argv)
    if args.validate:
        return validate()
    # Blocks until stdin closes. Every tool is still subject to the server's
    # own gates (JE_AUTOCONTROL_MCP_READONLY, roles, path roots, confirmation).
    ac.start_mcp_stdio_server(tool_mode="progressive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
