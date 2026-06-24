"""Headless tests for default-app / URL opening (pure planner + injected opener)."""
import os

import pytest

import je_auto_control as ac
from je_auto_control.utils.shell_open import open_path, plan_open


def test_plan_url_goes_to_browser():
    plan = plan_open("https://example.com/x")
    assert plan["kind"] == "url"
    assert plan["scheme"] == "https"
    assert plan["backend"] == "webbrowser"


def test_plan_mailto_and_tel():
    assert plan_open("mailto:a@b.com")["scheme"] == "mailto"
    assert plan_open("tel:+123")["scheme"] == "tel"


def test_plan_file_path_is_realpathed():
    plan = plan_open("report.pdf")
    assert plan["kind"] == "file"
    assert plan["target"] == os.path.realpath("report.pdf")
    assert plan["backend"] in ("startfile", "open", "xdg-open")


def test_windows_drive_is_a_file_not_a_scheme():
    assert plan_open(r"C:\tmp\a.txt")["kind"] == "file"


def test_verb_is_carried():
    assert plan_open("report.pdf", verb="print")["verb"] == "print"


def test_rejects_bad_scheme_and_empty():
    with pytest.raises(ValueError):
        plan_open("javascript://alert(1)")
    with pytest.raises(ValueError):
        plan_open("   ")


def test_open_path_dispatches_plan_to_injected_opener():
    captured = {}

    def fake_opener(plan):
        captured.update(plan)
        return True

    assert open_path("https://x.io", opener=fake_opener) is True
    assert captured["backend"] == "webbrowser"
    assert captured["target"] == "https://x.io"


def test_open_path_returns_opener_result():
    assert open_path("report.pdf", opener=lambda plan: False) is False


# --- wiring ---------------------------------------------------------------

def test_executor_pure_plan_path():
    from je_auto_control.utils.executor.action_executor import _plan_open
    plan = _plan_open("https://example.com")
    assert plan["backend"] == "webbrowser" and plan["kind"] == "url"


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_open_path", "AC_plan_open"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_open_path", "ac_plan_open"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_open_path", "AC_plan_open"} <= specs


def test_facade_exports():
    for name in ("plan_open", "open_path"):
        assert hasattr(ac, name) and name in ac.__all__
