"""Per-method LSP handlers — pure functions, easy to unit-test."""
from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from autocontrol_lsp.server.commands import (
    discover_actions, get_action_doc, known_action_names,
)
from autocontrol_lsp.server.diagnostics import diagnostics_for
from autocontrol_lsp.server.documents import (
    DocumentStore, Position, TextDocument,
)


# LSP CompletionItemKind / MarkupKind enums (subset used here).
_KIND_FUNCTION = 3
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
            "signatureHelpProvider": {
                "triggerCharacters": ["(", ","],
            },
        },
        "serverInfo": {
            "name": "autocontrol-lsp",
            "version": "0.2.0",
        },
    }


def handle_completion(_params: Dict[str, Any]) -> Dict[str, Any]:
    """Return every known AC_* command as a completion item."""
    items: List[Dict[str, Any]] = []
    for name, doc in discover_actions().items():
        item = {
            "label": name,
            "kind": _KIND_FUNCTION,
            "insertText": name,
        }
        if doc:
            item["documentation"] = {
                "kind": _MARKUP_PLAINTEXT, "value": doc,
            }
        items.append(item)
    return {"isIncomplete": False, "items": items}


def handle_hover(params: Dict[str, Any],
                  store: Optional[DocumentStore] = None) -> Dict[str, Any]:
    """Resolve the word at the cursor and show its docstring."""
    word = _word_from_params(params, store)
    if not word:
        return {}
    doc = get_action_doc(word)
    if doc:
        return {"contents": {"kind": _MARKUP_PLAINTEXT, "value": doc}}
    if word in known_action_names():
        return {
            "contents": {
                "kind": _MARKUP_PLAINTEXT,
                "value": f"{word} (no docstring available)",
            },
        }
    return {}


def handle_signature_help(params: Dict[str, Any],
                            store: Optional[DocumentStore] = None,
                            ) -> Dict[str, Any]:
    """Show parameter hints for the AC_* command under the cursor."""
    word = _word_from_params(params, store)
    if not word or word not in known_action_names():
        return {"signatures": []}
    signature_text = _signature_text(word)
    if signature_text is None:
        return {"signatures": []}
    return {
        "signatures": [{
            "label": signature_text,
            "documentation": {
                "kind": _MARKUP_PLAINTEXT,
                "value": get_action_doc(word) or "",
            },
        }],
        "activeSignature": 0,
        "activeParameter": 0,
    }


def handle_did_open(params: Dict[str, Any],
                     store: DocumentStore) -> List[Dict[str, Any]]:
    """Track a newly-opened document; returns its diagnostics."""
    doc_params = params.get("textDocument") or {}
    uri = doc_params.get("uri")
    if not isinstance(uri, str):
        return []
    text = str(doc_params.get("text") or "")
    version = int(doc_params.get("version") or 0)
    store.open(uri, text, version)
    return diagnostics_for(text)


def handle_did_change(params: Dict[str, Any],
                       store: DocumentStore,
                       ) -> List[Dict[str, Any]]:
    """Apply an incremental change and recompute diagnostics."""
    doc_params = params.get("textDocument") or {}
    uri = doc_params.get("uri")
    if not isinstance(uri, str):
        return []
    version = doc_params.get("version")
    changes = params.get("contentChanges") or []
    updated = store.apply_change(uri, changes, version=version)
    if updated is None:
        return []
    return diagnostics_for(updated.text)


def handle_did_close(params: Dict[str, Any],
                      store: DocumentStore) -> None:
    """Drop the document from the store."""
    doc_params = params.get("textDocument") or {}
    uri = doc_params.get("uri")
    if isinstance(uri, str):
        store.close(uri)


# --- helpers -------------------------------------------------

def _word_from_params(params: Dict[str, Any],
                       store: Optional[DocumentStore]) -> str:
    direct = params.get("word")
    if isinstance(direct, str):
        return direct
    if store is None:
        return ""
    doc = _document_from_params(params, store)
    if doc is None:
        return ""
    position = params.get("position") or {}
    return doc.word_at(Position(
        line=int(position.get("line", 0)),
        character=int(position.get("character", 0)),
    ))


def _document_from_params(params: Dict[str, Any],
                           store: DocumentStore,
                           ) -> Optional[TextDocument]:
    text_doc = params.get("textDocument") or {}
    uri = text_doc.get("uri")
    return store.get(uri) if isinstance(uri, str) else None


def _signature_text(name: str) -> Optional[str]:
    try:
        from je_auto_control.utils.executor.action_executor import executor
    except ImportError:
        return None
    handler = executor.event_dict.get(name)
    if handler is None:
        return None
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return f"{name}(*args, **kwargs)"
    return f"{name}{signature}"


def _extract_word(params: Dict[str, Any]) -> str:
    """Back-compat alias for the original test helper."""
    return _word_from_params(params, None)


__all__ = [
    "handle_completion", "handle_did_change", "handle_did_close",
    "handle_did_open", "handle_hover", "handle_initialize",
    "handle_signature_help",
]
