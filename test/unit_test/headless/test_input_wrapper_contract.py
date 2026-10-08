"""What the keyboard / mouse wrappers type, scroll and click, pinned on fakes.

The 2026-09-24 audit reproduced each of these against a recording backend:
``write("Hi")`` typed ``hi`` on Windows and X11 (a capital shares its key with
the lower-case letter and nothing held Shift), ``is_shift`` did nothing outside
macOS, CR LF pressed Enter twice, ``mouse_scroll(3)`` went down on X11 and up
everywhere else, a NaN scroll point was clamped to the desktop edge instead of
refused, fractional coordinates were cut toward zero, Unicode typing sent line
breaks and Tab as code points, a dead-key Shift level was labelled with the
unshifted character, and an unnamed clipboard format was called ``"None"``.

Nothing here reaches the real desktop: every backend is a recorder.
"""
import ctypes
import importlib
import inspect
import sys
import types

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlKeyboardException, AutoControlMouseException,
)
from je_auto_control.utils.keyboard_layout import keyboard_layout as kl
from je_auto_control.utils.text_unicode import text_unicode
from je_auto_control.wrapper import auto_control_keyboard as kb
from je_auto_control.wrapper import auto_control_mouse as ms

# The package re-exports a function of the same name, which hides the module.
cf = importlib.import_module("je_auto_control.utils.clipboard_formats.clipboard_formats")

SHIFT, RETURN, TAB = 16, 13, 9
_TABLE = {
    "shift": SHIFT, "return": RETURN, "tab": TAB, "control": 17, "space": 32,
    "back": 8,
    "a": 65, "A": 65, "h": 72, "H": 72, "i": 73, "I": 73, "s": 83, "S": 83,
    "b": 66, "B": 66,
}


class _Keys:
    """A keyboard backend that records key-down / key-up instead of typing."""

    def __init__(self, fail_on=None, unicode=False):
        self.events = []
        self._fail_on = fail_on
        if unicode:
            self.type_unicode_unit = lambda unit: self.events.append(("unit", unit))

    def press_key(self, keycode):
        if keycode == self._fail_on:
            raise OSError("SendInput refused the key")
        self.events.append(("down", keycode))

    def release_key(self, keycode):
        self.events.append(("up", keycode))


def _tap(code):
    return [("down", code), ("up", code)]


def _shifted(code):
    return [("down", SHIFT), *_tap(code), ("up", SHIFT)]


def _use(monkeypatch, backend, platform="win32", table=None):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(kb, "keyboard", backend)
    monkeypatch.setattr(kb, "keyboard_keys_table", dict(table or _TABLE))
    return backend


@pytest.fixture(params=["win32", "linux"])
def keys(request, monkeypatch):
    """The recording backend, once as Windows and once as X11."""
    return _use(monkeypatch, _Keys(), request.param)


# --- case and Shift ---------------------------------------------------------

def test_write_holds_shift_for_a_capital_letter(keys):
    assert kb.write("Hi") == "Hi"
    assert keys.events == _shifted(72) + _tap(73)


def test_write_leaves_lower_case_and_digits_alone(keys):
    kb.write("hi")
    assert keys.events == _tap(72) + _tap(73)


def test_write_shifts_punctuation_only_when_it_shares_its_key(monkeypatch):
    """X11 lists ``!`` under the key of ``1``; ``<`` may have a key of its own."""
    table = {"shift": SHIFT, "1": 10, "!": 10, ",": 59, "<": 94}
    backend = _use(monkeypatch, _Keys(), "linux", table)
    kb.write("1!<")
    assert backend.events == _tap(10) + _shifted(10) + _tap(94)


def test_is_shift_holds_shift_for_one_key(keys):
    kb.type_keyboard("a", is_shift=True)
    assert keys.events == _shifted(65)


def test_is_shift_holds_shift_for_every_key_of_write(keys):
    kb.write("ab", is_shift=True)
    assert keys.events == _shifted(65) + _shifted(66)


def test_is_shift_wraps_the_whole_hotkey(keys):
    kb.hotkey(["control", "s"], is_shift=True)
    assert keys.events == [("down", SHIFT), ("down", 17), ("down", 83),
                           ("up", 83), ("up", 17), ("up", SHIFT)]


def test_a_lone_press_with_is_shift_never_leaves_shift_down(keys):
    kb.press_keyboard_key("a", is_shift=True)
    assert keys.events == [("down", SHIFT), ("down", 65), ("up", SHIFT)]
    keys.events.clear()
    kb.release_keyboard_key("a", is_shift=True)
    assert keys.events == [("up", 65)]


def test_shift_is_released_when_the_key_fails(monkeypatch):
    backend = _use(monkeypatch, _Keys(fail_on=65))
    with pytest.raises(AutoControlKeyboardException):
        kb.write("A")
    assert backend.events == [("down", SHIFT), ("up", SHIFT)]


def test_macos_still_gets_the_flag_and_no_extra_shift_key(monkeypatch):
    events = []
    backend = types.SimpleNamespace(
        press_key=lambda code, is_shift: events.append(("down", code, is_shift)),
        release_key=lambda code, is_shift: events.append(("up", code, is_shift)))
    _use(monkeypatch, backend, "darwin")
    kb.type_keyboard("a", is_shift=True)
    kb.write("A")
    assert events == [("down", 65, True), ("up", 65, True),
                      ("down", 65, False), ("up", 65, False)]


# --- line endings -----------------------------------------------------------

@pytest.mark.parametrize("text", ["a\r\nb", "a\nb", "a\rb"])
def test_one_line_break_is_one_enter(keys, text):
    assert kb.write(text) == text
    assert keys.events == _tap(65) + _tap(RETURN) + _tap(66)


def test_two_line_breaks_are_still_two(keys):
    kb.write("\r\n\r\n")
    assert keys.events == _tap(RETURN) * 2


def test_write_secret_presses_line_breaks_as_keys(monkeypatch):
    backend = _use(monkeypatch, _Keys(unicode=True))
    kb.write_secret("a\r\nb\t")
    assert backend.events == [("unit", 97), *_tap(RETURN), ("unit", 98), *_tap(TAB)]


# --- Unicode typing ---------------------------------------------------------

def test_unicode_plan_presses_control_whitespace_as_keys():
    assert text_unicode.plan_unicode_keys("a\nb\tc") == [
        {"op": "unicode_unit", "unit": 97}, {"op": "key", "key": "return"},
        {"op": "unicode_unit", "unit": 98}, {"op": "key", "key": "tab"},
        {"op": "unicode_unit", "unit": 99}]
    assert text_unicode.plan_unicode_keys("\r\n") == [{"op": "key", "key": "return"}]
    assert kb.WRITE_CONTROL_KEYS is text_unicode.CONTROL_KEYS


def test_the_default_sink_types_a_key_op(monkeypatch):
    typed = []
    monkeypatch.setattr(kb, "type_keyboard", lambda key, *a, **k: typed.append(key))
    text_unicode._default_sink({"op": "key", "key": "return"})
    assert typed == ["return"]


def test_type_unicode_keys_reports_what_it_dispatched():
    events = []
    result = text_unicode.type_unicode_keys("a\n", sink=events.append)
    assert [event["op"] for event in events] == ["unicode_unit", "key"]
    assert result["ops"] == 2 and result["method"] == "keys"


# --- mouse ------------------------------------------------------------------

class _Mouse:
    """A mouse backend that records moves and scrolls."""

    def __init__(self):
        self.moves = []
        self.scrolls = []

    def set_position(self, x, y):
        self.moves.append((x, y))

    def position(self):
        return 5, 5

    def scroll(self, *args):
        self.scrolls.append(args)


@pytest.fixture
def mouse(monkeypatch):
    backend = _Mouse()
    monkeypatch.setattr(ms, "mouse", backend)
    monkeypatch.setattr(ms, "_scroll_bounds", lambda: (-1920, 0, 3840, 1080))
    return backend


def test_coordinates_are_rounded_not_cut_toward_zero(mouse):
    assert ms.set_mouse_position(-0.6, 10.9) == (-1, 11)
    assert mouse.moves == [(-1, 11)]
    assert ms.set_mouse_position(7, "12") == (7, 12)


@pytest.mark.parametrize("point", [
    {"x": float("nan"), "y": 100}, {"x": 100, "y": float("nan")},
    {"x": float("inf"), "y": 100}, {"x": "left", "y": 100},
])
def test_a_scroll_point_that_is_not_a_number_moves_nothing(mouse, point):
    with pytest.raises(AutoControlMouseException):
        ms.mouse_scroll(3, **point)
    assert mouse.moves == [] and mouse.scrolls == []


def test_a_scroll_point_off_the_desktop_is_still_clamped(mouse, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    ms.mouse_scroll(3, x=99999, y=100.4)
    assert mouse.moves == [(1919, 100)] and mouse.scrolls == [(3,)]


def test_a_positive_scroll_goes_up_by_default_on_x11(mouse, monkeypatch):
    up, down = 4, 5
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ms, "special_mouse_keys_table",
                        {"scroll_up": up, "scroll_down": down})
    assert ms.mouse_scroll(3) == (3, up)
    assert ms.mouse_scroll(3, scroll_direction="scroll_down") == (3, down)
    assert mouse.scrolls == [(3, up), (3, down)]


def test_every_scroll_entry_point_shares_the_default():
    from je_auto_control.utils.mcp_server import fake_backend
    from je_auto_control.utils.mcp_server.tools import _handlers_input
    for function in (ms.mouse_scroll, _handlers_input.mouse_scroll,
                     fake_backend._fake_mouse_scroll):
        default = inspect.signature(function).parameters["scroll_direction"].default
        assert default == "scroll_up", function


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows key table")
@pytest.mark.parametrize("name", ["plus", "minus", "comma", "period", "oem_2"])
def test_the_windows_table_has_the_punctuation_keys(name):
    from je_auto_control.wrapper.platform_wrapper import keyboard_keys_table
    assert isinstance(keyboard_keys_table[name], int)


# --- keyboard layout --------------------------------------------------------

def test_a_dead_shift_level_is_none_and_iso_keys_get_a_label():
    """Shift+6 on US-International is a dead key: no character, so ``None``."""
    chars = {(0x36, False): "6", (0x36, True): "",       # dead ^
             (0xE2, False): "<", (0xE2, True): ">",      # OEM_102
             (0xDF, False): "`", (0xDF, True): "¬",      # OEM_8 (UK)
             (0x41, False): "a", (0x41, True): "A"}
    table = kl._build_table(lambda vk, shifted: chars.get((vk, shifted), ""))
    assert table == {0x36: ("6", None), 0xE2: ("<", ">"),
                     0xDF: ("`", "¬"), 0x41: ("a", "A")}
    assert kl.vk_to_char(0x36, True, table) is None
    assert kl.vk_to_char(0x36, False, table) == "6"


class _FakeUser32:
    """``ToUnicodeEx`` for a layout whose Shift+6 is a dead key."""

    def __init__(self):
        self.ToUnicodeEx = self._to_unicode
        self.MapVirtualKeyExW = lambda vk, kind, layout: vk

    @staticmethod
    def _to_unicode(vk, _scan, state, buffer, _size, _flags, _layout):
        shifted = state[0x10] != b"\x00"
        if vk == 0x36 and shifted:
            return -1
        if 0x30 <= vk <= 0x39 and not shifted:
            buffer.value = chr(vk)
            return 1
        return 0


def test_the_layout_table_is_built_on_a_private_handle(monkeypatch):
    fake = _FakeUser32()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(kl, "_user32", lambda: fake)
    monkeypatch.setattr(kl, "_LAYOUT_CACHE", {})
    table = kl.layout_char_table(0x04090409)
    assert table[0x36] == ("6", None) and table[0x31] == ("1", None)


@pytest.mark.skipif(sys.platform != "win32", reason="ctypes.windll is Windows-only")
def test_the_shared_user32_keeps_its_prototypes():
    """Another caller's ``c_ubyte`` key-state array must still be accepted."""
    shared = ctypes.windll.user32
    assert kl._user32() is not shared
    before = shared.ToUnicodeEx.argtypes
    kl._translator(kl._user32(), 0x04090409)
    assert shared.ToUnicodeEx.argtypes == before


# --- clipboard formats ------------------------------------------------------

def test_an_unnamed_format_is_the_same_in_every_form():
    for item in ((49161, None), [49161, None], {"id": 49161, "name": None}, 49161):
        assert cf._coerce(item) == (49161, "")
    diff = cf.diff_formats([(13, None)], [{"id": 13, "name": None}])
    assert diff == {"added": [], "removed": [], "changed": False}
