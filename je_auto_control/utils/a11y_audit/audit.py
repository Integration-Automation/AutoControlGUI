"""Accessibility & i18n auditing — reuse the a11y tree + OCR to find defects.

The accessibility tree and OCR layer are normally used to *locate* widgets
to drive them. This module turns them around to *inspect* a UI for common
accessibility and localisation defects:

* :func:`audit_missing_labels` — interactive widgets (buttons, menu items,
  links, fields…) exposed through the a11y tree with no accessible name.
* :func:`contrast_ratio` / :func:`audit_contrast` — WCAG 2.x relative-
  luminance contrast ratio between foreground and background colours, with
  AA/AAA threshold checks.
* :func:`detect_truncation` — OCR strings ending in an ellipsis (text
  clipped by a too-narrow control after translation).

Every check accepts its inputs programmatically (elements / colour pairs /
strings) so it is fully unit-testable headlessly; :func:`run_audit` wires
the live a11y tree in for convenience.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

# WCAG 2.x AA / AAA contrast minimums for normal-size text.
WCAG_AA_NORMAL = 4.5
WCAG_AAA_NORMAL = 7.0

# Substrings of accessibility roles that imply an actionable control which
# must carry an accessible name. Matched case-insensitively.
INTERACTIVE_ROLE_HINTS = frozenset({
    "button", "menuitem", "menu item", "checkbox", "check box", "radio",
    "link", "hyperlink", "tab", "combobox", "combo box", "edit", "textbox",
    "text box", "slider", "listitem", "list item", "treeitem", "tree item",
    "switch", "spinbutton", "spin button",
})

_TRUNCATION_MARKERS = ("…", "...")


@dataclass(frozen=True)
class AuditIssue:
    """One accessibility / i18n defect."""

    kind: str
    severity: str
    message: str
    target: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditReport:
    """Collected issues for an audited scope."""

    issues: List[AuditIssue] = field(default_factory=list)
    scope: str = ""

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == SEVERITY_ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == SEVERITY_WARNING)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "total": len(self.issues),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def is_interactive(role: str) -> bool:
    """Return True when ``role`` names an actionable control."""
    lowered = (role or "").lower()
    return any(hint in lowered for hint in INTERACTIVE_ROLE_HINTS)


def audit_missing_labels(elements: Iterable[Any]) -> List[AuditIssue]:
    """Flag interactive elements whose accessible name is blank."""
    issues: List[AuditIssue] = []
    for element in elements:
        name = getattr(element, "name", "") or ""
        role = getattr(element, "role", "") or ""
        if is_interactive(role) and not name.strip():
            issues.append(AuditIssue(
                kind="missing_label", severity=SEVERITY_ERROR,
                message=f"{role} has no accessible name",
                target=role,
                detail={"bounds": list(getattr(element, "bounds", []))},
            ))
    return issues


def _channel(value: float) -> float:
    srgb = max(0.0, min(255.0, float(value))) / 255.0
    return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: Sequence[float]) -> float:
    """WCAG relative luminance of an sRGB colour."""
    r, g, b = (_channel(rgb[i]) for i in range(3))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(rgb1: Sequence[float], rgb2: Sequence[float]) -> float:
    """WCAG contrast ratio between two colours (1.0 .. 21.0)."""
    lum1, lum2 = relative_luminance(rgb1), relative_luminance(rgb2)
    lighter, darker = max(lum1, lum2), min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def audit_contrast(pairs: Iterable[Dict[str, Any]],
                   min_ratio: float = WCAG_AA_NORMAL) -> List[AuditIssue]:
    """Flag foreground/background colour pairs below ``min_ratio``.

    Each pair is ``{"foreground": [r,g,b], "background": [r,g,b],
    "label": "..."}``.
    """
    issues: List[AuditIssue] = []
    for pair in pairs:
        ratio = contrast_ratio(pair["foreground"], pair["background"])
        if ratio < min_ratio:
            issues.append(AuditIssue(
                kind="contrast", severity=SEVERITY_ERROR,
                message=(f"contrast {ratio:.2f}:1 below "
                         f"{min_ratio:.1f}:1 minimum"),
                target=str(pair.get("label", "")),
                detail={"ratio": round(ratio, 2),
                        "foreground": list(pair["foreground"]),
                        "background": list(pair["background"])},
            ))
    return issues


def detect_truncation(texts: Iterable[str],
                      markers: Tuple[str, ...] = _TRUNCATION_MARKERS,
                      ) -> List[AuditIssue]:
    """Flag OCR strings that end with an ellipsis (likely clipped text)."""
    issues: List[AuditIssue] = []
    for text in texts:
        stripped = (text or "").rstrip()
        if stripped and stripped.endswith(markers):
            issues.append(AuditIssue(
                kind="truncation", severity=SEVERITY_WARNING,
                message="text appears truncated (ends with ellipsis)",
                target=stripped,
            ))
    return issues


def run_audit(app_name: Optional[str] = None,
              elements: Optional[Iterable[Any]] = None,
              contrast_pairs: Optional[Iterable[Dict[str, Any]]] = None,
              texts: Optional[Iterable[str]] = None,
              min_ratio: float = WCAG_AA_NORMAL,
              max_results: int = 500) -> AuditReport:
    """Run every applicable check and return a combined :class:`AuditReport`.

    When ``elements`` is omitted the live accessibility tree is queried.
    ``contrast_pairs`` and ``texts`` are optional caller-supplied inputs.
    """
    if elements is None:
        from je_auto_control.utils.accessibility.accessibility_api import (
            list_accessibility_elements,
        )
        elements = list_accessibility_elements(
            app_name=app_name, max_results=int(max_results),
        )
    report = AuditReport(scope=app_name or "screen")
    report.issues.extend(audit_missing_labels(elements))
    if contrast_pairs is not None:
        report.issues.extend(audit_contrast(contrast_pairs, min_ratio))
    if texts is not None:
        report.issues.extend(detect_truncation(texts))
    return report
