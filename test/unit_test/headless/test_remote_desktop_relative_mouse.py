"""Phase 2.2: relative mouse dispatch tests."""
from unittest import mock

import pytest

from je_auto_control.utils.remote_desktop.input_dispatch import (
    InputDispatchError, _ALLOWED_ACTIONS, dispatch_input,
)


def test_relative_mouse_in_allowlist():
    assert "mouse_move_relative" in _ALLOWED_ACTIONS


def test_dispatch_mouse_move_relative_adds_delta(monkeypatch):
    """``dx`` / ``dy`` get added to the current cursor position."""
    fake = {
        "get_mouse_position": mock.Mock(return_value=(100, 200)),
        "set_mouse_position": mock.Mock(),
        "click_mouse": mock.Mock(),
        "mouse_scroll": mock.Mock(),
        "press_mouse": mock.Mock(),
        "release_mouse": mock.Mock(),
        "press_keyboard_key": mock.Mock(),
        "release_keyboard_key": mock.Mock(),
        "write": mock.Mock(),
    }
    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.input_dispatch._import_wrappers",
        lambda: fake,
    )
    dispatch_input({"action": "mouse_move_relative", "dx": 5, "dy": -3})
    fake["set_mouse_position"].assert_called_once_with(105, 197)


def test_dispatch_relative_with_no_dxdy_holds_still(monkeypatch):
    """Defaulted deltas of 0 leave the cursor exactly where it was."""
    fake = {
        "get_mouse_position": mock.Mock(return_value=(50, 60)),
        "set_mouse_position": mock.Mock(),
        "click_mouse": mock.Mock(),
        "mouse_scroll": mock.Mock(),
        "press_mouse": mock.Mock(),
        "release_mouse": mock.Mock(),
        "press_keyboard_key": mock.Mock(),
        "release_keyboard_key": mock.Mock(),
        "write": mock.Mock(),
    }
    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.input_dispatch._import_wrappers",
        lambda: fake,
    )
    dispatch_input({"action": "mouse_move_relative"})
    fake["set_mouse_position"].assert_called_once_with(50, 60)


def test_dispatch_relative_raises_when_position_unreadable(monkeypatch):
    fake = {
        "get_mouse_position": mock.Mock(return_value=None),
        "set_mouse_position": mock.Mock(),
        "click_mouse": mock.Mock(),
        "mouse_scroll": mock.Mock(),
        "press_mouse": mock.Mock(),
        "release_mouse": mock.Mock(),
        "press_keyboard_key": mock.Mock(),
        "release_keyboard_key": mock.Mock(),
        "write": mock.Mock(),
    }
    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.input_dispatch._import_wrappers",
        lambda: fake,
    )
    with pytest.raises(InputDispatchError):
        dispatch_input({"action": "mouse_move_relative", "dx": 1, "dy": 1})
