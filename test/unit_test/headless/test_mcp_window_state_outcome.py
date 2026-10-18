"""Window-state MCP tools return a handle only after the backend accepts them."""
import json
import sys
from types import SimpleNamespace

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry

TOOLS = (("ac_window_minimize", 6), ("ac_window_maximize", 3), ("ac_window_restore", 9))


@pytest.fixture
def backend(monkeypatch):
    from je_auto_control.windows import window as package
    from je_auto_control.wrapper import auto_control_window

    calls = []
    accepted = [True]

    def show(hwnd, command):
        calls.append((hwnd, command))
        return accepted[0]

    # The package itself has no Win32 imports. Replace its module attribute,
    # so these contract tests run on Linux/macOS without loading a Windows DLL.
    monkeypatch.setattr(package, "windows_window_manage", SimpleNamespace(show_window=show), raising=False)
    monkeypatch.setattr(auto_control_window, "find_window", lambda title, case_sensitive=False: (123, title))
    return accepted, calls


@pytest.mark.parametrize("name,command", TOOLS)
def test_accepted_window_state_returns_the_original_handle(name, command, backend):
    _, calls = backend
    tool = next(tool for tool in build_default_tool_registry() if tool.name == name)
    assert tool.invoke({"title_substring": "Test window", "case_sensitive": True}) == 123
    assert calls == [(123, command)]


@pytest.mark.parametrize("name,command", TOOLS)
def test_refused_window_state_raises_a_framework_error(name, command, backend):
    accepted, calls = backend
    accepted[0] = False
    tool = next(tool for tool in build_default_tool_registry() if tool.name == name)
    with pytest.raises(AutoControlException, match="could not apply"):
        tool.invoke({"title_substring": "Test window"})
    assert calls == [(123, command)]


@pytest.mark.parametrize("name,_command", TOOLS)
def test_jsonrpc_reports_backend_refusal_as_tool_error(name, _command, backend):
    accepted, _ = backend
    accepted[0] = False
    tool = next(tool for tool in build_default_tool_registry() if tool.name == name)
    server = MCPServer(tools=[tool])
    reply = json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": {"title_substring": "Test window"}},
    })))
    assert reply["result"]["isError"] is True
    assert "could not apply" in reply["result"]["content"][0]["text"]


@pytest.mark.skipif(sys.platform != "win32", reason="real Win32 adapter, with controlled user32 calls")
@pytest.mark.parametrize("name,command", TOOLS)
def test_previous_visibility_zero_is_not_mistaken_for_backend_failure(name, command, monkeypatch):
    from je_auto_control.windows.window import windows_window_manage
    from je_auto_control.wrapper import auto_control_window

    monkeypatch.setattr(windows_window_manage, "_user32", SimpleNamespace(
        IsWindow=lambda hwnd: True,
        ShowWindow=lambda hwnd, flag: 0,
        SetForegroundWindow=lambda hwnd: True,
    ))
    monkeypatch.setattr(auto_control_window, "find_window", lambda *_args, **_kwargs: (123, "Test"))
    tool = next(tool for tool in build_default_tool_registry() if tool.name == name)
    assert tool.invoke({"title_substring": "Test"}) == 123
