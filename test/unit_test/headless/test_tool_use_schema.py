"""Phase 7.8: tool-use schema exporter tests."""
from unittest.mock import patch

import pytest

from je_auto_control.utils.tool_use_schema import (
    export_anthropic_tools, export_openai_tools, infer_parameters,
    run_tool_call,
)


def test_anthropic_tools_include_ac_commands():
    tools = export_anthropic_tools()
    assert len(tools) > 30, "expected the executor to expose many AC_* commands"
    names = {t["name"] for t in tools}
    assert "AC_click_mouse" in names
    assert "AC_screenshot" in names
    for tool in tools:
        # Anthropic schema requires name, description, input_schema.
        assert set(tool.keys()) >= {"name", "description", "input_schema"}
        assert tool["input_schema"]["type"] == "object"


def test_openai_tools_use_function_calling_format():
    tools = export_openai_tools()
    for tool in tools:
        assert tool["type"] == "function"
        assert "function" in tool
        fn = tool["function"]
        assert {"name", "description", "parameters"}.issubset(fn.keys())
        assert fn["parameters"]["type"] == "object"


def test_only_filter_limits_exported_tools():
    subset = export_anthropic_tools(only=["AC_screenshot", "AC_click_mouse"])
    names = {t["name"] for t in subset}
    assert names == {"AC_screenshot", "AC_click_mouse"}


def test_infer_parameters_handles_no_signature():
    """If inspect.signature fails (e.g. a C-extension callable), fall back."""

    class _Opaque:
        pass

    props, required = infer_parameters(_Opaque)
    # No introspection possible → empty schema, no required fields.
    assert isinstance(props, dict)
    assert required == []


def test_infer_parameters_required_vs_optional():
    def sample(needed: int, optional: str = "hi") -> None:
        return None

    props, required = infer_parameters(sample)
    assert required == ["needed"]
    assert props["needed"]["type"] == "integer"
    assert props["optional"]["type"] == "string"
    assert props["optional"]["default"] == "hi"


def test_run_tool_call_dispatches_through_executor():
    """A successful tool_use forwards kwargs to the AC command."""
    captured = {}

    def fake_screenshot(file_path=None, screen_region=None):
        captured["called"] = True
        captured["file_path"] = file_path
        return {"ok": True}

    with patch(
        "je_auto_control.utils.executor.action_executor.executor.event_dict",
        {"AC_screenshot": fake_screenshot},
    ):
        # "/tmp/x.png" is just a string passed to the fake; no FS access.
        result = run_tool_call(
            "AC_screenshot",
            {"file_path": "/tmp/x.png"},  # NOSONAR python:S5443  # reason: literal arg, fake handler never writes
        )
    assert result == {"ok": True}
    assert captured["called"] is True
    assert captured["file_path"] == "/tmp/x.png"  # NOSONAR python:S5443  # reason: comparing literal echoed by the fake


def test_run_tool_call_rejects_unknown_command():
    with pytest.raises(ValueError, match="unknown AC command"):
        run_tool_call("AC_never_real", {})


def test_run_tool_call_accepts_empty_arguments():
    seen = []

    def noop():
        seen.append("ran")
        return "done"

    with patch(
        "je_auto_control.utils.executor.action_executor.executor.event_dict",
        {"AC_noop": noop},
    ):
        assert run_tool_call("AC_noop", {}) == "done"
        assert run_tool_call("AC_noop", None) == "done"  # type: ignore[arg-type]
    assert seen == ["ran", "ran"]


def test_anthropic_tools_alphabetically_sorted():
    tools = export_anthropic_tools()
    names = [t["name"] for t in tools]
    assert names == sorted(names)
