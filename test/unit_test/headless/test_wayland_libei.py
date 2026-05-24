"""Tests for the libei backend selector + ctypes binding."""
from unittest.mock import MagicMock

import pytest

from je_auto_control.linux_wayland import (
    LibeiBackend, LibeiUnavailable, get_default_backend,
    select_input_backend,
)
from je_auto_control.linux_wayland import libei as libei_mod
from je_auto_control.linux_wayland import (
    _select_input as select_mod,
)


def _fake_symbols() -> object:
    """Build a stand-in for :class:`_LibeiSymbols` we can introspect."""
    symbols = MagicMock()
    symbols.ei_new_sender = MagicMock(return_value=0xDEADBEEF)
    symbols.ei_setup_backend_socket = MagicMock(return_value=0)
    symbols.ei_device_keyboard_key = MagicMock()
    symbols.ei_device_pointer_motion_absolute = MagicMock()
    symbols.ei_device_button_button = MagicMock()
    symbols.ei_device_scroll = MagicMock()
    symbols.ei_unref = MagicMock()
    return symbols


# === Selector =============================================================

def test_select_input_backend_defaults_to_cli_when_libei_absent(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: False)
    assert select_input_backend({}) == "cli"


def test_select_input_backend_picks_libei_when_loadable(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: True)
    assert select_input_backend({}) == "libei"


def test_select_input_backend_honours_cli_override(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: True)
    assert select_input_backend({
        "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND": "cli",
    }) == "cli"


def test_select_input_backend_force_libei_raises_without_libei(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: False)
    with pytest.raises(RuntimeError, match="libei"):
        select_input_backend({
            "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND": "libei",
        })


def test_select_input_backend_invalid_override_treated_as_auto(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: False)
    assert select_input_backend({
        "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND": "garbage",
    }) == "cli"


# === LibeiBackend (mocked) ================================================

def test_backend_reports_unavailable_when_symbols_missing():
    backend = LibeiBackend(symbols=None)
    assert backend.is_available is False
    with pytest.raises(LibeiUnavailable):
        backend.connect()


def test_backend_connect_calls_new_sender_and_setup_socket():
    symbols = _fake_symbols()
    backend = LibeiBackend(symbols=symbols)
    backend.connect(socket_path=b"/tmp/eis-test")
    symbols.ei_new_sender.assert_called_once_with(b"je_auto_control")
    symbols.ei_setup_backend_socket.assert_called_once_with(
        0xDEADBEEF, b"/tmp/eis-test",
    )


def test_backend_connect_is_idempotent_within_one_instance():
    symbols = _fake_symbols()
    backend = LibeiBackend(symbols=symbols)
    backend.connect(socket_path=b"/x")
    backend.connect(socket_path=b"/x")
    assert symbols.ei_new_sender.call_count == 1


def test_backend_connect_unrefs_on_setup_failure():
    symbols = _fake_symbols()
    symbols.ei_setup_backend_socket.return_value = -1
    backend = LibeiBackend(symbols=symbols)
    with pytest.raises(LibeiUnavailable, match="setup_backend_socket"):
        backend.connect(socket_path=b"/x")
    symbols.ei_unref.assert_called_once_with(0xDEADBEEF)


def test_backend_press_key_calls_keyboard_key_with_state_one():
    symbols = _fake_symbols()
    backend = LibeiBackend(symbols=symbols)
    backend.connect(socket_path=b"/x")
    backend.press_key(28)  # KEY_ENTER
    symbols.ei_device_keyboard_key.assert_called_once_with(
        0xDEADBEEF, 28, 1,
    )


def test_backend_release_key_uses_state_zero():
    symbols = _fake_symbols()
    backend = LibeiBackend(symbols=symbols)
    backend.connect(socket_path=b"/x")
    backend.release_key(28)
    symbols.ei_device_keyboard_key.assert_called_once_with(
        0xDEADBEEF, 28, 0,
    )


def test_backend_set_position_uses_absolute_motion():
    symbols = _fake_symbols()
    backend = LibeiBackend(symbols=symbols)
    backend.connect(socket_path=b"/x")
    backend.set_position(120, 240)
    symbols.ei_device_pointer_motion_absolute.assert_called_once_with(
        0xDEADBEEF, 120.0, 240.0,
    )


def test_backend_click_button_sends_press_then_release():
    symbols = _fake_symbols()
    backend = LibeiBackend(symbols=symbols)
    backend.connect(socket_path=b"/x")
    backend.click_button(272)
    calls = symbols.ei_device_button_button.call_args_list
    assert len(calls) == 2
    assert calls[0].args == (0xDEADBEEF, 272, 1)
    assert calls[1].args == (0xDEADBEEF, 272, 0)


def test_backend_scroll_forwards_float_deltas():
    symbols = _fake_symbols()
    backend = LibeiBackend(symbols=symbols)
    backend.connect(socket_path=b"/x")
    backend.scroll(0, 3)
    symbols.ei_device_scroll.assert_called_once_with(0xDEADBEEF, 0.0, 3.0)


def test_backend_disconnect_releases_handle():
    symbols = _fake_symbols()
    backend = LibeiBackend(symbols=symbols)
    backend.connect(socket_path=b"/x")
    backend.disconnect()
    symbols.ei_unref.assert_called_once_with(0xDEADBEEF)


def test_backend_method_before_connect_raises():
    symbols = _fake_symbols()
    backend = LibeiBackend(symbols=symbols)
    with pytest.raises(LibeiUnavailable, match="not connected"):
        backend.press_key(28)


def test_get_default_backend_returns_none_when_unavailable(monkeypatch):
    libei_mod.reset_default_backend()
    monkeypatch.setattr(libei_mod, "_load_symbols", lambda: None)
    assert get_default_backend() is None
    libei_mod.reset_default_backend()


def test_get_default_backend_caches_single_instance(monkeypatch):
    libei_mod.reset_default_backend()
    symbols = _fake_symbols()
    monkeypatch.setattr(libei_mod, "_load_symbols", lambda: symbols)
    a = get_default_backend()
    b = get_default_backend()
    assert a is b
    libei_mod.reset_default_backend()


# === Library probe ========================================================

def test_try_load_library_returns_none_when_find_library_fails(monkeypatch):
    monkeypatch.setattr(libei_mod.ctypes.util, "find_library",
                         lambda _name: None)
    assert libei_mod._try_load_library() is None


# === Keyboard integration ================================================

def test_keyboard_press_key_uses_libei_when_selected(monkeypatch):
    from je_auto_control.linux_wayland import keyboard as wayland_kb
    libei_mock = MagicMock()
    monkeypatch.setattr(wayland_kb, "_try_libei", lambda: libei_mock)
    wayland_kb.press_key(28)
    libei_mock.press_key.assert_called_once_with(28)


def test_keyboard_falls_back_to_ydotool_when_libei_unavailable(monkeypatch):
    from je_auto_control.linux_wayland import keyboard as wayland_kb
    monkeypatch.setattr(wayland_kb, "_try_libei", lambda: None)
    monkeypatch.setattr(wayland_kb, "binary_path",
                         lambda _name: "/usr/bin/ydotool")
    monkeypatch.setattr(wayland_kb.subprocess, "run",
                         lambda *_args, **_kw: None)
    # Should not raise.
    wayland_kb.press_key(28)


def test_mouse_set_position_uses_libei_when_selected(monkeypatch):
    from je_auto_control.linux_wayland import mouse as wayland_mouse
    libei_mock = MagicMock()
    monkeypatch.setattr(wayland_mouse, "_try_libei", lambda: libei_mock)
    wayland_mouse.set_position(100, 200)
    libei_mock.set_position.assert_called_once_with(100, 200)


def test_mouse_falls_back_to_ydotool_when_libei_unavailable(monkeypatch):
    from je_auto_control.linux_wayland import mouse as wayland_mouse
    monkeypatch.setattr(wayland_mouse, "_try_libei", lambda: None)
    monkeypatch.setattr(wayland_mouse, "binary_path",
                         lambda _name: "/usr/bin/ydotool")
    monkeypatch.setattr(wayland_mouse.subprocess, "run",
                         lambda *_args, **_kw: None)
    wayland_mouse.set_position(0, 0)


# === Facade ===============================================================

def test_facade_exports_libei_helpers():
    from je_auto_control.linux_wayland import (
        LibeiBackend as LB, LibeiUnavailable as LU,
        get_default_backend as gdb, select_input_backend as sib,
    )
    assert LB is LibeiBackend
    assert LU is LibeiUnavailable
    assert callable(gdb) and callable(sib)
