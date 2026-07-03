"""Redact secret-looking values from config structures and log strings.

``utils/redaction`` only blurs PIL screenshots, and ``secrets_scan`` only
*detects* and reports findings — neither returns a masked copy of a config dict
or string safe for logs, reports, or ``config_bundle`` export. This reuses the
``secrets_scan`` detector to produce a redacted copy.

Pure standard library (``re`` + reuse of ``secrets_scan``); imports no
``PySide6``. Every function is pure (data in, redacted copy out), so it is fully
deterministic in CI.
"""
import re
from typing import Any, Set

from je_auto_control.utils.secrets_scan import scan_secrets

_DEFAULT_MASK = "***"
_PUNCT = ".,;:!?\"'()[]{}<>"


def _secret_paths(obj: Any) -> Set[str]:
    return {finding["path"] for finding in scan_secrets(obj)}


def _redact_node(node: Any, path: str, paths: Set[str], mask: str) -> Any:
    if isinstance(node, dict):
        return {key: _redact_node(value, f"{path}.{key}", paths, mask)
                for key, value in node.items()}
    if isinstance(node, list):
        return [_redact_node(value, f"{path}[{index}]", paths, mask)
                for index, value in enumerate(node)]
    return mask if path in paths else node


def redact_config(obj: Any, *, mask: str = _DEFAULT_MASK) -> Any:
    """Return a deep copy of ``obj`` with secret-looking values masked.

    Detection reuses ``secrets_scan`` (key-name patterns, known value formats,
    and high-entropy strings); values already referencing the vault
    (``${secrets.*}``) are left intact.
    """
    return _redact_node(obj, "$", _secret_paths(obj), mask)


def redact_secret_text(text: str, *, mask: str = _DEFAULT_MASK) -> str:
    """Mask secret-looking tokens within a free-text string (e.g. a log line)."""
    # Explicit credential syntax must be masked even when the value is short or
    # low-entropy and therefore intentionally below the generic scanner's
    # threshold (common in tests, local deployments, and leaked error text).
    text = re.sub(
        r"(?i)(\bauthorization\s*:\s*bearer\s+)[^\s,;]+",
        lambda match: match.group(1) + mask,
        text or "",
    )
    text = re.sub(
        r"(?i)(\b(?:api[_-]?key|access[_-]?token|token|password|passwd|secret)"
        r"\s*[=:]\s*)([^\s,;]+)",
        lambda match: match.group(1) + mask,
        text,
    )

    def _replace(match: "re.Match[str]") -> str:
        token = match.group(0)
        core = token.strip(_PUNCT)
        if core and scan_secrets({"value": core}):
            return token.replace(core, mask)
        return token

    return re.sub(r"\S+", _replace, text)
