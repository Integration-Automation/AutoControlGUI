"""Compile a JSON Schema ``pattern`` (ECMA-262 syntax) so it matches as ECMA-262 does.

JSON Schema specifies ``pattern`` and ``patternProperties`` as ECMA-262
regular expressions. Handing the string straight to ``re`` got the parts a
validator depends on wrong:

* ``$`` also matched before a trailing newline, so ``^[0-9]+$`` accepted
  ``"123\\n"``;
* ``\\d``, ``\\w`` and ``\\b`` are Unicode-aware in ``re``, so ``^\\d+$``
  accepted Arabic-Indic digits; ECMA-262 keeps all three ASCII;
* ``.`` matched ``\\r`` and the Unicode line separators, and ``\\s`` missed
  U+FEFF.

It also rejected valid ECMA-262 syntax as an invalid pattern: ``\\cX``
control escapes, ``\\p{...}`` / ``\\P{...}`` property escapes, ``\\u{...}``
code points, the empty class ``[]`` and its complement ``[^]``, and named
groups written ``(?<name>...)`` / ``\\k<name>``.

:func:`compile_ecma_pattern` rewrites those and compiles with ``re.ASCII``.
Property escapes cover the General_Category values (``L``, ``Letter``,
``Nd``, ``digit``, ``gc=Lu``, ...) and ``Any`` / ``ASCII`` / ``Assigned``;
scripts and the other binary properties are not in :mod:`unicodedata` and
raise. Inside a character class ``\\S`` keeps ``re``'s ASCII meaning (it
still matches a non-ASCII space there), and a negated ``\\P{...}`` raises.

Pure standard library; imports no ``PySide6``.
"""
import functools
import re
import string
import sys
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlJsonException

_BACKSLASH = chr(92)
_Ranges = Tuple[Tuple[int, int], ...]
# ECMA-262 WhiteSpace and LineTerminator: TAB LF VT FF CR, SPACE, NBSP, the
# Space_Separator code points, LS PS, and ZWNBSP.
_SPACE: _Ranges = ((0x09, 0x0D), (0x20, 0x20), (0xA0, 0xA0), (0x1680, 0x1680), (0x2000, 0x200A),
                   (0x2028, 0x2029), (0x202F, 0x202F), (0x205F, 0x205F), (0x3000, 0x3000),
                   (0xFEFF, 0xFEFF))
_LINE_TERMINATORS: _Ranges = ((0x0A, 0x0A), (0x0D, 0x0D), (0x2028, 0x2029))
# ``re`` reads these inside a class as the start of a set operation and warns.
_CLASS_ESCAPED = frozenset("[&~|")

_GC_GROUPS: Dict[str, Tuple[str, ...]] = {
    "C": ("Cc", "Cf", "Cn", "Co", "Cs"), "L": ("Ll", "Lm", "Lo", "Lt", "Lu"), "LC": ("Ll", "Lt", "Lu"),
    "M": ("Mc", "Me", "Mn"), "N": ("Nd", "Nl", "No"), "P": ("Pc", "Pd", "Pe", "Pf", "Pi", "Po", "Ps"),
    "S": ("Sc", "Sk", "Sm", "So"), "Z": ("Zl", "Zp", "Zs"),
}
_GC_VALUES = frozenset(member for group in ("C", "L", "M", "N", "P", "S", "Z") for member in _GC_GROUPS[group])
# Unicode PropertyValueAliases.txt, ``gc`` rows: long name and extra alias -> short name.
_GC_ALIASES: Dict[str, str] = {
    "Other": "C", "Control": "Cc", "cntrl": "Cc", "Format": "Cf", "Unassigned": "Cn",
    "Private_Use": "Co", "Surrogate": "Cs", "Letter": "L", "Cased_Letter": "LC",
    "Lowercase_Letter": "Ll", "Modifier_Letter": "Lm", "Other_Letter": "Lo", "Titlecase_Letter": "Lt",
    "Uppercase_Letter": "Lu", "Mark": "M", "Combining_Mark": "M", "Spacing_Mark": "Mc",
    "Enclosing_Mark": "Me", "Nonspacing_Mark": "Mn", "Number": "N", "Decimal_Number": "Nd", "digit": "Nd",
    "Letter_Number": "Nl", "Other_Number": "No", "Punctuation": "P", "punct": "P",
    "Connector_Punctuation": "Pc", "Dash_Punctuation": "Pd", "Close_Punctuation": "Pe",
    "Final_Punctuation": "Pf", "Initial_Punctuation": "Pi", "Other_Punctuation": "Po",
    "Open_Punctuation": "Ps", "Symbol": "S", "Currency_Symbol": "Sc", "Modifier_Symbol": "Sk",
    "Math_Symbol": "Sm", "Other_Symbol": "So", "Separator": "Z", "Line_Separator": "Zl",
    "Paragraph_Separator": "Zp", "Space_Separator": "Zs",
}


def _char(code: int) -> str:
    return f"{_BACKSLASH}U{code:08x}"


def _class_body(ranges: _Ranges) -> str:
    return "".join(_char(low) if low == high else f"{_char(low)}-{_char(high)}" for low, high in ranges)


def _class(body: str, negate: bool) -> str:
    return f"[{'^' if negate else ''}{body}]"


@functools.lru_cache(maxsize=1)
def _category_ranges() -> Dict[str, _Ranges]:
    """Code-point ranges of every two-letter General_Category, from one pass over :mod:`unicodedata`."""
    found: Dict[str, List[Tuple[int, int]]] = {}
    category = unicodedata.category
    start, current = 0, category(chr(0))
    for code in range(1, sys.maxunicode + 1):
        value = category(chr(code))
        if value != current:
            found.setdefault(current, []).append((start, code - 1))
            start, current = code, value
    found.setdefault(current, []).append((start, sys.maxunicode))
    return {key: tuple(value) for key, value in found.items()}


@functools.lru_cache(maxsize=64)
def _property_body(name: str) -> str:
    """Class body for ``\\p{name}``; an unknown or unsupported property raises."""
    if name == "Any":
        return _class_body(((0, sys.maxunicode),))
    if name == "ASCII":
        return _class_body(((0, 0x7F),))
    table = _category_ranges()
    if name == "Assigned":
        return "".join(_class_body(ranges) for key, ranges in table.items() if key != "Cn")
    value = name.split("=", 1)[1] if name.startswith(("General_Category=", "gc=")) else name
    short = _GC_ALIASES.get(value, value)
    members = _GC_GROUPS.get(short, (short,))
    if not all(member in _GC_VALUES for member in members):
        raise AutoControlJsonException(
            f"unsupported Unicode property {name!r} in pattern: only General_Category values, "
            f"Any, ASCII and Assigned are available")
    return "".join(_class_body(table.get(member, ())) for member in members)


_Escape = Callable[[str, int, bool], Optional[Tuple[str, int]]]


def _space_escape(pattern: str, index: int, in_class: bool) -> Optional[Tuple[str, int]]:
    negate = pattern[index + 1] == "S"
    if in_class:
        return (_BACKSLASH + "S" if negate else _class_body(_SPACE)), index + 2
    return _class(_class_body(_SPACE), negate), index + 2


def _control_escape(pattern: str, index: int, _in_class: bool) -> Optional[Tuple[str, int]]:
    letter = pattern[index + 2:index + 3]
    if not (letter.isascii() and letter.isalpha()):
        return None
    return _char(ord(letter) % 32), index + 3


def _property_escape(pattern: str, index: int, in_class: bool) -> Optional[Tuple[str, int]]:
    end = pattern.find("}", index + 3)
    if not pattern.startswith("{", index + 2) or end < 0:
        return None
    negate = pattern[index + 1] == "P"
    if in_class and negate:
        raise AutoControlJsonException(
            f"a negated property escape inside a character class is not supported: {pattern!r}")
    body = _property_body(pattern[index + 3:end])
    return (body if in_class else _class(body, negate)), end + 1


def _code_point_escape(pattern: str, index: int, _in_class: bool) -> Optional[Tuple[str, int]]:
    end = pattern.find("}", index + 3)
    digits = pattern[index + 3:end] if pattern.startswith("{", index + 2) and end > 0 else ""
    if not digits or not all(digit in string.hexdigits for digit in digits):
        return None
    code = int(digits, 16)
    return (_char(code), end + 1) if code <= sys.maxunicode else None


def _named_reference(pattern: str, index: int, _in_class: bool) -> Optional[Tuple[str, int]]:
    end = pattern.find(">", index + 3)
    if not pattern.startswith("<", index + 2) or end < 0:
        return None
    return f"(?P={pattern[index + 3:end]})", end + 1


_ESCAPES: Dict[str, _Escape] = {
    "s": _space_escape, "S": _space_escape, "c": _control_escape, "p": _property_escape,
    "P": _property_escape, "u": _code_point_escape, "k": _named_reference,
}


def _escape(pattern: str, index: int, in_class: bool) -> Tuple[str, int]:
    handler = _ESCAPES.get(pattern[index + 1:index + 2])
    translated = handler(pattern, index, in_class) if handler is not None else None
    # Anything else means the same in both dialects, or is an error ``re`` reports.
    return translated if translated is not None else (pattern[index:index + 2], index + 2)


def _open_class(pattern: str, index: int) -> Tuple[str, int, bool]:
    if pattern.startswith("[]", index):
        return "(?!)", index + 2, False                 # ECMA-262: the empty class matches nothing
    if pattern.startswith("[^]", index):
        return f"[{_BACKSLASH}s{_BACKSLASH}S]", index + 3, False      # ... and its complement everything
    if pattern.startswith("[^", index):
        return "[^", index + 2, True
    return "[", index + 1, True


def _outside_class(pattern: str, index: int) -> Tuple[str, int]:
    char = pattern[index]
    if char == "$":
        return _BACKSLASH + "Z", index + 1             # re's $ also matches before a final newline
    if char == ".":
        return _class(_class_body(_LINE_TERMINATORS), True), index + 1
    if pattern.startswith("(?<", index) and pattern[index + 3:index + 4] not in ("=", "!"):
        return "(?P<", index + 3                        # a named group, not a lookbehind
    return char, index + 1


def translate_ecma_pattern(pattern: str) -> str:
    """Rewrite an ECMA-262 ``pattern`` into ``re`` syntax with the same meaning (compile with ``re.ASCII``)."""
    out: List[str] = []
    index, in_class = 0, False
    while index < len(pattern):
        char = pattern[index]
        if char == _BACKSLASH:
            text, index = _escape(pattern, index, in_class)
        elif in_class:
            text, index, in_class = (_BACKSLASH + char if char in _CLASS_ESCAPED else char), index + 1, char != "]"
        elif char == "[":
            text, index, in_class = _open_class(pattern, index)
        else:
            text, index = _outside_class(pattern, index)
        out.append(text)
    return "".join(out)


@functools.lru_cache(maxsize=256)
def _compile(pattern: str) -> "re.Pattern[str]":
    try:
        return re.compile(translate_ecma_pattern(pattern), re.ASCII)
    except re.error as error:
        raise AutoControlJsonException(f"invalid pattern {pattern!r} in schema: {error}") from error


def compile_ecma_pattern(pattern: str) -> "re.Pattern[str]":
    """Compile a JSON Schema ``pattern``; an invalid or unsupported one raises ``AutoControlJsonException``.

    Compiled patterns are cached, so validating many values against one schema
    translates each pattern once.
    """
    if not isinstance(pattern, str):
        raise AutoControlJsonException(f"pattern must be a string, got {type(pattern).__name__}")
    return _compile(pattern)
