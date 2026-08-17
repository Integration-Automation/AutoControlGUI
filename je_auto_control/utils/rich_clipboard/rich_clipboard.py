"""Rich clipboard formats — HTML (CF_HTML) get / set, for rich paste into Office.

The base ``clipboard`` module handles plain text (CF_UNICODETEXT) and image (CF_DIB)
only; pasting formatted content into Word / Outlook / a rich editor needs the
``CF_HTML`` format, whose ``Version / StartHTML / EndHTML / StartFragment /
EndFragment`` *byte-offset* header is notoriously error-prone to build. This module's
``build_cf_html`` / ``parse_cf_html`` compute and recover that header in pure Python —
fully unit-testable round-trip — and the Windows ``get_clipboard_html`` /
``set_clipboard_html`` wrap them over the Win32 clipboard.

The byte-offset math is platform-independent and headless-testable; only the actual
clipboard I/O is Win32 (raising ``RuntimeError`` elsewhere, like the base module).
Imports no ``PySide6``.
"""
import re
import sys
from typing import Optional

_HEADER = ("Version:0.9\r\n"
           "StartHTML:{:010d}\r\n"
           "EndHTML:{:010d}\r\n"
           "StartFragment:{:010d}\r\n"
           "EndFragment:{:010d}\r\n")
_PRE = "<html><body><!--StartFragment-->"
_POST = "<!--EndFragment--></body></html>"
_START_MARK = "<!--StartFragment-->"
_END_MARK = "<!--EndFragment-->"
_HTML_FORMAT_NAME = "HTML Format"


def build_cf_html(html: str) -> bytes:
    """Wrap an HTML fragment in a valid ``CF_HTML`` clipboard payload (UTF-8 bytes).

    The fixed-width 10-digit offsets make the header length constant, so the byte
    offsets can be computed in a single pass.
    """
    if not isinstance(html, str):
        raise TypeError("build_cf_html expects a str")
    header_len = len(_HEADER.format(0, 0, 0, 0).encode("utf-8"))
    start_html = header_len
    start_fragment = start_html + len(_PRE.encode("utf-8"))
    end_fragment = start_fragment + len(html.encode("utf-8"))
    end_html = end_fragment + len(_POST.encode("utf-8"))
    header = _HEADER.format(start_html, end_html, start_fragment, end_fragment)
    return (header + _PRE + html + _POST).encode("utf-8")


def _header_offset(text: str, name: str) -> Optional[int]:
    match = re.search(rf"{name}:(\d+)", text)
    return int(match.group(1)) if match else None


def parse_cf_html(blob) -> str:
    """Extract the HTML fragment from a ``CF_HTML`` payload (bytes or str).

    Prefers the ``StartFragment`` / ``EndFragment`` comment markers, falling back to
    the header's byte offsets.
    """
    raw = bytes(blob) if isinstance(blob, (bytes, bytearray)) else None
    text = (raw.decode("utf-8", "replace") if raw is not None else str(blob))
    start = text.find(_START_MARK)
    end = text.find(_END_MARK)
    if start != -1 and end != -1:
        return text[start + len(_START_MARK):end]
    start_offset = _header_offset(text, "StartFragment")
    end_offset = _header_offset(text, "EndFragment")
    if raw is not None and start_offset is not None and end_offset is not None:
        return raw[start_offset:end_offset].decode("utf-8", "replace")
    return text


def set_clipboard_html(html: str, *, fragment_plaintext: Optional[str] = None) -> None:
    """Put an HTML fragment on the clipboard as ``CF_HTML`` (Windows only).

    ``fragment_plaintext`` is also placed as plain text so apps that ignore HTML still
    paste something. Raises ``RuntimeError`` on non-Windows platforms.
    """
    if not isinstance(html, str):
        raise TypeError("set_clipboard_html expects a str")
    if not sys.platform.startswith("win"):
        raise RuntimeError("set_clipboard_html is only supported on Windows")
    _win_set_html(build_cf_html(html), fragment_plaintext)


def get_clipboard_html() -> Optional[str]:
    """Return the clipboard's HTML fragment, or ``None`` (Windows only)."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("get_clipboard_html is only supported on Windows")
    blob = _win_get_html()
    return parse_cf_html(blob) if blob is not None else None


def _html_format_id():
    from je_auto_control.utils.clipboard.win32_clipboard_api import register_format
    return register_format(_HTML_FORMAT_NAME)


def _win_set_html(cf_html: bytes, fragment_plaintext: Optional[str]) -> None:
    """Put CF_HTML on the clipboard, optionally seeding a plain-text fallback.

    The Win32 dance (prototypes, alloc, lock, open) lives in
    ``utils/clipboard/win32_clipboard_api.py``; this module only decides *what*
    bytes go on the clipboard. It used to hand-roll those calls with ``restype``
    but no ``argtypes``, so every call raised ``OverflowError`` on 64-bit
    Windows — the function had never worked.
    """
    from je_auto_control.utils.clipboard.clipboard import set_clipboard
    from je_auto_control.utils.clipboard.win32_clipboard_api import (
        set_clipboard_format,
    )
    if fragment_plaintext is not None:
        set_clipboard(fragment_plaintext)            # seeds CF_UNICODETEXT first
    # Keep that seed when there is one: emptying the clipboard here would throw
    # the plain-text fallback away again.
    set_clipboard_format(_html_format_id(), cf_html + b"\x00",
                         empty_first=fragment_plaintext is None)


def _win_get_html() -> Optional[bytes]:
    from je_auto_control.utils.clipboard.win32_clipboard_api import (
        get_clipboard_format,
    )
    data = get_clipboard_format(_html_format_id())
    return None if data is None else data.split(b"\x00", 1)[0]
