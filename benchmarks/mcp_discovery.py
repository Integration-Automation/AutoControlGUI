"""What a new MCP session costs in each tool mode: full against progressive.

Drives an in-process ``MCPServer`` through ``handle_line``, the same entry
point both transports use, so the figures are the dispatcher's and exclude
pipe and socket time. No tool that touches the desktop is ever called: the
only ``tools/call`` requests are the progressive mode's own search, schema
and enable tools.

Per mode:

* ``count`` / ``json_bytes`` -- tools in a new session's ``tools/list`` and the
  UTF-8 size of that result, every page added up;
* ``handshake_ms`` -- ``initialize``, ``notifications/initialized`` and the
  whole ``tools/list``, on a server that is already built;
* ``search_ms`` / ``schema_ms`` / ``enable_ms`` -- one call of each core tool
  (``null`` in full mode, which has none), and ``search_json_bytes``, the size
  of one search reply.

Usage::

    python benchmarks/mcp_discovery.py            # the default registry
    python benchmarks/mcp_discovery.py --rounds 50
"""
import argparse
import json
import statistics
import time

_QUERY = "screenshot"


def _line(method, params=None, msg_id=1):
    message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if msg_id is not None:
        message["id"] = msg_id
    return json.dumps(message)


def _list_all(server):
    """``(tool count, result bytes)`` of a session's whole ``tools/list``."""
    count, size, cursor = 0, 0, None
    while True:
        reply = json.loads(server.handle_line(
            _line("tools/list", {"cursor": cursor} if cursor else {})))
        result = reply["result"]
        count += len(result["tools"])
        size += len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        cursor = result.get("nextCursor")
        if cursor is None:
            return count, size


def _handshake(server):
    server.handle_line(_line("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}}))
    server.handle_line(_line("notifications/initialized", msg_id=None))
    return _list_all(server)


def _call(server, name, arguments):
    reply = json.loads(server.handle_line(
        _line("tools/call", {"name": name, "arguments": arguments})))
    result = reply["result"]
    if result["isError"]:
        raise RuntimeError(f"{name} failed: {result['content'][0]['text']}")
    return result["content"][0]["text"]


def _median_ms(action, rounds):
    samples = []
    for _ in range(rounds):
        started = time.perf_counter()
        action()
        samples.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(samples), 3)


def _core_figures(server, target, rounds):
    """Timings of the progressive mode's own tools against ``server``."""
    def enable_and_disable():
        _call(server, "ac_tools_enable", {"names": [target]})
        _call(server, "ac_tools_disable", {"names": [target]})
    _call(server, "ac_tools_search", {"query": _QUERY})  # builds the index once
    return {
        "search_ms": _median_ms(lambda: _call(server, "ac_tools_search", {"query": _QUERY}), rounds),
        "search_json_bytes": len(_call(server, "ac_tools_search", {"query": _QUERY}).encode("utf-8")),
        "schema_ms": _median_ms(lambda: _call(server, "ac_tools_schema", {"name": target}), rounds),
        "enable_ms": _median_ms(enable_and_disable, rounds),
    }


def _measure_mode(mode, tools, rounds):
    from je_auto_control.utils.mcp_server.server import MCPServer
    server = MCPServer(tools=list(tools), tool_mode=mode)
    count, size = _handshake(server)
    figures = {
        "count": count, "json_bytes": size,
        "handshake_ms": _median_ms(lambda: _handshake(server), rounds),
        "search_ms": None, "search_json_bytes": None, "schema_ms": None, "enable_ms": None,
    }
    if mode == "progressive":
        figures.update(_core_figures(server, tools[0].name, rounds))
    return figures


def measure(tools=None, rounds=20):
    """Return the report for ``tools`` (default: the registry a server builds)."""
    if tools is None:
        from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
        tools = build_default_tool_registry()
    tools = list(tools)
    modes = {mode: _measure_mode(mode, tools, rounds) for mode in ("full", "progressive")}
    full, progressive = modes["full"], modes["progressive"]
    return {
        "registry_tools": len(tools), "rounds": rounds, "modes": modes,
        "progressive_json_bytes_percent_of_full": round(
            100 * progressive["json_bytes"] / max(1, full["json_bytes"]), 2),
    }


def main(argv=None):
    """Print the report as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=20,
                        help="Samples per timing; the median is reported.")
    args = parser.parse_args(argv)
    print(json.dumps(measure(rounds=max(1, args.rounds)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
