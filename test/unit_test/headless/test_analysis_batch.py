"""Headless tests for the analysis batch: self-heal analytics + secrets
scanning. Pure stdlib; events/data supplied inline (no log file needed)."""
import je_auto_control as ac
from je_auto_control.utils.heal_analytics import heal_stats
from je_auto_control.utils.secrets_scan import scan_secrets


# --- self-heal analytics --------------------------------------------------

def test_heal_stats_metrics():
    events = [
        {"method": "image", "coordinates": [1, 2], "duration_ms": 10},
        {"method": "vlm", "coordinates": [3, 4], "duration_ms": 50,
         "image_error": "not found", "template_path": "btn.png"},
        {"method": "vlm", "coordinates": None, "duration_ms": 30,
         "image_error": "not found", "template_path": "btn.png"},
    ]
    stats = heal_stats(events)
    assert stats["total"] == 3 and stats["healed"] == 2
    assert stats["heal_rate"] == round(2 / 3, 4)
    assert stats["by_method"] == {"image": 1, "vlm": 2}
    assert stats["fallbacks"] == 2 and stats["fallback_rate"] == round(2/3, 4)
    assert stats["avg_duration_ms"] == 30.0
    assert stats["top_brittle"][0] == {"locator": "btn.png", "fallbacks": 2}


def test_heal_stats_empty():
    stats = heal_stats([])
    assert stats["total"] == 0 and stats["heal_rate"] == 0.0


# --- secrets scan ---------------------------------------------------------

def test_scan_secrets_by_key_value_and_entropy():
    data = {
        "login": {"password": "hunter2pass", "user": "ada"},
        "ref": "${secrets.TOKEN}",                       # vault ref -> ignored
        "aws": "AKIAIOSFODNN7EXAMPLE",
        "note": "hello world",                           # benign -> ignored
        "blob": "aGVsbG9Xb3JsZFNlY3JldEtleTEyMzQ1Njc4OQ",  # high entropy
    }
    findings = scan_secrets(data)
    kinds = {f["kind"] for f in findings}
    paths = {f["path"] for f in findings}
    assert "hardcoded-secret-key" in kinds       # password
    assert "aws-access-key" in kinds
    assert "$.login.password" in paths
    assert all("hunter2" not in f["preview"] for f in findings)  # masked
    assert not any(f["path"] == "$.ref" for f in findings)       # vault ok
    assert not any(f["path"] == "$.note" for f in findings)      # benign ok


def test_scan_secrets_clean():
    assert scan_secrets({"a": "ok", "b": "${secrets.X}", "n": 5}) == []


# --- wiring ---------------------------------------------------------------

def test_executor_wiring():
    rec = ac.execute_action([["AC_scan_secrets", {
        "data": {"password": "secretvalue123"}}]])
    assert any("hardcoded-secret-key" in str(v) for v in rec.values())
    heal = ac.execute_action([["AC_heal_stats", {"limit": 10}]])
    assert any("heal_rate" in str(v) for v in heal.values())
    known = ac.executor.known_commands()
    assert {"AC_heal_stats", "AC_scan_secrets"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_heal_stats", "ac_scan_secrets"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_heal_stats", "AC_scan_secrets"} <= cmds


def test_facade_exports():
    for attr in ("analyze_heal_log", "heal_stats", "scan_secrets"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
