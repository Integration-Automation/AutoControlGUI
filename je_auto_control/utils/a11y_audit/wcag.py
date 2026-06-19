"""WCAG 2.2 / EN 301 549 success-criterion tagging for a11y audits.

The base :mod:`je_auto_control.utils.a11y_audit` checks find *defects*; this
layer tags each defect with the WCAG **success criterion** it violates
(id + name + conformance level + impact) and adds a new WCAG 2.2 rule —
**Target Size (Minimum), SC 2.5.8** — computable from element bounds. The
result is a conformance-style report you can map to EN 301 549 for
accessibility compliance evidence (EAA enforceable since June 2025).

Pure standard library; imports no ``PySide6``. Reuses the base audit's
pure functions, so it is fully unit-testable with supplied elements.
"""
from typing import Any, Dict, Iterable, List, Optional

from je_auto_control.utils.a11y_audit.audit import (
    AuditIssue, SEVERITY_ERROR, SEVERITY_WARNING, WCAG_AA_NORMAL,
    audit_contrast, audit_missing_labels, detect_truncation, is_interactive,
)

# kind -> (SC id, criterion name, conformance level)
_SC_BY_KIND = {
    "missing_label": ("4.1.2", "Name, Role, Value", "A"),
    "contrast": ("1.4.3", "Contrast (Minimum)", "AA"),
    "truncation": ("1.4.10", "Reflow", "AA"),
    "target_size": ("2.5.8", "Target Size (Minimum)", "AA"),
}
_IMPACT_BY_SEVERITY = {SEVERITY_ERROR: "serious", SEVERITY_WARNING: "moderate"}
_LEVEL_ORDER = {"A": 1, "AA": 2, "AAA": 3}
_MIN_TARGET_PX = 24


def audit_target_size(elements: Iterable[Any],
                      min_px: int = _MIN_TARGET_PX) -> List[AuditIssue]:
    """Flag interactive elements smaller than ``min_px`` on either side.

    WCAG 2.2 SC 2.5.8 (Target Size, Minimum) — pointer targets should be at
    least 24x24 CSS px. Elements with unknown (zero) size are skipped.
    """
    issues: List[AuditIssue] = []
    for element in elements:
        role = getattr(element, "role", "") or ""
        bounds = list(getattr(element, "bounds", []) or [])
        if not is_interactive(role) or len(bounds) < 4:
            continue
        width, height = int(bounds[2]), int(bounds[3])
        if width <= 0 or height <= 0 or min(width, height) >= int(min_px):
            continue
        issues.append(AuditIssue(
            kind="target_size", severity=SEVERITY_WARNING,
            message=f"target {width}x{height}px below {min_px}px minimum",
            target=role,
            detail={"width": width, "height": height, "min_px": int(min_px)}))
    return issues


def tag_issue(issue: AuditIssue) -> Dict[str, Any]:
    """Return an issue annotated with its WCAG success criterion."""
    sc, criterion, level = _SC_BY_KIND.get(issue.kind, ("", "", ""))
    return {
        "sc": sc, "criterion": criterion, "level": level,
        "impact": _IMPACT_BY_SEVERITY.get(issue.severity, "minor"),
        "kind": issue.kind, "severity": issue.severity,
        "message": issue.message, "target": issue.target,
        "detail": issue.detail,
    }


def _level_ok(found_level: str, target_level: str) -> bool:
    return (_LEVEL_ORDER.get(found_level, 99)
            <= _LEVEL_ORDER.get(target_level, 2))


def _fetch_elements(app_name: Optional[str], elements: Optional[Iterable[Any]],
                    max_results: int) -> List[Any]:
    if elements is not None:
        return list(elements)
    from je_auto_control.utils.accessibility.accessibility_api import (
        list_accessibility_elements)
    return list_accessibility_elements(app_name=app_name,
                                       max_results=int(max_results))


def _collect_issues(app_name: Optional[str], elements: Optional[Iterable[Any]],
                    contrast_pairs: Optional[Iterable[Dict[str, Any]]],
                    texts: Optional[Iterable[str]], min_ratio: float,
                    min_target_px: int, max_results: int) -> List[AuditIssue]:
    els = _fetch_elements(app_name, elements, max_results)
    issues = list(audit_missing_labels(els))
    issues.extend(audit_target_size(els, min_target_px))
    if contrast_pairs is not None:
        issues.extend(audit_contrast(contrast_pairs, min_ratio))
    if texts is not None:
        issues.extend(detect_truncation(texts))
    return issues


def _summary(findings: List[Dict[str, Any]], level: str) -> Dict[str, Any]:
    by_criterion: Dict[str, int] = {}
    by_impact: Dict[str, int] = {}
    for finding in findings:
        key = f"{finding['sc']} {finding['criterion']}".strip()
        by_criterion[key] = by_criterion.get(key, 0) + 1
        by_impact[finding["impact"]] = by_impact.get(finding["impact"], 0) + 1
    return {
        "level": level, "total": len(findings),
        "conformant": len(findings) == 0,
        "by_criterion": by_criterion, "by_impact": by_impact,
        "findings": findings,
    }


def wcag_audit(*, app_name: Optional[str] = None,
               elements: Optional[Iterable[Any]] = None,
               contrast_pairs: Optional[Iterable[Dict[str, Any]]] = None,
               texts: Optional[Iterable[str]] = None,
               min_ratio: float = WCAG_AA_NORMAL,
               min_target_px: int = _MIN_TARGET_PX,
               level: str = "AA", max_results: int = 500) -> Dict[str, Any]:
    """Run WCAG-tagged audits and return a conformance report.

    Findings are tagged with WCAG SC id / level / impact and filtered to the
    requested conformance ``level`` (A, AA, or AAA). When ``elements`` is
    omitted the live accessibility tree is queried.
    """
    issues = _collect_issues(app_name, elements, contrast_pairs, texts,
                             min_ratio, min_target_px, max_results)
    findings = [tag_issue(issue) for issue in issues]
    findings = [f for f in findings if _level_ok(f["level"], level)]
    return _summary(findings, level)
