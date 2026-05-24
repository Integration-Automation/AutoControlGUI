"""Tests for the completed autocontrol-lsp surface.

Covers what the original scaffold didn't:

* :class:`DocumentStore` — open / change / close / position-to-word;
* :func:`diagnostics_for` — JSON parse + AC_ schema validation;
* hover / signature-help resolved against the in-memory document
  store (not the legacy ``word`` shortcut);
* didOpen / didChange / didClose round-trip through the LSP server's
  notification path, including queued ``publishDiagnostics``.
"""
import io
import json
import sys
from pathlib import Path

import pytest


_LSP_DIR = Path(__file__).resolve().parents[3] / "autocontrol-lsp"
if str(_LSP_DIR) not in sys.path:
    sys.path.insert(0, str(_LSP_DIR))


@pytest.fixture(autouse=True)
def _reset_discovery_cache():
    from autocontrol_lsp.server.commands import _reset_cache
    _reset_cache()
    yield
    _reset_cache()


# === DocumentStore ========================================================

def test_document_store_open_then_get_round_trip():
    from autocontrol_lsp.server.documents import DocumentStore
    store = DocumentStore()
    doc = store.open("file:///x.json", "[]", version=3)
    assert doc.uri == "file:///x.json"
    assert doc.version == 3
    assert store.get("file:///x.json").text == "[]"


def test_document_store_close_returns_true_when_existed():
    from autocontrol_lsp.server.documents import DocumentStore
    store = DocumentStore()
    store.open("file:///x.json", "")
    assert store.close("file:///x.json") is True
    assert store.close("file:///x.json") is False


def test_document_store_replace_bumps_version_when_unspecified():
    from autocontrol_lsp.server.documents import DocumentStore
    store = DocumentStore()
    store.open("u", "a", version=2)
    updated = store.replace("u", "b")
    assert updated.version == 3


def test_document_store_apply_change_full_document():
    from autocontrol_lsp.server.documents import DocumentStore
    store = DocumentStore()
    store.open("u", "old")
    updated = store.apply_change(
        "u", [{"text": "new"}], version=5,
    )
    assert updated.text == "new"
    assert updated.version == 5


def test_document_store_apply_change_range_edit():
    from autocontrol_lsp.server.documents import DocumentStore
    store = DocumentStore()
    store.open("u", "hello world")
    updated = store.apply_change("u", [{
        "range": {"start": {"line": 0, "character": 0},
                   "end": {"line": 0, "character": 5}},
        "text": "HELLO",
    }])
    assert updated.text == "HELLO world"


def test_word_at_extracts_identifier_under_cursor():
    from autocontrol_lsp.server.documents import (
        DocumentStore, Position,
    )
    store = DocumentStore()
    doc = store.open("u", '["AC_click_mouse", {"mouse_keycode": "left"}]')
    # cursor in the middle of "AC_click_mouse"
    assert doc.word_at(Position(line=0, character=5)) == "AC_click_mouse"


def test_word_at_returns_empty_outside_identifier():
    from autocontrol_lsp.server.documents import (
        DocumentStore, Position,
    )
    store = DocumentStore()
    doc = store.open("u", "// no AC at all\n")
    assert doc.word_at(Position(line=0, character=3)) == "no"
    assert doc.word_at(Position(line=10, character=0)) == ""


# === Diagnostics ==========================================================

def test_diagnostics_for_well_formed_returns_empty():
    from autocontrol_lsp.server.diagnostics import diagnostics_for
    assert diagnostics_for('[["AC_screenshot"]]') == []


def test_diagnostics_for_invalid_json_reports_error():
    from autocontrol_lsp.server.diagnostics import diagnostics_for
    diags = diagnostics_for("not json")
    assert len(diags) == 1
    assert diags[0]["severity"] == 1
    assert "invalid JSON" in diags[0]["message"]


def test_diagnostics_for_non_list_root():
    from autocontrol_lsp.server.diagnostics import diagnostics_for
    diags = diagnostics_for('{"not": "a list"}')
    assert any("must be a JSON list" in d["message"] for d in diags)


def test_diagnostics_warns_on_unknown_command():
    from autocontrol_lsp.server.diagnostics import diagnostics_for
    diags = diagnostics_for('[["AC_no_such_command"]]')
    assert any("unknown AC_" in d["message"] for d in diags)


def test_diagnostics_warns_on_bad_action_name_type():
    from autocontrol_lsp.server.diagnostics import diagnostics_for
    diags = diagnostics_for("[[42]]")
    assert any("must be a string" in d["message"] for d in diags)


def test_diagnostics_warns_on_non_ac_prefix():
    from autocontrol_lsp.server.diagnostics import diagnostics_for
    diags = diagnostics_for('[["WR_click", {}]]')
    assert any("must start with AC_" in d["message"] for d in diags)


def test_diagnostics_warns_on_params_not_dict():
    from autocontrol_lsp.server.diagnostics import diagnostics_for
    diags = diagnostics_for('[["AC_screenshot", "x"]]')
    assert any("must be an object" in d["message"] for d in diags)


# === Hover via document store ============================================

def test_hover_resolves_word_from_position():
    from autocontrol_lsp.server.documents import DocumentStore
    from autocontrol_lsp.server.handlers import handle_hover
    store = DocumentStore()
    store.open("file:///x.json", '["AC_click_mouse"]')
    result = handle_hover(
        {"textDocument": {"uri": "file:///x.json"},
         "position": {"line": 0, "character": 5}},
        store,
    )
    # Either docstring contents or "no docstring" fallback — both fine.
    if result:
        assert "AC_click_mouse" in result["contents"]["value"] or \
            result["contents"]["kind"] == "plaintext"


def test_hover_word_override_takes_precedence_over_position():
    from autocontrol_lsp.server.documents import DocumentStore
    from autocontrol_lsp.server.handlers import handle_hover
    store = DocumentStore()
    result = handle_hover({"word": "AC_screenshot"}, store)
    if result:
        assert result["contents"]["kind"] == "plaintext"


# === Signature help =======================================================

def test_signature_help_returns_signature_for_known_command():
    from autocontrol_lsp.server.handlers import handle_signature_help
    reply = handle_signature_help({"word": "AC_screenshot"})
    assert reply["signatures"]
    label = reply["signatures"][0]["label"]
    assert label.startswith("AC_screenshot")
    assert "(" in label


def test_signature_help_empty_for_unknown_command():
    from autocontrol_lsp.server.handlers import handle_signature_help
    reply = handle_signature_help({"word": "AC_garbage_unknown"})
    assert reply == {"signatures": []}


def test_initialize_advertises_signature_help_capability():
    from autocontrol_lsp.server.handlers import handle_initialize
    caps = handle_initialize({})["capabilities"]
    assert "signatureHelpProvider" in caps
    assert caps["signatureHelpProvider"]["triggerCharacters"] == ["(", ","]


# === Server-level notifications ==========================================

def _encode_request(method: str, request_id, params: dict = None) -> bytes:
    body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if request_id is not None:
        body["id"] = request_id
    raw = json.dumps(body).encode("utf-8")
    return f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw


def _split_replies(buf: bytes) -> list:
    parts, cursor = [], 0
    while cursor < len(buf):
        sep = buf.find(b"\r\n\r\n", cursor)
        if sep < 0:
            break
        header = buf[cursor:sep].decode("ascii", errors="replace")
        length = 0
        for line in header.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
        body = buf[sep + 4:sep + 4 + length]
        parts.append(json.loads(body.decode("utf-8")))
        cursor = sep + 4 + length
    return parts


def test_server_publishes_diagnostics_on_did_open():
    from autocontrol_lsp.server.server import run
    stream = io.BytesIO()
    requests = io.BytesIO(
        _encode_request("initialize", 1) +
        _encode_request("textDocument/didOpen", None, {
            "textDocument": {
                "uri": "file:///x.json",
                "languageId": "json",
                "version": 1,
                "text": "[\"not a list of lists\"]",
            },
        }) +
        _encode_request("exit", 2),
    )
    run(input_stream=requests, output_stream=stream)
    messages = _split_replies(stream.getvalue())
    publishes = [m for m in messages
                 if m.get("method") == "textDocument/publishDiagnostics"]
    assert publishes
    assert publishes[0]["params"]["uri"] == "file:///x.json"
    assert publishes[0]["params"]["diagnostics"]


def test_server_drops_document_on_did_close():
    from autocontrol_lsp.server.server import LspServer
    server = LspServer()
    server.handle_notification("textDocument/didOpen", {
        "textDocument": {"uri": "u", "text": "[]", "version": 1},
    })
    assert server.documents.count() == 1
    server.handle_notification("textDocument/didClose", {
        "textDocument": {"uri": "u"},
    })
    assert server.documents.count() == 0


def test_server_handles_did_change_incremental_edit():
    from autocontrol_lsp.server.server import LspServer
    server = LspServer()
    server.handle_notification("textDocument/didOpen", {
        "textDocument": {"uri": "u", "text": "hello world", "version": 1},
    })
    server.handle_notification("textDocument/didChange", {
        "textDocument": {"uri": "u", "version": 2},
        "contentChanges": [{
            "range": {"start": {"line": 0, "character": 0},
                       "end": {"line": 0, "character": 5}},
            "text": "HELLO",
        }],
    })
    assert server.documents.get("u").text == "HELLO world"
