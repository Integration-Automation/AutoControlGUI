"""Headless tests for the process-doc (SOP) generator. Pure stdlib."""
import je_auto_control as ac
from je_auto_control.utils.process_doc import (
    describe_step, generate_sop, write_sop)


def test_describe_step_uses_verb_and_detail():
    assert describe_step("AC_write", {"write_string": "hello"}) == \
        "Type text (write_string: hello)"
    assert describe_step("AC_click_mouse", {}) == "Click the mouse"
    assert describe_step("AC_custom_thing", {}) == "custom thing"


def test_generate_sop_structure_and_html():
    actions = [
        ["AC_set_mouse_position", {"x": 10, "y": 20}],
        ["AC_click_mouse", {}],
        ["AC_write", {"write_string": "<b>hi</b>"}],
    ]
    doc = generate_sop(actions, title="Login Flow")
    assert doc["title"] == "Login Flow" and doc["step_count"] == 3
    assert [s["n"] for s in doc["steps"]] == [1, 2, 3]
    assert doc["steps"][1]["description"] == "Click the mouse"
    # HTML escapes user content and is well-formed
    assert "&lt;b&gt;hi&lt;/b&gt;" in doc["html"]
    assert doc["html"].startswith("<!doctype html>")
    assert "<h1>Login Flow</h1>" in doc["html"]


def test_write_sop_writes_file(tmp_path):
    path = write_sop([["AC_click_mouse", {}]], str(tmp_path / "sop.html"),
                     title="P")
    assert open(path, encoding="utf-8").read().count("<li>") == 1


# --- wiring ---------------------------------------------------------------

def test_executor_wiring(tmp_path):
    rec = ac.execute_action([["AC_generate_sop", {
        "actions": [["AC_click_mouse", {}]], "title": "T"}]])
    assert any("step_count" in str(v) for v in rec.values())
    assert "AC_generate_sop" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    assert "ac_generate_sop" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_generate_sop" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("describe_step", "generate_sop", "write_sop"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
