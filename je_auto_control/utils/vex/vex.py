"""Author and apply OpenVEX statements over vulnerability findings.

``utils/vuln_scan`` produces vulnerability findings, but every known CVE then
shows up forever — there was no way to record "we looked, this one does not
affect us" and drop it. VEX (Vulnerability Exploitability eXchange) is the
standard for exactly that triage signal. This builds `OpenVEX
<https://openvex.dev>`_ 0.2.0 statements and applies them to the findings from
the scanner: ``not_affected`` / ``fixed`` statements suppress a finding, while
``affected`` / ``under_investigation`` annotate it with the assessed status.

Pure standard library (``hashlib`` + ``json`` + ``datetime``); imports no
``PySide6``.
"""
import datetime
import hashlib
import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import unquote

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.vuln_scan.vuln_scan import version_key

_CONTEXT = "https://openvex.dev/ns/v0.2.0"

VEX_STATUSES = frozenset({
    "not_affected", "affected", "fixed", "under_investigation",
})
VEX_JUSTIFICATIONS = frozenset({
    "component_not_present", "vulnerable_code_not_present",
    "vulnerable_code_not_in_execute_path",
    "vulnerable_code_cannot_be_controlled_by_adversary",
    "inline_mitigations_already_exist",
})
_SUPPRESSED = frozenset({"not_affected", "fixed"})


def _check_statement(status: str, justification: Optional[str],
                     impact_statement: Optional[str]) -> None:
    if status not in VEX_STATUSES:
        raise AutoControlException(f"invalid VEX status {status!r}")
    if status == "not_affected" and not (justification or impact_statement):
        raise AutoControlException(
            "not_affected requires a justification or impact_statement")
    if justification and justification not in VEX_JUSTIFICATIONS:
        raise AutoControlException(f"invalid VEX justification {justification!r}")


def vex_statement(vuln_id: str, status: str, *,
                  products: Optional[Sequence[str]] = None,
                  justification: Optional[str] = None,
                  impact_statement: Optional[str] = None) -> Dict[str, Any]:
    """Build one validated OpenVEX statement for ``vuln_id``."""
    _check_statement(status, justification, impact_statement)
    statement: Dict[str, Any] = {
        "vulnerability": {"name": str(vuln_id)},
        "products": [{"@id": str(product)} for product in (products or [])],
        "status": status,
    }
    if justification:
        statement["justification"] = justification
    if impact_statement:
        statement["impact_statement"] = impact_statement
    return statement


def _doc_id(statements: Sequence[Mapping[str, Any]]) -> str:
    basis = json.dumps(list(statements), sort_keys=True, default=str)
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
    return f"https://openvex.dev/docs/auto-{digest}"


def build_vex(statements: Sequence[Mapping[str, Any]], *,
              author: str = "AutoControl", vex_id: Optional[str] = None,
              version: int = 1, timestamp: Optional[str] = None) -> Dict[str, Any]:
    """Wrap ``statements`` in an OpenVEX 0.2.0 document."""
    when = timestamp or datetime.datetime.now(
        datetime.timezone.utc).isoformat()
    return {
        "@context": _CONTEXT,
        "@id": vex_id or _doc_id(statements),
        "author": str(author),
        "timestamp": when,
        "version": int(version),
        "statements": list(statements),
    }


def _normal_name(name: str) -> str:
    """PEP 503 form: ``PySide6_Essentials`` and ``pyside6-essentials`` are one package."""
    return re.sub(r"[-_.]+", "-", unquote(name).strip().lower())


def _product_parts(product_id: str) -> Tuple[str, Optional[str]]:
    """``(name, version)`` of a purl (``pkg:pypi/requests@2.0``), else ``(id, None)``."""
    if not product_id.startswith("pkg:"):
        return _normal_name(product_id), None
    path = product_id[4:].split("?", 1)[0].split("#", 1)[0]
    path, _, version = path.partition("@")
    return _normal_name(path.rsplit("/", 1)[-1]), (unquote(version) or None)


def _product_matches(product_id: str, package: str, version: str) -> bool:
    """Whether a statement's product is this finding's package (and version).

    The purl's version was dropped, so ``not_affected`` for requests 2.0.0
    also silenced the finding in requests 2.31.0.
    """
    name, product_version = _product_parts(product_id)
    if name != _normal_name(package):
        return False
    return (product_version is None or not version
            or version_key(product_version) == version_key(version))


def _statement_matches(statement: Mapping[str, Any],
                       finding: Mapping[str, Any]) -> bool:
    vulnerability = statement.get("vulnerability", {})
    names = {vulnerability.get("name", "")} | set(vulnerability.get("aliases", []))
    identifiers = {finding.get("id")} | set(finding.get("aliases", []))
    if not names & identifiers:
        return False
    products = [str(item.get("@id", "")) for item in
                statement.get("products", [])]
    if not products:
        return True
    # By name, not substring: a statement about ``requests-toolbelt`` must not
    # suppress a finding in ``requests``.
    package = str(finding.get("package", ""))
    version = str(finding.get("version", "") or "")
    return bool(package) and any(_product_matches(product, package, version)
                                 for product in products)


def _resolve_status(finding: Mapping[str, Any],
                    statements: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """Status of the last matching statement: later ones supersede earlier ones."""
    status = None
    for statement in statements:
        if _statement_matches(statement, finding):
            status = statement.get("status")
    return status


def apply_vex(findings: Sequence[Mapping[str, Any]],
              vex_doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return findings with ``not_affected``/``fixed`` ones suppressed."""
    statements = vex_doc.get("statements", [])
    kept: List[Dict[str, Any]] = []
    for finding in findings:
        status = _resolve_status(finding, statements)
        if status in _SUPPRESSED:
            continue
        entry = dict(finding)
        if status is not None:
            entry["vex_status"] = status
        kept.append(entry)
    return kept
