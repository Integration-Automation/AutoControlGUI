"""Tests for the pure-logic parts of the hotkey daemon."""
import pytest

from je_auto_control.utils.hotkey.hotkey_daemon import (
    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, parse_combo,
)


def test_parse_single_modifier_and_letter():
    modifiers, vk = parse_combo("ctrl+alt+1")
    assert modifiers & MOD_CONTROL
    assert modifiers & MOD_ALT
    assert modifiers & MOD_NOREPEAT
    assert vk == ord("1")


def test_parse_is_case_and_whitespace_insensitive():
    modifiers, vk = parse_combo("  SHIFT +  A  ")
    assert modifiers & MOD_SHIFT
    assert vk == ord("A")


def test_parse_win_aliases():
    mods_win, _ = parse_combo("win+a")
    mods_super, _ = parse_combo("super+a")
    mods_meta, _ = parse_combo("meta+a")
    assert mods_win == mods_super == mods_meta


def test_parse_function_key():
    _, vk = parse_combo("ctrl+f5")
    assert vk == 0x74


def test_parse_rejects_empty():
    with pytest.raises(ValueError):
        parse_combo("")


def test_parse_rejects_two_primary_keys():
    with pytest.raises(ValueError):
        parse_combo("a+b")


def test_parse_rejects_modifier_only():
    with pytest.raises(ValueError):
        parse_combo("ctrl+alt")


def test_parse_rejects_unknown_key_name():
    with pytest.raises(ValueError):
        parse_combo("ctrl+blorp")
