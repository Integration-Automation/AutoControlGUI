"""Headless tests for the SPDX license-policy gate. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.license_policy import (
    DEFAULT_COPYLEFT, evaluate_license, evaluate_sbom,
    license_findings_to_sarif, normalize_spdx)
from je_auto_control.utils.sarif import to_sarif

ALLOW = ["MIT", "Apache-2.0", "BSD-3-Clause"]
COMPONENTS = [
    {"name": "a", "version": "1.0", "licenses": [{"license": {"name": "MIT"}}]},
    {"name": "b", "version": "2.0",
     "licenses": [{"license": {"name": "GPL-3.0-only"}}]},
    {"name": "c", "version": "3.0"},
    {"name": "d", "version": "4.0", "licenses": [{"expression": "MIT OR Apache-2.0"}]},
]


def test_normalize_spdx_aliases():
    assert normalize_spdx("MIT License") == "MIT"
    assert normalize_spdx("Apache 2.0") == "Apache-2.0"
    assert normalize_spdx("GPL-3.0-only") == "GPL-3.0-only"
    assert normalize_spdx("") == ""


def test_evaluate_license_allowlist():
    assert evaluate_license("MIT", allow=ALLOW) == "allowed"
    assert evaluate_license("GPL-3.0-only", allow=ALLOW) == "denied"
    assert evaluate_license("", allow=ALLOW) == "unknown"


def test_evaluate_license_denylist_copyleft():
    assert evaluate_license("GPL-3.0-only", deny=DEFAULT_COPYLEFT) == "denied"
    assert evaluate_license("MIT", deny=DEFAULT_COPYLEFT) == "allowed"


def test_evaluate_license_no_policy_allows_known():
    assert evaluate_license("Anything-1.0") == "allowed"


def test_or_expression_is_a_choice():
    assert evaluate_license("MIT OR GPL-3.0-only", allow=["MIT"]) == "allowed"


def test_and_expression_requires_all():
    assert evaluate_license("MIT AND GPL-3.0-only", allow=["MIT"]) == "denied"


def test_evaluate_sbom_violations():
    violations = evaluate_sbom(COMPONENTS, allow=ALLOW)
    by_name = {v["name"]: v["status"] for v in violations}
    assert by_name == {"b": "denied", "c": "unknown"}
    assert "a" not in by_name and "d" not in by_name


def test_deny_takes_precedence_in_sbom():
    violations = evaluate_sbom(COMPONENTS, deny=["GPL-3.0-only"])
    assert {v["name"] for v in violations} == {"b", "c"}


def test_findings_to_sarif_levels():
    violations = evaluate_sbom(COMPONENTS, allow=ALLOW)
    document = to_sarif(license_findings_to_sarif(violations))
    levels = {r["ruleId"]: r["level"] for r in document["runs"][0]["results"]}
    assert levels["license/b"] == "error"
    assert levels["license/c"] == "warning"


def test_license_id_field_supported():
    components = [{"name": "z", "version": "1.0",
                  "licenses": [{"license": {"id": "GPL-3.0-only"}}]}]
    assert evaluate_sbom(components, allow=ALLOW)[0]["status"] == "denied"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    sbom = {"components": COMPONENTS}
    rec = ac.execute_action([[
        "AC_check_licenses",
        {"components": json.dumps(sbom), "allow": json.dumps(ALLOW)},
    ]])
    payload = next(v for v in rec.values() if isinstance(v, dict))
    assert payload["count"] == 2
    assert {v["name"] for v in payload["violations"]} == {"b", "c"}


def test_wiring():
    assert "AC_check_licenses" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_check_licenses" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_check_licenses" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("evaluate_license", "evaluate_sbom", "normalize_spdx",
                 "license_findings_to_sarif", "DEFAULT_COPYLEFT"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
