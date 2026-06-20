"""Evaluate dependency licenses against an allow / deny policy.

``utils/sbom`` records each component's license *name* but never judges it, so
a copyleft or otherwise-disallowed license could ship unnoticed. This adds the
policy gate: normalize the SBOM's license strings to SPDX ids, evaluate them
against an allowlist / denylist (with a built-in strong-copyleft set), and emit
violations that bridge into the existing SARIF exporter — the license-compliance
lane beside the OSV vulnerability lane.

Pure standard library (``re``); imports no ``PySide6``.
"""
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from je_auto_control.utils.sarif import make_finding

# Strong/network copyleft SPDX ids most policies want to flag.
DEFAULT_COPYLEFT = frozenset({
    "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later", "LGPL-2.1-only", "LGPL-3.0-only",
    "LGPL-3.0-or-later", "MPL-2.0", "EPL-2.0", "CDDL-1.0",
})

# Canonical SPDX id -> the loose names that should normalize to it. Inverted
# below so each SPDX id literal appears exactly once (no duplicated literals).
_ALIAS_GROUPS = {
    "MIT": ("mit license", "the mit license", "mit"),
    "Apache-2.0": ("apache 2.0", "apache-2", "apache 2", "apache2",
                   "apache software license", "apache license 2.0"),
    "BSD-3-Clause": ("bsd", "bsd license", "new bsd license"),
    "GPL-2.0-only": ("gplv2",),
    "GPL-3.0-only": ("gplv3", "gnu gplv3"),
    "LGPL-3.0-only": ("lgplv3",),
    "MPL-2.0": ("mpl 2.0",),
    "ISC": ("isc license",),
}
_ALIASES = {alias: spdx for spdx, names in _ALIAS_GROUPS.items()
            for alias in names}

_OPERATOR_RE = re.compile(r"\b(?:OR|AND|WITH)\b|[()]", re.IGNORECASE)


def normalize_spdx(raw: str) -> str:
    """Normalize a single license token to a canonical SPDX id (best effort)."""
    text = str(raw).strip()
    if not text:
        return ""
    alias = _ALIASES.get(text.lower())
    if alias:
        return alias
    lowered = text.lower()
    for suffix in (" license", " licence"):
        if lowered.endswith(suffix):
            return text[:-len(suffix)].strip()
    return text


def _extract_ids(license_str: str) -> List[str]:
    parts = _OPERATOR_RE.split(str(license_str))
    return [spdx for spdx in (normalize_spdx(part) for part in parts) if spdx]


def _norm_set(values: Optional[Sequence[str]]) -> Set[str]:
    return {normalize_spdx(value) for value in values} if values else set()


def _allow_status(ids: Sequence[str], allow: Sequence[str],
                  license_str: str) -> str:
    allow_set = _norm_set(allow)
    matcher = any if " or " in f" {str(license_str).lower()} " else all
    return "allowed" if matcher(spdx in allow_set for spdx in ids) else "denied"


def evaluate_license(license_str: str, *,
                     allow: Optional[Sequence[str]] = None,
                     deny: Optional[Sequence[str]] = None) -> str:
    """Return ``allowed`` / ``denied`` / ``unknown`` for a license string."""
    ids = _extract_ids(license_str)
    if not ids:
        return "unknown"
    deny_set = _norm_set(deny)
    if deny_set and any(spdx in deny_set for spdx in ids):
        return "denied"
    if allow is None:
        return "allowed"
    return _allow_status(ids, allow, license_str)


def _component_license(component: Mapping[str, Any]) -> str:
    for entry in component.get("licenses", []):
        if "expression" in entry:
            return str(entry["expression"])
        license_obj = entry.get("license", {})
        name = license_obj.get("id") or license_obj.get("name")
        if name:
            return str(name)
    return ""


def evaluate_sbom(components: Sequence[Mapping[str, Any]], *,
                  allow: Optional[Sequence[str]] = None,
                  deny: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Return a violation per component whose license is not ``allowed``."""
    violations: List[Dict[str, Any]] = []
    for component in components:
        license_str = _component_license(component)
        status = evaluate_license(license_str, allow=allow, deny=deny)
        if status != "allowed":
            violations.append({
                "name": str(component.get("name", "")),
                "version": str(component.get("version", "")),
                "license": license_str,
                "status": status,
            })
    return violations


def license_findings_to_sarif(violations: Sequence[Mapping[str, Any]]
                              ) -> List[Dict[str, Any]]:
    """Convert license violations into SARIF-ready normalized findings."""
    findings = []
    for violation in violations:
        level = "error" if violation["status"] == "denied" else "warning"
        shown = violation["license"] or "unknown"
        message = (f"{violation['name']} {violation['version']}: license "
                   f"'{shown}' is {violation['status']}")
        findings.append(make_finding(
            f"license/{violation['name']}", message, level=level))
    return findings
