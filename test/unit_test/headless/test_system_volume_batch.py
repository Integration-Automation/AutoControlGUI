"""Headless tests for system volume / mute control (injected fake driver)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.system_volume import (
    change_volume, clamp_percent, get_volume, is_muted, mute,
    percent_to_scalar, scalar_to_percent, set_mute, set_volume, toggle_mute,
    unmute,
)


class FakeVolume:
    """In-memory VolumeDriver: stores a 0..1 scalar and a mute flag."""

    def __init__(self, scalar=0.5, muted=False):
        self.scalar = scalar
        self.muted = muted

    def get_scalar(self):
        return self.scalar

    def set_scalar(self, scalar):
        self.scalar = scalar

    def get_mute(self):
        return self.muted

    def set_mute(self, muted):
        self.muted = muted


# --- pure conversion ------------------------------------------------------

def test_clamp_percent_bounds():
    assert clamp_percent(-20) == 0
    assert clamp_percent(150) == 100
    assert clamp_percent(37.6) == 38


def test_percent_scalar_round_trip():
    assert percent_to_scalar(50) == pytest.approx(0.5)
    assert scalar_to_percent(0.5) == 50
    assert scalar_to_percent(1.5) == 100  # clamped
    assert scalar_to_percent(-0.2) == 0


# --- volume read / write --------------------------------------------------

def test_get_volume_reads_driver():
    assert get_volume(driver=FakeVolume(scalar=0.4)) == 40


def test_set_volume_clamps_and_applies():
    drv = FakeVolume(scalar=0.0)
    assert set_volume(73, driver=drv) == 73
    assert drv.scalar == pytest.approx(0.73)
    assert set_volume(250, driver=drv) == 100
    assert set_volume(-5, driver=drv) == 0


def test_change_volume_relative():
    drv = FakeVolume(scalar=0.5)
    assert change_volume(20, driver=drv) == 70
    assert change_volume(-100, driver=drv) == 0
    assert change_volume(10, driver=drv) == 10


# --- mute -----------------------------------------------------------------

def test_is_muted_and_set_mute():
    drv = FakeVolume(muted=False)
    assert is_muted(driver=drv) is False
    assert set_mute(True, driver=drv) is True
    assert drv.muted is True


def test_mute_unmute_helpers():
    drv = FakeVolume(muted=False)
    assert mute(driver=drv) is True
    assert is_muted(driver=drv) is True
    assert unmute(driver=drv) is False
    assert is_muted(driver=drv) is False


def test_toggle_mute_flips():
    drv = FakeVolume(muted=False)
    assert toggle_mute(driver=drv) is True
    assert toggle_mute(driver=drv) is False


# --- wiring ---------------------------------------------------------------

def test_executor_pure_path_with_default_driver_absent_on_linux():
    # The executor adapters use the OS default driver; on a non-Windows CI box
    # that raises a clear RuntimeError rather than silently passing.
    from je_auto_control.utils.system_volume.system_volume import (
        _default_driver,
    )
    import sys
    if not sys.platform.startswith("win"):
        with pytest.raises(RuntimeError):
            _default_driver()


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_get_volume", "AC_set_volume", "AC_change_volume",
            "AC_set_mute", "AC_toggle_mute"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_get_volume", "ac_set_volume", "ac_change_volume",
            "ac_set_mute", "ac_toggle_mute"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_get_volume", "AC_set_volume", "AC_change_volume",
            "AC_set_mute", "AC_toggle_mute"} <= specs


def test_facade_exports():
    for name in ("get_volume", "set_volume", "change_volume", "is_muted",
                 "set_mute", "mute", "unmute", "toggle_mute"):
        assert hasattr(ac, name) and name in ac.__all__
