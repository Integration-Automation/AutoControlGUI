"""Headless tests for key-to-character translation. No Qt, no real keyboard."""
import je_auto_control as ac
from je_auto_control.utils.keyboard_layout import keyboard_layout as kl


def test_us_fallback_covers_letters_digits_and_punctuation():
    # Letters and digits are the same on every Latin layout; punctuation is
    # exactly what differs, which is why the OS is asked first.
    assert kl.US_PRINTABLE_VK[0x41] == ("a", "A")
    assert kl.US_PRINTABLE_VK[0x31] == ("1", "!")
    assert kl.US_PRINTABLE_VK[0xBC] == (",", "<")


def test_char_table_prefers_the_layout_over_the_fallback(monkeypatch):
    # A layout that reports a different punctuation key must win, or every
    # comma recorded on a non-US keyboard is mislabelled.
    monkeypatch.setattr(kl, "layout_char_table", lambda layout=None: {0xBC: (";", ":")})
    table = kl.char_table()
    assert table[0xBC] == (";", ":")
    assert table[0x41] == ("a", "A")      # untouched keys still come from US


def test_char_table_falls_back_when_the_os_says_nothing(monkeypatch):
    monkeypatch.setattr(kl, "layout_char_table", lambda layout=None: {})
    assert kl.char_table()[0xBC] == (",", "<")


def test_vk_to_char_picks_the_shifted_half():
    table = {0x41: ("a", "A")}
    assert kl.vk_to_char(0x41, False, table) == "a"
    assert kl.vk_to_char(0x41, True, table) == "A"
    assert kl.vk_to_char(0x99, False, table) is None


def test_layout_table_is_empty_off_windows(monkeypatch):
    monkeypatch.setattr(kl.sys, "platform", "linux")
    assert kl.layout_char_table(12345) == {}
    assert kl.foreground_keyboard_layout() is None


def test_facade_exports():
    for attr in ("char_table", "vk_to_char", "layout_char_table",
                 "foreground_keyboard_layout"):
        assert hasattr(ac, attr) and attr in ac.__all__
