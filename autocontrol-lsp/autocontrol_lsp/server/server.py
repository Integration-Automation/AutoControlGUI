"""LSP server entry point — JSON-RPC 2.0 over stdio.

Usage::

    python -m autocontrol_lsp.server

The server reads ``Content-Length``-prefixed JSON-RPC messages from
stdin (the LSP wire format), dispatches to one of the per-method
handlers, and writes the response back to stdout. Stays alive until
the editor sends ``shutdown`` + ``exit`` or closes stdin.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable, Dict, Optional

from autocontrol_lsp.server.handlers import (
    handle_completion, handle_hover, handle_initialize,
)


_HEADER_TERMINATOR = b"\r\n\r\n"


def _dispatch(method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Route an LSP request to the matching handler."""
    handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
        "initialize": handle_initialize,
        "textDocument/completion": handle_completion,
        "textDocument/hover": handle_hover,
    }
    handler = handlers.get(method)
    if handler is None:
        return None
    return handler(params or {})


def _read_message(stream) -> Optional[Dict[str, Any]]:
    """Read one LSP JSON-RPC message from ``stream`` (a buffered binary stdin)."""
    header_bytes = bytearray()
    while True:
        chunk = stream.read(1)
        if not chunk:
            return None
        header_bytes.extend(chunk)
        if header_bytes.endswith(_HEADER_TERMINATOR):
            break
        if len(header_bytes) > 16 * 1024:
            return None
    length = _content_length(bytes(header_bytes))
    if length is None or length <= 0:
        return None
    body = stream.read(length)
    if len(body) != length:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _content_length(header: bytes) -> Optional[int]:
    """Parse ``Content-Length:`` out of an LSP header block."""
    text = header.decode("ascii", errors="replace")
    for line in text.split("\r\n"):
        if not line.strip():
            continue
        name, _colon, value = line.partition(":")
        if name.strip().lower() == "content-length":
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None


def _write_message(stream, message: Dict[str, Any]) -> None:
    body = json.dumps(message).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    stream.write(header + body)
    stream.flush()


def run(input_stream=None, output_stream=None) -> int:
    """Run the LSP loop. Returns 0 on clean shutdown, 1 on transport error."""
    inp = input_stream or sys.stdin.buffer
    out = output_stream or sys.stdout.buffer
    try:
        while True:
            request = _read_message(inp)
            if request is None:
                return 0
            method = request.get("method")
            if method == "exit":
                return 0
            params = request.get("params") or {}
            result = (
                _dispatch(method, params) if isinstance(method, str) else None
            )
            request_id = request.get("id")
            if request_id is None:
                continue  # notification; no response needed
            reply: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
            if result is None:
                reply["error"] = {
                    "code": -32601, "message": f"method not found: {method}",
                }
            else:
                reply["result"] = result
            _write_message(out, reply)
    except (OSError, ValueError):
        return 1


if __name__ == "__main__":  # pragma: no cover - entry point
    sys.exit(run())


__all__ = ["run"]
