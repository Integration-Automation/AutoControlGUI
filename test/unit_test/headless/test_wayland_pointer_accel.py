"""The operator declares whether the compositor's pointer acceleration is off.

``mousemove --absolute`` is relative motion under the hood, so the compositor
scales it: measured against a real wlroots session, libinput's default
adaptive profile lands the cursor twice as far from the corner as asked. The
factor is compositor configuration and no client can read it back, so the
library cannot compensate — only the operator knows. ``POINTER_ACCEL_ENV`` is
how they say so, and these tests pin what each answer does.

The libei path is absolute at the protocol level, so none of this applies to
it; the last test holds that line.
"""
import subprocess
from unittest.mock import patch

import pytest

from je_auto_control.linux_wayland import (
    _layout, _ydotool_cli, mouse as wayland_mouse,
)
from je_auto_control.utils.exception.exceptions import AutoControlException


@pytest.fixture(autouse=True)
def _pin_the_cli_input_path(monkeypatch):
    """Force the ydotool argv and re-arm the once-per-process warnings."""
    _ydotool_cli.reset_cache()
    _ydotool_cli._cache["/usr/bin/ydotool"] = _ydotool_cli.MODERN
    wayland_mouse._warn_once.cache_clear()
    _layout.reset_cache()
    monkeypatch.delenv(wayland_mouse.POINTER_ACCEL_ENV, raising=False)
    try:
        with patch.object(wayland_mouse, "_try_libei", return_value=None):
            yield
    finally:
        _ydotool_cli.reset_cache()
        wayland_mouse._warn_once.cache_clear()
        _layout.reset_cache()


def _move(x=10, y=20):
    """Run ``set_position`` on the CLI path; return (argv list, warnings)."""
    captured: list = []
    warned: list = []

    def runner(argv, **_kwargs):
        captured.append(list(argv))
        # CompletedProcess is a *constructor* (not a process spawn).
        return subprocess.CompletedProcess(argv, 0, b"", b"")  # nosemgrep

    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse, "layout_origin", return_value=(0, 0)), \
         patch.object(wayland_mouse.autocontrol_logger, "warning",
                      side_effect=lambda message, *a, **k: warned.append(
                          str(message))), \
         patch.object(wayland_mouse.subprocess, "run", side_effect=runner):
        wayland_mouse.set_position(x, y)
    return captured, warned


def test_unset_means_warn_once_and_move_anyway():
    """The default keeps every existing caller working, loudly."""
    argv, warned = _move()
    assert argv == [["/usr/bin/ydotool", "mousemove", "--absolute",
                     "-x", "10", "-y", "20"]]
    assert len(warned) == 1
    assert "acceleration" in warned[0]


def test_the_warning_names_the_way_out():
    """A warning nobody can act on is noise: it must name the variable."""
    _, warned = _move()
    assert wayland_mouse.POINTER_ACCEL_ENV in warned[0]
    assert "flat" in warned[0]
    assert "strict" in warned[0]


def test_warn_does_not_repeat_on_every_move():
    """A script making thousands of moves gets one line, not thousands."""
    _move()
    _, warned = _move()
    assert warned == []


def test_flat_moves_silently(monkeypatch):
    """The operator has switched acceleration off; there is nothing to say."""
    monkeypatch.setenv(wayland_mouse.POINTER_ACCEL_ENV, "flat")
    argv, warned = _move()
    assert len(argv) == 1
    assert warned == []


def test_strict_refuses_rather_than_landing_somewhere_else(monkeypatch):
    """Fail fast: no argv is sent at all, so nothing lands anywhere."""
    monkeypatch.setenv(wayland_mouse.POINTER_ACCEL_ENV, "strict")
    with pytest.raises(AutoControlException) as raised:
        _move()
    assert wayland_mouse.POINTER_ACCEL_ENV in str(raised.value)


def test_strict_sends_no_command(monkeypatch):
    """The refusal happens before the subprocess, not after."""
    monkeypatch.setenv(wayland_mouse.POINTER_ACCEL_ENV, "strict")
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=lambda argv, **k: captured.append(argv)), \
         pytest.raises(AutoControlException):
        wayland_mouse.set_position(10, 20)
    assert captured == []


@pytest.mark.parametrize("declared, expected", [
    ("flat", "flat"),
    ("FLAT", "flat"),
    ("  strict  ", "strict"),
    ("warn", "warn"),
])
def test_the_value_is_read_case_and_whitespace_insensitively(declared,
                                                             expected):
    """Operators type these into shell profiles and CI YAML by hand."""
    assert wayland_mouse.pointer_accel_mode(
        {wayland_mouse.POINTER_ACCEL_ENV: declared}) == expected


@pytest.mark.parametrize("declared", ["", "   ", "off", "flatt", "0"])
def test_an_unrecognised_value_falls_back_to_the_safe_answer(declared):
    """A typo must not silently promote a move to trusted-exact."""
    assert wayland_mouse.pointer_accel_mode(
        {wayland_mouse.POINTER_ACCEL_ENV: declared}) == "warn"


def test_a_typo_says_so_rather_than_being_swallowed():
    """Falling back silently is how an operator believes a lie."""
    warned: list = []
    with patch.object(wayland_mouse.autocontrol_logger, "warning",
                      side_effect=lambda message, *a, **k: warned.append(
                          str(message))):
        wayland_mouse.pointer_accel_mode(
            {wayland_mouse.POINTER_ACCEL_ENV: "flatt"})
    assert len(warned) == 1
    assert "flatt" in warned[0]
    assert "warn" in warned[0]


def test_a_missing_variable_is_not_a_typo():
    """An absent variable is the default, and says nothing."""
    warned: list = []
    with patch.object(wayland_mouse.autocontrol_logger, "warning",
                      side_effect=lambda message, *a, **k: warned.append(
                          str(message))):
        assert wayland_mouse.pointer_accel_mode({}) == "warn"
    assert warned == []


def test_strict_does_not_touch_the_libei_path(monkeypatch):
    """libei is absolute at the protocol level; the caveat is ydotool's."""
    monkeypatch.setenv(wayland_mouse.POINTER_ACCEL_ENV, "strict")
    moved: list = []

    class _Device:
        def set_position(self, x, y):
            moved.append((x, y))

    with patch.object(wayland_mouse, "_try_libei", return_value=_Device()), \
         patch.object(wayland_mouse, "emitted",
                      side_effect=lambda backend, call: (call(backend), True)[1]):
        wayland_mouse.set_position(7, 9)
    assert moved == [(7, 9)]
