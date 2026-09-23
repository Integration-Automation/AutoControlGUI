"""A small JSONPath-style query engine over already-parsed JSON.

The executor's built-in path walker only splits on ``.`` and indexes — it can't
do wildcards, recursive descent, or filters, so API/DB responses with arrays are
awkward to extract from. This adds a focused JSONPath subset:

* ``$``               root (optional prefix)
* ``.name`` / ``name``  member access
* ``[n]`` / ``[-n]``   list index (negative from the end)
* ``*`` / ``[*]``      wildcard (all members / all elements)
* ``..``               recursive descent
* ``[?(@.k op v)]``    filter array elements (``op`` ∈ == != < <= > >=);
  ``@.a.b`` reaches into nested objects and ``[?(@.k)]`` tests that ``k``
  exists. Values of different types never compare equal (``true != 1``).

A path this subset cannot read -- an unsupported filter, an unterminated
``[``, a stray character -- raises ``ValueError`` rather than matching
something else.

Pure standard library (``re``); imports no ``PySide6``.
"""
import re
from typing import Any, Dict, List, Mapping, Tuple

_COMPARATORS = {
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
}

# The field path of a filter; the operator and value are split off by hand, so
# no pattern has two quantifiers competing for the same characters.
_FILTER_FIELD = re.compile(r"@\.([\w-]+(?:\.[\w-]+)*)")
_OPERATORS = ("==", "!=", "<=", ">=", "<", ">")
_ABSENT = object()


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if raw[:1] in "'\"" and raw[-1:] in "'\"":
        return raw[1:-1]
    for caster in (int, float):
        try:
            return caster(raw)
        except ValueError:
            continue
    return {"true": True, "false": False, "null": None}.get(raw, raw)


def _parse_bracket(inner: str) -> Tuple[str, Any]:
    """Turn the text inside ``[...]`` into a token."""
    inner = inner.strip()
    if inner == "*":
        return ("wild", None)
    if inner.startswith("?"):
        body = inner[1:].strip().lstrip("(").rstrip(")").strip()
        return ("filter", _parse_filter(body, inner))
    if inner[:1] in "'\"" and inner[-1:] in "'\"":
        return ("key", inner[1:-1])
    try:
        return ("index", int(inner))
    except ValueError:
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
        search_from = path.find(opener, start + 2) + 1
    closer = ")]" if opener == "?" and path.find(")]", start) != -1 else "]"
    close = path.find(closer, search_from) if search_from else -1
    if close == -1:
        raise ValueError(f"unterminated '[' in JSONPath {path!r}")
    close += len(closer) - 1
    return path[start + 1:close], close + 1


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


def _match_filter(node: Any, spec: Tuple[Tuple[str, ...], Any, Any]) -> bool:
    fields, op, value = spec
    actual = _field(node, fields)
    if actual is _ABSENT or op is None:
        return actual is not _ABSENT
    if isinstance(actual, bool) != isinstance(value, bool):
        return op == "!="   # Python has True == 1; JSON does not
    try:
        return _COMPARATORS[op](actual, value)
    except TypeError:
        return False


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
    elements = node if isinstance(node, list) else [node]
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
