"""Arguments that are a path only sometimes are held to the roots when they are one.

``"format": "path"`` marks an argument that is always a file. Five arguments
are a path on some calls and something else on others -- ``target`` of
``ac_open_path`` / ``ac_plan_open`` (path or URL), of ``ac_file_association``
(path or extension) and of ``ac_act_in_view`` (template path or text), and
``path`` of ``ac_handle_file_dialog`` -- so they carried no annotation and the
configured roots never saw them: with roots set, ``ac_open_path`` still opened
any file on the machine.

They are marked ``"format": "path-or-other"``: a value that looks like an
absolute path, or that names something that exists, is checked like a path;
anything else passes untouched.

**No real handler runs here.** The real schemas are used, with every handler
replaced by a recorder -- ``ac_open_path`` would otherwise launch an
application and ``ac_handle_file_dialog`` would type into one.
"""
import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

from je_auto_control.utils.mcp_server._argument_policy import (
    PATH_OR_OTHER_FORMAT, ArgumentPolicy, looks_like_path,
)
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.path_guard.policy import (
    MCP_CLIENT_ROOTS_ENV, MCP_PATH_ROOTS_ENV,
)

_MARKED = {
    "ac_open_path": "target", "ac_plan_open": "target", "ac_file_association": "target",
    "ac_act_in_view": "target", "ac_handle_file_dialog": "path",
}
_UNMARKED = {"ac_launch_process": "argv", "ac_shell": "command"}


@pytest.fixture(autouse=True)
def _no_ambient_policy(monkeypatch):
    for name in (MCP_PATH_ROOTS_ENV, MCP_CLIENT_ROOTS_ENV, "JE_AUTOCONTROL_MCP_ENV_REF_ALLOW",
                 "JE_AUTOCONTROL_MCP_READONLY", "JE_AUTOCONTROL_MCP_TOOL_MODE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def registry():
    return {tool.name: tool
            for tool in build_default_tool_registry(read_only=False, aliases=False)}


@pytest.fixture()
def harness(registry, tmp_path, monkeypatch):
    """A server over the real schemas with recording handlers, rooted at ``root``."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "inside.txt").write_text("in", encoding="utf-8")
    (outside / "secret.txt").write_text("out", encoding="utf-8")
    monkeypatch.setenv(MCP_PATH_ROOTS_ENV, str(root))
    monkeypatch.chdir(root)
    calls = []

    def recorder(name):
        def handler(**arguments):
            calls.append((name, arguments))
            return {"ran": name}
        return handler
    tools = [dataclasses.replace(registry[name], handler=recorder(name))
             for name in list(_MARKED) + list(_UNMARKED)]
    server = MCPServer(tools=tools)

    def call(name, **arguments):
        line = server.handle_line(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}))
        result = json.loads(line)["result"]
        return result["isError"], "".join(block.get("text", "") for block in result["content"])
    return type("Harness", (), {"call": staticmethod(call), "calls": calls, "root": root,
                                "outside": outside})


# --- the annotation ----------------------------------------------------------------------------

@pytest.mark.parametrize("tool, argument", sorted(_MARKED.items()))
def test_the_sometimes_a_path_arguments_are_marked(registry, tool, argument):
    assert registry[tool].input_schema["properties"][argument]["format"] == PATH_OR_OTHER_FORMAT


@pytest.mark.parametrize("tool, argument", sorted(_UNMARKED.items()))
def test_shell_arguments_are_deliberately_left_alone(registry, tool, argument):
    """A command line is a program: no reading of it as a path would confine it."""
    assert "format" not in registry[tool].input_schema["properties"][argument]


def test_the_marked_tools_are_found_as_path_taking_by_the_search_index(registry):
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    index = ToolIndex(registry[name] for name in _MARKED)
    for name in _MARKED:
        rows = [row for row in index.search(name, limit=10) if row.name == name]
        assert rows and rows[0].takes_paths, name


# --- what counts as a path ---------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "/etc/passwd", "~/notes.txt", "~", "\\\\server\\share\\x", "//server/share/x",
    "C:\\Windows\\win.ini", "c:/Windows/win.ini", "\\Windows\\win.ini",
    "file:///etc/passwd", "FILE:///C:/Windows/win.ini", "file://server/share/x",
])
def test_absolute_looking_values_are_paths_whether_or_not_they_exist(value):
    assert looks_like_path(value)


@pytest.mark.parametrize("value", [
    "https://example.test/a/b", "mailto:someone@example.test", ".txt", "txt", "Save",
    "Q: is this a drive?", "OK", "", "docs/readme-that-does-not-exist.md", "x:y",
])
def test_other_values_are_not_paths_unless_they_exist(value, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not looks_like_path(value)


def test_a_relative_name_that_exists_is_a_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Save").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    assert looks_like_path("Save") and looks_like_path("sub") and looks_like_path("./Save")
    assert not looks_like_path("Open")


# --- through a server ----------------------------------------------------------------------------

@pytest.mark.parametrize("tool, argument", sorted(_MARKED.items()))
def test_a_path_outside_the_roots_is_refused_and_the_handler_never_runs(harness, tool, argument):
    is_error, text = harness.call(tool, **{argument: str(harness.outside / "secret.txt")})
    assert is_error and f"Invalid arguments for {tool}" in text and "outside the allowed" in text
    assert harness.calls == []


@pytest.mark.parametrize("tool, argument", sorted(_MARKED.items()))
def test_a_path_inside_the_roots_reaches_the_handler_unchanged(harness, tool, argument):
    inside = str(harness.root / "inside.txt")
    is_error, _text = harness.call(tool, **{argument: inside})
    assert not is_error
    assert harness.calls == [(tool, {argument: inside})]


@pytest.mark.parametrize("escape", ["..", "..\\..", "../outside/secret.txt"])
def test_a_relative_path_that_exists_outside_the_roots_is_refused(harness, escape):
    is_error, text = harness.call("ac_open_path", target=escape.replace("\\", os.sep))
    assert is_error and "outside the allowed" in text and harness.calls == []


def test_a_file_url_is_judged_by_the_file_it_names(harness):
    outside = (harness.outside / "secret.txt").as_uri()
    is_error, text = harness.call("ac_open_path", target=outside)
    assert is_error and "outside the allowed" in text and harness.calls == []
    inside = (harness.root / "inside.txt").as_uri()
    assert harness.call("ac_open_path", target=inside)[0] is False
    assert harness.calls == [("ac_open_path", {"target": inside})]


@pytest.mark.parametrize("tool, argument, value", [
    ("ac_open_path", "target", "https://example.test/docs"),
    ("ac_plan_open", "target", "mailto:someone@example.test"),
    ("ac_file_association", "target", ".txt"),
    ("ac_file_association", "target", "txt"),
    ("ac_act_in_view", "target", "Submit order"),
    ("ac_handle_file_dialog", "path", "report-2026.xlsx"),
])
def test_a_value_that_is_not_a_path_passes_untouched(harness, tool, argument, value):
    is_error, _text = harness.call(tool, **{argument: value})
    assert not is_error
    assert harness.calls == [(tool, {argument: value})]


def test_a_text_target_that_names_an_existing_file_inside_the_roots_is_not_rewritten(harness):
    """Checked, not canonicalised: for kind=text the value is the text to look for."""
    assert harness.call("ac_act_in_view", target="inside.txt", kind="text")[0] is False
    assert harness.calls == [("ac_act_in_view", {"target": "inside.txt", "kind": "text"})]


def test_shell_arguments_are_not_judged(harness):
    secret = str(harness.outside / "secret.txt")
    assert harness.call("ac_launch_process", argv=["viewer", secret])[0] is False
    assert harness.call("ac_shell", command=f"viewer {secret}")[0] is False
    assert [name for name, _arguments in harness.calls] == ["ac_launch_process", "ac_shell"]


def test_without_roots_nothing_is_judged(registry, tmp_path, monkeypatch):
    calls = []
    tool = dataclasses.replace(registry["ac_open_path"],
                               handler=lambda **arguments: calls.append(arguments) or {"ok": 1})
    server = MCPServer(tools=[tool])
    assert not server.argument_policy.enabled
    line = server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "ac_open_path", "arguments": {"target": str(tmp_path / "any.txt")}}}))
    assert json.loads(line)["result"]["isError"] is False and len(calls) == 1


# --- the policy on its own --------------------------------------------------------------------------

_SCHEMA = {"type": "object", "properties": {
    "target": {"type": "string", "format": PATH_OR_OTHER_FORMAT},
    "many": {"type": "array", "items": {"type": "string", "format": PATH_OR_OTHER_FORMAT}}}}


def test_the_policy_checks_nested_values_and_returns_them_as_given(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    policy = ArgumentPolicy(PathPolicy([root]))
    inside = str(root / "a.png")
    arguments = {"target": inside, "many": ["Save", "https://example.test", inside]}
    assert policy.apply("tool", _SCHEMA, arguments) == arguments
    with pytest.raises(PathNotAllowedError, match=r"tool \$\.many\[1\]"):
        policy.apply("tool", _SCHEMA, {"many": [inside, str(tmp_path / "elsewhere.png")]})


@pytest.mark.skipif(sys.platform != "win32", reason="drive letters and UNC are Windows paths")
def test_another_drive_and_a_unc_share_are_outside_the_roots(tmp_path):
    policy = ArgumentPolicy(PathPolicy([tmp_path]))
    other = "D:\\" if Path(tmp_path).drive.upper() != "D:" else "E:\\"
    for value in (other + "secret.txt", "\\\\server\\share\\secret.txt",
                  "file://server/share/secret.txt"):
        with pytest.raises(PathNotAllowedError):
            policy.apply("tool", _SCHEMA, {"target": value})
