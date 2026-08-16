"""Cross-platform headless clipboard access."""
from je_auto_control.utils.clipboard.clipboard import (
    get_clipboard, get_clipboard_image, set_clipboard, set_clipboard_image,
)

__all__ = [
    "get_clipboard", "get_clipboard_image",
    "set_clipboard", "set_clipboard_image",
]
