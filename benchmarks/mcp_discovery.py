"""Compare local MCP handshake/schema cost against one registry and request policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess  # nosec B404  # reason: fixed git inspection without a shell
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# pylint: disable=wrong-import-position  # reason: direct script execution first selects the measured source root
from je_auto_control.utils.mcp_server.discovery import ToolIndex  # noqa: E402  # reason: explicit source root
from je_auto_control.utils.mcp_server.server import MCPServer  # noqa: E402  # reason: explicit source root
from je_auto_control.utils.mcp_server.tools import (  # noqa: E402  # reason: explicit source root
    MCPTool, build_default_tool_registry,
)
from je_auto_control.utils.mcp_server.disclosure import DisclosureMode  # noqa: E402  # reason: explicit source root

# pylint: enable=wrong-import-position


def _rpc(server: MCPServer, method: str, params: dict[str, Any]) -> dict[str, Any]:
    line = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
    reply = server.handle_line(line)
    if reply is None:
        raise RuntimeError('benchmark expects synchronous replies')
    document: dict[str, Any] = json.loads(reply)
    if 'error' in document:
        raise RuntimeError(str(document['error']))
    return document['result']


def measure(mode: DisclosureMode, registry: list[MCPTool], *, repeats: int = 5) -> dict[str, Any]:
    """Measure initialize plus complete tools/list locally, with one untimed warmup."""
    if repeats < 1 or repeats > 100:
        raise ValueError('repeats must be from1 to100')
    timings, searches = [], []
    descriptors: list[dict[str, Any]] = []
    first_bytes = 0
    for sample in range(repeats + 1):
        server = MCPServer(tools=registry)
        server.configure_tool_disclosure(mode)
        started = time.perf_counter()
        _rpc(server, 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                   'clientInfo': {'name': 'benchmark', 'version': '1'}})
        page = _rpc(server, 'tools/list', {})
        first_bytes = len(json.dumps(page, ensure_ascii=False).encode('utf-8'))
        descriptors = list(page['tools'])
        while page.get('nextCursor'):
            page = _rpc(server, 'tools/list', {'cursor': page['nextCursor']})
            descriptors.extend(page['tools'])
        elapsed = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        _rpc(server, 'tools/call', {'name': 'ac_discover_tools',
                                   'arguments': {'query': 'screenshot', 'limit': 10}})
        search_elapsed = (time.perf_counter() - started) * 1000
        if sample:
            timings.append(elapsed)
            searches.append(search_elapsed)
        server._disclosure.close()  # pylint: disable=protected-access  # reason: reclaim benchmark-owned local views
    return {'count': len(descriptors), 'json_bytes': len(json.dumps({'tools': descriptors},
            ensure_ascii=False).encode('utf-8')), 'first_page_json_bytes': first_bytes,
            'handshake_ms': statistics.median(timings), 'search_ms': statistics.median(searches),
            'handshake_samples_ms': timings, 'search_samples_ms': searches}


def benchmark(*, repeats: int = 5) -> dict[str, Any]:
    """Return comparable full/progressive measurements without native device calls."""
    registry = build_default_tool_registry()
    index = ToolIndex(registry)
    result = subprocess.run(  # nosec B603, B607  # reason: fixed git inspection argv; no shell
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
        text=True, check=True, timeout=10)
    revision = result.stdout.strip()
    digest = hashlib.sha256()
    for path in sorted((ROOT / 'je_auto_control/utils/mcp_server').rglob('*.py')):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return {'source_revision': revision, 'mcp_source_sha256': digest.hexdigest(),
            'module_path': str(ROOT / 'je_auto_control/utils/mcp_server/server.py'),
            'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                            'authorized_registry_count': len(index.authorized_names())},
            'workload': 'local JSON-RPC initialize + all tools/list pages; screenshot summary search; no network',
            'warmups': 1, 'repeats': repeats,
            'full': measure('full', registry, repeats=repeats),
            'progressive': measure('progressive', registry, repeats=repeats)}


def main() -> None:
    """Write a reproducible JSON measurement artifact to an explicit destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    report = benchmark(repeats=args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
