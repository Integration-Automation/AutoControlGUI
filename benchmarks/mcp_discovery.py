"""Measure MCP initial schema bytes and metadata latency without executing automation tools."""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from typing import Any

from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, build_default_tool_registry


def _rpc(server: MCPServer, method: str, params: dict | None = None) -> tuple[dict, float, int]:
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    start = time.perf_counter()
    raw = server.handle_line(request)
    elapsed = (time.perf_counter() - start) * 1000
    if raw is None:
        raise ValueError("benchmark request produced no reply")
    response = json.loads(raw)
    if "error" in response or response["result"].get("isError"):
        raise ValueError("benchmark metadata request failed: " + raw)
    return response["result"], elapsed, len(raw.encode("utf-8"))


def _latency(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {"median_ms": round(statistics.median(ordered), 3),
            "p95_ms": round(ordered[max(0, int(len(ordered) * .95) - 1)], 3)}


def _mode(tools: list[MCPTool], mode: str, repeats: int) -> dict[str, Any]:
    started = time.perf_counter()
    server = MCPServer(tools=tools)
    server.configure_tool_disclosure(mode, names=["ac_screen_size"] if mode == "static" else (), read_only=False)
    try:
        _rpc(server, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        initial, _, wire_bytes = _rpc(server, "tools/list")
        handshake_ms = (time.perf_counter() - started) * 1000
        search, enable = [], []
        search_bytes = 0
        for _ in range(repeats):
            _, elapsed, search_bytes = _rpc(server, "tools/call", {
                "name": "ac_mcp_tool_search", "arguments": {"query": "screen", "limit": 10}})
            search.append(elapsed)
            if mode == "progressive":
                _, elapsed, _ = _rpc(server, "tools/call", {
                    "name": "ac_mcp_tools_enable", "arguments": {"names": ["ac_screen_size"]}})
                enable.append(elapsed)
                _rpc(server, "tools/call", {
                    "name": "ac_mcp_tools_disable", "arguments": {"names": ["ac_screen_size"]}})
        return {"count": len(initial["tools"]), "response_json_bytes": wire_bytes,
                "descriptor_json_bytes": len(json.dumps(initial["tools"], ensure_ascii=False,
                                                        separators=(",", ":")).encode("utf-8")),
                "handshake_ms": round(handshake_ms, 3), "search": _latency(search),
                "search_response_json_bytes": search_bytes, "enable": _latency(enable) if enable else None}
    finally:
        server.stop()


def measure_discovery(repeats: int = 20) -> dict[str, Any]:
    """Compare full/progressive/static modes using warm imports and real JSON-RPC metadata handlers."""
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 100:
        raise ValueError("repeats must be an integer from 1 to 100")
    tools = build_default_tool_registry(read_only=False, aliases=True)
    return {"python": platform.python_version(), "platform": platform.system(), "repeats": repeats,
            "measurement": "warm in-process server construction, initialize and first tools/list; no native tools",
            "modes": {mode: _mode(tools, mode, repeats) for mode in ("full", "progressive", "static")}}


def main() -> None:
    """Print a reproducible JSON report; all operations are metadata-only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(measure_discovery(args.repeats), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
