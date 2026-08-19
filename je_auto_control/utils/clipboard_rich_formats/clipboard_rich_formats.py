"""Rich clipboard formats — RTF and CSV/TSV get / set.

``rich_clipboard`` added ``CF_HTML`` for rich paste into Word / Outlook, but two
other cross-app formats were still missing:

* **RTF** (``"Rich Text Format"``) — the format almost every rich editor accepts
  for styled paste. Building / stripping RTF control words and ``\\uNNNN`` /
  ``\\'XX`` escapes is the error-prone part; :func:`build_rtf` / :func:`rtf_to_text`
  do it in pure Python with a fully unit-testable round-trip.
* **CSV / TSV** (the registered ``"Csv"`` format Excel reads) — :func:`rows_to_csv`
  / :func:`csv_to_rows` are a thin, delimiter-parametrised wrapper over the stdlib
  ``csv`` module so a table can be put on / read off the clipboard.

The codecs are platform-independent and headless-testable; only the actual
clipboard I/O is Win32 (raising ``RuntimeError`` elsewhere, like the base
``clipboard`` module). The Win32 byte transfer is a single generic helper shared
by both formats. Imports no ``PySide6``.
"""
import csv
import io
import sys
from typing import List, Optional, Sequence

_RTF_FORMAT_NAME = "Rich Text Format"
_CSV_FORMAT_NAME = "Csv"
_GMEM_MOVEABLE = 0x0002
_RTF_PREAMBLE = "{\\rtf1\\ansi\\ansicpg1252\\deff0{\\fonttbl{\\f0\\fnil Calibri;}}\n"
_RTF_LITERAL_ESCAPE = {"\\": "\\\\", "{": "\\{", "}": "\\}",
                       "\n": "\\par\n", "\r": "", "\t": "\\tab "}
# RTF destination groups whose textual content is metadata, not document text.
_RTF_DESTINATIONS = frozenset({
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer",
    "object", "themedata", "datastore", "operator", "generator", "rsidtbl",
})


# --- RTF codec (pure) ------------------------------------------------------

def _escape_char(char: str) -> str:
    if char in _RTF_LITERAL_ESCAPE:
        return _RTF_LITERAL_ESCAPE[char]
    if ord(char) > 127:
        return f"\\u{ord(char)}?"
    return char


def build_rtf(text: str) -> str:
    """Wrap plain ``text`` in a minimal, valid RTF document.

    Backslash / brace are escaped, newlines become ``\\par`` and non-ASCII
    characters become ``\\uNNNN?`` escapes, so the result is pure ASCII.
    """
    if not isinstance(text, str):
        raise TypeError("build_rtf expects a str")
    return _RTF_PREAMBLE + "".join(_escape_char(ch) for ch in text) + "}"


def _apply_word(word: str, param: str, stack: List[bool],
                result: List[str]) -> int:
    """Apply one RTF control word; return how many following chars to skip."""
    if word in _RTF_DESTINATIONS:
        stack[-1] = True
        return 0
    if stack[-1]:
        return 1 if word == "u" else 0
    if word in ("par", "line"):
        result.append("\n")
    elif word == "tab":
        result.append("\t")
    elif word == "u" and param:
        result.append(chr(int(param) % 0x10000))
        return 1  # the trailing fallback char is consumed
    return 0


def _consume_word(text: str, i: int, stack: List[bool],
                  result: List[str]) -> int:
    n = len(text)
    j = i + 1
    while j < n and text[j].isalpha():
        j += 1
    k = j + 1 if j < n and text[j] == "-" else j
    while k < n and text[k].isdigit():
        k += 1
    param = text[j:k]
    if k < n and text[k] == " ":
        k += 1
    return k + _apply_word(text[i + 1:j], param, stack, result)


def _consume_hex(text: str, i: int, stack: List[bool],
                 result: List[str]) -> int:
    if not stack[-1]:
        try:
            byte = bytes([int(text[i + 2:i + 4], 16)])
            result.append(byte.decode("cp1252", "replace"))
        except ValueError:
            pass
    return i + 4


def _consume_control(text: str, i: int, stack: List[bool],
                     result: List[str]) -> int:
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if nxt in "\\{}":
        if not stack[-1]:
            result.append(nxt)
        return i + 2
    if nxt == "*":
        stack[-1] = True
        return i + 2
    if nxt == "'":
        return _consume_hex(text, i, stack, result)
    if nxt.isalpha():
        return _consume_word(text, i, stack, result)
    return i + 2  # other control symbol (\~, \-, …)


def rtf_to_text(rtf: str) -> str:
    """Strip an RTF document to its plain text (inverse of :func:`build_rtf`).

    Drops metadata groups (font / colour / style tables, etc.), converts
    ``\\par`` / ``\\line`` to newlines and ``\\tab`` to a tab, and decodes
    ``\\uNNNN`` / ``\\'XX`` character escapes.
    """
    text = str(rtf)
    result: List[str] = []
    stack: List[bool] = [False]
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == "{":
            stack.append(stack[-1])
            i += 1
        elif char == "}":
            if len(stack) > 1:
                stack.pop()
            i += 1
        elif char == "\\":
            i = _consume_control(text, i, stack, result)
        elif char in "\r\n":
            i += 1  # raw line breaks in the source are insignificant
        else:
            if not stack[-1]:
                result.append(char)
            i += 1
    return "".join(result)


# --- CSV / TSV codec (pure) ------------------------------------------------

def rows_to_csv(rows: Sequence[Sequence[object]], *, delimiter: str = ",") -> str:
    """Serialise rows of cells to CSV/TSV text (use ``delimiter="\\t"`` for TSV)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
    writer.writerows([[str(cell) for cell in row] for row in rows])
    return buffer.getvalue()


def csv_to_rows(text: str, *, delimiter: str = ",") -> List[List[str]]:
    """Parse CSV/TSV text into a list of cell-string rows."""
    return [list(row) for row in csv.reader(io.StringIO(str(text)),
                                            delimiter=delimiter)]


# --- Win32 clipboard I/O ---------------------------------------------------

def _format_id(name: str) -> int:
    from je_auto_control.utils.clipboard.win32_clipboard_api import register_format
    return register_format(name)


def _win_set_format(format_id: int, payload: bytes, *,
                    empty_first: bool = True) -> None:
    """Delegates to the one place that declares the Win32 prototypes.

    This used to hand-roll the calls with ``restype`` but no ``argtypes``, so
    ``GlobalLock`` raised ``OverflowError`` on 64-bit Windows and
    ``set_clipboard_rtf`` / ``set_clipboard_csv`` had never worked.
    """
    from je_auto_control.utils.clipboard.win32_clipboard_api import (
        set_clipboard_format,
    )
    set_clipboard_format(format_id, payload, empty_first=empty_first)


def _win_get_format(format_id: int) -> Optional[bytes]:
    from je_auto_control.utils.clipboard.win32_clipboard_api import (
        get_clipboard_format,
    )
    data = get_clipboard_format(format_id)
    return None if data is None else data.split(b"\x00", 1)[0]


def _seed_plaintext(text: str) -> None:
    from je_auto_control.utils.clipboard.clipboard import set_clipboard
    set_clipboard(text)


def set_clipboard_rtf(text: str, *, plaintext: bool = True) -> None:
    """Put ``text`` on the clipboard as Rich Text Format (Windows only).

    With ``plaintext`` (default) the raw text is also placed as ``CF_UNICODETEXT``
    so plain editors still paste something. Raises ``RuntimeError`` off Windows.
    """
    if not isinstance(text, str):
        raise TypeError("set_clipboard_rtf expects a str")
    if not sys.platform.startswith("win"):
        raise RuntimeError("set_clipboard_rtf is only supported on Windows")
    payload = build_rtf(text).encode("ascii", "replace") + b"\x00"
    if plaintext:
        _seed_plaintext(text)
    _win_set_format(_format_id(_RTF_FORMAT_NAME), payload, empty_first=not plaintext)


def get_clipboard_rtf() -> Optional[str]:
    """Return the clipboard's RTF document string, or ``None`` (Windows only)."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("get_clipboard_rtf is only supported on Windows")
    blob = _win_get_format(_format_id(_RTF_FORMAT_NAME))
    return blob.decode("latin-1") if blob is not None else None


def set_clipboard_csv(rows: Sequence[Sequence[object]], *, delimiter: str = ",",
                      plaintext: bool = True) -> None:
    """Put a table on the clipboard as the ``Csv`` format Excel reads (Windows)."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("set_clipboard_csv is only supported on Windows")
    text = rows_to_csv(rows, delimiter=delimiter)
    payload = text.encode("utf-8") + b"\x00"
    if plaintext:
        _seed_plaintext(text)
    _win_set_format(_format_id(_CSV_FORMAT_NAME), payload, empty_first=not plaintext)


def get_clipboard_csv(*, delimiter: str = ",") -> Optional[List[List[str]]]:
    """Return the clipboard's ``Csv`` content as cell-string rows, or ``None``."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("get_clipboard_csv is only supported on Windows")
    blob = _win_get_format(_format_id(_CSV_FORMAT_NAME))
    if blob is None:
        return None
    return csv_to_rows(blob.decode("utf-8", "replace"), delimiter=delimiter)
