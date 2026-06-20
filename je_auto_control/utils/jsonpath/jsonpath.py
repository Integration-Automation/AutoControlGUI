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

_TOKEN_RE = re.compile(
    r"""\.\.                                   # recursive descent
        |\.?\*                                 # wildcard (* or .*)
        |\[\*\]                                # [*]
        |\[\?\(?@\.(?P<f>\w+)\s*               # filter field
            (?P<op>==|!=|<=|>=|<|>)\s*
            (?P<v>'[^']*'|"[^"]*"|[^)\]]+)\)?\]
        |\[(?P<idx>-?\d+)\]                     # index
        |\['(?P<q>[^']*)'\]                     # ['quoted key']
        |\.(?P<k>\w+)                           # .key
        |(?P<kb>\w+)                            # bare key (leading or after ..)
    """,
    re.VERBOSE,
)


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


def _tokenize(path: str) -> List[Tuple[str, Any]]:
    path = path.strip()
    if path.startswith("$"):
        path = path[1:]
    tokens: List[Tuple[str, Any]] = []
    for match in _TOKEN_RE.finditer(path):
        text = match.group(0)
        if text == "..":
            tokens.append(("recurse", None))
        elif text in ("*", ".*", "[*]"):
            tokens.append(("wild", None))
        elif match.group("idx") is not None:
            tokens.append(("index", int(match.group("idx"))))
        elif match.group("f") is not None:
            tokens.append(("filter", (match.group("f"), match.group("op"),
                                      _parse_value(match.group("v")))))
        else:
            tokens.append(("key", match.group("q") or match.group("k")
                           or match.group("kb")))
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
