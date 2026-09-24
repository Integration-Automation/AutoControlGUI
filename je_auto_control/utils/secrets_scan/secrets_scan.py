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

#: Whole words of a key that mark its value as a secret. Matched per word --
#: snake_case, kebab-case and camelCase split apart -- so ``db_password`` and
#: ``apiKey`` count while ``tokenizer``, ``bypass_proxy`` and
#: ``compass_heading`` (substring hits of the old pattern) do not.
_SECRET_WORDS = frozenset({
    "password", "passwd", "pwd", "pass", "passphrase", "secret", "secrets",
    "token", "tokens", "credential", "credentials", "cookie", "authorization",
    "apikey", "accesskey", "privatekey", "sessionid",
})
_KEY_WORD = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")

_VALUE_PATTERNS: Tuple[Tuple[str, "re.Pattern"], ...] = (
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----")),
    ("bearer-token", re.compile(r"(?i)\bBearer\s+[a-z0-9._-]{16,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]*")),
    # The (?!\*\*\*@) lets an already-masked URL keep its host readable.
    # The scheme is bounded and cannot start right after a letter, digit or
    # "." -- as written, "a.a.a..." started a scan to the end at every dot.
    ("url-credentials", re.compile(
        r"(?i)(?<![a-z0-9+.-])[a-z][a-z0-9+.-]{0,31}://[^/\s:@]{1,256}:(?!\*\*\*@)[^/\s@]{1,256}@")),
)


def is_secret_key(key: Any) -> bool:
    """Whether a mapping key names a secret (``password``, ``client_secret``, ``apiKey``...)."""
    words = [word.lower() for word in _KEY_WORD.findall(str(key))]
    pairs = (first + second for first, second in zip(words, words[1:]))
    return any(word in _SECRET_WORDS for word in words) or any(
        pair in _SECRET_WORDS for pair in pairs)

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


def _check(key: Optional[str], value: Any, path: str,
           out: List[Dict[str, Any]]) -> None:
    kind, preview = _classify(key, value)
    if kind is not None:
        out.append({"path": path, "kind": kind, "preview": preview})


def _classify_scalar(secret_key: bool, value: Any) -> Tuple[Optional[str], str]:
    # A number under a secret key (``"password": 1234``) is still that
    # secret; only a string can be a vault reference.
    flagged = secret_key and value is not None and not isinstance(value, bool)
    return ("hardcoded-secret-key", "***") if flagged else (None, "")


def _classify(key: Optional[str], value: Any) -> Tuple[Optional[str], str]:
    """``(kind, preview)`` for a scalar that looks like a secret, else ``(None, "")``."""
    secret_key = bool(key) and is_secret_key(key)
    if not isinstance(value, str):
        return _classify_scalar(secret_key, value)
    if not value or value.startswith("${"):   # already a vault / variable ref
        return None, ""
    if secret_key and value.strip():
        return "hardcoded-secret-key", _preview(value)
    kind = _value_finding(value)
    return (kind, _preview(value)) if kind is not None else (None, "")


def _walk(node: Any, path: str, out: List[Dict[str, Any]],
          key: Optional[str] = None) -> None:
    """Visit every scalar; list items inherit the key of the list they sit in.

    ``"tokens": ["..."]`` and ``"db": ("admin", "...")`` used to lose their key
    (list items were checked as keyless, tuples not at all).
    """
    if isinstance(node, dict):
        for child_key, value in node.items():
            _walk(value, f"{path}.{child_key}", out, str(child_key))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _walk(value, f"{path}[{index}]", out, key)
    else:
        _check(key, node, path, out)


def scan_secrets(data: Any) -> List[Dict[str, Any]]:
    """Return a list of likely-secret findings in ``data``.

    Each finding is ``{path, kind, preview}`` (the value is masked).
    Values already referencing the vault (``${secrets.*}``) are ignored.
    """
    findings: List[Dict[str, Any]] = []
    _walk(data, "$", findings)
    return findings
