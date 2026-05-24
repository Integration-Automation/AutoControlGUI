"""LSP server entry point — JSON-RPC 2.0 over stdio.

Usage::

    python -m autocontrol_lsp.server

The server reads ``Content-Length``-prefixed JSON-RPC messages from
stdin (the LSP wire format), dispatches to one of the per-method
handlers, and writes the response back to stdout. Stays alive until
the editor sends ``shutdown`` + ``exit`` or closes stdin.

Implements the AutoControl-specific surface:

* ``initialize`` / ``shutdown`` / ``exit`` lifecycle;
* ``textDocument/didOpen`` / ``didChange`` / ``didClose`` document
  tracking;
* ``textDocument/publishDiagnostics`` notifications on every
  open / change;
* ``textDocument/completion`` for every registered ``AC_*`` command;
* ``textDocument/hover`` + ``textDocument/signatureHelp`` resolved
  against the in-memory document store.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from autocontrol_lsp.server.documents import DocumentStore
from autocontrol_lsp.server.handlers import (
    handle_completion, handle_did_change, handle_did_close,
    handle_did_open, handle_hover, handle_initialize,
    handle_signature_help,
)


_HEADER_TERMINATOR = b"\r\n\r\n"


class LspServer:
    """Per-process LSP loop. State lives here so tests can reuse it."""

    def __init__(self) -> None:
        self._store = DocumentStore()
        self._pending_diagnostics: List[Dict[str, Any]] = []

    @property
    def documents(self) -> DocumentStore:
        return self._store

    def dispatch(self, method: str,
                 params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Route a request method to its reply payload, or None if unknown."""
        if method == "initialize":
            return handle_initialize(params)
        if method == "textDocument/completion":
            return handle_completion(params)
        if method == "textDocument/hover":
            return handle_hover(params, self._store)
        if method == "textDocument/signatureHelp":
            return handle_signature_help(params, self._store)
        if method == "shutdown":
            return None
        return None

    def handle_notification(self, method: str,
                            params: Dict[str, Any]) -> None:
        """Apply a notification + queue diagnostics if needed."""
        if method == "textDocument/didOpen":
            diags = handle_did_open(params, self._store)
            self._pending_diagnostics.append(
                _publish_payload(params, diags),
            )
        elif method == "textDocument/didChange":
            diags = handle_did_change(params, self._store)
            self._pending_diagnostics.append(
                _publish_payload(params, diags),
            )
        elif method == "textDocument/didClose":
            handle_did_close(params, self._store)

    def drain_diagnostics(self) -> List[Dict[str, Any]]:
        """Return + clear the queued ``publishDiagnostics`` notifications."""
        out = list(self._pending_diagnostics)
        self._pending_diagnostics.clear()
        return out


def _publish_payload(params: Dict[str, Any],
                      diagnostics: List[Dict[str, Any]],
                      ) -> Dict[str, Any]:
    text_doc = params.get("textDocument") or {}
    return {
        "uri": text_doc.get("uri"),
        "diagnostics": list(diagnostics),
    }


def _dispatch(server: LspServer, method: str,
               params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Back-compat dispatch helper that delegates to ``server.dispatch``."""
    return server.dispatch(method, params)


def _read_message(stream) -> Optional[Dict[str, Any]]:
    """Read one LSP JSON-RPC message from ``stream``."""
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


def _build_reply(method, request_id, result) -> Dict[str, Any]:
    reply: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if result is None and method != "shutdown":
        reply["error"] = {
            "code": -32601, "message": f"method not found: {method}",
        }
    else:
        reply["result"] = result
    return reply


def _publish_diagnostics(stream, payload: Dict[str, Any]) -> None:
    _write_message(stream, {
        "jsonrpc": "2.0",
        "method": "textDocument/publishDiagnostics",
        "params": payload,
    })


def run(input_stream=None, output_stream=None) -> int:
    """Run the LSP loop. Returns 0 on clean shutdown, 1 on transport error."""
    inp = input_stream or sys.stdin.buffer
    out = output_stream or sys.stdout.buffer
    server = LspServer()
    try:
        while _process_one_message(inp, out, server):
            pass
    except (OSError, ValueError):
        return 1
    return 0


def _process_one_message(inp, out, server: LspServer) -> bool:
    """Read one LSP message and dispatch it. Returns False to end the loop."""
    request = _read_message(inp)
    if request is None or request.get("method") == "exit":
        return False
    method = request.get("method")
    params = request.get("params") or {}
    if not isinstance(method, str):
        return True
    if request.get("id") is None:
        server.handle_notification(method, params)
    else:
        result = server.dispatch(method, params)
        _write_message(out, _build_reply(method, request["id"], result))
    for payload in server.drain_diagnostics():
        _publish_diagnostics(out, payload)
    return True


if __name__ == "__main__":  # pragma: no cover - entry point
    sys.exit(run())


__all__ = ["LspServer", "run"]
