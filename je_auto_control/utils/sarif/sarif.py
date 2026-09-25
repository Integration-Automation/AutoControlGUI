"""Unify AutoControl findings into a SARIF 2.1.0 document.

The framework has several findings producers — action-lint, the secrets scan,
the WCAG/a11y audit, the guardrail — but no common export, so results couldn't
land in GitHub/Azure DevOps "code scanning" (the durable, deduplicated,
line-anchored alert store). SARIF 2.1.0 (OASIS) is that interchange format.

This builds a SARIF document from a list of normalized *findings*
(``{rule_id, level, message, file?, line?}``), with adapters for the existing
lint / audit shapes and stable ``partialFingerprints`` so the same issue
deduplicates across runs. Pure standard library (``json`` + ``hashlib``);
imports no ``PySide6``.
"""
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence

SARIF_VERSION = "2.1.0"
_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_LEVELS = {
    "error": "error", "critical": "error", "serious": "error",
    "high": "error", "warning": "warning", "moderate": "warning",
    "medium": "warning", "info": "note", "note": "note", "minor": "note",
    "low": "note", "none": "none",
}


def _level(severity: Any) -> str:
    # No severity is a warning: str(None) is "none", a level SARIF 2.1.0
    # 3.27.10 reserves for results whose kind is not "fail".
    if severity is None:
        return "warning"
    return _LEVELS.get(str(severity).lower(), "warning")


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def make_finding(rule_id: str, message: str, *, level: str = "warning",
                 file: Optional[str] = None,
                 line: Optional[int] = None) -> Dict[str, Any]:
    """Build one normalized finding for :func:`to_sarif`."""
    finding: Dict[str, Any] = {"rule_id": str(rule_id), "level": level,
                               "message": str(message)}
    if file is not None:
        finding["file"] = file
    if line is not None:
        finding["line"] = int(line)
    return finding


def result_fingerprint(finding: Mapping[str, Any]) -> str:
    """Stable short hash of a finding (for SARIF partialFingerprints/dedupe)."""
    basis = "|".join(str(finding.get(k, "")) for k in
                     ("rule_id", "message", "file", "line"))
    # surrogatepass: a lone surrogate in a message raised UnicodeEncodeError.
    return hashlib.sha256(basis.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def _artifact_uri(path: Any) -> str:
    """A SARIF ``artifactLocation.uri``: a URI reference, not an OS path.

    ``C:\\my dir\\flow file.json`` is not a URI; an absolute path becomes a
    ``file:`` URI and a relative one a percent-encoded POSIX path.
    """
    import urllib.parse
    from pathlib import PurePath, PureWindowsPath
    text = str(path)
    if "://" in text:
        return text
    pure = PureWindowsPath(text) if "\\" in text else PurePath(text)
    if pure.is_absolute():
        return _file_uri(pure)
    return urllib.parse.quote(pure.as_posix())


def _file_uri(pure: Any) -> str:
    """The ``file:`` URI of an absolute path, as ``PurePath.as_uri()`` wrote it.

    That method is deprecated since Python 3.14 (removal in 3.19), and
    ``Path.as_uri()`` cannot take a Windows path on another platform, which a
    finding from a Windows run read elsewhere is.
    """
    import urllib.parse
    drive, posix = pure.drive, pure.as_posix()
    if len(drive) == 2 and drive[1] == ":":
        prefix, path = "file:///" + drive, posix[2:]   # C:/a/b -> file:///C:/a/b
    elif drive:
        prefix, path = "file:", posix                   # //host/share/a -> file://host/share/a
    else:
        prefix, path = "file://", posix                 # /etc/hosts -> file:///etc/hosts
    return prefix + urllib.parse.quote(path)


def _start_line(line: Any) -> Any:
    """A 1-based ``startLine``, or ``None`` when there is no valid line."""
    try:
        number = int(line)
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


def _result(finding: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ruleId": str(finding.get("rule_id", "AC0000")),
        # SARIF allows only none / note / warning / error.
        "level": _level(finding.get("level", "warning")),
        # SARIF requires a string; a None message was written as null.
        "message": {"text": "" if finding.get("message") is None else str(finding.get("message"))},
        "partialFingerprints": {"primaryLocationLineHash":
                                result_fingerprint(finding)},
    }
    if finding.get("file"):
        line = _start_line(finding.get("line"))
        region = {"startLine": line} if line is not None else {}
        result["locations"] = [{"physicalLocation": {
            "artifactLocation": {"uri": _artifact_uri(finding["file"])},
            **({"region": region} if region else {})}}]
    return result


def to_sarif(findings: Sequence[Mapping[str, Any]], *,
             tool_name: str = "AutoControl",
             rules: Optional[Sequence[Mapping[str, Any]]] = None
             ) -> Dict[str, Any]:
    """Build a SARIF 2.1.0 document from normalized findings."""
    if rules is None:
        rule_ids = sorted({str(f.get("rule_id", "AC0000")) for f in findings})
        rules = [{"id": rule_id} for rule_id in rule_ids]
    return {
        "version": SARIF_VERSION, "$schema": _SCHEMA,
        "runs": [{
            "tool": {"driver": {"name": tool_name, "rules": list(rules)}},
            "results": [_result(f) for f in findings],
        }],
    }


def write_sarif(findings: Sequence[Mapping[str, Any]], path: str,
                **kwargs: Any) -> str:
    """Write a SARIF document for ``findings`` to ``path``; return the path."""
    from pathlib import Path
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    from je_auto_control.utils.http_headers import wire_json_text
    from je_auto_control.utils.json_store.json_store import atomic_write_text
    # wire_json_text: escaped only if a lone surrogate would not encode.
    atomic_write_text(str(output), wire_json_text(to_sarif(findings, **kwargs)))
    return str(output)


def from_lint_issues(issues: Sequence[Any], *,
                     file: Optional[str] = None) -> List[Dict[str, Any]]:
    """Normalize action-lint issues (``index/severity/code/message``)."""
    return [
        make_finding(str(_get(i, "code") or "lint"), _get(i, "message", ""),
                     level=_level(_get(i, "severity")), file=file,
                     # ``index`` is the 0-based action index; SARIF lines are 1-based.
                     line=(int(_get(i, "index")) + 1
                           if isinstance(_get(i, "index"), int) and _get(i, "index") >= 0
                           else None))
        for i in issues
    ]


def from_audit_findings(findings: Sequence[Mapping[str, Any]]
                        ) -> List[Dict[str, Any]]:
    """Normalize WCAG audit findings (``sc/criterion/kind/severity``)."""
    return [
        make_finding(str(f.get("sc") or f.get("criterion") or "wcag"),
                     f"{f.get('criterion', '')}: {f.get('kind', '')}".strip(),
                     level=_level(f.get("severity")))
        for f in findings
    ]
