"""Accessibility & i18n auditing over the a11y tree + OCR.

Public surface::

    from je_auto_control import (
        run_audit, audit_missing_labels, audit_contrast,
        detect_truncation, contrast_ratio, AuditReport, AuditIssue,
    )
"""
from je_auto_control.utils.a11y_audit.audit import (
    AuditIssue,
    AuditReport,
    audit_contrast,
    audit_missing_labels,
    contrast_ratio,
    detect_truncation,
    is_interactive,
    relative_luminance,
    run_audit,
)
from je_auto_control.utils.a11y_audit.wcag import (
    audit_target_size,
    tag_issue,
    wcag_audit,
)


__all__ = [
    "AuditIssue",
    "AuditReport",
    "audit_contrast",
    "audit_missing_labels",
    "audit_target_size",
    "contrast_ratio",
    "detect_truncation",
    "is_interactive",
    "relative_luminance",
    "run_audit",
    "tag_issue",
    "wcag_audit",
]
