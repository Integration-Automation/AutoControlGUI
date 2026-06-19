"""Scan action JSON / data for hardcoded secrets.

Hard-coded passwords/tokens in action files are the #1 RPA audit failure;
they should reference the encrypted vault (``${secrets.NAME}``) instead.
This walks a JSON-like structure and flags string values that look like
secrets — by key name (``password`` / ``token`` / ``api_key`` …), by value
pattern (AWS keys, private-key headers, bearer tokens), or by high entropy.

Pure standard library (``re`` / ``math``); imports no ``PySide6``.
"""
import math
import re
from typing import Any, Dict, List, Optional, Tuple

_SECRET_KEY = re.compile(
    r"pass(word|wd)?|secret|token|api[_-]?key|credential|access[_-]?key|"
    r"private[_-]?key", re.IGNORECASE)

_VALUE_PATTERNS: Tuple[Tuple[str, "re.Pattern"], ...] = (
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer-token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
)

_TOKENISH = re.compile(r"^[A-Za-z0-9+/_\-=]{20,}$")


def _preview(value: str) -> str:
    if len(value) <= 6:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _shannon_entropy(value: str) -> float:
    counts: Dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _high_entropy(value: str) -> bool:
    return bool(_TOKENISH.match(value)) and _shannon_entropy(value) > 4.0


def _value_finding(value: str) -> Optional[str]:
    for kind, pattern in _VALUE_PATTERNS:
        if pattern.search(value):
            return kind
    if _high_entropy(value):
        return "high-entropy-string"
    return None


def _check(key: Optional[str], value: str, path: str,
           out: List[Dict[str, Any]]) -> None:
    if not value or value.startswith("${"):   # already a vault / variable ref
        return
    if key and _SECRET_KEY.search(key) and value.strip():
        out.append({"path": path, "kind": "hardcoded-secret-key",
                    "preview": _preview(value)})
        return
    kind = _value_finding(value)
    if kind is not None:
        out.append({"path": path, "kind": kind, "preview": _preview(value)})


def _walk(node: Any, path: str, out: List[Dict[str, Any]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}"
            if isinstance(value, str):
                _check(str(key), value, child, out)
            else:
                _walk(value, child, out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child = f"{path}[{index}]"
            if isinstance(value, str):
                _check(None, value, child, out)
            else:
                _walk(value, child, out)


def scan_secrets(data: Any) -> List[Dict[str, Any]]:
    """Return a list of likely-secret findings in ``data``.

    Each finding is ``{path, kind, preview}`` (the value is masked).
    Values already referencing the vault (``${secrets.*}``) are ignored.
    """
    findings: List[Dict[str, Any]] = []
    _walk(data, "$", findings)
    return findings
