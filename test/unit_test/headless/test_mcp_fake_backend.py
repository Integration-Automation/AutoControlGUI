"""Tests for the fake backend used in CI smoke runs."""
import pytest

from je_auto_control.utils.mcp_server.fake_backend import (
    fake_state, install_fake_backend, maybe_install_from_env,
    reset_fake_state, uninstall_fake_backend,
)
from je_auto_control.utils.mcp_server.tools import (
    build_default_tool_registry,
)


@pytest.fixture()
def fake_backend():
    """Install the fake backend for the duration of the test."""
    reset_fake_state()
    install_fake_backend()
    yield
    uninstall_fake_backend()
    reset_fake_state()


def test_set_mouse_position_records_in_fake_state(fake_backend):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    by_name["ac_set_mouse_position"].invoke({"x": 100, "y": 200})
    assert fake_state().cursor == (100, 200)
    assert ("set_position", 100, 200) in fake_state().mouse_actions


def test_click_mouse_records_button_and_coords(fake_backend):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    by_name["ac_click_mouse"].invoke({
        "mouse_keycode": "mouse_left", "x": 50, "y": 60,
    })
    assert ("click", "mouse_left", 50, 60) in fake_state().mouse_actions


def test_clipboard_round_trip_via_fake_backend(fake_backend):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    by_name["ac_set_clipboard"].invoke({"text": "hi"})
    assert by_name["ac_get_clipboard"].invoke({}) == "hi"
    assert fake_state().clipboard_text == "hi"


def test_type_text_appends_to_typed_history(fake_backend):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    by_name["ac_type_text"].invoke({"text": "hello"})
    assert "hello" in fake_state().typed_text


def test_install_is_idempotent(fake_backend):
    install_fake_backend()
    install_fake_backend()
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    by_name["ac_set_mouse_position"].invoke({"x": 1, "y": 2})
    assert fake_state().cursor == (1, 2)


def test_maybe_install_from_env_respects_flag(monkeypatch):
    reset_fake_state()
    uninstall_fake_backend()
    monkeypatch.setenv("JE_AUTOCONTROL_FAKE_BACKEND", "1")
    try:
        assert maybe_install_from_env() is True
        from je_auto_control.wrapper import auto_control_mouse as mouse_module
        moved = mouse_module.set_mouse_position(7, 9)
        assert moved == (7, 9)
        assert fake_state().cursor == (7, 9)
    finally:
        uninstall_fake_backend()


def test_maybe_install_from_env_skips_when_unset(monkeypatch):
    monkeypatch.delenv("JE_AUTOCONTROL_FAKE_BACKEND", raising=False)
    assert maybe_install_from_env() is False
