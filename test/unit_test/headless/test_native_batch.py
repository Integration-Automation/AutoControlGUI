"""Headless tests for the native-authoring batch: element repository
(object repository) and the flow step debugger / tracer. Pure stdlib;
no Qt imports."""
from types import SimpleNamespace

import pytest

import je_auto_control as ac
from je_auto_control.utils.element_repository import ElementRepository
from je_auto_control.utils.flow_debugger import FlowDebugger, trace_actions


# --- element repository ---------------------------------------------------

def test_repo_crud_and_persistence(tmp_path):
    path = str(tmp_path / "r.json")
    repo = ElementRepository(path)
    repo.save("login.submit", name="Submit", role="button")
    assert repo.get("login.submit") == {"name": "Submit", "role": "button"}
    assert repo.keys() == ["login.submit"]
    # reload from disk in a fresh instance
    again = ElementRepository(path)
    assert again.get("login.submit") == {"name": "Submit", "role": "button"}
    assert again.remove("login.submit") is True
    assert again.remove("login.submit") is False
    assert again.keys() == []


def test_repo_requires_a_filter(tmp_path):
    repo = ElementRepository(str(tmp_path / "r.json"))
    with pytest.raises(ValueError):
        repo.save("empty")


def test_repo_resolve_and_click(tmp_path, monkeypatch):
    import je_auto_control.utils.accessibility as a11y
    repo = ElementRepository(str(tmp_path / "r.json"))
    repo.save("btn", name="OK", role="button")
    element = SimpleNamespace(name="OK", role="button", center=(10, 20))
    monkeypatch.setattr(a11y, "find_accessibility_element",
                        lambda **kw: element if kw.get("name") == "OK" else None)
    monkeypatch.setattr(a11y, "click_accessibility_element",
                        lambda **kw: kw.get("name") == "OK")
    assert repo.find_info("btn") == {
        "found": True, "name": "OK", "role": "button", "center": [10, 20]}
    assert repo.click("btn") is True
    with pytest.raises(KeyError):
        repo.find_info("missing")


# --- flow debugger --------------------------------------------------------

def _vars_program():
    return [["AC_set_var", {"name": "a", "value": 1}],
            ["AC_set_var", {"name": "b", "value": 2}],
            ["AC_inc_var", {"name": "a", "by": 10}]]


def test_debugger_step_and_variables():
    dbg = FlowDebugger(_vars_program())
    step = dbg.step()
    assert step["index"] == 0 and step["command"] == "AC_set_var"
    assert dbg.variables()["a"] == 1
    dbg.run_to_end()
    assert dbg.finished
    assert dbg.variables() == {"a": 11, "b": 2}


def test_debugger_breakpoint_pauses_then_resumes():
    dbg = FlowDebugger(_vars_program(), breakpoints=[2])
    first = dbg.continue_()
    assert [s["index"] for s in first] == [0, 1]   # paused before index 2
    assert dbg.index == 2 and not dbg.finished
    rest = dbg.continue_()
    assert [s["index"] for s in rest] == [2]
    assert dbg.finished


def test_debugger_reset():
    dbg = FlowDebugger(_vars_program())
    dbg.run_to_end()
    dbg.reset()
    assert dbg.index == 0 and dbg.variables() == {}


def test_trace_actions_dry_run_and_real():
    real = trace_actions(_vars_program())
    assert [t["command"] for t in real] == \
        ["AC_set_var", "AC_set_var", "AC_inc_var"]
    planned = trace_actions(_vars_program(), dry_run=True)
    assert len(planned) == 3
    assert all("not executed" in str(t["result"]) for t in planned)


# --- wiring ---------------------------------------------------------------

def test_executor_wiring(tmp_path):
    path = str(tmp_path / "repo.json")
    ac.execute_action([["AC_element_save",
                        {"path": path, "key": "ok", "name": "OK"}]])
    rec = ac.execute_action([["AC_element_list", {"path": path}]])
    assert any("ok" in str(v) for v in rec.values())
    trace_rec = ac.execute_action(
        [["AC_debug_trace",
          {"actions": [["AC_set_var", {"name": "x", "value": 1}]],
           "dry_run": True}]])
    assert any("trace" in str(v) for v in trace_rec.values())
    known = ac.executor.known_commands()
    assert {"AC_element_save", "AC_element_find", "AC_element_click",
            "AC_element_remove", "AC_element_list", "AC_debug_trace"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_element_save", "ac_element_find", "ac_element_click",
            "ac_element_remove", "ac_element_list", "ac_debug_trace"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_element_save", "AC_element_find", "AC_element_click",
            "AC_element_remove", "AC_element_list", "AC_debug_trace"} <= cmds


def test_facade_exports():
    for attr in ("ElementRepository", "FlowDebugger", "trace_actions"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
