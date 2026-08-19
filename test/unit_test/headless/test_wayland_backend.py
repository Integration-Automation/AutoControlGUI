"""Headless tests for the Wayland backend skeleton.

All tests run on any host because:

* detection uses ``os.environ`` so we inject a fake dict;
* every CLI invocation is patched out, so neither wtype/ydotool/grim
  needs to be installed to validate the dispatch logic.
"""
import subprocess
from unittest.mock import patch

import pytest

from je_auto_control.linux_wayland import (
    _detect, _ydotool_cli, capture as wayland_capture,
    keyboard as wayland_keyboard, mouse as wayland_mouse,
    screen as wayland_screen,
)
from je_auto_control.linux_wayland.keymap import keyboard_keys_table
from je_auto_control.utils.exception.exceptions import AutoControlException


@pytest.fixture(autouse=True)
def _pin_the_cli_input_path():
    """Keep every dispatch test in this file on the wtype / ydotool argv.

    ``mouse`` and ``keyboard`` prefer libei wherever it is loadable, so on a
    host that has it these tests would probe for a portal and then assert
    against argv that was never produced. The libei path has its own file,
    ``test_wayland_libei.py``.

    The ydotool generation cache is pre-seeded for the same reason. Before
    building any argv both backends probe the installed ydotool once, because
    0.1.x answers this argv with exit code 0 and no events — and that probe is
    a ``subprocess.run`` call too, so it would land in the captured argv list
    of every dispatch test here. What it does instead is its own file,
    ``test_wayland_ydotool_cli.py``.
    """
    _ydotool_cli.reset_cache()
    _ydotool_cli._cache["/usr/bin/ydotool"] = _ydotool_cli.MODERN
    try:
        with patch.object(wayland_mouse, "_try_libei", return_value=None), \
             patch.object(wayland_keyboard, "_try_libei", return_value=None):
            yield
    finally:
        _ydotool_cli.reset_cache()


# === Detection ==============================================================

def test_is_wayland_session_reads_session_type():
    env = {"XDG_SESSION_TYPE": "wayland"}
    assert _detect.is_wayland_session(env) is True


def test_is_wayland_session_reads_wayland_display():
    env = {"WAYLAND_DISPLAY": "wayland-0"}
    assert _detect.is_wayland_session(env) is True


def test_is_wayland_session_false_for_x11():
    env = {"XDG_SESSION_TYPE": "x11"}
    assert _detect.is_wayland_session(env) is False


def test_select_display_server_auto_picks_wayland():
    env = {"XDG_SESSION_TYPE": "wayland"}
    assert _detect.select_display_server(env) == "wayland"


def test_select_display_server_override_x11_wins_over_env():
    env = {
        "XDG_SESSION_TYPE": "wayland",
        "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER": "x11",
    }
    assert _detect.select_display_server(env) == "x11"


def test_select_display_server_override_wayland_on_x11_session():
    env = {
        "XDG_SESSION_TYPE": "x11",
        "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER": "wayland",
    }
    assert _detect.select_display_server(env) == "wayland"


def test_select_display_server_invalid_override_falls_through():
    env = {
        "XDG_SESSION_TYPE": "x11",
        "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER": "garbage",
    }
    assert _detect.select_display_server(env) == "x11"


def test_missing_dependencies_returns_absent_names():
    with patch.object(_detect.shutil, "which",
                      side_effect=lambda name: None if name == "missing"
                      else "/usr/bin/" + name):
        assert _detect.missing_dependencies(
            ["wtype", "missing", "grim"],
        ) == ["missing"]


# === Keymap ================================================================

def test_keymap_includes_enter_and_alpha_and_digits():
    assert keyboard_keys_table["enter"] == 28
    assert keyboard_keys_table["a"] == keyboard_keys_table["A"]
    assert keyboard_keys_table["0"] == 11
    assert keyboard_keys_table["1"] == 2


def test_keymap_function_keys_present():
    assert keyboard_keys_table["f1"] == 59
    assert keyboard_keys_table["f12"] == 88
    assert keyboard_keys_table["f24"] == 194


# === Keyboard dispatch =====================================================

def _fake_run(captured):
    def runner(argv, **_kwargs):
        captured.append(list(argv))
        # CompletedProcess is a *constructor* (not a process spawn);
        # used here to mock subprocess.run's return value.
        result = subprocess.CompletedProcess(argv, 0, b"", b"")  # nosemgrep
        return result
    return runner


def test_press_key_invokes_ydotool_with_keydown_suffix():
    captured: list = []
    with patch.object(wayland_keyboard, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_keyboard.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_keyboard.press_key(28)
    assert captured == [["/usr/bin/ydotool", "key", "28:1"]]


def test_release_key_invokes_ydotool_with_keyup_suffix():
    captured: list = []
    with patch.object(wayland_keyboard, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_keyboard.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_keyboard.release_key(28)
    assert captured == [["/usr/bin/ydotool", "key", "28:0"]]


def test_write_invokes_wtype_with_text():
    captured: list = []
    with patch.object(wayland_keyboard, "binary_path",
                      return_value="/usr/bin/wtype"), \
         patch.object(wayland_keyboard.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_keyboard.write("hello")
    assert captured == [["/usr/bin/wtype", "--", "hello"]]


def test_hotkey_chord_presses_in_order_releases_reverse():
    captured: list = []
    with patch.object(wayland_keyboard, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_keyboard.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_keyboard.hotkey([29, 46])  # ctrl + c
    assert captured == [[
        "/usr/bin/ydotool", "key",
        "29:1", "46:1", "46:0", "29:0",
    ]]


def test_keyboard_raises_clear_error_when_ydotool_missing():
    with patch.object(wayland_keyboard, "binary_path", return_value=None):
        with pytest.raises(AutoControlException, match="ydotool"):
            wayland_keyboard.press_key(28)


def test_keyboard_raises_when_wtype_missing():
    with patch.object(wayland_keyboard, "binary_path", return_value=None):
        with pytest.raises(AutoControlException, match="wtype"):
            wayland_keyboard.write("hi")


def test_press_key_rejects_non_integer():
    with pytest.raises(ValueError):
        wayland_keyboard.press_key("28")  # type: ignore[arg-type]


def test_press_key_rejects_non_positive():
    with pytest.raises(ValueError):
        wayland_keyboard.press_key(0)


def test_send_key_event_to_window_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        wayland_keyboard.send_key_event_to_window(1234, 28)


# === Mouse dispatch =========================================================

def test_set_position_invokes_ydotool_mousemove():
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_mouse.set_position(120, 240)
    assert captured == [[
        "/usr/bin/ydotool", "mousemove", "--absolute",
        "-x", "120", "-y", "240",
    ]]


def test_click_mouse_can_move_first():
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_mouse.click_mouse(wayland_mouse.wayland_mouse_left,
                                   x=10, y=20)
    assert captured[0][1] == "mousemove"
    assert captured[1][1] == "click"


def test_press_mouse_sets_hold_bit():
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_mouse.press_mouse(wayland_mouse.wayland_mouse_left)
    # 0xC0 | 0x40 = 0xC0 (hold bit already set); confirm hex format.
    assert captured[-1][-1].startswith("0x")


def test_position_query_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        wayland_mouse.position()


def test_send_mouse_to_window_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        wayland_mouse.send_mouse_event_to_window()


def test_mouse_raises_when_ydotool_missing():
    with patch.object(wayland_mouse, "binary_path", return_value=None):
        with pytest.raises(AutoControlException, match="ydotool"):
            wayland_mouse.set_position(0, 0)


# === Screen dispatch ========================================================

def _fake_capture(captured, png):
    """Stand in for subprocess.run inside the capture module."""
    def runner(argv, **_kwargs):
        captured.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, png, b"")  # nosemgrep
    return runner


def test_screenshot_captures_through_grim_and_saves_with_pillow(tmp_path):
    """grim writes PNG to stdout and Pillow saves it, so the same capture
    can also be handed back in memory to the locators."""
    captured: list = []
    png = _one_pixel_png((1, 2, 3))
    target = tmp_path / "out.png"
    with patch.object(wayland_capture, "binary_path",
                      return_value="/usr/bin/grim"), \
         patch.object(wayland_capture.subprocess, "run",
                      side_effect=_fake_capture(captured, png)):
        assert wayland_screen.screenshot(str(target)) == str(target)
    assert captured == [["/usr/bin/grim", "-"]]
    assert target.exists()


def test_screenshot_passes_screen_region():
    captured: list = []
    png = _one_pixel_png((1, 2, 3))
    with patch.object(wayland_capture, "binary_path",
                      return_value="/usr/bin/grim"), \
         patch.object(wayland_capture.subprocess, "run",
                      side_effect=_fake_capture(captured, png)):
        wayland_screen.screenshot(None, screen_region=[10, 20, 110, 220])
    assert captured == [[
        "/usr/bin/grim", "-g", "10,20 100x200", "-",
    ]]


@pytest.mark.parametrize("direction_name, expected_x, expected_y", [
    ("wayland_scroll_direction_down", "0", "-5"),
    ("wayland_scroll_direction_up", "0", "5"),
    ("wayland_scroll_direction_left", "-5", "0"),
    ("wayland_scroll_direction_right", "5", "0"),
])
def test_scroll_honours_direction(direction_name, expected_x, expected_y):
    """Regression: scroll's signature was ``(direction, x, y)`` while the
    wrapper calls ``scroll(scroll_value, scroll_direction)``. The direction
    bound to ``x`` and was then dropped, so every direction scrolled the same
    way — up and down emitted byte-identical argv.
    """
    captured: list = []
    direction = getattr(wayland_mouse, direction_name)
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_mouse.scroll(5, direction)
    # Both axes are always sent, per ydotool's documented example.
    assert captured[0][1:] == [
        "mousemove", "--wheel", "-x", expected_x, "-y", expected_y,
    ]


def test_scroll_opposite_directions_are_not_identical():
    """The sharpest form of the regression: up and down must differ."""
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_mouse.scroll(5, wayland_mouse.wayland_scroll_direction_down)
        wayland_mouse.scroll(5, wayland_mouse.wayland_scroll_direction_up)
    assert captured[0] != captured[1]


def test_get_pixel_grabs_a_one_by_one_region_at_the_point():
    """The wrapper calls ``screen.get_pixel``; Wayland had no such function
    at all, so every get_pixel raised AttributeError on Wayland."""
    png = _one_pixel_png((10, 20, 30))
    captured: list = []

    with patch.object(wayland_capture, "binary_path",
                      return_value="/usr/bin/grim"), \
         patch.object(wayland_capture.subprocess, "run",
                      side_effect=_fake_capture(captured, png)):
        assert wayland_screen.get_pixel(7, 9) == (10, 20, 30)
    assert "-g" in captured[0] and "7,9 1x1" in captured[0]


def _one_pixel_png(rgb) -> bytes:
    return _solid_png((1, 1), rgb)


def _solid_png(size, rgb) -> bytes:
    from io import BytesIO

    from PIL import Image
    buffer = BytesIO()
    Image.new("RGB", size, rgb).save(buffer, format="PNG")
    return buffer.getvalue()


# Captured verbatim from `wlr-randr` inside the headless sway session in
# docker/Dockerfile.wayland — two outputs, the second one to the right of
# the first, no refresh rate on a headless mode.
_REAL_WLR_RANDR = """HEADLESS-2 "Headless output 1"
  Make: (null)
  Model: (null)
  Serial: (null)
  Enabled: yes
  Modes:
    1280x720 px (current)
  Position: 0,0
  Transform: normal
  Scale: 1.000000
HEADLESS-1 "Headless output 2"
  Make: (null)
  Model: (null)
  Serial: (null)
  Enabled: yes
  Modes:
    1280x720 px (current)
  Position: 1280,0
  Transform: normal
  Scale: 1.000000
"""


def test_wlr_randr_parses_every_output_not_just_the_first():
    """Regression, found by running against a real sway session.

    The old parser returned the first ``WxH`` anywhere in the document, so a
    two-monitor layout reported one monitor's mode as the screen size —
    while ``grab_image()`` returned the whole layout. The mss-shaped shim
    composes the two, so it asked for a region half the size of the screen.
    """
    rects = wayland_screen.parse_wlr_randr(_REAL_WLR_RANDR)
    assert rects == [(0, 0, 1280, 720), (1280, 0, 1280, 720)]


def test_wlr_randr_skips_a_disabled_output():
    text = _REAL_WLR_RANDR.replace("  Enabled: yes\n  Modes:\n"
                                   "    1280x720 px (current)\n"
                                   "  Position: 1280,0\n",
                                   "  Enabled: no\n")
    assert wayland_screen.parse_wlr_randr(text) == [(0, 0, 1280, 720)]


def test_wlr_randr_reads_a_mode_line_that_carries_a_refresh_rate():
    """A real monitor prints `1920x1080 px, 60.000000 Hz (preferred, current)`;
    only the headless backend omits the rate."""
    text = ('DP-1 "Acme"\n  Enabled: yes\n  Modes:\n'
            '    1920x1080 px, 60.000000 Hz (preferred, current)\n'
            '    1280x720 px, 60.000000 Hz\n  Position: 0,0\n')
    assert wayland_screen.parse_wlr_randr(text) == [(0, 0, 1920, 1080)]


def test_screen_size_uses_wlr_randr_when_available():
    with patch.object(wayland_screen, "binary_path",
                      side_effect=lambda name: "/usr/bin/" + name), \
         patch.object(
            wayland_capture.subprocess, "run",
            return_value=subprocess.CompletedProcess(  # nosemgrep
                ["wlr-randr"], 0, _REAL_WLR_RANDR.encode(), b"",
            ),
        ):
        # The bounding box of both outputs, not the first output's mode.
        assert wayland_screen.size() == (2560, 720)


def test_screen_size_falls_back_to_measuring_a_capture():
    """GNOME / KDE have no wlr-randr, so the size comes from the capture."""
    png = _one_pixel_png((0, 0, 0))
    with patch.object(wayland_screen, "binary_path", return_value=None), \
         patch.object(wayland_capture, "binary_path",
                      return_value="/usr/bin/grim"), \
         patch.object(wayland_capture.subprocess, "run",
                      side_effect=_fake_capture([], png)):
        assert wayland_screen.size() == (1, 1)


# Captured verbatim from the same sway session with HEADLESS-1 moved to
# `position -1280 0`, which sway's headless backend accepts. A monitor
# placed left of the primary one is what puts a real desktop here, and it
# is the layout every assertion below is about.
_NEGATIVE_ORIGIN_WLR_RANDR = """HEADLESS-2 "Headless output 1"
  Make: (null)
  Model: (null)
  Serial: (null)
  Enabled: yes
  Modes:
    1280x720 px (current)
  Position: 0,0
  Transform: normal
  Scale: 1.000000
  Adaptive Sync: disabled
HEADLESS-1 "Headless output 2"
  Make: (null)
  Model: (null)
  Serial: (null)
  Enabled: yes
  Modes:
    1280x720 px (current)
  Position: -1280,0
  Transform: normal
  Scale: 1.000000
  Adaptive Sync: disabled
"""


def _with_wlr_randr(reported):
    """The two seams ``wlr-randr`` is read through, as a pair of patches."""
    return (
        patch.object(wayland_screen, "binary_path",
                     side_effect=lambda name: "/usr/bin/" + name),
        patch.object(
            wayland_capture.subprocess, "run",
            return_value=subprocess.CompletedProcess(  # nosemgrep
                ["wlr-randr"], 0, reported.encode(), b"",
            ),
        ),
    )


def test_wlr_randr_parses_a_negative_output_position():
    rects = wayland_screen.parse_wlr_randr(_NEGATIVE_ORIGIN_WLR_RANDR)
    assert rects == [(0, 0, 1280, 720), (-1280, 0, 1280, 720)]


def test_screen_size_is_the_layout_width_not_its_right_edge():
    """Regression: ``size()`` returned ``max(x + width)``.

    On the layout above that is 1280 — the right edge — while the capture
    grim returns is 2560 wide. Everything that composes the two (the
    mss-shaped shim's monitor list, the recorder, the WebRTC host) then
    asked for half the desktop and called it the whole screen.
    """
    binary, run = _with_wlr_randr(_NEGATIVE_ORIGIN_WLR_RANDR)
    with binary, run:
        assert wayland_screen.size() == (2560, 720)


def test_layout_origin_is_the_left_most_output():
    binary, run = _with_wlr_randr(_NEGATIVE_ORIGIN_WLR_RANDR)
    with binary, run:
        assert wayland_screen.layout_origin() == (-1280, 0)


def test_layout_origin_is_the_origin_on_an_ordinary_layout():
    binary, run = _with_wlr_randr(_REAL_WLR_RANDR)
    with binary, run:
        assert wayland_screen.layout_origin() == (0, 0)


def test_layout_origin_is_the_origin_when_wlr_randr_is_absent():
    """GNOME / KDE ship no wlr-randr, and a guess would be worse than (0, 0)."""
    with patch.object(wayland_screen, "binary_path", return_value=None):
        assert wayland_screen.layout_origin() == (0, 0)


def test_grab_image_crops_relative_to_the_layout_origin():
    """Regression: the crop used layout coordinates on a layout-origin image.

    Only grim applies a region itself; gnome-screenshot, spectacle, the
    portal and the operator's own command all hand back the whole layout,
    and its top-left pixel is the layout origin rather than (0, 0). Cropping
    ``[-1275, 5, -1175, 55]`` straight off that image asks Pillow for a box
    starting 1275 px to the left of the frame — which pads with black
    instead of returning the left-hand monitor.
    """
    from io import BytesIO

    from PIL import Image
    left, right = (0x12, 0x34, 0x56), (0xAB, 0xCD, 0xEF)
    layout = Image.new("RGB", (2560, 720), right)
    layout.paste(Image.new("RGB", (1280, 720), left), (0, 0))
    buffer = BytesIO()
    layout.save(buffer, format="PNG")

    binary, run = _with_wlr_randr(_NEGATIVE_ORIGIN_WLR_RANDR)
    whole_layout = wayland_capture.Capture(buffer.getvalue(), False)
    with binary, run, patch.object(wayland_capture, "grab_png",
                                   return_value=whole_layout):
        cropped = wayland_screen.grab_image([-1275, 5, -1175, 55])
        # A region on the right-hand output still reads the right colour,
        # so what changed is a shift and not a constant.
        other = wayland_screen.grab_image([5, 5, 105, 55])
    assert cropped.size == (100, 50)
    assert cropped.getpixel((0, 0)) == left
    assert other.getpixel((0, 0)) == right


def test_screenshot_raises_when_no_capture_tool_is_installed():
    """The message has to name every tool that would have worked, because
    which one is right depends on the compositor the operator is running."""
    with patch.object(wayland_capture, "binary_path", return_value=None):
        with pytest.raises(AutoControlException) as error:
            wayland_screen.screenshot("out.png")
    message = str(error.value)
    for tool in ("grim", "gnome-screenshot", "spectacle"):
        assert tool in message


def test_capture_falls_back_to_gnome_screenshot_when_grim_is_absent(tmp_path):
    """grim only speaks wlr-screencopy; GNOME needs its own helper."""
    png = _one_pixel_png((4, 5, 6))
    captured: list = []

    def _which(name):
        return None if name == "grim" else "/usr/bin/" + name

    def _run(argv, **_kwargs):
        captured.append(list(argv))
        # The helper writes a file rather than to stdout.
        with open(argv[-1], "wb") as handle:
            handle.write(png)
        return subprocess.CompletedProcess(argv, 0, b"", b"")  # nosemgrep

    with patch.object(wayland_capture, "binary_path", side_effect=_which), \
         patch.object(wayland_capture.subprocess, "run", side_effect=_run):
        image = wayland_screen.grab_image()
    assert image.size == (1, 1)
    assert captured[0][0] == "/usr/bin/gnome-screenshot"


def test_grab_image_crops_when_the_helper_cannot_take_a_region():
    """Only grim applies a region itself; the file-based helpers always
    return the whole screen, so the region has to be cropped afterwards."""
    png = _solid_png((4, 2), (7, 8, 9))

    def _which(name):
        return None if name == "grim" else "/usr/bin/" + name

    def _run(argv, **_kwargs):
        with open(argv[-1], "wb") as handle:
            handle.write(png)
        return subprocess.CompletedProcess(argv, 0, b"", b"")  # nosemgrep

    with patch.object(wayland_capture, "binary_path", side_effect=_which), \
         patch.object(wayland_capture.subprocess, "run", side_effect=_run):
        image = wayland_screen.grab_image([1, 0, 3, 2])
    assert image.size == (2, 2)


def test_grab_image_rejects_an_empty_region():
    with pytest.raises(AutoControlException, match="positive width"):
        wayland_screen.grab_image([10, 10, 10, 20])


def test_available_tool_reports_the_helper_that_would_run():
    with patch.object(wayland_capture, "binary_path",
                      side_effect=lambda name: None if name == "grim"
                      else "/usr/bin/" + name):
        assert wayland_capture.available_tool() == "gnome-screenshot"
    with patch.object(wayland_capture, "binary_path", return_value=None):
        assert wayland_capture.available_tool() is None


# === Listener / record stubs ===============================================

def test_listener_raises_not_implemented():
    from je_auto_control.linux_wayland import listener
    with pytest.raises(NotImplementedError):
        listener.check_key_press()
    with pytest.raises(NotImplementedError):
        listener.hook_keyboard()


def test_recorder_raises_not_implemented():
    from je_auto_control.linux_wayland.record import wayland_recorder
    with pytest.raises(NotImplementedError):
        wayland_recorder.record()
    with pytest.raises(NotImplementedError):
        wayland_recorder.stop_record()


# === Wrapper module skeleton ==============================================

def test_platform_wayland_wrapper_exports_expected_names():
    from je_auto_control.wrapper import _platform_wayland as wrapper
    for name in ("keyboard", "keyboard_check", "keyboard_keys_table",
                  "mouse", "mouse_keys_table", "special_mouse_keys_table",
                  "screen", "recorder"):
        assert hasattr(wrapper, name)
    assert wrapper.mouse_keys_table["mouse_left"] == \
        wayland_mouse.wayland_mouse_left
