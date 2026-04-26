"""Tests for the input-message dispatcher (no real OS calls)."""
import pytest

from je_auto_control.utils.remote_desktop import input_dispatch
from je_auto_control.utils.remote_desktop.input_dispatch import (
    InputDispatchError, dispatch_input,
)


@pytest.fixture()
def fake_wrappers(monkeypatch):
    calls = []

    def make(name):
        def stub(*args, **kwargs):
            calls.append((name, args, kwargs))
            return ("ok", name)
        return stub

    fake = {
        name: make(name)
        for name in (
            "click_mouse", "mouse_scroll", "press_mouse", "release_mouse",
            "set_mouse_position", "press_keyboard_key", "release_keyboard_key",
            "write",
        )
    }
    monkeypatch.setattr(input_dispatch, "_import_wrappers", lambda: fake)
    return calls


def test_unknown_action_is_rejected(fake_wrappers):
    with pytest.raises(InputDispatchError):
        dispatch_input({"action": "drop_table"})
    assert fake_wrappers == []


def test_non_mapping_message_is_rejected():
    with pytest.raises(InputDispatchError):
        dispatch_input(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_ping_returns_none_without_calling_wrappers(fake_wrappers):
    assert dispatch_input({"action": "ping"}) is None
    assert fake_wrappers == []


def test_mouse_move_calls_set_mouse_position(fake_wrappers):
    dispatch_input({"action": "mouse_move", "x": 12, "y": 34})
    assert fake_wrappers == [("set_mouse_position", (12, 34), {})]


def test_mouse_click_with_coords_moves_then_clicks(fake_wrappers):
    dispatch_input({"action": "mouse_click", "x": 5, "y": 6,
                    "button": "mouse_right"})
    assert [name for name, *_ in fake_wrappers] == [
        "set_mouse_position", "click_mouse",
    ]
    assert fake_wrappers[1][1] == ("mouse_right",)


def test_mouse_click_without_coords_skips_move(fake_wrappers):
    dispatch_input({"action": "mouse_click"})
    assert [name for name, *_ in fake_wrappers] == ["click_mouse"]


def test_mouse_scroll_passes_through_amount_and_position(fake_wrappers):
    dispatch_input({"action": "mouse_scroll", "amount": -3, "x": 10, "y": 20})
    assert fake_wrappers == [("mouse_scroll", (-3, 10, 20), {})]


def test_key_press_and_release(fake_wrappers):
    dispatch_input({"action": "key_press", "keycode": "a"})
    dispatch_input({"action": "key_release", "keycode": "a"})
    assert [name for name, *_ in fake_wrappers] == [
        "press_keyboard_key", "release_keyboard_key",
    ]


def test_type_writes_text(fake_wrappers):
    dispatch_input({"action": "type", "text": "hello"})
    assert fake_wrappers == [("write", ("hello",), {})]


def test_type_rejects_non_string(fake_wrappers):
    with pytest.raises(InputDispatchError):
        dispatch_input({"action": "type", "text": 123})
    assert fake_wrappers == []
