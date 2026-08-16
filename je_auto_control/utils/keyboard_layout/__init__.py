"""What character each key produces on the active keyboard layout."""
from je_auto_control.utils.keyboard_layout.keyboard_layout import (
    US_PRINTABLE_VK, char_table, foreground_keyboard_layout,
    layout_char_table, vk_to_char,
)

__all__ = ["US_PRINTABLE_VK", "char_table", "foreground_keyboard_layout",
           "layout_char_table", "vk_to_char"]
