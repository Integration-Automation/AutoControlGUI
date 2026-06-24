"""Normalise an error message into a stable failure signature.

Two runs that failed the *same way* almost never have byte-identical error text —
paths, line numbers, memory addresses, ids and timestamps differ every time. That
defeats any attempt to ask "is this the same failure as yesterday?" or "which
tests fail *together*?". ``failure_signature`` strips the variable parts of an
error to a canonical form and hashes it (SHA-256), so the same *kind* of failure
gets the same short signature across runs — the join key the rest of the
test-robustness tools (run diffing, flake clustering) group on.

Pure standard library (``re`` + ``hashlib``); no device, no ``PySide6``.
"""
import hashlib
import re
from typing import Any, Dict, Iterable, List

# Ordered (pattern, replacement): the volatile parts of an error, most specific
# first so e.g. a path's trailing line number isn't half-collapsed by the digit rule.
_NORMALIZERS = [
    (re.compile(r"[A-Za-z]:\\[^\s:*?\"<>|]+"), "<path>"),          # Windows path
    (re.compile(r"(?:/[\w.\-]+)+/[\w.\-]+"), "<path>"),            # POSIX path
    (re.compile(r"0x[0-9A-Fa-f]+"), "0x<addr>"),                   # memory address
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
                r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?"), "<ts>"),
    (re.compile(r"\bline\s+\d+\b", re.IGNORECASE), "line <n>"),
    (re.compile(r"\b\d+\b"), "<n>"),                               # any leftover int
]
_WHITESPACE = re.compile(r"\s+")


def normalize_error(message: str) -> str:
    """Collapse the volatile parts of an error message to a canonical form.

    Paths, hex addresses, UUIDs, timestamps, line numbers and bare integers
    become placeholders, and whitespace is squeezed — so messages that differ
    only in those details normalise to the same string.
    """
    text = str(message)
    for pattern, replacement in _NORMALIZERS:
        text = pattern.sub(replacement, text)
    return _WHITESPACE.sub(" ", text).strip()


def failure_signature(message: str, *, length: int = 12) -> str:
    """Return a short stable SHA-256 signature of a normalised error message."""
    digest = hashlib.sha256(normalize_error(message).encode("utf-8")).hexdigest()
    return digest[:max(1, int(length))]


def group_failures(messages: Iterable[str]) -> List[Dict[str, Any]]:
    """Group error messages by signature, most frequent first.

    Returns ``[{signature, normalized, count, examples}]`` (up to three distinct
    raw examples per group). ``None`` / empty messages are skipped.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for message in messages:
        if not message:
            continue
        signature = failure_signature(message)
        group = groups.setdefault(signature, {
            "signature": signature, "normalized": normalize_error(message),
            "count": 0, "examples": []})
        group["count"] += 1
        if len(group["examples"]) < 3 and str(message) not in group["examples"]:
            group["examples"].append(str(message))
    return sorted(groups.values(), key=lambda group: group["count"], reverse=True)
