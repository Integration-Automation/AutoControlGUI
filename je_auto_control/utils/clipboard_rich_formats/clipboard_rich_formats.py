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
from typing import Any, List, Optional, Sequence

_RTF_FORMAT_NAME = "Rich Text Format"
_CSV_FORMAT_NAME = "Csv"
_GMEM_MOVEABLE = 0x0002
_RTF_PREAMBLE = "{\\rtf1\\ansi\\ansicpg1252\\deff0{\\fonttbl{\\f0\\fnil Calibri;}}\n"
_RTF_LITERAL_ESCAPE = {"\\": "\\\\", "{": "\\{", "}": "\\}",
                       "\n": "\\par\n", "\t": "\\tab "}
# RTF destination groups whose textual content is metadata, not document text.
_RTF_DESTINATIONS = frozenset({
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer",
    "object", "themedata", "datastore", "operator", "generator", "rsidtbl",
})


# --- RTF codec (pure) ------------------------------------------------------

def _escape_char(char: str) -> str:
    if char in _RTF_LITERAL_ESCAPE:
        return _RTF_LITERAL_ESCAPE[char]
    if ord(char) <= 127:
        return char
    # \uN takes a *signed* 16-bit N, one per UTF-16 unit: U+AC00 is
    # \u-21504? and an emoji is a surrogate pair of two escapes.
    units = char.encode("utf-16-le")
    return "".join(
        f"\\u{unit - 0x10000 if unit > 0x7FFF else unit}?"
        for unit in (int.from_bytes(units[i:i + 2], "little")
                     for i in range(0, len(units), 2)))


def build_rtf(text: str) -> str:
    """Wrap plain ``text`` in a minimal, valid RTF document.

    Backslash / brace are escaped, line breaks (``\\n``, ``\\r\\n`` or a lone
    ``\\r``) become ``\\par`` and non-ASCII characters become ``\\uN?`` escapes
    of their UTF-16 units, so the result is pure ASCII.
    """
    if not isinstance(text, str):
        raise TypeError("build_rtf expects a str")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _RTF_PREAMBLE + "".join(_escape_char(ch) for ch in text) + "}"


class _RtfReader:
    """Single pass over an RTF document collecting its visible text.

    Each group frame is ``[hidden, uc]``: whether the group is metadata, and
    its ``\\ucN`` -- how many fallback *tokens* follow each ``\\uN`` (a
    ``\\'xx`` escape is one token, and a control word ends the fallback).
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0
        self.frames: List[List[Any]] = [[False, 1]]
        self.skip = 0
        self.result: List[str] = []

    def read(self) -> str:
        while self.index < len(self.text):
            self._step(self.text[self.index])
        # \uN escapes of a surrogate pair arrive as two halves; join them.
        joined = "".join(self.result)
        return joined.encode("utf-16", "surrogatepass").decode("utf-16", "replace")

    def _emit(self, text: str) -> None:
        if self.skip > 0:
            self.skip -= 1
        elif not self.frames[-1][0]:
            self.result.append(text)

    def _step(self, char: str) -> None:
        if char == "{":
            self.frames.append(list(self.frames[-1]))
            self.skip = 0
            self.index += 1
        elif char == "}":
            if len(self.frames) > 1:
                self.frames.pop()
            self.skip = 0
            self.index += 1
        elif char == "\\":
            self._control()
        else:
            if char not in "\r\n":   # raw line breaks in the source are insignificant
                self._emit(char)
            self.index += 1

    def _control(self) -> None:
        text, i = self.text, self.index
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if nxt in ("\\", "{", "}"):
            self._emit(nxt)
            self.index = i + 2
        elif nxt == "*":
            self.frames[-1][0] = True
            self.index = i + 2
        elif nxt == "'":
            self._hex(text[i + 2:i + 4])
            self.index = i + 4
        elif nxt.isalpha():
            self._word()
        else:
            self.index = i + 2   # other control symbol (\~, \-, ...)

    def _hex(self, digits: str) -> None:
        try:
            byte = bytes([int(digits, 16)])
        except ValueError:
            return
        self._emit(byte.decode("cp1252", "replace"))

    def _word(self) -> None:
        text, start = self.text, self.index + 1
        end = start
        while end < len(text) and text[end].isalpha():
            end += 1
        stop = end + 1 if end < len(text) and text[end] == "-" else end
        while stop < len(text) and text[stop].isdigit():
            stop += 1
        param = text[end:stop]
        if stop < len(text) and text[stop] == " ":
            stop += 1
        self.index = stop
        self.skip = 0                   # a control word ends a fallback
        self._apply(text[start:end], param)

    def _apply(self, word: str, param: str) -> None:
        frame = self.frames[-1]
        if word in _RTF_DESTINATIONS:
            frame[0] = True
        elif word == "uc" and param:
            frame[1] = max(0, int(param))
        elif frame[0]:
            return
        elif word in ("par", "line"):
            self.result.append("\n")
        elif word == "tab":
            self.result.append("\t")
        elif word == "u" and param:
            self.result.append(chr(int(param) % 0x10000))
            self.skip = frame[1]


def rtf_to_text(rtf: str) -> str:
    """Strip an RTF document to its plain text (inverse of :func:`build_rtf`).

    Drops metadata groups (font / colour / style tables, etc.), converts
    ``\\par`` / ``\\line`` to newlines and ``\\tab`` to a tab, and decodes
    ``\\uN`` (honouring ``\\ucN`` and surrogate pairs) / ``\\'XX`` escapes.
    """
    return _RtfReader(str(rtf)).read()


# --- CSV / TSV codec (pure) ------------------------------------------------

def rows_to_csv(rows: Sequence[Sequence[object]], *, delimiter: str = ",") -> str:
    """Serialise rows of cells to CSV/TSV text (use ``delimiter="\\t"`` for TSV)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
    # None (JSON null) is an empty cell, as csv.writer writes it -- not the text "None".
    writer.writerows([["" if cell is None else str(cell) for cell in row] for row in rows])
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
