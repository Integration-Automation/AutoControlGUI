"""Key aliases, the added Windows keys, and the canonical reverse lookup.

``keyboard_key_name`` answers "which name does this virtual key have?" for
recorders. Aliases resolve to the same code but must never be the answer, or
adding one would change the key names a recording writes. Reads tables only;
no key is sent. No Qt imports.
"""
import re
import sys

import pytest

import je_auto_control as ac
from je_auto_control.wrapper import auto_control_keyboard
from je_auto_control.wrapper import platform_wrapper

windows_only = pytest.mark.skipif(not sys.platform.startswith("win"),
                                  reason="the Win32 virtual-key table loads on Windows only")

#: Microsoft "Virtual-Key Codes (Winuser.h)" for the keys added here.
_ADDED_WINDOWS_KEYS = {
    "browser_home": 0xAC, "launch_app2": 0xB7,
    "oem_1": 0xBA, "oem_plus": 0xBB, "oem_comma": 0xBC, "oem_minus": 0xBD,
    "oem_period": 0xBE, "oem_2": 0xBF, "oem_3": 0xC0, "oem_4": 0xDB,
    "oem_5": 0xDC, "oem_6": 0xDD, "oem_7": 0xDE, "oem_8": 0xDF,
    "oem_102": 0xE2, "oem_clear": 0xFE,
}

#: What a recorder must keep writing for keys that gained aliases: the name a
#: shortest-lower-case lookup picked before any alias existed.
_CANONICAL_BEFORE_ALIASES = {
    0x11: "control", 0xA2: "lcontrol", 0xA3: "rcontrol",
    0x12: "menu", 0xA4: "lmenu", 0xA5: "rmenu",
    0x0D: "return", 0x1B: "escape", 0x5B: "lwin", 0x08: "back",
    0x2E: "delete", 0x2D: "insert", 0x21: "prior", 0x22: "next",
    0x14: "capital", 0x2C: "snapshot", 0x91: "scroll",
    **{0x60 + digit: f"num{digit}" for digit in range(10)},
    0x28: "down", 0x41: "a",
}


def _shortest_lower_case(table, code, skip=()):
    names = [name for name, value in table.items() if value == code and name not in skip]
    return min(names, key=lambda name: (name != name.lower(), len(name), name), default=None)


# --- the Windows table -------------------------------------------------------

@windows_only
@pytest.mark.parametrize("name, code", sorted(_ADDED_WINDOWS_KEYS.items()))
def test_the_added_keys_carry_microsofts_codes(name, code):
    assert platform_wrapper.keyboard_keys_table[name] == code


@windows_only
def test_the_upper_case_launch_app2_spelling_stays():
    assert platform_wrapper.keyboard_keys_table["LAUNCH_APP2"] == 0xB7


@windows_only
def test_every_alias_resolves_to_its_targets_code():
    table = platform_wrapper.keyboard_keys_table
    aliases = platform_wrapper.keyboard_key_aliases
    assert len(aliases) >= 40, "the alias map is empty; the checks below would pass vacuously"
    # Names resolved through the keyboard layout answer differently per
    # machine; test_windows_layout_key_aliases.py covers them with a fake.
    layout_names = set(table.layout_names())
    for alias, target in aliases.items():
        assert target in table, (alias, target)
        assert target not in aliases, (alias, target)
        if alias in layout_names:
            continue
        assert table[alias] == table[target], alias
        assert auto_control_keyboard._resolve_keycode(alias) == table[target], alias


@windows_only
@pytest.mark.parametrize("alias, target", [
    ("ctrl", "control"), ("alt", "menu"), ("enter", "return"), ("esc", "escape"),
    ("win", "lwin"), ("backspace", "back"), ("del", "delete"), ("pgup", "prior"),
    ("pagedown", "next"), ("capslock", "capital"), ("prtsc", "snapshot"),
    ("numpad5", "num5"), ("plus", "oem_plus"), ("period", "oem_period"),
])
def test_common_aliases(alias, target):
    assert platform_wrapper.keyboard_key_aliases[alias] == target


@windows_only
def test_every_name_is_typable_except_the_legacy_capitals():
    """Callers lower-case what a user types; every added name survives that."""
    typable = re.compile(r"[a-z0-9_]+")
    added = set(_ADDED_WINDOWS_KEYS) | set(platform_wrapper.keyboard_key_aliases)
    assert all(typable.fullmatch(name) for name in added)


@windows_only
def test_layout_dependent_oem_keys_get_no_fixed_alias():
    """``oem_1`` is ";" on a US layout only; a fixed "semicolon" would lie.

    The only aliases that may land on such a key are the ones the table
    resolves through the keyboard layout when they are looked up.
    """
    layout_bound = {0xBA, 0xBF, 0xC0, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF, 0xE2}
    table = platform_wrapper.keyboard_keys_table
    layout_names = set(table.layout_names())
    stored = dict(table)                        # the static codes, no layout lookup
    for alias in platform_wrapper.keyboard_key_aliases:
        if alias not in layout_names:
            assert stored[alias] not in layout_bound, alias


# --- reverse lookup: canonical names only ----------------------------------------

@windows_only
@pytest.mark.parametrize("code, name", sorted(_CANONICAL_BEFORE_ALIASES.items()))
def test_reverse_lookup_keeps_the_pre_alias_name(code, name):
    assert ac.keyboard_key_name(code) == name


@windows_only
def test_no_alias_changes_any_reverse_lookup():
    """For every code, the answer is the old lookup over the table minus aliases."""
    table = platform_wrapper.keyboard_keys_table
    aliases = platform_wrapper.keyboard_key_aliases
    for code in set(table.values()):
        assert ac.keyboard_key_name(code) == _shortest_lower_case(table, code, aliases), hex(code)


@windows_only
def test_reverse_lookup_names_the_added_keys():
    for name, code in _ADDED_WINDOWS_KEYS.items():
        assert ac.keyboard_key_name(code) == name
    assert ac.keyboard_key_name(0xFC) is None          # VK_NONAME: no entry


def test_the_preference_order_on_a_synthetic_table(monkeypatch):
    """Platform-independent: aliases lose, then untypable names, then length, then order."""
    monkeypatch.setattr(auto_control_keyboard, "keyboard_keys_table", {
        "esc": 27, "escape": 27,              # alias vs canonical
        "\b": 8, "backspace": 8,              # untypable vs typable
        "LAUNCH_APP2": 183, "launch_app2": 183,
        "vk_down": 40, "down": 40,            # length
        "next": 34, "pgdn": 34,               # same length: alphabetical
        "only_alias": 99,
    })
    monkeypatch.setattr(auto_control_keyboard, "keyboard_key_aliases",
                        {"esc": "escape", "pgdn": "next", "only_alias": "x"})
    name = auto_control_keyboard.keyboard_key_name
    assert [name(27), name(8), name(183), name(40), name(34)] == [
        "escape", "backspace", "launch_app2", "down", "next"]
    assert name(99) is None
    assert name(12345) is None


def test_every_platform_publishes_an_alias_map():
    aliases = platform_wrapper.keyboard_key_aliases
    assert isinstance(aliases, dict)
    assert all(alias in platform_wrapper.keyboard_keys_table for alias in aliases)


def test_facade_export():
    assert "keyboard_key_name" in ac.__all__
    assert callable(ac.keyboard_key_name)
