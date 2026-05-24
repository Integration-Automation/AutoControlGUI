"""Wayland keyboard mapping: friendly name → evdev key code.

ydotool speaks raw Linux evdev key codes (those declared in
``/usr/include/linux/input-event-codes.h``). This module names every
code the AutoControl wrappers exercise so the Wayland backend can
build a parallel ``keyboard_keys_table`` while keeping the public API
identical to the X11 backend.

Only the subset AutoControl actually uses is listed — extending the
map is just one more ``"name": code`` entry.
"""
from __future__ import annotations

from typing import Dict


# Modifier / control keys ----------------------------------------------
KEY_ESC = 1
KEY_BACKSPACE = 14
KEY_TAB = 15
KEY_ENTER = 28
KEY_LEFTCTRL = 29
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
KEY_LEFTALT = 56
KEY_SPACE = 57
KEY_CAPSLOCK = 58
KEY_F1 = 59
KEY_NUMLOCK = 69
KEY_SCROLLLOCK = 70
KEY_RIGHTCTRL = 97
KEY_RIGHTALT = 100
KEY_HOME = 102
KEY_UP = 103
KEY_PAGEUP = 104
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_END = 107
KEY_DOWN = 108
KEY_PAGEDOWN = 109
KEY_INSERT = 110
KEY_DELETE = 111
KEY_PAUSE = 119
KEY_LEFTMETA = 125
KEY_RIGHTMETA = 126
KEY_COMPOSE = 127
KEY_PRINT = 99
KEY_HELP = 138


def _function_keys(start_code: int = KEY_F1) -> Dict[str, int]:
    """``f1`` .. ``f10`` are contiguous from KEY_F1 = 59. ``f11`` / ``f12``
    live at 87 / 88, then ``f13`` .. ``f24`` start at 183.
    """
    table: Dict[str, int] = {}
    for offset in range(10):
        table[f"f{offset + 1}"] = start_code + offset
    table["f11"] = 87
    table["f12"] = 88
    for offset in range(12):
        table[f"f{13 + offset}"] = 183 + offset
    return table


def _numpad_keys() -> Dict[str, int]:
    return {
        "num0": 82, "num1": 79, "num2": 80, "num3": 81,
        "num4": 75, "num5": 76, "num6": 77,
        "num7": 71, "num8": 72, "num9": 73,
        "multiply": 55, "add": 78, "subtract": 74,
        "decimal": 83, "divide": 98,
        "separator": 95,
    }


def _alpha_keys() -> Dict[str, int]:
    # KEY_A..KEY_Z map to keyboard scan codes, not 'A'..'Z' positions.
    rows = (
        "qwertyuiop",   # 16..25
        "asdfghjkl",    # 30..38
        "zxcvbnm",      # 44..50
    )
    base_codes = (16, 30, 44)
    table: Dict[str, int] = {}
    for row, base in zip(rows, base_codes):
        for index, char in enumerate(row):
            table[char] = base + index
            table[char.upper()] = base + index
    return table


def _digit_keys() -> Dict[str, int]:
    # "1" .. "9" → 2 .. 10, "0" → 11
    return {**{str(d): 1 + d for d in range(1, 10)}, "0": 11}


def _build_table() -> Dict[str, int]:
    table: Dict[str, int] = {
        "backspace": KEY_BACKSPACE,
        "\b": KEY_BACKSPACE,
        "tab": KEY_TAB,
        "enter": KEY_ENTER,
        "return": KEY_ENTER,
        "shift": KEY_LEFTSHIFT,
        "shiftleft": KEY_LEFTSHIFT,
        "shiftright": KEY_RIGHTSHIFT,
        "ctrl": KEY_LEFTCTRL,
        "ctrlleft": KEY_LEFTCTRL,
        "ctrlright": KEY_RIGHTCTRL,
        "alt": KEY_LEFTALT,
        "altleft": KEY_LEFTALT,
        "altright": KEY_RIGHTALT,
        "esc": KEY_ESC,
        "space": KEY_SPACE,
        "capslock": KEY_CAPSLOCK,
        "numlock": KEY_NUMLOCK,
        "scrolllock": KEY_SCROLLLOCK,
        "pause": KEY_PAUSE,
        "home": KEY_HOME,
        "end": KEY_END,
        "pgup": KEY_PAGEUP,
        "pgdn": KEY_PAGEDOWN,
        "pageup": KEY_PAGEUP,
        "pagedown": KEY_PAGEDOWN,
        "left": KEY_LEFT,
        "right": KEY_RIGHT,
        "up": KEY_UP,
        "down": KEY_DOWN,
        "insert": KEY_INSERT,
        "del": KEY_DELETE,
        "delete": KEY_DELETE,
        "print": KEY_PRINT,
        "prtsc": KEY_PRINT,
        "prtscr": KEY_PRINT,
        "prntscrn": KEY_PRINT,
        "win": KEY_LEFTMETA,
        "winleft": KEY_LEFTMETA,
        "winright": KEY_RIGHTMETA,
        "apps": KEY_COMPOSE,
        "help": KEY_HELP,
        "\n": KEY_ENTER,
        "\r": KEY_ENTER,
        "\t": KEY_TAB,
    }
    table.update(_function_keys())
    table.update(_numpad_keys())
    table.update(_alpha_keys())
    table.update(_digit_keys())
    return table


keyboard_keys_table: Dict[str, int] = _build_table()


__all__ = ["keyboard_keys_table"]
