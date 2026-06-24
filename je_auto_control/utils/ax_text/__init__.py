"""Native text reading via the UI Automation TextPattern (document/selection/visible)."""
from je_auto_control.utils.ax_text.ax_text import (
    get_control_text, get_selected_text, get_visible_text,
)

__all__ = [
    "get_control_text", "get_selected_text", "get_visible_text",
]
