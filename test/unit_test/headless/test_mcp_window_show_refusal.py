"""``ac_window_minimize`` / ``maximize`` / ``restore`` report a refused request.

``show_window`` answers ``False`` when the handle is no longer a window or
when Windows refused to bring an activating command's window forward. The MCP
handlers ignored that and returned the handle, so a client was told the
request had worked.

The window lookup and ``show_window`` are fakes: no real window is touched.
"""
import json
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform not in ("win32", "cygwin", "msys"),
    reason="windows_window_manage uses ctypes.WINFUNCTYPE; Win32-only.")

_TOOLS = [("ac_window_minimize", 6, "minimise"), ("ac_window_maximize", 3, "maximise"),
          ("ac_window_restore", 9, "restore")]


@pytest.fixture
def show(monkeypatch):
    """Fake window lookup and ``show_window``; ``show.answer`` is what it returns."""
    import je_auto_control.wrapper.auto_control_window as window_module
    from je_auto_control.windows.window import windows_window_manage

    class _Show:
        answer = True
        calls = []

    def fake_show(hwnd, cmd_show):
        _Show.calls.append((int(hwnd), int(cmd_show)))
        return _Show.answer

    monkeypatch.setattr(window_module, "find_window",
                        lambda title, case_sensitive=False: (456, title))
    monkeypatch.setattr(windows_window_manage, "show_window", fake_show)
    return _Show


def _tool(name):
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    return {tool.name: tool for tool in build_default_tool_registry()}[name]


@pytest.mark.parametrize("name, command, verb", _TOOLS)
def test_a_refused_show_command_is_an_error(show, name, command, verb):
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    show.answer = False
    tool = _tool(name)
    with pytest.raises(AutoControlActionException) as refused:
        tool.invoke({"title_substring": "Notepad"})
    assert show.calls == [(456, command)]
    message = str(refused.value)
    assert f"could not {verb} 'Notepad' (hwnd 456)" in message
    assert "refused" in message
    assert "gone" in message


@pytest.mark.parametrize("name, command, _verb", _TOOLS)
@pytest.mark.parametrize("answer", [True, None], ids=["succeeded", "cannot-tell"])
def test_a_show_command_that_was_not_refused_returns_the_handle(show, name, command, _verb,
                                                                 answer):
    show.answer = answer
    assert _tool(name).invoke({"title_substring": "Notepad"}) == 456
    assert show.calls == [(456, command)]


def test_the_refusal_reaches_the_client_as_a_tool_error(show):
    from je_auto_control.utils.mcp_server.server import MCPServer
    show.answer = False
    server = MCPServer(tools=[_tool("ac_window_restore")])
    reply = json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "ac_window_restore", "arguments": {"title_substring": "Notepad"}},
    })))
    result = reply["result"]
    assert result["isError"] is True
    assert "could not restore 'Notepad'" in result["content"][0]["text"]


def test_a_window_that_does_not_match_is_still_its_own_error(show, monkeypatch):
    import je_auto_control.wrapper.auto_control_window as window_module
    monkeypatch.setattr(window_module, "find_window", lambda title, case_sensitive=False: None)
    tool = _tool("ac_window_minimize")
    with pytest.raises(ValueError, match="no window matches"):
        tool.invoke({"title_substring": "Nope"})
    assert show.calls == []
