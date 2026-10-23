"""Tests for the je_auto_control_mcp CLI introspection flags."""
import io
import json
import sys

from je_auto_control.utils.mcp_server.__main__ import main


def _capture(monkeypatch, argv):
    """Run ``main(argv)`` for its side effect and return captured stdout."""
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    main(argv)
    return buffer.getvalue()


def test_list_tools_emits_json_and_exits(monkeypatch):
    output = _capture(monkeypatch, ["--list-tools"])
    descriptors = json.loads(output)
    assert isinstance(descriptors, list)
    assert descriptors
    assert all("name" in d and "inputSchema" in d for d in descriptors)


def test_list_tools_with_read_only_drops_destructive(monkeypatch):
    output = _capture(monkeypatch, ["--list-tools", "--read-only"])
    descriptors = json.loads(output)
    names = {d["name"] for d in descriptors}
    assert "ac_click_mouse" not in names
    assert "ac_get_mouse_position" in names


def test_search_and_single_schema_flags_do_not_start_the_server(monkeypatch):
    results = json.loads(_capture(monkeypatch, ["--search-tools", "ac_mcp_tool_schema", "--limit", "1"]))
    assert len(results) == 1 and results[0]["name"] == "ac_mcp_tool_schema"
    assert "inputSchema" not in results[0]
    schema = json.loads(_capture(monkeypatch, ["--tool-schema", "ac_mcp_tool_schema"]))
    assert schema["name"] == "ac_mcp_tool_schema" and "inputSchema" in schema


def test_list_resources_emits_json(monkeypatch):
    output = _capture(monkeypatch, ["--list-resources"])
    descriptors = json.loads(output)
    assert isinstance(descriptors, list)
    uris = {d["uri"] for d in descriptors}
    assert "autocontrol://history" in uris
    assert "autocontrol://commands" in uris


def test_list_prompts_emits_json(monkeypatch):
    output = _capture(monkeypatch, ["--list-prompts"])
    descriptors = json.loads(output)
    assert isinstance(descriptors, list)
    names = {d["name"] for d in descriptors}
    assert {"automate_ui_task", "find_widget"}.issubset(names)


def test_no_flags_starts_stdio_server(monkeypatch):
    """With no flags, main() should dispatch to start_mcp_stdio_server."""
    started = []
    import je_auto_control.utils.mcp_server.__main__ as cli_mod
    monkeypatch.setattr(cli_mod, "start_mcp_stdio_server",
                        lambda read_only=None: started.append(read_only))
    main([])
    main(["--read-only"])
    # None leaves JE_AUTOCONTROL_MCP_READONLY in charge; the flag forces it on.
    assert started == [None, True]
