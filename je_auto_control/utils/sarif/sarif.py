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
    "low": "note",
}


def _level(severity: Any) -> str:
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
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _result(finding: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ruleId": finding.get("rule_id", "AC0000"),
        "level": finding.get("level", "warning"),
        "message": {"text": finding.get("message", "")},
        "partialFingerprints": {"primaryLocationLineHash":
                                result_fingerprint(finding)},
    }
    if finding.get("file"):
        region = {"startLine": int(finding["line"])} if finding.get("line") \
            else {}
        result["locations"] = [{"physicalLocation": {
            "artifactLocation": {"uri": finding["file"]},
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
    import json
    from pathlib import Path
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(to_sarif(findings, **kwargs), ensure_ascii=False, indent=2),
        encoding="utf-8")
    return str(output)


def from_lint_issues(issues: Sequence[Any], *,
                     file: Optional[str] = None) -> List[Dict[str, Any]]:
    """Normalize action-lint issues (``index/severity/code/message``)."""
    return [
        make_finding(str(_get(i, "code") or "lint"), _get(i, "message", ""),
                     level=_level(_get(i, "severity")), file=file,
                     line=(_get(i, "index") if (_get(i, "index") or 0) >= 0
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
