"""A small JSONPath-style query engine over already-parsed JSON.

The executor's built-in path walker only splits on ``.`` and indexes — it can't
do wildcards, recursive descent, or filters, so API/DB responses with arrays are
awkward to extract from. This adds a focused JSONPath subset:

* ``$``               root (optional prefix)
* ``.name`` / ``name``  member access
* ``[n]`` / ``[-n]``   list index (negative from the end)
* ``*`` / ``[*]``      wildcard (all members / all elements)
* ``..``               recursive descent
* ``[?(@.k op v)]``    filter array elements (``op`` ∈ == != < <= > >=)

Pure standard library (``re``); imports no ``PySide6``.
"""
import re
from typing import Any, Dict, List, Mapping, Tuple

_COMPARATORS = {
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
}

# A small, linear filter pattern (no nested quantifiers -> no backtracking).
_FILTER_RE = re.compile(r"@\.(\w+)\s*(==|!=|<=|>=|<|>)\s*(.+)")


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
        match = _FILTER_RE.match(body)
        if match:
            return ("filter", (match.group(1), match.group(2),
                               _parse_value(match.group(3))))
        return ("wild", None)
    if inner[:1] in "'\"" and inner[-1:] in "'\"":
        return ("key", inner[1:-1])
    try:
        return ("index", int(inner))
    except ValueError:
        return ("key", inner)


def _read_bare_key(path: str, start: int) -> Tuple[str, int]:
    end = start
    while end < len(path) and (path[end].isalnum() or path[end] == "_"):
        end += 1
    return path[start:end], end


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
            close = path.find("]", index)
            if close == -1:
                break
            tokens.append(_parse_bracket(path[index + 1:close]))
            index = close + 1
        else:
            name, index = _read_bare_key(path, index)
            if name:
                tokens.append(("key", name))
            else:
                index += 1                   # skip an unrecognized char
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


def _match_filter(node: Any, spec: Tuple[str, str, Any]) -> bool:
    field, op, value = spec
    if not isinstance(node, dict) or field not in node:
        return False
    try:
        return _COMPARATORS[op](node[field], value)
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
