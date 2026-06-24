"""Inspect and classify the clipboard's available formats (pure classify/diff + Win32 enum)."""
from je_auto_control.utils.clipboard_formats.clipboard_formats import (
    classify_format, classify_formats, clipboard_formats, diff_formats,
    list_clipboard_formats,
)

__all__ = [
    "classify_format", "classify_formats", "diff_formats",
    "list_clipboard_formats", "clipboard_formats",
]
