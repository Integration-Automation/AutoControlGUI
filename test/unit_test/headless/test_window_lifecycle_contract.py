"""Window management reports what happened, and leaves windows where they were.

Every Win32 call here is a fake: nothing in this file focuses, moves, shows or
types into a real window.

* ``post_key`` posted ``WM_KEYDOWN`` + ``WM_CHAR`` + ``WM_KEYUP`` for a printable
  key. The target's ``TranslateMessage`` makes a ``WM_CHAR`` of its own from the
  key-down, and another from a key-up whose ``lParam`` is 0 (no release bit), so
  one character arrived three times. ``post_key_to_window(title, "enter")``
  raised ``unknown key name`` on Windows, whose table calls that key ``return``.
* ``focus_window`` / ``show_window`` / the z-order driver dropped the BOOL the
  Win32 call returned and reported success when Windows had refused.
* ``list_windows`` listed windows DWM is cloaking and windows with no area.
* A saved layout held the visible frame and was restored through
  ``MoveWindow``, which positions the larger rectangle around it: 7 px right and
  14 x 7 px smaller on every round. Snap / grid / cascade used the whole screen,
  so the bottom rows sat under the taskbar.
* ``wait_for_window`` slept a whole ``poll`` past its timeout, and ``poll=inf``
  raised ``OverflowError``.
"""
import ctypes
import math
import sys
import types

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.window_capture import window_capture
from je_auto_control.utils.window_zorder import window_zorder
from je_auto_control.wrapper import auto_control_window as w

_WINDOWS = sys.platform in ("win32", "cygwin", "msys")
windows_only = pytest.mark.skipif(not _WINDOWS, reason="the Win32 modules import on Windows only")

WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
_SCAN_CODES = {0x0D: 0x1C, 0x1B: 0x01, 0x26: 0x48, 0x41: 0x1E}
_TEXT_KEYS = {0x41: "a"}


class _MessageQueue:
    """``user32`` as far as ``post_key`` uses it, recording what was posted."""

    def __init__(self):
        self.messages = []

    def PostMessageW(self, hwnd, message, w_param, l_param):  # noqa: N802  # reason: Win32 name
        self.messages.append((message, w_param, l_param))
        return 1

    def MapVirtualKeyW(self, keycode, _kind):  # noqa: N802  # reason: Win32 name
        return _SCAN_CODES.get(keycode, 0)

    def GetWindowThreadProcessId(self, hwnd, _pid):  # noqa: N802  # reason: Win32 name
        return 0                      # no GUI thread info: the target is hwnd itself


def _typed(messages):
    """The text an edit control ends up with, as ``TranslateMessage`` would build it.

    A key message for a text key yields a ``WM_CHAR`` when its ``lParam`` says
    the key is going down (bit 31 clear) — for ``WM_KEYUP`` too, which is how a
    key-up posted with ``lParam=0`` typed a second copy.
    """
    text = ""
    for message, w_param, l_param in messages:
        if message == WM_CHAR:
            text += chr(w_param)
        elif message in (WM_KEYDOWN, WM_KEYUP) and not l_param & 0x80000000:
            text += _TEXT_KEYS.get(w_param, "")
    return text


@pytest.fixture
def queue(monkeypatch):
    from je_auto_control.windows.window import windows_window_manage as module
    fake = _MessageQueue()
    monkeypatch.setattr(module, "_user32", fake)
    return fake


# --- post_key ----------------------------------------------------------------

@windows_only
def test_a_printable_key_is_typed_once(queue):
    from je_auto_control.windows.window import windows_window_manage as module
    assert module.post_key(5, 0x41, "a") is True
    assert _typed(queue.messages) == "a"
    assert [message for message, _w, _l in queue.messages] == [WM_CHAR]


@windows_only
def test_a_control_key_is_one_press_and_one_release(queue):
    from je_auto_control.windows.window import windows_window_manage as module
    assert module.post_key(5, 0x0D) is True
    (down, down_key, down_l), (up, up_key, up_l) = queue.messages
    assert (down, down_key, up, up_key) == (WM_KEYDOWN, 0x0D, WM_KEYUP, 0x0D)
    assert down_l == 1 | (0x1C << 16), "repeat count 1 and the scan code"
    assert up_l == 0xC0000001 | (0x1C << 16), "previous-state and transition bits set"


@windows_only
def test_a_virtual_key_that_is_text_is_typed_once_too(queue):
    """An int key carries no character: the key-down types it, the key-up must not."""
    from je_auto_control.windows.window import windows_window_manage as module
    module.post_key(5, 0x41)
    assert _typed(queue.messages) == "a"


@windows_only
def test_an_arrow_key_carries_the_extended_bit(queue):
    from je_auto_control.windows.window import windows_window_manage as module
    module.post_key(5, 0x26)
    assert all(l_param & (1 << 24) for _message, _w, l_param in queue.messages)


class _PostBackend:
    def __init__(self):
        self.posted = []

    def list_windows(self):
        return [(11, "Editor")]

    def post_key(self, window_id, keycode, character=""):
        self.posted.append((window_id, keycode, character))
        return True


@pytest.mark.parametrize("name, expected", [
    ("enter", (11, 13, "")), ("return", (11, 13, "")), ("ENTER", (11, 13, "")),
    ("esc", (11, 27, "")), ("escape", (11, 27, "")), ("a", (11, 65, "a")),
])
def test_post_key_to_window_takes_every_spelling_of_a_key(monkeypatch, name, expected):
    """The Windows table says ``return`` / ``escape``; ``enter`` / ``esc`` raised."""
    from je_auto_control.wrapper import platform_wrapper
    backend = _PostBackend()
    monkeypatch.setattr(w, "get_backend", lambda: backend)
    monkeypatch.setattr(platform_wrapper, "keyboard_keys_table",
                        {"return": 13, "escape": 27, "a": 65}, raising=False)
    assert w.post_key_to_window("Editor", name) is True
    assert backend.posted == [expected]


def test_an_unknown_key_name_is_still_refused(monkeypatch):
    from je_auto_control.wrapper import platform_wrapper
    monkeypatch.setattr(w, "get_backend", _PostBackend)
    monkeypatch.setattr(platform_wrapper, "keyboard_keys_table", {"return": 13}, raising=False)
    with pytest.raises(AutoControlActionException, match="unknown key name"):
        w.post_key_to_window("Editor", "no_such_key")


# --- focus / show / z-order --------------------------------------------------

class _FocusBackend:
    """A desktop whose foreground lock refuses unless ``allow`` is set."""

    confirms_foreground = True

    def __init__(self, allow):
        self.allow = allow
        self.foreground = 99
        self.show_result = None

    def list_windows(self):
        return [(11, "Editor")]

    def is_minimized(self, window_id):
        return False

    def set_foreground(self, window_id):
        if self.allow:
            self.foreground = window_id

    def foreground_window(self):
        return self.foreground

    def show(self, window_id, cmd_show):
        return self.show_result


def test_foreground_failure_propagates(monkeypatch):
    backend = _FocusBackend(allow=False)
    monkeypatch.setattr(w, "get_backend", lambda: backend)
    monkeypatch.setattr(w, "_FOCUS_SETTLE_S", 0.05)
    with pytest.raises(AutoControlActionException, match="did not become the foreground"):
        w.focus_window("Editor")


def test_a_backend_that_cannot_confirm_the_foreground_is_not_second_guessed(monkeypatch):
    # macOS and X11 may report the foreground window under another id; a
    # mismatch there is not evidence that the request was refused.
    backend = _FocusBackend(allow=False)
    backend.confirms_foreground = False
    monkeypatch.setattr(w, "get_backend", lambda: backend)
    assert w.focus_window("Editor") == 11


def test_focus_window_returns_the_handle_once_it_is_in_front(monkeypatch):
    backend = _FocusBackend(allow=True)
    monkeypatch.setattr(w, "get_backend", lambda: backend)
    assert w.focus_window("Editor") == 11


@pytest.mark.parametrize("backend_answer, expected", [(False, False), (True, True), (None, True)])
def test_show_window_by_title_reports_the_backends_answer(monkeypatch, backend_answer, expected):
    """``None`` is a backend that cannot tell, which is not a failure."""
    backend = _FocusBackend(allow=True)
    backend.show_result = backend_answer
    monkeypatch.setattr(w, "get_backend", lambda: backend)
    assert w.show_window_by_title("Editor", 3) is expected


def _user32(**functions):
    return types.SimpleNamespace(**functions)


@windows_only
@pytest.mark.parametrize("accepted", [0, 1])
def test_set_foreground_window_returns_what_windows_said(monkeypatch, accepted):
    from je_auto_control.windows.window import windows_window_manage as module
    monkeypatch.setattr(module, "_user32", _user32(SetForegroundWindow=lambda hwnd: accepted))
    assert module.set_foreground_window(7) is bool(accepted)


@windows_only
def test_show_window_reports_a_dead_handle_and_a_refused_activation(monkeypatch):
    from je_auto_control.windows.window import windows_window_manage as module
    shown = []
    fake = _user32(IsWindow=lambda hwnd: 0, ShowWindow=lambda hwnd, cmd: shown.append(cmd),
                   SetForegroundWindow=lambda hwnd: 0)
    monkeypatch.setattr(module, "_user32", fake)
    assert module.show_window(7, 3) is False and shown == [], "not a window: nothing shown"
    fake.IsWindow = lambda hwnd: 1
    assert module.show_window(7, 3) is False, "maximised but refused the foreground"
    assert module.show_window(7, 6) is True, "minimising does not need the foreground"
    assert shown == [3, 6]


@windows_only
@pytest.mark.parametrize("win32_result", [0, 1])
def test_zorder_reports_what_set_window_pos_said(monkeypatch, win32_result):
    from je_auto_control.windows.window import windows_window_manage as module
    seen = []
    monkeypatch.setattr(module, "_user32", _user32(
        SetWindowPos=lambda hwnd, after, *rest: seen.append((hwnd, after)) or win32_result))
    monkeypatch.setattr(w, "find_window", lambda title, case_sensitive=False: (11, "Editor"))
    assert window_zorder.set_topmost("Editor") is bool(win32_result)
    assert seen == [(11, -1)]


# --- listing -----------------------------------------------------------------

class _Desktop:
    """``user32`` + ``dwmapi`` for window enumeration: ``hwnd -> (title, rect, cloaked)``."""

    def __init__(self, windows):
        self.windows = windows

    def EnumWindows(self, callback, l_param):  # noqa: N802  # reason: Win32 name
        for hwnd in self.windows:
            callback(hwnd, l_param)
        return 1

    def IsWindowVisible(self, hwnd):  # noqa: N802  # reason: Win32 name
        return 1

    def GetWindowTextLengthW(self, hwnd):  # noqa: N802  # reason: Win32 name
        return len(self.windows[hwnd][0])

    def GetWindowTextW(self, hwnd, buffer, _size):  # noqa: N802  # reason: Win32 name
        buffer.value = self.windows[hwnd][0]
        return len(buffer.value)

    def GetWindowRect(self, hwnd, reference):  # noqa: N802  # reason: Win32 name
        rect = reference._obj
        rect.left, rect.top, rect.right, rect.bottom = self.windows[hwnd][1]
        return 1

    def DwmGetWindowAttribute(self, hwnd, _attribute, reference, _size):  # noqa: N802  # reason: Win32 name
        reference._obj.value = self.windows[hwnd][2]
        return 0


@windows_only
def test_cloaked_window_filtered(monkeypatch):
    from je_auto_control.windows.window import windows_window_manage as module
    desktop = _Desktop({
        1: ("Editor", (0, 0, 800, 600), 0),
        2: ("Settings", (0, 0, 800, 600), 2),            # DWM_CLOAKED_SHELL
        3: ("Windows Input Experience", (0, 0, 0, 0), 0),
        4: ("Browser", (-1920, 0, -1000, 500), 0),       # on a monitor to the left
    })
    monkeypatch.setattr(module, "_user32", desktop)
    monkeypatch.setattr(module, "_dwmapi", desktop)
    assert module.get_all_window_hwnd() == [(1, "Editor"), (4, "Browser")]


@windows_only
def test_listing_survives_a_system_without_dwm(monkeypatch):
    from je_auto_control.windows.window import windows_window_manage as module
    monkeypatch.setattr(module, "_user32", _Desktop({1: ("Editor", (0, 0, 800, 600), 9)}))
    monkeypatch.setattr(module, "_dwmapi", None)
    assert module.get_all_window_hwnd() == [(1, "Editor")]


# --- layout ------------------------------------------------------------------

_BORDER = 7           # the invisible resize border of a Windows 10 / 11 window


class _Window:
    """One window as Win32 sees it: ``MoveWindow`` and ``GetWindowRect`` agree."""

    def __init__(self, x, y, width, height):
        self.rect = (x, y, width, height)

    def win32(self):
        """``ctypes.windll`` reading this window: the DWM frame is inside the rect."""
        def get_window_rect(_hwnd, reference):
            x, y, width, height = self.rect
            rect = reference._obj
            rect.left, rect.top, rect.right, rect.bottom = x, y, x + width, y + height
            return 1

        def frame_bounds(_hwnd, _attribute, reference, _size):
            x, y, width, height = self.rect
            rect = reference._obj
            rect.left, rect.top = x + _BORDER, y
            rect.right, rect.bottom = x + width - _BORDER, y + height - _BORDER
            return 0

        return types.SimpleNamespace(
            user32=types.SimpleNamespace(IsIconic=lambda hwnd: 0, GetWindowRect=get_window_rect),
            dwmapi=types.SimpleNamespace(DwmGetWindowAttribute=frame_bounds))


@windows_only
def test_capture_does_not_move_window(monkeypatch):
    """Saving and restoring a layout, three times over, leaves the window where it was."""
    window = _Window(100, 50, 800, 600)
    monkeypatch.setattr(ctypes, "windll", window.win32())

    def move(_title, x, y, width, height):
        window.rect = (x, y, width, height)
        return True

    for _round in range(3):
        layout = window_capture.save_window_layout(lister=lambda: [(1, "Editor")])
        assert window_capture.restore_window_layout(layout, mover=move) == 1
    assert window.rect == (100, 50, 800, 600)


@windows_only
def test_a_window_capture_still_takes_the_visible_frame(monkeypatch):
    monkeypatch.setattr(ctypes, "windll", _Window(100, 50, 800, 600).win32())
    assert window_capture._win32_geometry(1) == (107, 50, 786, 593)
    assert window_capture._win32_window_rect(1) == (100, 50, 800, 600)


@windows_only
def test_a_minimised_window_is_not_saved(monkeypatch):
    fake = _Window(-32000, -32000, 160, 28).win32()
    fake.user32.IsIconic = lambda hwnd: 1
    monkeypatch.setattr(ctypes, "windll", fake)
    assert window_capture.save_window_layout(lister=lambda: [(1, "Editor")]) == []


def _moves():
    seen = []

    def move(title, x, y, width, height):
        seen.append((x, y, width, height))
        return True

    return seen, move


@pytest.fixture
def work_area(monkeypatch):
    """A 1920 x 1080 screen with a 48 px taskbar along the bottom."""
    monkeypatch.setattr(window_capture, "_default_work_area", lambda: (0, 0, 1920, 1032))


def test_snap_stays_above_the_taskbar(work_area):
    seen, move = _moves()
    assert window_capture.snap_window("Editor", "bottom", mover=move)
    assert window_capture.snap_window("Editor", "max", mover=move)
    assert seen == [(0, 516, 1920, 516), (0, 0, 1920, 1032)]


def test_snap_starts_at_the_work_areas_corner():
    """A taskbar on the left or top moves the origin, not just the size."""
    seen, move = _moves()
    window_capture.snap_window("Editor", "left", mover=move, work_area=lambda: (60, 0, 1860, 1080))
    assert seen == [(60, 0, 930, 1080)]


def test_grid_and_cascade_stay_above_the_taskbar(work_area):
    seen, move = _moves()
    assert window_capture.arrange_grid(["a", "b", "c", "d"], mover=move) == 4
    assert window_capture.arrange_cascade(["a", "b"], mover=move) == 2
    assert max(y + height for _x, y, _width, height in seen) <= 1032
    assert (960, 516, 960, 516) in seen, "the bottom-right cell ends at the work area"


def test_an_injected_screen_size_still_means_that_size_at_the_origin(work_area):
    seen, move = _moves()
    window_capture.snap_window("Editor", "bottom", mover=move, screen_size=lambda: (1000, 800))
    assert seen == [(0, 400, 1000, 400)]


@windows_only
def test_the_work_area_comes_from_system_parameters_info(monkeypatch):
    def system_parameters_info(action, _param, reference, _flags):
        rect = reference._obj
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, 1920, 1032
        return 1 if action == 0x0030 else 0

    fake = types.SimpleNamespace(user32=types.SimpleNamespace(
        SystemParametersInfoW=system_parameters_info))
    monkeypatch.setattr(ctypes, "windll", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    assert window_capture._default_work_area() == (0, 0, 1920, 1032)


def test_without_a_work_area_the_whole_screen_is_used(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(window_capture, "_default_screen_size", lambda: (1280, 720))
    assert window_capture._default_work_area() == (0, 0, 1280, 720)


# --- waiting -----------------------------------------------------------------

class _Clock:
    """``time`` for the wrapper: sleeping advances it and nothing really waits."""

    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = _Clock()
    monkeypatch.setattr(w, "time", fake)
    monkeypatch.setattr(w, "find_window", lambda title, case_sensitive=False: None)
    return fake


def test_poll_is_bounded(clock):
    """``poll=30`` with ``timeout=1`` slept 30 seconds before giving up."""
    with pytest.raises(AutoControlActionException, match="timeout"):
        w.wait_for_window("never", timeout=1.0, poll=30)
    assert sum(clock.sleeps) == pytest.approx(1.0)
    assert max(clock.sleeps) <= 1.0


def test_an_infinite_poll_does_not_overflow(clock):
    with pytest.raises(AutoControlActionException, match="timeout"):
        w.wait_for_window("never", timeout=2.0, poll=math.inf)
    assert sum(clock.sleeps) == pytest.approx(2.0)


def test_a_short_poll_still_polls_at_its_own_pace(clock):
    with pytest.raises(AutoControlActionException):
        w.wait_for_window("never", timeout=1.0, poll=0.25)
    assert clock.sleeps[0] == pytest.approx(0.25)
    assert sum(clock.sleeps) == pytest.approx(1.0)
