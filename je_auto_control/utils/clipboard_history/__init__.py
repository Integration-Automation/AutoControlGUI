"""Clipboard history: a ring buffer + background poller over the clipboard."""
from je_auto_control.utils.clipboard_history.clipboard_history import (
    ClipboardHistory, default_clipboard_history,
)

__all__ = ["ClipboardHistory", "default_clipboard_history"]
