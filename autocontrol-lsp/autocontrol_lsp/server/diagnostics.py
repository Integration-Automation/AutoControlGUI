"""Build LSP ``Diagnostic`` lists for an AutoControl action JSON file.

Two layers of checking:

1. **JSON parse**: a parse failure surfaces as a diagnostic at the
   reported error line, with severity ``Error``;
2. **Schema**: top-level must be a list; each entry must be a 1- or
   2-element list ``[name]`` / ``[name, params_dict]`` where ``name``
   is a registered ``AC_*`` command and ``params`` is an object.

Diagnostics are returned in the LSP wire shape — the server hands
them straight to ``textDocument/publishDiagnostics``.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from autocontrol_lsp.server.commands import known_action_names


_SEVERITY_ERROR = 1
_SEVERITY_WARNING = 2


def diagnostics_for(text: str) -> List[Dict[str, Any]]:
    """Return every problem found in ``text`` as an LSP Diagnostic dict."""
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError as error:
        return [_parse_error_diagnostic(error)]
    return _schema_diagnostics(data)


def _parse_error_diagnostic(error: json.JSONDecodeError) -> Dict[str, Any]:
    line = max(0, int(error.lineno) - 1)
    column = max(0, int(error.colno) - 1)
    return {
        "range": {
            "start": {"line": line, "character": column},
            "end": {"line": line, "character": column + 1},
        },
        "severity": _SEVERITY_ERROR,
        "source": "autocontrol-lsp",
        "message": f"invalid JSON: {error.msg}",
    }


def _schema_diagnostics(data: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(data, list):
        out.append(_root_must_be_list_diagnostic())
        return out
    known = set(known_action_names())
    for index, entry in enumerate(data):
        problem = _check_entry(entry, known)
        if problem is None:
            continue
        out.append(_diagnostic_for_entry(index, problem))
    return out


def _check_entry(entry: Any, known: set) -> Optional[str]:
    if not isinstance(entry, list):
        return "action must be a list of [name] or [name, params]"
    if not entry:
        return "action list cannot be empty"
    name = entry[0]
    if not isinstance(name, str):
        return f"action name must be a string, got {type(name).__name__}"
    if not name.startswith("AC_"):
        return f"action name {name!r} must start with AC_"
    if name not in known:
        return f"unknown AC_ command: {name!r}"
    if len(entry) > 2:
        return "action accepts at most [name, params]"
    if len(entry) == 2 and not isinstance(entry[1], dict):
        return "params must be an object"
    return None


def _diagnostic_for_entry(index: int, message: str) -> Dict[str, Any]:
    return {
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 1},
        },
        "severity": _SEVERITY_WARNING,
        "source": "autocontrol-lsp",
        "message": f"action[{index}]: {message}",
    }


def _root_must_be_list_diagnostic() -> Dict[str, Any]:
    return {
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 1},
        },
        "severity": _SEVERITY_ERROR,
        "source": "autocontrol-lsp",
        "message": "action file must be a JSON list of [name, params] entries",
    }


__all__ = ["diagnostics_for"]
