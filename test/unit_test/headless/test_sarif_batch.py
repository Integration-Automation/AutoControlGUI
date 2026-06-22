"""Headless tests for SARIF 2.1.0 export. Pure stdlib, no Qt imports."""
import json

import je_auto_control as ac
from je_auto_control.utils.sarif import (
    from_audit_findings, from_lint_issues, make_finding, result_fingerprint,
    to_sarif, write_sarif)


def test_document_shape():
    doc = to_sarif([make_finding("AC101", "boom", level="error",
                                 file="flow.json", line=3)],
                   tool_name="AutoControl")
    assert doc["version"] == "2.1.0" and "$schema" in doc
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "AutoControl"
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["AC101"]
    result = run["results"][0]
    assert result["ruleId"] == "AC101" and result["level"] == "error"
    assert result["message"]["text"] == "boom"
    loc = result["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "flow.json"
    assert loc["region"]["startLine"] == 3


def test_finding_without_location():
    doc = to_sarif([make_finding("AC1", "msg")])
    assert "locations" not in doc["runs"][0]["results"][0]


def test_fingerprint_stable_and_distinct():
    a = make_finding("R", "same", file="f", line=1)
    assert result_fingerprint(a) == result_fingerprint(dict(a))
    assert result_fingerprint(a) != result_fingerprint(make_finding("R", "x"))


def test_explicit_rules_passthrough():
    doc = to_sarif([make_finding("R1", "m")],
                   rules=[{"id": "R1", "name": "Custom"}])
    assert doc["runs"][0]["tool"]["driver"]["rules"][0]["name"] == "Custom"


def test_from_lint_issues():
    findings = from_lint_issues(
        [{"index": 4, "severity": "error", "code": "E1", "message": "bad"}],
        file="flow.json")
    assert findings[0] == {"rule_id": "E1", "level": "error", "message": "bad",
                           "file": "flow.json", "line": 4}


def test_from_lint_negative_index_has_no_line():
    findings = from_lint_issues(
        [{"index": -1, "severity": "warning", "code": "E2", "message": "x"}])
    assert "line" not in findings[0] and findings[0]["level"] == "warning"


def test_from_audit_findings():
    findings = from_audit_findings(
        [{"sc": "1.4.3", "criterion": "Contrast", "kind": "low-contrast",
          "severity": "serious"}])
    assert findings[0]["rule_id"] == "1.4.3"
    assert findings[0]["level"] == "error"
    assert "Contrast" in findings[0]["message"]


def test_write_sarif(tmp_path):
    from pathlib import Path
    path = write_sarif([make_finding("R", "m")], str(tmp_path / "out.sarif"))
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert doc["version"] == "2.1.0"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip(tmp_path):
    out = str(tmp_path / "r.sarif")
    rec = ac.execute_action([[
        "AC_export_sarif",
        {"findings": [{"rule_id": "AC1", "message": "m", "level": "warning"}],
         "path": out},
    ]])
    res = next(v for v in rec.values() if isinstance(v, dict) and "sarif" in v)
    assert res["sarif"]["version"] == "2.1.0"
    assert res["path"] == out


def test_wiring():
    assert "AC_export_sarif" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_export_sarif" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_export_sarif" in cmds


def test_facade_exports():
    for attr in ("to_sarif", "write_sarif", "make_finding", "from_lint_issues",
                 "from_audit_findings"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
