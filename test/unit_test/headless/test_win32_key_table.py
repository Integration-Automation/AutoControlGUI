"""The Windows ``keyboard_keys_table`` holds virtual-key codes and nothing else.

The table used to be built from every constant in ``win32_vk.py``, including
the ``MOUSEEVENTF_*`` flags, the ``KEYEVENTF_*`` flags and a ``MapVirtualKey``
type. None of those are keys, but their values collide with real ones, so the
names typed something unrelated: ``down`` was ``MOUSEEVENTF_XDOWN`` (0x80) and
pressed F17 instead of the Down arrow, while ``middledown`` pressed space. Linux
and macOS have always mapped ``down`` to the arrow key.

Reads the table only; no key is sent.
"""
import sys

import pytest

if not sys.platform.startswith("win"):        # pragma: no cover
    pytest.skip("Win32 virtual-key table", allow_module_level=True)

from je_auto_control.windows.core.utils import win32_vk  # noqa: E402
from je_auto_control.wrapper.platform_wrapper import (  # noqa: E402
    keyboard_keys_table,
)

#: Names that were in the table without being keys. They must stay out.
_NOT_KEYS = ("absolute", "eventf_extendedkey", "eventf_keyup",
             "eventf_scancode", "eventf_unicode", "hwheel", "leftdown",
             "leftup", "middledown", "middleup", "move", "rightdown",
             "rightup", "xbutton1", "xbutton2", "vktovsc", "wheel", "xup")


@pytest.mark.parametrize("name, vk", [
    ("down", win32_vk.WIN32_VK_DOWN), ("up", win32_vk.WIN32_VK_UP),
    ("left", win32_vk.WIN32_VK_LEFT), ("right", win32_vk.WIN32_VK_RIGHT),
])
def test_arrow_names_are_the_arrow_keys(name, vk):
    assert keyboard_keys_table[name] == vk


def test_down_is_not_f17():
    assert keyboard_keys_table["down"] != keyboard_keys_table["f17"]
    assert keyboard_keys_table["down"] == keyboard_keys_table["vk_down"]


@pytest.mark.parametrize("name", _NOT_KEYS)
def test_non_key_constants_are_not_key_names(name):
    assert name not in keyboard_keys_table


def test_every_value_is_a_virtual_key_code():
    """VK codes are 1..254; the mouse flags reached 0x8000."""
    out_of_range = {name: code for name, code in keyboard_keys_table.items()
                    if not 0x01 <= code <= 0xFE}
    assert not out_of_range
