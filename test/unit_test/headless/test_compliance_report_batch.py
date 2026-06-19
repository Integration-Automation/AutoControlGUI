"""Headless tests for the SOC2/ISO compliance control report. Pure stdlib, no
Qt imports."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.compliance import (
    build_compliance_report, render_compliance_html, write_compliance_report)

FULL_EVIDENCE = {
    "egress_allowlist_enforced": True,
    "jit_credentials_used": True,
    "secrets_scanned": True,
    "audit_logging_enabled": True,
    "change_approval_required": True,
    "sbom_generated": True,
}


def test_all_satisfied():
    report = build_compliance_report(FULL_EVIDENCE)
    assert report["summary"]["gap"] == 0
    assert report["summary"]["not_assessed"] == 0
    assert report["summary"]["satisfied"] == report["summary"]["total"]
    assert all(c["status"] == "satisfied" for c in report["controls"])


def test_gap_and_not_assessed():
    report = build_compliance_report({"egress_allowlist_enforced": False})
    statuses = {c["evidence_key"]: c["status"] for c in report["controls"]}
    assert statuses["egress_allowlist_enforced"] == "gap"
    assert statuses["sbom_generated"] == "not_assessed"
    assert report["summary"]["gap"] >= 1
    assert report["summary"]["not_assessed"] >= 1


def test_framework_filter():
    report = build_compliance_report(FULL_EVIDENCE, frameworks=["SOC2"])
    assert {c["framework"] for c in report["controls"]} == {"SOC2"}
    assert report["summary"]["total"] >= 1


def test_html_render_contains_controls():
    report = build_compliance_report(FULL_EVIDENCE)
    out = render_compliance_html(report)
    assert "<table" in out and "CC6.1" in out and "A.8.30" in out


def test_write_json_and_html(tmp_path):
    from pathlib import Path
    report = build_compliance_report(FULL_EVIDENCE)
    jpath = write_compliance_report(report, str(tmp_path / "r.json"), "json")
    hpath = write_compliance_report(report, str(tmp_path / "r.html"), "html")
    loaded = json.loads(Path(jpath).read_text(encoding="utf-8"))
    assert loaded["summary"]["total"]
    assert "<html" in Path(hpath).read_text(encoding="utf-8")


def test_unknown_format_raises(tmp_path):
    report = build_compliance_report(FULL_EVIDENCE)
    with pytest.raises(ValueError):
        write_compliance_report(report, str(tmp_path / "r.xml"), "xml")


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip(tmp_path):
    out = str(tmp_path / "compliance.json")
    rec = ac.execute_action([[
        "AC_compliance_report",
        {"evidence": json.dumps(FULL_EVIDENCE), "frameworks": "SOC2",
         "path": out, "fmt": "json"},
    ]])
    report = next(v for v in rec.values() if isinstance(v, dict))
    assert report["summary"]["total"] >= 1
    assert report["path"] == out


def test_wiring():
    assert "AC_compliance_report" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_compliance_report" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_compliance_report" in cmds


def test_facade_exports():
    for attr in ("build_compliance_report", "render_compliance_html",
                 "write_compliance_report"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
