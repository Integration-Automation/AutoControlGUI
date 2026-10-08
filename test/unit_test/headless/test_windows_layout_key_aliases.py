"""``slash`` and its siblings name a character and follow the keyboard layout.

The Windows key table had no readable name for the layout-dependent ``oem_N``
keys because a fixed alias would be right on a US keyboard only. These names
are resolved when they are looked up: ``VkKeyScanExW`` on the character,
against the foreground window's layout, falling back to the US position when
the layout has no bare key for it.

``user32`` and the layout probe are fakes: no key is sent and the real layout
of the machine running the test does not matter.
"""
import sys

import pytest

from je_auto_control.windows.core.utils import win32_layout_vk
from je_auto_control.windows.core.utils.win32_layout_vk import (
    LAYOUT_KEY_ALIASES, LayoutKeyTable, layout_virtual_key,
)

windows_only = pytest.mark.skipif(not sys.platform.startswith("win"),
                                  reason="the Win32 virtual-key table loads on Windows only")

#: Microsoft "Virtual-Key Codes": the US positions of the eight characters.
_US = {"slash": 0xBF, "backslash": 0xDC, "semicolon": 0xBA, "quote": 0xDE,
       "backquote": 0xC0, "bracketleft": 0xDB, "bracketright": 0xDD, "equal": 0xBB}
_OEM = {"oem_1": 0xBA, "oem_2": 0xBF, "oem_3": 0xC0, "oem_4": 0xDB, "oem_5": 0xDC,
        "oem_6": 0xDD, "oem_7": 0xDE, "oem_plus": 0xBB, "oem_minus": 0xBD}
_US_LAYOUT, _OTHER_LAYOUT = 0x04090409, 0x04070407
_SHIFT = 0x100


class _Function:
    """A ctypes function stand-in: accepts prototypes, records its calls."""

    def __init__(self, answer):
        self._answer = answer
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, character, layout):
        self.calls.append((character, layout))
        return self._answer(character, layout)


class _User32:
    """``user32`` with a ``VkKeyScanExW`` that answers from a per-layout map."""

    def __init__(self, layouts):
        self.VkKeyScanExW = _Function(
            lambda character, layout: layouts.get(layout, {}).get(character, -1))


#: German-like: "/" is Shift+7, "=" is Shift+0, "\\" needs AltGr, "`" is absent;
#: ";" sits on a bare key at another position, and so do the brackets.
_LAYOUTS = {
    _US_LAYOUT: {"/": 0xBF, "\\": 0xDC, ";": 0xBA, "'": 0xDE, "`": 0xC0,
                 "[": 0xDB, "]": 0xDD, "=": 0xBB},
    _OTHER_LAYOUT: {"/": 0x37 | _SHIFT, "=": 0x30 | _SHIFT, "\\": 0xDB | 0x600,
                    ";": 0xBC, "'": 0xBF, "[": 0xDE, "]": 0xBA},
}


@pytest.fixture
def layout(monkeypatch):
    """Fake ``user32`` and layout probe; set ``layout.active`` to switch layouts."""
    user32 = _User32(_LAYOUTS)

    class _State:
        active = _US_LAYOUT
        fake = user32

    monkeypatch.setattr(win32_layout_vk, "_user32", lambda: user32)
    monkeypatch.setattr(win32_layout_vk, "foreground_keyboard_layout", lambda: _State.active)
    return _State


def _table() -> LayoutKeyTable:
    return LayoutKeyTable(dict(_OEM))


# --- the lookup -------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(_US))
def test_on_a_us_layout_each_name_is_its_us_key(layout, name):
    table = _table()
    assert table[name] == _US[name]
    assert table.get(name) == _US[name]


def test_another_layout_gives_the_key_that_types_the_character(layout):
    layout.active = _OTHER_LAYOUT
    table = _table()
    assert table["semicolon"] == 0xBC       # not oem_1
    assert table.get("quote") == 0xBF
    assert table["bracketleft"] == 0xDE
    assert table["bracketright"] == 0xBA


@pytest.mark.parametrize("name", ["slash", "equal", "backslash", "backquote"],
                         ids=["shift", "shift-digit", "altgr", "absent"])
def test_a_character_with_no_bare_key_falls_back_to_the_us_position(layout, name):
    layout.active = _OTHER_LAYOUT
    assert _table()[name] == _US[name]
    assert _table().get(name) == _US[name]


def test_the_layout_is_asked_at_every_lookup_not_once(layout):
    table = _table()
    assert table["semicolon"] == 0xBA
    layout.active = _OTHER_LAYOUT           # the user switches layout mid-run
    assert table["semicolon"] == 0xBC
    assert layout.fake.VkKeyScanExW.calls == [(";", _US_LAYOUT), (";", _OTHER_LAYOUT)]


def test_the_prototype_is_declared_before_the_call(layout):
    import ctypes
    from ctypes import wintypes
    assert layout_virtual_key("/") == 0xBF
    function = layout.fake.VkKeyScanExW
    assert function.argtypes == [wintypes.WCHAR, wintypes.HKL]
    assert function.restype is ctypes.c_short


def test_no_layout_means_the_us_position(layout):
    layout.active = None                    # the probe failed, or this is not Windows
    assert _table()["slash"] == 0xBF
    assert layout.fake.VkKeyScanExW.calls == []


@pytest.mark.parametrize("error", [OSError("no user32"), AttributeError("no WinDLL"),
                                   ValueError("bad argument")])
def test_a_failing_user32_means_the_us_position(layout, monkeypatch, error):
    def broken():
        raise error

    monkeypatch.setattr(win32_layout_vk, "_user32", broken)
    assert layout_virtual_key("/") is None
    assert _table()["slash"] == 0xBF


def test_a_zero_virtual_key_is_not_an_answer(layout, monkeypatch):
    monkeypatch.setitem(_LAYOUTS[_US_LAYOUT], "/", 0)
    assert layout_virtual_key("/") is None
    assert _table()["slash"] == 0xBF


# --- the table stays a dict -------------------------------------------------

def test_every_other_name_is_untouched_and_never_asks_the_layout(layout):
    table = _table()
    for name, code in _OEM.items():
        assert table[name] == code
        assert table.get(name) == code
    assert table.get("no_such_key") is None
    assert table.get("no_such_key", 7) == 7
    with pytest.raises(KeyError):
        table["no_such_key"]  # noqa: B018  # reason: the lookup is the assertion
    assert table.get(65) is None            # a caller passing a key code, not a name
    assert layout.fake.VkKeyScanExW.calls == []


def test_iteration_shows_the_us_positions_without_asking_the_layout(layout):
    layout.active = _OTHER_LAYOUT
    table = _table()
    assert isinstance(table, dict)
    assert set(table) == set(_OEM) | set(_US)
    assert len(table) == len(_OEM) + len(_US)
    assert {name: table.copy()[name] for name in _US} == _US
    assert dict(table.items())["semicolon"] == 0xBA
    assert "slash" in table
    assert sorted(table.layout_names()) == sorted(_US)
    assert layout.fake.VkKeyScanExW.calls == []


def test_a_name_the_table_already_has_is_kept_as_it_is(layout):
    layout.active = _OTHER_LAYOUT
    table = LayoutKeyTable({**_OEM, "semicolon": 0x99})
    assert table["semicolon"] == 0x99       # existing name: its code, no layout lookup
    assert "semicolon" not in table.layout_names()
    assert table["quote"] == 0xBF           # the others still follow the layout


def test_the_alias_set_is_the_documented_one():
    assert {name: character for name, (character, _us) in LAYOUT_KEY_ALIASES.items()} == {
        "slash": "/", "backslash": "\\", "semicolon": ";", "quote": "'", "backquote": "`",
        "bracketleft": "[", "bracketright": "]", "equal": "="}


# --- the real Windows table --------------------------------------------------

@windows_only
def test_the_platform_table_resolves_the_names_through_the_layout(layout):
    from je_auto_control.wrapper import auto_control_keyboard, platform_wrapper
    table = platform_wrapper.keyboard_keys_table
    assert isinstance(table, LayoutKeyTable)
    for name, code in _US.items():
        assert table[name] == code
        assert auto_control_keyboard._resolve_keycode(name) == code
    layout.active = _OTHER_LAYOUT
    assert auto_control_keyboard._resolve_keycode("semicolon") == 0xBC
    assert auto_control_keyboard._resolve_keycode("slash") == 0xBF      # fallback
    assert auto_control_keyboard._resolve_keycode("oem_1") == 0xBA      # positions do not move


@windows_only
def test_the_platform_aliases_never_answer_a_reverse_lookup(layout):
    import je_auto_control as ac
    from je_auto_control.wrapper import platform_wrapper
    for name, (_character, us_name) in LAYOUT_KEY_ALIASES.items():
        assert platform_wrapper.keyboard_key_aliases[name] == us_name
        assert ac.keyboard_key_name(_US[name]) == us_name       # what a recorder writes
    assert ac.keyboard_key_name(0xBD) == "oem_minus"


@windows_only
def test_every_name_that_existed_before_is_still_there():
    from je_auto_control.wrapper import platform_wrapper
    table = platform_wrapper.keyboard_keys_table
    for name in ("plus", "minus", "comma", "period", "ctrl", "enter", "oem_1", "oem_8",
                 "oem_102", "a", "A", "f24", "LAUNCH_APP2"):
        assert name in table, name
    assert dict(table)["plus"] == 0xBB and dict(table)["minus"] == 0xBD
