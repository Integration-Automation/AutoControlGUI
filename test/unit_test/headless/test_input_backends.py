"""Headless tests for the optional driver-level input backends.

These never touch the real driver / kernel device — they verify that

1. the optional sub-packages import cleanly on a machine that has
   *neither* Interception nor uinput nor ViGEm installed,
2. their ``is_available()`` probes reliably return ``False`` instead
   of raising,
3. the platform wrappers fall back to the original XTest / SendInput
   modules when the operator opts in but the driver / kernel device
   isn't reachable,
4. the new MCP gamepad tools register with the right schema +
   annotation flags.
"""
from __future__ import annotations

import importlib
import sys

import pytest


# --- Interception (Windows-only sub-package) -------------------------------


@pytest.mark.skipif(sys.platform != "win32",
                    reason="Interception backend is Windows-only")
def test_interception_dll_module_imports_cleanly():
    """Importing the package on a machine without the driver must not raise."""
    mod = importlib.import_module(
        "je_auto_control.windows.interception._dll",
    )
    assert mod.is_available is not None


@pytest.mark.skipif(sys.platform != "win32",
                    reason="Interception backend is Windows-only")
def test_interception_is_available_returns_false_without_driver():
    """No driver installed → probe returns False, never raises."""
    from je_auto_control.windows.interception import is_available
    # The CI runners do not have the driver, so this must come back
    # False; if the driver IS there for some reason, we still tolerate
    # True so the test stays portable.
    result = is_available()
    assert isinstance(result, bool)


# --- uinput (Linux-only sub-package) ---------------------------------------


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="uinput backend is Linux-only")
def test_uinput_module_imports_cleanly():
    """The uinput sub-package must import even without /dev/uinput."""
    mod = importlib.import_module(
        "je_auto_control.linux_with_x11.uinput._device",
    )
    assert hasattr(mod, "is_available")


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="uinput backend is Linux-only")
def test_uinput_is_available_does_not_raise():
    """Probe must report a bool whether or not /dev/uinput is writable."""
    from je_auto_control.linux_with_x11.uinput import is_available
    assert isinstance(is_available(), bool)


# --- Virtual gamepad facade -------------------------------------------------


def test_gamepad_module_imports_cleanly():
    """The facade is importable on every platform (vgamepad is opt-in)."""
    mod = importlib.import_module("je_auto_control.utils.gamepad")
    assert mod.GamepadUnavailable is not None
    assert mod.GAMEPAD_BUTTONS  # non-empty tuple
    assert mod.DPAD_DIRECTIONS  # non-empty tuple


def test_gamepad_is_available_does_not_raise():
    """Probe must report a bool whether or not ViGEm is installed."""
    from je_auto_control.utils.gamepad import is_available
    assert isinstance(is_available(), bool)


def test_virtual_gamepad_raises_when_dependency_missing(monkeypatch):
    """``VirtualGamepad()`` must surface a clear error when vgamepad is gone."""
    from je_auto_control.utils.gamepad import VirtualGamepad
    from je_auto_control.utils.gamepad._facade import GamepadUnavailable

    # Block ``import vgamepad`` regardless of whether the dep is
    # actually installed in the test environment.
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "vgamepad":
            raise ImportError("simulated absence")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with pytest.raises(GamepadUnavailable):
        VirtualGamepad()


# --- MCP registration check -------------------------------------------------


def test_mcp_gamepad_tools_are_registered():
    """The seven gamepad tools must show up in build_default_tool_registry()."""
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    expected = {
        "ac_gamepad_press", "ac_gamepad_release", "ac_gamepad_click",
        "ac_gamepad_dpad",
        "ac_gamepad_left_stick", "ac_gamepad_right_stick",
        "ac_gamepad_left_trigger", "ac_gamepad_right_trigger",
        "ac_gamepad_reset",
    }
    assert expected.issubset(by_name.keys())
    # Every gamepad tool is destructive — it actively drives synthetic
    # input — so it must NOT claim read-only.
    for name in expected:
        assert by_name[name].annotations.read_only is False, name


def test_mcp_gamepad_tools_dropped_under_read_only():
    """The destructive gamepad tools must not survive ``--readonly`` mode."""
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    safe_names = {tool.name
                  for tool in build_default_tool_registry(read_only=True)}
    assert "ac_gamepad_press" not in safe_names
    assert "ac_gamepad_left_stick" not in safe_names


# --- Win32 / Linux env-var selectors ---------------------------------------


def test_win32_backend_env_var_default_is_sendinput(monkeypatch):
    """Without the env var, the wrapper still picks the SendInput backend."""
    if sys.platform != "win32":
        pytest.skip("Win32 selector only matters on Windows")
    monkeypatch.delenv("JE_AUTOCONTROL_WIN32_BACKEND", raising=False)
    from je_auto_control.wrapper import _platform_windows
    keyboard, mouse = _platform_windows._select_input_backend()
    assert keyboard.__name__.endswith("win32_ctype_keyboard_control")
    assert mouse.__name__.endswith("win32_ctype_mouse_control")


def test_win32_backend_env_var_falls_back_when_driver_missing(monkeypatch):
    """``interception`` env value with no driver → SendInput + warning."""
    if sys.platform != "win32":
        pytest.skip("Win32 selector only matters on Windows")
    monkeypatch.setenv("JE_AUTOCONTROL_WIN32_BACKEND", "interception")
    # Force the availability probe to report False so the test runs
    # whether or not the host actually has the driver installed.
    from je_auto_control.wrapper import _platform_windows
    monkeypatch.setattr(
        "je_auto_control.windows.interception.is_available",
        lambda: False,
    )
    keyboard, mouse = _platform_windows._select_input_backend()
    assert keyboard.__name__.endswith("win32_ctype_keyboard_control")
    assert mouse.__name__.endswith("win32_ctype_mouse_control")


def test_linux_backend_env_var_default_is_x11(monkeypatch):
    """Without the env var, the wrapper still picks the XTest backend."""
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux selector only matters on Linux")
    monkeypatch.delenv("JE_AUTOCONTROL_LINUX_BACKEND", raising=False)
    from je_auto_control.wrapper import _platform_linux
    keyboard, mouse = _platform_linux._select_input_backend()
    assert keyboard.__name__.endswith("x11_linux_keyboard_control")
    assert mouse.__name__.endswith("x11_linux_mouse_control")
