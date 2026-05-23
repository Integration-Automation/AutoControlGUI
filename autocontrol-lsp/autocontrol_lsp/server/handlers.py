"""Per-method LSP handlers — pure functions, easy to unit-test."""
from __future__ import annotations

from typing import Any, Dict, List

from autocontrol_lsp.server.commands import (
    discover_actions, get_action_doc, known_action_names,
)


# LSP CompletionItemKind enum (subset used here).
_KIND_FUNCTION = 3
_KIND_TEXT = 1

# LSP MarkupKind for hover.
_MARKUP_PLAINTEXT = "plaintext"


def handle_initialize(_params: Dict[str, Any]) -> Dict[str, Any]:
    """Reply to LSP ``initialize`` with the capabilities we implement."""
    return {
        "capabilities": {
            "textDocumentSync": 1,  # full document sync
            "completionProvider": {
                "triggerCharacters": ["\"", "_", "A"],
            },
            "hoverProvider": True,
        },
        "serverInfo": {
            "name": "autocontrol-lsp",
            "version": "0.1.0",
        },
    }


def handle_completion(_params: Dict[str, Any]) -> Dict[str, Any]:
    """Return every known AC_* command as a completion item.

    The editor filters by the prefix the user has typed, so we don't
    need to slice the list ourselves — keeps the handler stateless.
    """
    items: List[Dict[str, Any]] = []
    for name, doc in discover_actions().items():
        item = {
            "label": name,
            "kind": _KIND_FUNCTION,
            "insertText": name,
        }
        if doc:
            item["documentation"] = {
                "kind": _MARKUP_PLAINTEXT,
                "value": doc,
            }
        items.append(item)
    return {"isIncomplete": False, "items": items}


def handle_hover(params: Dict[str, Any]) -> Dict[str, Any]:
    """Show the action's docstring when the cursor is on a command name."""
    word = _extract_word(params)
    if not word:
        return {}
    doc = get_action_doc(word)
    if not doc:
        # Fall back to "known but undocumented" hint, or no hover at all
        # if the word isn't an AC_* command we recognise.
        if word in known_action_names():
            return {
                "contents": {
                    "kind": _MARKUP_PLAINTEXT,
                    "value": f"{word} (no docstring available)",
                },
            }
        return {}
    return {
        "contents": {
            "kind": _MARKUP_PLAINTEXT,
            "value": doc,
        },
    }


def _extract_word(params: Dict[str, Any]) -> str:
    """Pull the word at the hover position out of an LSP ``hover`` request.

    The standard ``hover`` request gives ``position`` plus a
    ``textDocument`` URI — for the scaffold we accept callers passing
    the pre-extracted ``word`` field directly, which keeps the unit
    tests independent of a real document store.
    """
    word = params.get("word")
    return word if isinstance(word, str) else ""


__all__ = ["handle_initialize", "handle_completion", "handle_hover"]
