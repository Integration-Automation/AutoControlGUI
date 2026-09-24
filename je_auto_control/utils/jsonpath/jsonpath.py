"""A small JSONPath-style query engine over already-parsed JSON.

The executor's built-in path walker only splits on ``.`` and indexes — it can't
do wildcards, recursive descent, or filters, so API/DB responses with arrays are
awkward to extract from. This adds a focused JSONPath subset:

* ``$``               root (optional prefix)
* ``.name`` / ``name``  member access
* ``[n]`` / ``[-n]``   list index (negative from the end)
* ``*`` / ``[*]``      wildcard (all members / all elements)
* ``..``               recursive descent
* ``[?(@.k op v)]``    filter array elements or object member values
  (``op`` ∈ == != < <= > >=; ``v`` a JSON number, quoted string, true,
  false or null);
  ``@.a.b`` reaches into nested objects and ``[?(@.k)]`` tests that ``k``
  exists. Values of different types never compare equal (``true != 1``);
  ``<`` / ``>`` order only two numbers or two strings (RFC 9535).
* ``['name']``         quoted member, with RFC 9535 escapes decoded

A path this subset cannot read -- an unsupported filter, an unterminated
``[``, a stray character -- raises ``ValueError`` rather than matching
something else.

Pure standard library (``re``); imports no ``PySide6``.
"""
import re
from typing import Any, Dict, List, Mapping, Tuple

_ESCAPES = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
            "/": "/", "\\": "\\", "'": "'", '"': '"'}

# The field path of a filter; the operator and value are split off by hand, so
# no pattern has two quantifiers competing for the same characters.
_FILTER_FIELD = re.compile(r"@\.([\w-]+(?:\.[\w-]+)*)")
_OPERATORS = ("==", "!=", "<=", ">=", "<", ">")
_JSON_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_LITERALS = {"true": True, "false": False, "null": None}
_BARE_KEY = re.compile(r"[\w-]+")
_ABSENT = object()


def _scan_quoted(text: str, start: int) -> Tuple[str, int]:
    """Decode the string literal whose quote is at ``start``; return it and the index after its closing quote.

    RFC 9535 2.3.1.2 escapes are decoded (``\\'``, ``\\"``, ``\\uXXXX`` ...);
    a missing closing quote raises ``ValueError``.
    """
    quote, index = text[start], start + 1
    chars: List[str] = []
    while index < len(text):
        char = text[index]
        if char == quote:
            return "".join(chars), index + 1
        if char == "\\":
            decoded, index = _escape(text, index + 1)
            chars.append(decoded)
            continue
        chars.append(char)
        index += 1
    raise ValueError(f"unterminated string in JSONPath {text!r}")


def _escape(text: str, index: int) -> Tuple[str, int]:
    """The character an escape stands for (``index`` is after the backslash) and the index after it."""
    code = text[index:index + 1]
    if code == "u" and re.fullmatch(r"[0-9A-Fa-f]{4}", text[index + 1:index + 5]):
        return chr(int(text[index + 1:index + 5], 16)), index + 5
    if code in _ESCAPES:
        return _ESCAPES[code], index + 1
    raise ValueError(f"invalid escape in JSONPath {text!r}")


def _whole_string(raw: str) -> str:
    """``raw`` as one quoted string literal; mismatched or trailing quotes raise."""
    value, end = _scan_quoted(raw, 0)
    if end != len(raw):   # ['a','b'] used to be the key "a','b"
        raise ValueError(f"unsupported JSONPath string {raw!r}")
    return value


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        return _whole_string(raw)
    if _JSON_NUMBER.fullmatch(raw):
        return float(raw) if any(ch in raw for ch in ".eE") else int(raw)
    if raw in _LITERALS:
        return _LITERALS[raw]
    # "1 && @.b==2" used to be compared as that string and match nothing,
    # and Python-only spellings (1_000, nan, inf) were accepted.
    raise ValueError(f"unsupported JSONPath filter value {raw!r}")


def _parse_bracket(inner: str) -> Tuple[str, Any]:
    """Turn the text inside ``[...]`` into a token."""
    inner = inner.strip()
    if not inner:
        raise ValueError("empty JSONPath selector []")
    if inner == "*":
        return ("wild", None)
    if inner.startswith("?"):
        body = inner[1:].strip().lstrip("(").rstrip(")").strip()
        return ("filter", _parse_filter(body, inner))
    if inner[:1] in ("'", '"'):
        return ("key", _whole_string(inner))
    if re.fullmatch(r"-?\d+", inner):
        return ("index", int(inner))
    if not _BARE_KEY.fullmatch(inner):
        # Slices ([0:2]), unions ([0,1]) and [] were looked up as keys.
        raise ValueError(f"unsupported JSONPath selector [{inner}]")
    return ("key", inner)


def _parse_filter(body: str, inner: str) -> Tuple[Tuple[str, ...], Any, Any]:
    """``(field path, operator or None, value)`` for a ``?(...)`` body.

    Anything else raises: an unreadable filter used to become a wildcard and
    return every element.
    """
    match = _FILTER_FIELD.match(body)
    rest = body[match.end():].strip() if match else ""
    operator = next((op for op in _OPERATORS if rest.startswith(op)), None)
    if match is None or (rest and (operator is None or not rest[len(operator):].strip())):
        raise ValueError(f"unsupported JSONPath filter {inner!r}")
    value = None if operator is None else _parse_value(rest[len(operator):])
    return tuple(match.group(1).split(".")), operator, value


def _read_bare_key(path: str, start: int) -> Tuple[str, int]:
    end = start
    while end < len(path) and (path[end].isalnum() or path[end] in "_-"):
        end += 1
    return path[start:end], end


def _read_bracket(path: str, start: int) -> Tuple[str, int]:
    """Text inside the ``[`` at ``start`` and the index after its ``]``.

    A quoted key or a filter may itself contain ``]`` (``['a]b']``,
    ``[?(@.k == "x]")]``), so the search starts after the quote / looks for
    the filter's ``)]``.
    """
    opener = path[start + 1:start + 2]
    search_from = start + 1
    if opener in ("'", '"'):
        search_from = _scan_quoted(path, start + 1)[1]
    # Only a parenthesised filter ends at ")]": searching for it in
    # "[?@.a==1].b[?(@.c)]" ran on into the next filter.
    if path.startswith("?(", start + 1):
        close = _filter_close(path, start + 3)
    else:
        close = path.find("]", search_from)
    if close == -1:
        raise ValueError(f"unterminated '[' in JSONPath {path!r}")
    if path.startswith("?(", start + 1):
        close += 1
    return path[start + 1:close], close + 1


def _filter_close(path: str, index: int) -> int:
    """Index of the ``)]`` that ends a filter, skipping string literals.

    A plain search stopped at ``)]`` inside ``[?(@.k == "a)]")]``.
    """
    while index < len(path):
        if path[index] in ("'", '"'):
            index = _scan_quoted(path, index)[1]
        elif path.startswith(")]", index):
            return index
        else:
            index += 1
    return -1


def _tokenize(path: str) -> List[Tuple[str, Any]]:
    """Tokenize a JSONPath with a linear scan (no backtracking regex)."""
    path = path.strip()
    if path.startswith("$"):
        path = path[1:]
    tokens: List[Tuple[str, Any]] = []
    index, length = 0, len(path)
    while index < length:
        char = path[index]
        if path.startswith("..", index):
            tokens.append(("recurse", None))
            index += 2
        elif char == ".":
            index += 1                       # skip dot; key/* read next pass
        elif char == "*":
            tokens.append(("wild", None))
            index += 1
        elif char == "[":
            inner, index = _read_bracket(path, index)
            tokens.append(_parse_bracket(inner))
        else:
            name, index = _read_bare_key(path, index)
            if not name:
                raise ValueError(f"unexpected {char!r} in JSONPath {path!r}")
            tokens.append(("key", name))
    return tokens


def _descendants(node: Any) -> List[Any]:
    found = [node]
    if isinstance(node, dict):
        for value in node.values():
            found.extend(_descendants(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_descendants(item))
    return found


def _field(node: Any, fields: Tuple[str, ...]) -> Any:
    for name in fields:
        if not isinstance(node, dict) or name not in node:
            return _ABSENT
        node = node[name]
    return node


def _json_equal(left: Any, right: Any) -> bool:
    # Python has True == 1; JSON does not.
    return isinstance(left, bool) == isinstance(right, bool) and left == right


def _json_less(left: Any, right: Any) -> bool:
    """RFC 9535 "<": only two numbers or two strings are ordered (Python ordered False < True)."""
    def is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if is_number(left) and is_number(right):
        return left < right
    return isinstance(left, str) and isinstance(right, str) and left < right


_COMPARATORS = {
    "==": _json_equal, "!=": lambda a, b: not _json_equal(a, b),
    "<": _json_less, ">": lambda a, b: _json_less(b, a),
    # "<=" is "<" or "==", so null <= null holds.
    "<=": lambda a, b: _json_less(a, b) or _json_equal(a, b),
    ">=": lambda a, b: _json_less(b, a) or _json_equal(a, b),
}


def _match_filter(node: Any, spec: Tuple[Tuple[str, ...], Any, Any]) -> bool:
    fields, op, value = spec
    actual = _field(node, fields)
    if op is None:
        return actual is not _ABSENT
    if actual is _ABSENT:
        # RFC 9535 2.3.5.2.2: a missing member is Nothing, which equals no
        # value and orders against none, so only "!=" holds.
        return op == "!="
    return _COMPARATORS[op](actual, value)


def _on_key(node: Any, arg: Any) -> List[Any]:
    return [node[arg]] if isinstance(node, dict) and arg in node else []


def _on_index(node: Any, arg: Any) -> List[Any]:
    if isinstance(node, list) and -len(node) <= arg < len(node):
        return [node[arg]]
    return []


def _on_wild(node: Any, _arg: Any) -> List[Any]:
    if isinstance(node, dict):
        return list(node.values())
    return list(node) if isinstance(node, list) else []


def _on_filter(node: Any, arg: Any) -> List[Any]:
    # RFC 9535: a filter selects among an array's elements or an object's
    # member values; it used to test the object itself.
    if isinstance(node, dict):
        elements = list(node.values())
    elif isinstance(node, list):
        elements = node
    else:
        return []
    return [item for item in elements if _match_filter(item, arg)]


_STEP_HANDLERS = {
    "key": _on_key, "index": _on_index, "wild": _on_wild,
    "recurse": lambda node, _arg: _descendants(node), "filter": _on_filter,
}


def _step(nodes: List[Any], token: Tuple[str, Any]) -> List[Any]:
    kind, arg = token
    handler = _STEP_HANDLERS[kind]
    result: List[Any] = []
    for node in nodes:
        result.extend(handler(node, arg))
    return result


def json_query(data: Any, path: str) -> List[Any]:
    """Return every value in ``data`` matching the JSONPath ``path``."""
    nodes: List[Any] = [data]
    for token in _tokenize(path):
        nodes = _step(nodes, token)
    return nodes


def json_query_one(data: Any, path: str, default: Any = None) -> Any:
    """Return the first match for ``path``, or ``default`` if none."""
    matches = json_query(data, path)
    return matches[0] if matches else default


def json_extract(data: Any, mapping: Mapping[str, str]) -> Dict[str, Any]:
    """Return ``{key: json_query_one(data, path)}`` for each ``key: path``."""
    return {key: json_query_one(data, path) for key, path in mapping.items()}
