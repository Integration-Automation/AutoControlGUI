"""Headless tests for OpenVEX authoring and triage. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.vex import (
    VEX_JUSTIFICATIONS, VEX_STATUSES, apply_vex, build_vex, vex_statement)
from je_auto_control.utils.vuln_scan import scan_components

FINDINGS = [
    {"id": "GHSA-foo", "package": "foo", "version": "1.0.0",
     "aliases": ["CVE-2024-1"], "severity": "error"},
    {"id": "GHSA-bar", "package": "bar", "version": "1.0.0",
     "aliases": [], "severity": "note"},
]


def test_statuses_and_justifications_constants():
    assert "not_affected" in VEX_STATUSES
    assert "vulnerable_code_not_present" in VEX_JUSTIFICATIONS


def test_vex_statement_shape():
    statement = vex_statement("CVE-2024-1", "not_affected",
                              products=["pkg:pypi/foo"],
                              justification="vulnerable_code_not_present")
    assert statement["vulnerability"]["name"] == "CVE-2024-1"
    assert statement["status"] == "not_affected"
    assert statement["products"] == [{"@id": "pkg:pypi/foo"}]
    assert statement["justification"] == "vulnerable_code_not_present"


def test_vex_statement_validation():
    with pytest.raises(AutoControlException):
        vex_statement("X", "bogus")
    with pytest.raises(AutoControlException):
        vex_statement("X", "not_affected")
    with pytest.raises(AutoControlException):
        vex_statement("X", "affected", justification="not-a-real-one")


def test_build_vex_envelope_is_deterministic_with_timestamp():
    statement = vex_statement("CVE-2024-1", "fixed")
    doc = build_vex([statement], author="sec@me",
                    timestamp="2026-06-21T00:00:00+00:00")
    again = build_vex([statement], author="sec@me",
                      timestamp="2026-06-21T00:00:00+00:00")
    assert doc["@context"] == "https://openvex.dev/ns/v0.2.0"
    assert doc["author"] == "sec@me"
    assert doc["@id"] == again["@id"]


def test_apply_vex_suppresses_via_alias_match():
    statement = vex_statement("CVE-2024-1", "not_affected",
                              products=["pkg:pypi/foo"],
                              justification="vulnerable_code_not_present")
    doc = build_vex([statement], timestamp="2026-06-21T00:00:00+00:00")
    kept = apply_vex(FINDINGS, doc)
    assert [f["id"] for f in kept] == ["GHSA-bar"]


def test_apply_vex_annotates_non_suppressed():
    statement = vex_statement("GHSA-bar", "under_investigation")
    doc = build_vex([statement], timestamp="2026-06-21T00:00:00+00:00")
    kept = apply_vex(FINDINGS, doc)
    bar = next(f for f in kept if f["id"] == "GHSA-bar")
    assert bar["vex_status"] == "under_investigation"


def test_apply_vex_product_scoping():
    # statement scoped to a different product must not suppress foo
    statement = vex_statement("CVE-2024-1", "not_affected",
                              products=["pkg:pypi/other"],
                              justification="component_not_present")
    doc = build_vex([statement], timestamp="2026-06-21T00:00:00+00:00")
    assert [f["id"] for f in apply_vex(FINDINGS, doc)] == ["GHSA-foo", "GHSA-bar"]


def test_apply_vex_no_statements_keeps_all():
    doc = build_vex([], timestamp="2026-06-21T00:00:00+00:00")
    assert len(apply_vex(FINDINGS, doc)) == len(FINDINGS)


def test_composes_with_vuln_scanner():
    advisories = [{
        "id": "GHSA-foo", "aliases": ["CVE-2024-1"],
        "database_specific": {"severity": "HIGH"},
        "affected": [{"package": {"ecosystem": "PyPI", "name": "foo"},
                      "ranges": [{"type": "ECOSYSTEM",
                                  "events": [{"introduced": "0"},
                                             {"fixed": "2.0.0"}]}]}],
    }]
    components = [{"name": "foo", "version": "1.0.0",
                  "purl": "pkg:pypi/foo@1.0.0"}]
    findings = scan_components(components, advisories)
    assert [f["id"] for f in findings] == ["GHSA-foo"]
    statement = vex_statement("CVE-2024-1", "not_affected",
                              justification="vulnerable_code_not_present")
    doc = build_vex([statement], timestamp="2026-06-21T00:00:00+00:00")
    assert apply_vex(findings, doc) == []


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    statement = vex_statement("CVE-2024-1", "not_affected",
                              justification="vulnerable_code_not_present")
    doc = build_vex([statement], timestamp="2026-06-21T00:00:00+00:00")
    rec = ac.execute_action([[
        "AC_apply_vex",
        {"findings": json.dumps(FINDINGS), "vex": json.dumps(doc)},
    ]])
    payload = next(v for v in rec.values() if isinstance(v, dict))
    assert payload["count"] == 1
    assert payload["findings"][0]["id"] == "GHSA-bar"


def test_wiring():
    assert "AC_apply_vex" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_apply_vex" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_apply_vex" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("apply_vex", "build_vex", "vex_statement", "VEX_STATUSES",
                 "VEX_JUSTIFICATIONS"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
