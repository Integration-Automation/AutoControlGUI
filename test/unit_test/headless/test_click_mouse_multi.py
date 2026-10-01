"""``click_mouse(clicks=, interval=)``: multi-click in one call.

The backend and the clock are stand-ins, so no real click is sent and nothing
sleeps. No Qt imports.
"""
import math
import sys
import types

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlMouseException
from je_auto_control.wrapper import auto_control_mouse


class _Backend:
    """Records each backend click; mirrors the Windows / X11 signature."""

    def __init__(self):
        self.clicks = []

    def click_mouse(self, mouse_keycode, x=None, y=None):
        self.clicks.append((mouse_keycode, x, y))


@pytest.fixture()
def env(monkeypatch):
    backend = _Backend()
    sleeps = []
    records = []
    monkeypatch.setattr(auto_control_mouse, "mouse", backend)
    monkeypatch.setattr(auto_control_mouse, "time", types.SimpleNamespace(sleep=sleeps.append))
    monkeypatch.setattr(auto_control_mouse, "mouse_keys_table", {"mouse_left": 1, "mouse_right": 2})
    monkeypatch.setattr(auto_control_mouse, "record_action_to_list",
                        lambda name, param, error=None: records.append((name, dict(param or {}), error)))
    monkeypatch.setattr(auto_control_mouse, "get_mouse_position", lambda: (7, 8))
    monkeypatch.setattr(sys, "platform", "win32")
    return types.SimpleNamespace(backend=backend, sleeps=sleeps, records=records)


def test_the_default_is_one_click_with_no_pause_and_the_old_record(env):
    assert auto_control_mouse.click_mouse("mouse_left", 10, 20) == (1, 10, 20)
    assert env.backend.clicks == [(1, 10, 20)]
    assert env.sleeps == []
    assert env.records == [("click_mouse", {"keycode": "mouse_left", "x": 10, "y": 20}, None)]


def test_a_double_click_is_two_clicks_on_one_point_with_one_pause(env):
    auto_control_mouse.click_mouse("mouse_left", 10, 20, clicks=2, interval=0.06)
    assert env.backend.clicks == [(1, 10, 20), (1, 10, 20)]
    assert env.sleeps == [0.06]
    name, param, error = env.records[-1]
    assert (name, error) == ("click_mouse", None)
    assert param["clicks"] == 2 and param["interval"] == 0.06


def test_no_pause_between_clicks_when_interval_is_zero(env):
    auto_control_mouse.click_mouse("mouse_right", clicks=3)
    assert env.backend.clicks == [(2, 7, 8)] * 3          # the cursor, resolved once
    assert env.sleeps == []


def test_an_integer_string_is_accepted(env):
    auto_control_mouse.click_mouse("mouse_left", 1, 2, clicks="2")
    assert len(env.backend.clicks) == 2


def test_macos_binds_every_click_xy_first(env, monkeypatch):
    calls = []
    monkeypatch.setattr(auto_control_mouse, "mouse", types.SimpleNamespace(
        click_mouse=lambda x, y, mouse_button: calls.append((x, y, mouse_button))))
    monkeypatch.setattr(sys, "platform", "darwin")
    auto_control_mouse.click_mouse("mouse_left", 5, 6, clicks=2)
    assert calls == [(5, 6, 1), (5, 6, 1)]


@pytest.mark.parametrize("clicks", [0, -1, True, False, 1.5, 2.0, "x", None])
def test_an_invalid_click_count_clicks_nothing(env, clicks):
    with pytest.raises(AutoControlMouseException):
        auto_control_mouse.click_mouse("mouse_left", 1, 2, clicks=clicks)
    assert env.backend.clicks == []


@pytest.mark.parametrize("interval", [-0.1, math.nan, math.inf, "soon", None])
def test_an_invalid_interval_clicks_nothing(env, interval):
    with pytest.raises(AutoControlMouseException):
        auto_control_mouse.click_mouse("mouse_left", 1, 2, clicks=2, interval=interval)
    assert env.backend.clicks == []
    assert env.records[-1][2] is not None                  # the failure is recorded


def test_the_executor_command_forwards_both_parameters(env):
    from je_auto_control.utils.executor.action_executor import executor
    executor.event_dict["AC_click_mouse"]("mouse_left", 3, 4, clicks=2, interval=0.05)
    assert env.backend.clicks == [(1, 3, 4), (1, 3, 4)]
    assert env.sleeps == [0.05]


def test_the_mcp_handler_forwards_both_parameters(env):
    from je_auto_control.utils.mcp_server.tools import _handlers_input
    assert _handlers_input.click_mouse("mouse_left", 3, 4, clicks=2, interval=0.05) == [1, 3, 4]
    assert len(env.backend.clicks) == 2


def test_the_mcp_fake_backend_records_each_click():
    from je_auto_control.utils.mcp_server import fake_backend
    from je_auto_control.utils.mcp_server.tools import _handlers_input
    fake_backend.reset_fake_state()
    fake_backend.install_fake_backend()
    try:
        _handlers_input.click_mouse("mouse_left", 3, 4, clicks=2)
        assert fake_backend.fake_state().mouse_actions == [("click", "mouse_left", 3, 4)] * 2
    finally:
        fake_backend.uninstall_fake_backend()


def test_the_mcp_tool_and_script_builder_declare_both_parameters():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    tool = next(t for t in build_default_tool_registry() if t.name == "ac_click_mouse")
    assert {"clicks", "interval"} <= set(tool.input_schema["properties"])
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    spec = next(s for s in _build_specs() if s.command == "AC_click_mouse")
    assert {"clicks", "interval"} <= {field.name for field in spec.fields}
