"""Headless tests for the OSV vulnerability matcher. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.sarif import to_sarif
from je_auto_control.utils.vuln_scan import (
    findings_to_sarif, is_affected, match_package, scan_components, version_key)

ADVISORIES = [
    {
        "id": "GHSA-foo", "summary": "RCE in foo", "aliases": ["CVE-2024-1"],
        "database_specific": {"severity": "HIGH"},
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "foo"},
            "ranges": [{"type": "ECOSYSTEM",
                        "events": [{"introduced": "0"}, {"fixed": "1.2.0"}]}],
        }],
    },
    {
        "id": "GHSA-bar", "summary": "bug", "database_specific": {"severity": "LOW"},
        "affected": [{"package": {"ecosystem": "PyPI", "name": "bar"},
                      "versions": ["2.0.0"]}],
    },
]


def test_version_key_orders_releases_and_prereleases():
    assert version_key("2.0.0") > version_key("1.9.9")
    assert version_key("1.2.0") > version_key("1.2.0-rc1")
    assert version_key("1.10.0") > version_key("1.9.0")


def test_is_affected_introduced_fixed_range():
    rng = {"type": "ECOSYSTEM",
           "events": [{"introduced": "1.0.0"}, {"fixed": "2.0.0"}]}
    assert is_affected("1.5.0", rng) is True
    assert is_affected("2.0.0", rng) is False
    assert is_affected("0.9.0", rng) is False


def test_is_affected_last_affected_and_git_skip():
    rng = {"type": "ECOSYSTEM",
           "events": [{"introduced": "1.0.0"}, {"last_affected": "1.5.0"}]}
    assert is_affected("1.5.0", rng) is True
    assert is_affected("1.6.0", rng) is False
    assert is_affected("abcdef", {"type": "GIT", "events": []}) is False


def test_match_package_range_and_boundary():
    assert match_package("PyPI", "foo", "1.0.0", ADVISORIES)
    assert not match_package("PyPI", "foo", "1.2.0", ADVISORIES)
    assert not match_package("PyPI", "foo", "1.3.0", ADVISORIES)


def test_match_package_explicit_versions():
    assert match_package("PyPI", "bar", "2.0.0", ADVISORIES)
    assert not match_package("PyPI", "bar", "2.1.0", ADVISORIES)


def test_match_package_name_normalization_and_ecosystem():
    assert match_package("PyPI", "Foo", "1.0.0", ADVISORIES)
    assert not match_package("npm", "foo", "1.0.0", ADVISORIES)


def test_finding_shape_severity_and_fixed():
    finding = match_package("PyPI", "foo", "1.0.0", ADVISORIES)[0]
    assert finding["id"] == "GHSA-foo"
    assert finding["severity"] == "error"
    assert finding["fixed"] == "1.2.0"
    assert finding["aliases"] == ["CVE-2024-1"]


def test_scan_components_from_purl_ecosystem():
    components = [
        {"name": "foo", "version": "1.1.0", "purl": "pkg:pypi/foo@1.1.0"},
        {"name": "safe", "version": "9.9.9", "purl": "pkg:pypi/safe@9.9.9"},
    ]
    findings = scan_components(components, ADVISORIES)
    assert [f["id"] for f in findings] == ["GHSA-foo"]


def test_scan_components_with_injected_fetcher():
    extra = ADVISORIES
    components = [{"name": "foo", "version": "1.0.0",
                  "purl": "pkg:pypi/foo@1.0.0"}]
    calls = []

    def fetcher(ecosystem, name):
        calls.append((ecosystem, name))
        return extra

    findings = scan_components(components, None, fetcher=fetcher)
    assert calls == [("PyPI", "foo")]
    assert findings and findings[0]["id"] == "GHSA-foo"


def test_findings_to_sarif_bridge():
    findings = scan_components(
        [{"name": "foo", "version": "1.0.0", "purl": "pkg:pypi/foo@1.0.0"}],
        ADVISORIES)
    document = to_sarif(findings_to_sarif(findings))
    result = document["runs"][0]["results"][0]
    assert result["ruleId"] == "GHSA-foo"
    assert result["level"] == "error"
    assert "fixed in 1.2.0" in result["message"]["text"]


def test_severity_defaults_to_warning_when_unknown():
    advisory = [{"id": "X", "affected": [{
        "package": {"ecosystem": "PyPI", "name": "q"}, "versions": ["1.0.0"]}]}]
    assert match_package("PyPI", "q", "1.0.0", advisory)[0]["severity"] == "warning"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    sbom = {"components": [{"name": "foo", "version": "1.0.0",
                           "purl": "pkg:pypi/foo@1.0.0"}]}
    rec = ac.execute_action([[
        "AC_scan_vulns",
        {"components": json.dumps(sbom), "advisories": json.dumps(ADVISORIES)},
    ]])
    payload = next(v for v in rec.values() if isinstance(v, dict))
    assert payload["count"] == 1
    assert payload["findings"][0]["id"] == "GHSA-foo"


def test_wiring():
    assert "AC_scan_vulns" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_scan_vulns" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_scan_vulns" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("scan_components", "match_package", "is_affected",
                 "version_key", "findings_to_sarif"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
