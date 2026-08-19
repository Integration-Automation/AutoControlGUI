"""The ydotool fallback counts absolute moves from the layout's corner.

``mousemove --absolute`` sends no absolute event: it drives the cursor into
the corner the compositor clamps to and then moves relative to it. That corner
is the top-left of the output layout, which is layout ``(0, 0)`` only while
every output sits at a non-negative position — so on a desktop with a monitor
left of the primary one, a raw layout coordinate lands a monitor's width away.

Measured against a real wlroots session in ``docker/Dockerfile.seat``; these
tests pin the translation that measurement produced, on any host, without a
compositor.
"""
import subprocess
from unittest.mock import patch

import pytest

from je_auto_control.linux_wayland import (
    _layout, _ydotool_cli, libei as wayland_libei, mouse as wayland_mouse,
)


@pytest.fixture(autouse=True)
def _pin_the_cli_input_path():
    """Keep every test here on the ydotool argv, as the sibling file does."""
    _ydotool_cli.reset_cache()
    _ydotool_cli._cache["/usr/bin/ydotool"] = _ydotool_cli.MODERN
    wayland_mouse._warn_once.cache_clear()
    _layout.reset_cache()
    try:
        with patch.object(wayland_mouse, "_try_libei", return_value=None):
            yield
    finally:
        _ydotool_cli.reset_cache()
        wayland_mouse._warn_once.cache_clear()
        _layout.reset_cache()


def _fake_run(captured):
    def runner(argv, **_kwargs):
        captured.append(list(argv))
        # CompletedProcess is a *constructor* (not a process spawn).
        return subprocess.CompletedProcess(argv, 0, b"", b"")  # nosemgrep
    return runner


def _argv_for(point, origin):
    """The argv ``set_position(*point)`` builds on a layout at ``origin``."""
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse, "layout_origin", return_value=origin), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_mouse.set_position(*point)
    assert len(captured) == 1
    return captured[0]


def test_a_layout_that_starts_at_the_origin_needs_no_translation():
    assert _argv_for((120, 240), (0, 0)) == [
        "/usr/bin/ydotool", "mousemove", "--absolute", "-x", "120", "-y", "240",
    ]


def test_a_negative_origin_is_subtracted_from_the_request():
    """A point on the primary monitor is 1,280 px into the layout."""
    assert _argv_for((120, 90), (-1280, 0)) == [
        "/usr/bin/ydotool", "mousemove", "--absolute", "-x", "1400", "-y", "90",
    ]


def test_a_point_on_the_left_hand_monitor_reaches_the_corner():
    """And the monitor left of the primary starts at the corner itself."""
    assert _argv_for((-1280, 0), (-1280, 0)) == [
        "/usr/bin/ydotool", "mousemove", "--absolute", "-x", "0", "-y", "0",
    ]


def test_a_negative_vertical_origin_is_subtracted_too():
    assert _argv_for((40, -300), (0, -400)) == [
        "/usr/bin/ydotool", "mousemove", "--absolute", "-x", "40", "-y", "100",
    ]


def test_the_translation_is_the_difference_the_capture_path_applies():
    """``_ydotool_point`` is exactly ``point - layout_origin()``."""
    with patch.object(wayland_mouse, "layout_origin", return_value=(-1280, -20)):
        assert wayland_mouse._ydotool_point(120, 90) == (1400, 110)


# === The shared origin lookup ==============================================

def test_both_input_paths_share_one_origin_lookup():
    """libei and ydotool must not drift apart on what the origin is."""
    assert wayland_libei.layout_origin is _layout.layout_origin


def test_the_origin_is_zero_when_the_screen_module_cannot_answer():
    """A host without Pillow or wlr-randr still moves, just untranslated."""
    with patch("je_auto_control.linux_wayland.screen.layout_origin",
               side_effect=OSError("no capture tool")):
        assert _layout.layout_origin() == (0, 0)


def test_the_origin_is_whatever_the_screen_module_reports():
    with patch("je_auto_control.linux_wayland.screen.layout_origin",
               return_value=(-1280, 0)):
        assert _layout.layout_origin() == (-1280, 0)


def test_the_origin_is_read_once_for_a_burst_of_moves():
    """A drag emits many moves; each must not spawn its own ``wlr-randr``."""
    with patch("je_auto_control.linux_wayland.screen.layout_origin",
               return_value=(-1280, 0)) as reader:
        for _ in range(20):
            assert _layout.layout_origin() == (-1280, 0)
    assert reader.call_count == 1


def test_a_reset_makes_the_next_call_measure_again():
    """The window is short so a rearranged desktop is picked up, not pinned."""
    with patch("je_auto_control.linux_wayland.screen.layout_origin",
               return_value=(-1280, 0)):
        assert _layout.layout_origin() == (-1280, 0)
    _layout.reset_cache()
    with patch("je_auto_control.linux_wayland.screen.layout_origin",
               return_value=(0, 0)):
        assert _layout.layout_origin() == (0, 0)


def test_a_reading_older_than_the_window_is_measured_again():
    with patch("je_auto_control.linux_wayland.screen.layout_origin",
               return_value=(-1280, 0)):
        assert _layout.layout_origin() == (-1280, 0)
    stamp, value = _layout._CACHE["origin"]
    _layout._CACHE["origin"] = (stamp - _layout._CACHE_SECONDS - 1, value)
    with patch("je_auto_control.linux_wayland.screen.layout_origin",
               return_value=(0, -400)) as reader:
        assert _layout.layout_origin() == (0, -400)
    assert reader.call_count == 1


# === The acceleration caveat ===============================================

def test_the_acceleration_caveat_is_logged_once_per_process():
    """Silently landing in the wrong place is the failure being prevented."""
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse, "layout_origin", return_value=(0, 0)), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)), \
         patch.object(wayland_mouse.autocontrol_logger, "warning") as warned:
        wayland_mouse.set_position(10, 10)
        wayland_mouse.set_position(20, 20)
    assert warned.call_count == 1
    assert "acceleration" in warned.call_args[0][0]


def test_the_libei_path_says_nothing_about_acceleration():
    """It is absolute at the protocol level, so the caveat does not apply."""
    sent: list = []

    class _Device:
        def set_position(self, x, y):
            sent.append((x, y))

    with patch.object(wayland_mouse, "_try_libei", return_value=_Device()), \
         patch.object(wayland_mouse, "emitted",
                      side_effect=lambda backend, send: (send(backend), True)[1]), \
         patch.object(wayland_mouse.autocontrol_logger, "warning") as warned:
        wayland_mouse.set_position(120, 90)
    assert sent == [(120, 90)]
    assert warned.call_count == 0
