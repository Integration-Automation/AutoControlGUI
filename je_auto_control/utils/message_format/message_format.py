"""ICU-lite MessageFormat: plural / select / selectordinal message rendering.

``i18n_test.check_catalog`` only compares placeholder *sets* and ``interpolate``
does flat ``${var}`` substitution — neither can render the count-aware messages
real localisation needs: ``"{count, plural, one {# item} other {# items}}"``.
This implements the ICU MessageFormat subset most apps use: simple ``{name}``
arguments, ``select`` (e.g. gender), ``plural`` and ``selectordinal`` with CLDR
plural categories, exact ``=N`` selectors, the ``#`` count placeholder, an
``offset:`` and ICU apostrophe quoting.

Pure standard library; imports no ``PySide6``. The plural/ordinal category
functions are pure and the rule callables are injectable, so rendering is fully
deterministic in CI.
"""
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

Node = Tuple
PluralRule = Callable[[Any], str]

_WHITESPACE = " \t\r\n"
_TOKEN_STOP = set(_WHITESPACE) | {",", "{", "}"}
_QUOTABLE = "{}#|"


# --- CLDR plural / ordinal categories -------------------------------------

def _to_operands(value: Any) -> Tuple[float, int, bool]:
    """Return ``(number, integer_part, is_integer)`` for a numeric value."""
    number = float(value)
    return number, int(number), number.is_integer()


def _cardinal_en(_number: float, integer: int, is_int: bool) -> str:
    return "one" if (is_int and integer == 1) else "other"


def _cardinal_fr(_number: float, integer: int, _is_int: bool) -> str:
    return "one" if integer in (0, 1) else "other"


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


_CARDINAL = {"en": _cardinal_en, "fr": _cardinal_fr}
_ORDINAL = {"en": _ordinal_en}


def plural_category(number: Any, locale: str = "en") -> str:
    """Return the CLDR cardinal plural category (``one``/``other``/...)."""
    rule = _CARDINAL.get(locale, _cardinal_en)
    return rule(*_to_operands(number))


def ordinal_category(number: Any, locale: str = "en") -> str:
    """Return the CLDR ordinal plural category (``one``/``two``/``few``/...)."""
    rule = _ORDINAL.get(locale, _ordinal_en)
    return rule(*_to_operands(number))


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


def _consume_quote(text: str, index: int, buffer: List[str]) -> int:
    """Handle an ICU apostrophe at ``index``; append literal text to buffer."""
    nxt = text[index + 1] if index + 1 < len(text) else ""
    if nxt == "'":
        buffer.append("'")
        return index + 2
    if nxt in _QUOTABLE:
        index += 1
        while index < len(text) and text[index] != "'":
            buffer.append(text[index])
            index += 1
        return index + 1 if index < len(text) else index
    buffer.append("'")
    return index + 1


def _parse_message(text: str, index: int) -> Tuple[List[Node], int]:
    """Parse a (sub)message until end of string or an unescaped ``}``."""
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
            index = _consume_quote(text, index, buffer)
        else:
            buffer.append(char)
            index += 1
    _flush(buffer, nodes)
    return nodes, index


def _parse_options(text: str, index: int) -> Tuple[Dict[str, List[Node]], int, int]:
    """Parse ``selector {submessage}`` pairs (and an optional ``offset:``)."""
    options: Dict[str, List[Node]] = {}
    offset = 0
    index = _skip_ws(text, index)
    while index < len(text) and text[index] != "}":
        selector, index = _read_token(text, index)
        index = _skip_ws(text, index)
        if selector.startswith("offset:"):
            offset = int(selector[len("offset:"):])
            continue
        submessage, index = _parse_message(text, index + 1)
        options[selector] = submessage
        index = _skip_ws(text, index + 1)
    return options, offset, index


def _parse_argument(text: str, index: int) -> Tuple[Node, int]:
    """Parse a ``{...}`` argument starting at the opening brace."""
    index = _skip_ws(text, index + 1)
    name, index = _read_token(text, index)
    index = _skip_ws(text, index)
    if index < len(text) and text[index] == "}":
        return ("arg", name), index + 1
    index = _skip_ws(text, index + 1)            # skip the comma
    arg_type, index = _read_token(text, index)
    index = _skip_ws(text, index)
    if arg_type not in ("plural", "selectordinal", "select"):
        raise ValueError(f"unknown argument type: {arg_type!r}")
    options, offset, index = _parse_options(text, index + 1)   # skip the comma
    index += 1                                    # skip the closing brace
    if arg_type == "select":
        return ("select", name, options), index
    return ("plural", name, options, arg_type == "selectordinal", offset), index


# --- rendering ------------------------------------------------------------

def _render_select(node: Node, args: Mapping[str, Any],
                   rules: Tuple[PluralRule, PluralRule]) -> str:
    _, name, options = node
    chosen = options.get(str(args.get(name, ""))) or options.get("other") or []
    return _render(chosen, args, rules)


def _render_plural(node: Node, args: Mapping[str, Any],
                   rules: Tuple[PluralRule, PluralRule]) -> str:
    _, name, options, is_ordinal, offset = node
    value = args.get(name, 0)
    number, integer, is_int = _to_operands(value)
    exact = "=" + (str(integer) if is_int else _format_number(number))
    chosen = options.get(exact)
    if chosen is None:
        rule = rules[1] if is_ordinal else rules[0]
        chosen = options.get(rule(value)) or options.get("other") or []
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
    nodes, _ = _parse_message(pattern or "", 0)
    cardinal = plural_rules or (lambda value: plural_category(value, locale))
    ordinal = ordinal_rules or (lambda value: ordinal_category(value, locale))
    return _render(nodes, args, (cardinal, ordinal))
