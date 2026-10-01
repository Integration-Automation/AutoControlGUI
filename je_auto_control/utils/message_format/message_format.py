"""ICU-lite MessageFormat: plural / select / selectordinal message rendering.

``i18n_test.check_catalog`` only compares placeholder *sets* and ``interpolate``
does flat ``${var}`` substitution — neither can render the count-aware messages
real localisation needs: ``"{count, plural, one {# item} other {# items}}"``.
This implements the ICU MessageFormat subset most apps use: simple ``{name}``
arguments, ``select`` (e.g. gender), ``plural`` and ``selectordinal`` with CLDR
plural categories, exact ``=N`` selectors, the ``#`` count placeholder, an
``offset:`` and ICU apostrophe quoting.

English and French rules are built in; any other locale uses Babel's CLDR
data when Babel is installed (``je_auto_control[locale]``) and is refused
otherwise, rather than silently getting English rules. A pattern ICU would
reject -- an unterminated argument, a selector without ``{...}``, no
``other``, a duplicate selector, ``offset:`` anywhere but first -- raises
:class:`MessageFormatError`.

Pure standard library (Babel only for the locales above); imports no
``PySide6``. The plural/ordinal category functions are pure and the rule
callables are injectable, so rendering is fully deterministic in CI.
"""
import math
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

Node = Tuple
PluralRule = Callable[[Any], str]
_Operands = Callable[[float, int, bool], str]


class MessageFormatError(AutoControlException, ValueError):
    """A message pattern ICU would reject, or an argument it cannot render."""

_WHITESPACE = " \t\r\n"
_TOKEN_STOP = set(_WHITESPACE) | {",", "{", "}"}
#: Characters an apostrophe quotes (ICU ApostropheMode.DOUBLE_OPTIONAL): braces
#: everywhere, "#" only in a plural sub-message. ("|" belongs to ChoiceFormat,
#: which is not supported, so it is never quoted.)
_QUOTABLE = "{}"
_QUOTABLE_IN_PLURAL = "{}#"


# --- CLDR plural / ordinal categories -------------------------------------

def _to_operands(value: Any) -> Tuple[float, int, bool]:
    """Return ``(number, integer_part, is_integer)`` for a numeric value.

    An ``int`` stays an ``int``: through ``float`` a 17-digit count lost
    its last digit in ``#``.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value, value, True
    number = float(value)
    if not math.isfinite(number):      # int(inf) raised OverflowError
        return number, 0, False
    return number, int(number), number.is_integer()


def _category_operands(value: Any) -> Tuple[float, int, bool]:
    """Operands for a plural rule: CLDR's n and i are absolute values, so -1 is ``one``."""
    number, integer, is_int = _to_operands(value)
    return abs(number), abs(integer), is_int


def _cardinal_en(_number: float, integer: int, is_int: bool) -> str:
    return "one" if (is_int and integer == 1) else "other"


def _cardinal_fr(_number: float, integer: int, is_int: bool) -> str:
    if integer in (0, 1):
        return "one"
    # CLDR: "many" is i != 0 and i % 1000000 = 0 and v = 0 ("1 000 000 de").
    if is_int and integer % 1_000_000 == 0:
        return "many"
    return "other"


def _ordinal_en(_number: float, integer: int, is_int: bool) -> str:
    if not is_int:
        return "other"
    mod10, mod100 = integer % 10, integer % 100
    if mod10 == 1 and mod100 != 11:
        return "one"
    if mod10 == 2 and mod100 != 12:
        return "two"
    if mod10 == 3 and mod100 != 13:
        return "few"
    return "other"


def _ordinal_fr(_number: float, integer: int, is_int: bool) -> str:
    # CLDR: one is n = 1 only ("1er", "2e", "21e"); French used the English rules.
    return "one" if (is_int and integer == 1) else "other"


_CARDINAL: Dict[str, _Operands] = {"en": _cardinal_en, "fr": _cardinal_fr}
_ORDINAL: Dict[str, _Operands] = {"en": _ordinal_en, "fr": _ordinal_fr}


def _language(locale: str) -> str:
    """``fr_FR`` / ``fr-CA`` / ``FR`` -> ``fr``: only an exact key used to match."""
    return str(locale or "en").replace("-", "_").split("_", 1)[0].lower()


def _babel_rule(locale: str, ordinal: bool) -> Optional[_Operands]:
    """CLDR rules for ``locale`` from Babel, or ``None`` when Babel is not installed."""
    try:
        from babel import Locale, UnknownLocaleError
    except ImportError:
        return None
    try:
        parsed = Locale.parse(str(locale).replace("-", "_"))
    except (UnknownLocaleError, ValueError, TypeError) as error:
        raise MessageFormatError(f"unknown locale {locale!r}") from error
    form = parsed.ordinal_form if ordinal else parsed.plural_form
    return lambda number, integer, is_int: form(integer if is_int else number)


def _rule_for(locale: str, ordinal: bool) -> _Operands:
    table = _ORDINAL if ordinal else _CARDINAL
    rule = table.get(_language(locale)) or _babel_rule(locale, ordinal)
    if rule is None:
        # "ru" used to get English rules: 2 was "other", CLDR says "few".
        raise MessageFormatError(
            f"no {'ordinal' if ordinal else 'plural'} rules for locale {locale!r}: en and fr are "
            "built in, other locales need Babel (pip install je_auto_control[locale])")
    return rule


def plural_category(number: Any, locale: str = "en") -> str:
    """Return the CLDR cardinal plural category (``one``/``other``/...)."""
    return _rule_for(locale, False)(*_category_operands(number))


def ordinal_category(number: Any, locale: str = "en") -> str:
    """Return the CLDR ordinal plural category (``one``/``two``/``few``/...)."""
    return _rule_for(locale, True)(*_category_operands(number))


def _format_number(value: Any) -> str:
    """Render a number without a trailing ``.0`` for integer values."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


# --- parsing --------------------------------------------------------------

def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index] in _WHITESPACE:
        index += 1
    return index


def _read_token(text: str, index: int) -> Tuple[str, int]:
    start = index
    while index < len(text) and text[index] not in _TOKEN_STOP:
        index += 1
    return text[start:index], index


def _flush(buffer: List[str], nodes: List[Node]) -> None:
    if buffer:
        nodes.append(("text", "".join(buffer)))
        buffer.clear()


def _consume_quote(text: str, index: int, buffer: List[str], quotable: str) -> int:
    """Handle an ICU apostrophe at ``index``; append literal text to buffer.

    An apostrophe before a character that is not special where it stands is
    itself literal: ``'#'`` outside a plural read as ``#``.
    """
    nxt = text[index + 1] if index + 1 < len(text) else ""
    if nxt == "'":
        buffer.append("'")
        return index + 2
    if nxt and nxt in quotable:
        index += 1
        while index < len(text):
            if text[index] == "'":
                if text[index + 1:index + 2] != "'":
                    return index + 1
                index += 1  # '' inside a quoted section is one apostrophe
            buffer.append(text[index])
            index += 1
        return index
    buffer.append("'")
    return index + 1


def _parse_message(text: str, index: int,
                   in_plural: bool = False) -> Tuple[List[Node], int]:
    """Parse a (sub)message until end of string or an unescaped ``}``."""
    quotable = _QUOTABLE_IN_PLURAL if in_plural else _QUOTABLE
    nodes: List[Node] = []
    buffer: List[str] = []
    while index < len(text) and text[index] != "}":
        char = text[index]
        if char == "{":
            _flush(buffer, nodes)
            node, index = _parse_argument(text, index)
            nodes.append(node)
        elif char == "#":
            _flush(buffer, nodes)
            nodes.append(("hash",))
            index += 1
        elif char == "'":
            index = _consume_quote(text, index, buffer, quotable)
        else:
            buffer.append(char)
            index += 1
    _flush(buffer, nodes)
    return nodes, index


def _read_offset(selector: str, text: str, index: int) -> Tuple[int, int]:
    value = selector[len("offset:"):]
    if not value:   # ICU allows "offset: 1"
        value, index = _read_token(text, index)
        index = _skip_ws(text, index)
    try:
        return int(value), index
    except ValueError as error:
        raise MessageFormatError(f"offset must be an integer, got {value!r}") from error


def _check_selector(selector: str, options: Dict[str, List[Node]], in_plural: bool) -> None:
    if not selector:
        raise MessageFormatError("a selector is missing before '{'")
    if selector in options:
        raise MessageFormatError(f"duplicate selector {selector!r}")
    if in_plural and selector.startswith("="):
        try:
            float(selector[1:])
        except ValueError as error:
            raise MessageFormatError(f"{selector!r} is not an =number selector") from error


def _parse_options(text: str, index: int,
                   in_plural: bool) -> Tuple[Dict[str, List[Node]], int, int]:
    """Parse ``selector {submessage}`` pairs (and an optional leading ``offset:``).

    Malformed options raised nothing: ``{n, plural, one {x}`` rendered ``x``
    and ``one x other {y}`` rendered " other ". ICU rejects both, a message
    without ``other``, a duplicate selector and a late ``offset:``.
    """
    options: Dict[str, List[Node]] = {}
    offset = 0
    index = _skip_ws(text, index)
    while index < len(text) and text[index] != "}":
        selector, index = _read_token(text, index)
        index = _skip_ws(text, index)
        if selector.startswith("offset:") and in_plural and not options:
            offset, index = _read_offset(selector, text, index)
            continue
        _check_selector(selector, options, in_plural)
        if not text.startswith("{", index):
            raise MessageFormatError(f"expected '{{' after selector {selector!r} at position {index}")
        submessage, index = _parse_message(text, index + 1, in_plural)
        if not text.startswith("}", index):
            raise MessageFormatError(f"unterminated sub-message for {selector!r}")
        options[selector] = submessage
        index = _skip_ws(text, index + 1)
    if index >= len(text):
        raise MessageFormatError("unterminated argument: missing '}'")
    if "other" not in options:
        raise MessageFormatError("a plural or select argument needs an 'other' selector")
    return options, offset, index


def _parse_argument(text: str, index: int) -> Tuple[Node, int]:
    """Parse a ``{...}`` argument starting at the opening brace."""
    index = _skip_ws(text, index + 1)
    name, index = _read_token(text, index)
    index = _skip_ws(text, index)
    if not name:
        raise MessageFormatError(f"an argument needs a name at position {index}")
    if index < len(text) and text[index] == "}":
        return ("arg", name), index + 1
    if not text.startswith(",", index):
        raise MessageFormatError(f"expected ',' or '}}' after argument {name!r}")
    index = _skip_ws(text, index + 1)            # skip the comma
    arg_type, index = _read_token(text, index)
    index = _skip_ws(text, index)
    if arg_type not in ("plural", "selectordinal", "select"):
        raise MessageFormatError(f"unknown argument type: {arg_type!r}")
    if not text.startswith(",", index):
        # "{n, plural} tail {x}" read " tail {x}" as its options.
        raise MessageFormatError(f"the {arg_type} argument {name!r} needs a ',' and its options")
    options, offset, index = _parse_options(   # skip the comma
        text, index + 1, arg_type != "select")
    index += 1                                    # skip the closing brace
    if arg_type == "select":
        return ("select", name, options), index
    return ("plural", name, options, arg_type == "selectordinal", offset), index


# --- rendering ------------------------------------------------------------

def _render_select(node: Node, args: Mapping[str, Any],
                   rules: Tuple[PluralRule, PluralRule]) -> str:
    _, name, options = node
    # "is None", not "or": an empty chosen branch ({}) is a valid message.
    chosen = options.get(str(args.get(name, "")))
    if chosen is None:
        chosen = options.get("other", [])
    return _render(chosen, args, rules)


def _exact_option(options: Dict[str, List[Node]], number: float) -> Optional[List[Node]]:
    """The ``=N`` sub-message whose N equals ``number``, compared as numbers.

    It was compared as text, so ``=1.0`` never matched 1.
    """
    for selector, nodes in options.items():
        if selector.startswith("=") and float(selector[1:]) == number:
            return nodes
    return None


def _render_plural(node: Node, args: Mapping[str, Any],
                   rules: Tuple[PluralRule, PluralRule]) -> str:
    _, name, options, is_ordinal, offset = node
    value = args.get(name, 0)
    try:
        number, integer, is_int = _to_operands(value)
    except (TypeError, ValueError) as error:
        raise MessageFormatError(f"plural argument {name!r} is not a number: {value!r}") from error
    if not math.isfinite(number):
        raise MessageFormatError(f"plural argument {name!r} is not a number: {value!r}")
    chosen = _exact_option(options, number)
    if chosen is None:
        rule = rules[1] if is_ordinal else rules[0]
        # ICU picks the keyword from the value minus the offset.
        keyword = rule(integer - offset if is_int else number - offset)
        chosen = options.get(keyword)
        if chosen is None:
            chosen = options.get("other", [])
    return _render(chosen, args, rules, plural_value=number - offset)


def _render(nodes: List[Node], args: Mapping[str, Any],
            rules: Tuple[PluralRule, PluralRule],
            plural_value: Optional[float] = None) -> str:
    parts: List[str] = []
    for node in nodes:
        kind = node[0]
        if kind == "text":
            parts.append(node[1])
        elif kind == "hash":
            parts.append(_format_number(plural_value)
                         if plural_value is not None else "#")
        elif kind == "arg":
            parts.append(str(args.get(node[1], "")))
        elif kind == "select":
            parts.append(_render_select(node, args, rules))
        else:
            parts.append(_render_plural(node, args, rules))
    return "".join(parts)


def format_message(pattern: str, arguments: Optional[Mapping[str, Any]] = None,
                   *, locale: str = "en",
                   plural_rules: Optional[PluralRule] = None,
                   ordinal_rules: Optional[PluralRule] = None) -> str:
    """Render an ICU-lite ``pattern`` against ``arguments``.

    Supports ``{name}`` placeholders, ``select``, ``plural`` and
    ``selectordinal`` with CLDR categories, exact ``=N`` selectors, ``#`` (the
    count, minus any ``offset:``) and ``'`` quoting. ``plural_rules`` /
    ``ordinal_rules`` override the locale's category functions.
    """
    args = arguments or {}
    text = pattern or ""
    nodes, end = _parse_message(text, 0)
    if end < len(text):
        # A stray "}" silently cut the rest of the message off.
        raise MessageFormatError(f"unmatched '}}' at position {end} in message pattern")
    cardinal = plural_rules or (lambda value: plural_category(value, locale))
    ordinal = ordinal_rules or (lambda value: ordinal_category(value, locale))
    return _render(nodes, args, (cardinal, ordinal))
