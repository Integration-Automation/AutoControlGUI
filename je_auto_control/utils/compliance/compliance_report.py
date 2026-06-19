"""Map AutoControl governance evidence to SOC2 / ISO 27001 controls.

The framework already ships the *controls* an auditor cares about — an egress
allowlist, just-in-time credential leases, maker-checker approval, a secrets
scanner, audit logging, a CycloneDX SBOM. This module turns "are those controls
in place?" into an auditor-readable **control evidence report**: the caller
supplies a flat ``evidence`` mapping of observed facts, and each catalogued
control is marked ``satisfied`` / ``gap`` / ``not_assessed`` accordingly.

It is a reporting aid, not a certification: it does not itself verify the
controls, it records the evidence you assert. Pure standard library; imports no
``PySide6``.
"""
import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

STATUS_SATISFIED = "satisfied"
STATUS_GAP = "gap"
STATUS_NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class Control:
    """A single mapped control and the evidence key that satisfies it."""

    control_id: str
    framework: str
    title: str
    evidence_key: str


CONTROL_CATALOGUE: Sequence[Control] = (
    Control("CC6.1", "SOC2", "Logical access restricted to authorized hosts",
            "egress_allowlist_enforced"),
    Control("CC6.3", "SOC2", "Least-privilege, time-boxed credentials",
            "jit_credentials_used"),
    Control("CC6.8", "SOC2", "Secrets are not hardcoded and are scanned",
            "secrets_scanned"),
    Control("CC7.3", "SOC2", "Security-relevant events are logged for review",
            "audit_logging_enabled"),
    Control("CC8.1", "SOC2", "Changes require segregated (maker-checker) approval",
            "change_approval_required"),
    Control("A.5.23", "ISO27001", "Information security for cloud/network egress",
            "egress_allowlist_enforced"),
    Control("A.8.16", "ISO27001", "Monitoring activities / audit trail",
            "audit_logging_enabled"),
    Control("A.8.30", "ISO27001", "Software bill of materials maintained",
            "sbom_generated"),
)


def _status_for(evidence: Mapping[str, Any], key: str) -> str:
    if key not in evidence:
        return STATUS_NOT_ASSESSED
    return STATUS_SATISFIED if evidence[key] else STATUS_GAP


def build_compliance_report(evidence: Mapping[str, Any],
                            frameworks: Optional[Sequence[str]] = None
                            ) -> Dict[str, Any]:
    """Map ``evidence`` to the control catalogue, optionally filtered.

    ``frameworks`` restricts the report (e.g. ``["SOC2"]``); ``None`` includes
    all. Each control is ``satisfied`` (truthy evidence), ``gap`` (explicitly
    falsy), or ``not_assessed`` (key absent).
    """
    wanted = {f.upper() for f in frameworks} if frameworks else None
    controls: List[Dict[str, Any]] = []
    summary = {STATUS_SATISFIED: 0, STATUS_GAP: 0, STATUS_NOT_ASSESSED: 0}
    for control in CONTROL_CATALOGUE:
        if wanted is not None and control.framework.upper() not in wanted:
            continue
        status = _status_for(evidence, control.evidence_key)
        summary[status] += 1
        controls.append({
            "control_id": control.control_id, "framework": control.framework,
            "title": control.title, "evidence_key": control.evidence_key,
            "status": status,
        })
    summary["total"] = len(controls)
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary, "controls": controls,
    }


def render_compliance_html(report: Mapping[str, Any]) -> str:
    """Render a compliance ``report`` as a standalone HTML table."""
    summary = report.get("summary", {})
    rows = "".join(
        f"<tr class='{html.escape(str(c['status']))}'>"
        f"<td>{html.escape(str(c['framework']))}</td>"
        f"<td>{html.escape(str(c['control_id']))}</td>"
        f"<td>{html.escape(str(c['title']))}</td>"
        f"<td>{html.escape(str(c['status']))}</td></tr>"
        for c in report.get("controls", []))
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>Compliance Control Evidence</title></head><body>"
        "<h1>Compliance Control Evidence</h1>"
        f"<p>Generated {html.escape(str(report.get('generated_utc', '')))} — "
        f"satisfied {summary.get(STATUS_SATISFIED, 0)}, "
        f"gap {summary.get(STATUS_GAP, 0)}, "
        f"not assessed {summary.get(STATUS_NOT_ASSESSED, 0)}.</p>"
        "<table border='1'><tr><th>Framework</th><th>Control</th>"
        "<th>Title</th><th>Status</th></tr>"
        f"{rows}</table></body></html>")


def write_compliance_report(report: Mapping[str, Any], path: str,
                            fmt: str = "json") -> str:
    """Write ``report`` to ``path`` as ``json`` or ``html``; return the path."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "html":
        output.write_text(render_compliance_html(report), encoding="utf-8")
    elif fmt == "json":
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    else:
        raise ValueError(f"unknown compliance report format: {fmt!r}")
    return str(output)
