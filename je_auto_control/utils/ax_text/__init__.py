"""Native text via the UI Automation TextPattern (read / find / select / attributes)."""
from je_auto_control.utils.ax_text.ax_text import (
    control_text_attributes, find_control_text, get_control_text,
    get_selected_text, get_visible_text, select_control_text,
)

__all__ = [
    "get_control_text", "get_selected_text", "get_visible_text",
    "find_control_text", "select_control_text", "control_text_attributes",
]
