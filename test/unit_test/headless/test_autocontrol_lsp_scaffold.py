"""Phase 6.10: scaffold-level tests for the autocontrol-lsp server.

The LSP package lives in ``autocontrol-lsp/`` so it can be lifted into
its own repo later; these tests prepend that directory to ``sys.path``
so they work without installing the scaffold.
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
    """Each test starts with a fresh AC_* discovery cache."""
    from autocontrol_lsp.server.commands import _reset_cache
    _reset_cache()
    yield
    _reset_cache()


# --- command discovery -------------------------------------------------

def test_discover_actions_returns_dict_of_ac_commands():
    from autocontrol_lsp.server.commands import discover_actions
    actions = discover_actions()
    assert isinstance(actions, dict)
    # The executor is large — we should see at least 50 AC_* commands.
    assert len(actions) > 50, "expected many AC_* commands in the executor"
    assert all(name.startswith("AC_") for name in actions)
    # A few familiar names from the readme.
    assert "AC_click_mouse" in actions
    assert "AC_screenshot" in actions
    assert "AC_screen_size" in actions


def test_known_action_names_sorted():
    from autocontrol_lsp.server.commands import known_action_names
    names = known_action_names()
    assert names == sorted(names)


def test_get_action_doc_returns_string_or_none():
    from autocontrol_lsp.server.commands import get_action_doc
    # Existing command: docstring is either a string or None.
    doc = get_action_doc("AC_click_mouse")
    assert doc is None or isinstance(doc, str)
    # Unknown command: definitively None.
    assert get_action_doc("AC_definitely_not_real") is None


# --- LSP handlers ------------------------------------------------------

def test_initialize_advertises_capabilities():
    from autocontrol_lsp.server.handlers import handle_initialize
    result = handle_initialize({})
    caps = result["capabilities"]
    assert caps["completionProvider"]["triggerCharacters"] == ["\"", "_", "A"]
    assert caps["hoverProvider"] is True


def test_completion_returns_every_ac_command():
    from autocontrol_lsp.server.commands import known_action_names
    from autocontrol_lsp.server.handlers import handle_completion
    reply = handle_completion({})
    assert reply["isIncomplete"] is False
    items = reply["items"]
    labels = {item["label"] for item in items}
    assert set(known_action_names()).issubset(labels)
    # Each item must specify a CompletionItemKind so the editor picks
    # the right icon (we use Function = 3).
    for item in items:
        assert item["kind"] == 3
        assert item["insertText"] == item["label"]


def test_hover_returns_docstring_for_known_command():
    from autocontrol_lsp.server.handlers import handle_hover
    reply = handle_hover({"word": "AC_click_mouse"})
    if reply:  # only if the action carries a docstring
        assert reply["contents"]["kind"] == "plaintext"
        assert isinstance(reply["contents"]["value"], str)


def test_hover_returns_empty_for_unknown_command():
    from autocontrol_lsp.server.handlers import handle_hover
    assert handle_hover({"word": "AC_no_such_thing"}) == {}


def test_hover_handles_missing_word_param():
    from autocontrol_lsp.server.handlers import handle_hover
    assert handle_hover({}) == {}


# --- LSP wire format --------------------------------------------------

def _encode_request(method: str, request_id: int,
                    params: dict | None = None) -> bytes:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method,
         "params": params or {}},
    ).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def _decode_reply(buf: bytes) -> dict:
    sep = buf.index(b"\r\n\r\n")
    return json.loads(buf[sep + 4:].decode("utf-8"))


def test_server_handles_initialize_and_completion_round_trip():
    from autocontrol_lsp.server.server import run
    request_stream = io.BytesIO(
        _encode_request("initialize", 1)
        + _encode_request("textDocument/completion", 2)
        + _encode_request("exit", 3),
    )
    response_stream = io.BytesIO()
    run(input_stream=request_stream, output_stream=response_stream)
    raw = response_stream.getvalue()
    # Split the raw stream into the two replies.
    parts = raw.split(b"Content-Length: ")
    # First chunk is empty (split artefact), then two replies.
    payloads = [b"Content-Length: " + p for p in parts if p]
    assert len(payloads) == 2
    first = _decode_reply(payloads[0])
    second = _decode_reply(payloads[1])
    assert first["id"] == 1
    assert "capabilities" in first["result"]
    assert second["id"] == 2
    assert len(second["result"]["items"]) > 50


def test_server_replies_method_not_found_for_unknown_request():
    from autocontrol_lsp.server.server import run
    request_stream = io.BytesIO(
        _encode_request("textDocument/somethingExotic", 1)
        + _encode_request("exit", 2),
    )
    response_stream = io.BytesIO()
    run(input_stream=request_stream, output_stream=response_stream)
    reply = _decode_reply(response_stream.getvalue())
    assert reply["error"]["code"] == -32601


# --- VSCode extension manifest sanity --------------------------------

def test_vscode_package_json_declares_extension():
    pkg = json.loads(
        (_LSP_DIR / "vscode" / "package.json").read_text(encoding="utf-8"),
    )
    assert pkg["name"] == "autocontrol-lsp"
    assert "onLanguage:json" in pkg["activationEvents"]
    assert pkg["contributes"]["configuration"]["title"] == "AutoControl LSP"
